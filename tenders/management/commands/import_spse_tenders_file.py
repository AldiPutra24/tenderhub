import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from tenders.models import Tender


REALISASI_VALUABLE_FIELDS = {
    "nama_penyedia",
    "total_nilai",
    "nilai_pdn",
    "status_paket",
    "kode_paket",
    "kode_rup",
}
SKIP_FIELDS = {"id", "pk", "created_at", "updated_at"}


def clean_text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def is_empty(value):
    return value is None or value == "" or value == []


def model_field_names():
    return {
        field.name: field
        for field in Tender._meta.get_fields()
        if getattr(field, "concrete", False) and not getattr(field, "many_to_many", False)
    }


def coerce_value(field, value):
    if is_empty(value):
        return value
    if isinstance(field, models.DateTimeField):
        return parse_datetime(value) if isinstance(value, str) else value
    if isinstance(field, models.DateField):
        return parse_date(value) if isinstance(value, str) else value
    return value


def resolve_source(existing, source):
    if not existing:
        return source
    if existing.data_source == Tender.SOURCE_REALISASI and source == Tender.SOURCE_SPSE:
        return Tender.SOURCE_MIXED
    if existing.data_source == Tender.SOURCE_MIXED:
        return Tender.SOURCE_MIXED
    return source


def find_existing(kode_tender, lpse_slug):
    queryset = Tender.objects.filter(kode_tender=kode_tender)
    if lpse_slug:
        existing = queryset.filter(lpse_slug=lpse_slug).first()
        if existing:
            return existing
        return queryset.filter(lpse_slug="").first()
    return queryset.first()


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def row_identity(item):
    if not isinstance(item, dict):
        return "", ""

    fields = item.get("fields", item)
    if not isinstance(fields, dict):
        return "", ""

    return clean_text(fields.get("kode_tender")), clean_text(fields.get("lpse_slug"))


class Command(BaseCommand):
    help = "Import SPSE Tender JSON dump with safe upsert by kode_tender and lpse_slug"

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="JSON file from dumpdata tenders.Tender")
        parser.add_argument("--dry-run", action="store_true", help="Read and validate without writing to database")
        parser.add_argument("--limit", type=int, help="Limit number of JSON rows to process")
        parser.add_argument("--batch-size", type=int, default=1000, help="Rows per bulk database batch")
        parser.add_argument("--progress-every", type=int, default=1000, help="Print progress every N rows")
        parser.add_argument(
            "--source",
            choices=[Tender.SOURCE_SPSE, Tender.SOURCE_REALISASI, Tender.SOURCE_LKPP_API, Tender.SOURCE_MIXED],
            default=Tender.SOURCE_SPSE,
            help="Source marker to apply to imported rows",
        )

    def handle(self, *args, **options):
        path = Path(options["file_path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise CommandError(f"File is not UTF-8. Convert it first: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        if not isinstance(payload, list):
            raise CommandError("Expected a JSON list from dumpdata tenders.Tender")

        limit = options.get("limit")
        if limit is not None:
            payload = payload[:limit]

        field_names = model_field_names()
        batch_size = max(options["batch_size"], 1)
        progress_every = max(options["progress_every"], 0)
        dry_run = options["dry_run"]
        source = options["source"]

        self.write_progress(f"Loaded {len(payload)} rows from {path}")

        existing_by_exact, existing_by_blank, existing_by_code = self.load_existing_tenders(payload, batch_size)
        total = created = updated = skipped = errors = 0
        now = timezone.now()
        create_objects = []
        create_by_key = {}
        update_objects = {}
        update_fields = set()

        for item in payload:
            total += 1
            try:
                result = self.prepare_item(
                    item,
                    field_names,
                    source,
                    dry_run,
                    now,
                    existing_by_exact,
                    existing_by_blank,
                    existing_by_code,
                    create_objects,
                    create_by_key,
                    update_objects,
                    update_fields,
                )
            except (ValueError, TypeError) as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(f"ERROR row={total}: {exc}"))
                continue

            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

            if progress_every and total % progress_every == 0:
                self.write_progress(
                    f"Prepared {total}/{len(payload)} rows "
                    f"(create {created}, update {updated}, skip {skipped}, error {errors})"
                )

        if not dry_run:
            try:
                self.write_progress(
                    f"Writing {len(create_objects)} creates and {len(update_objects)} updates "
                    f"in batches of {batch_size}"
                )
                self.write_batches(create_objects, update_objects, update_fields, batch_size)
            except DatabaseError as exc:
                raise CommandError(f"Database write failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"TOTAL {total} CREATED {created} UPDATED {updated} SKIPPED {skipped} ERROR {errors}"
            )
        )

    def write_progress(self, message):
        self.stdout.write(message)
        self.stdout.flush()

    def load_existing_tenders(self, payload, batch_size):
        kode_tenders = sorted({kode_tender for kode_tender, _ in map(row_identity, payload) if kode_tender})
        existing_by_exact = {}
        existing_by_blank = {}
        existing_by_code = {}

        for kode_batch in chunked(kode_tenders, batch_size):
            for tender in Tender.objects.filter(kode_tender__in=kode_batch):
                key = (tender.kode_tender, tender.lpse_slug or "")
                existing_by_exact[key] = tender
                existing_by_code.setdefault(tender.kode_tender, tender)
                if not tender.lpse_slug:
                    existing_by_blank.setdefault(tender.kode_tender, tender)

        self.write_progress(f"Matched {len(existing_by_exact)} existing database rows")
        return existing_by_exact, existing_by_blank, existing_by_code

    def resolve_existing_from_cache(self, kode_tender, lpse_slug, existing_by_exact, existing_by_blank, existing_by_code):
        if lpse_slug:
            existing = existing_by_exact.get((kode_tender, lpse_slug))
            if existing:
                return existing
            return existing_by_blank.get(kode_tender)
        return existing_by_code.get(kode_tender)

    def prepare_item(
        self,
        item,
        field_names,
        source,
        dry_run,
        now,
        existing_by_exact,
        existing_by_blank,
        existing_by_code,
        create_objects,
        create_by_key,
        update_objects,
        update_fields,
    ):
        if not isinstance(item, dict):
            return "skipped"

        fields = item.get("fields", item)
        if not isinstance(fields, dict):
            return "skipped"

        kode_tender = clean_text(fields.get("kode_tender"))
        if not kode_tender:
            return "skipped"

        lpse_slug = clean_text(fields.get("lpse_slug"))
        existing = self.resolve_existing_from_cache(
            kode_tender,
            lpse_slug,
            existing_by_exact,
            existing_by_blank,
            existing_by_code,
        )
        defaults = {}

        for field_name, value in fields.items():
            if field_name in SKIP_FIELDS or field_name not in field_names:
                continue
            if field_name in REALISASI_VALUABLE_FIELDS and existing:
                continue
            if is_empty(value):
                continue
            defaults[field_name] = coerce_value(field_names[field_name], value)

        defaults["kode_tender"] = kode_tender
        if lpse_slug:
            defaults["lpse_slug"] = lpse_slug
        defaults["data_source"] = resolve_source(existing, source)

        if dry_run:
            return "updated" if existing else "created"

        if existing and existing.pk is None:
            for field_name, value in defaults.items():
                setattr(existing, field_name, value)
            if lpse_slug:
                create_by_key[(kode_tender, lpse_slug)] = existing
                existing_by_exact[(kode_tender, lpse_slug)] = existing
            return "updated"

        if existing:
            for field_name, value in defaults.items():
                setattr(existing, field_name, value)
                update_fields.add(field_name)
            if "updated_at" in field_names:
                existing.updated_at = now
                update_fields.add("updated_at")
            update_objects[existing.pk] = existing
            if lpse_slug:
                existing_by_exact[(kode_tender, lpse_slug)] = existing
            return "updated"

        key = (kode_tender, lpse_slug)
        create_object = create_by_key.get(key)
        if create_object:
            for field_name, value in defaults.items():
                setattr(create_object, field_name, value)
            return "updated"

        create_object = Tender(**defaults)
        if "created_at" in field_names:
            create_object.created_at = now
        if "updated_at" in field_names:
            create_object.updated_at = now
        create_objects.append(create_object)
        create_by_key[key] = create_object
        existing_by_code.setdefault(kode_tender, create_object)
        if lpse_slug:
            existing_by_exact[key] = create_object
        else:
            existing_by_blank.setdefault(kode_tender, create_object)
        return "created"

    def write_batches(self, create_objects, update_objects, update_fields, batch_size):
        with transaction.atomic():
            for create_batch in chunked(create_objects, batch_size):
                Tender.objects.bulk_create(create_batch, batch_size=batch_size)

            fields = sorted(update_fields - {"id", "pk", "created_at"})
            if fields:
                update_list = list(update_objects.values())
                for update_batch in chunked(update_list, batch_size):
                    Tender.objects.bulk_update(update_batch, fields, batch_size=batch_size)
