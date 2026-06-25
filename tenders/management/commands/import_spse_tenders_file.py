import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, models, transaction
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


class Command(BaseCommand):
    help = "Import SPSE Tender JSON dump with safe upsert by kode_tender and lpse_slug"

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="JSON file from dumpdata tenders.Tender")
        parser.add_argument("--dry-run", action="store_true", help="Read and validate without writing to database")
        parser.add_argument("--limit", type=int, help="Limit number of JSON rows to process")
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
        total = created = updated = skipped = errors = 0

        for item in payload:
            total += 1
            try:
                result = self.import_item(item, field_names, options["source"], options["dry_run"])
            except (DatabaseError, ValueError, TypeError) as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(f"ERROR row={total}: {exc}"))
                continue

            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"TOTAL {total} CREATED {created} UPDATED {updated} SKIPPED {skipped} ERROR {errors}"
            )
        )

    def import_item(self, item, field_names, source, dry_run=False):
        if not isinstance(item, dict):
            return "skipped"

        fields = item.get("fields", item)
        if not isinstance(fields, dict):
            return "skipped"

        kode_tender = clean_text(fields.get("kode_tender"))
        if not kode_tender:
            return "skipped"

        lpse_slug = clean_text(fields.get("lpse_slug"))
        existing = find_existing(kode_tender, lpse_slug)
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

        with transaction.atomic():
            if existing:
                _, created = Tender.objects.update_or_create(pk=existing.pk, defaults=defaults)
            elif lpse_slug:
                _, created = Tender.objects.update_or_create(
                    kode_tender=kode_tender,
                    lpse_slug=lpse_slug,
                    defaults=defaults,
                )
            else:
                Tender.objects.create(**defaults)
                created = True

        return "created" if created else "updated"
