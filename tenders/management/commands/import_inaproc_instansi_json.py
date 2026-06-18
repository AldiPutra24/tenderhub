import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenders.models import InaprocInstansi
from tenders.services.inaproc_realisasi_client import VALID_JENIS_KLPD


class Command(BaseCommand):
    help = "Import INAPROC instansi mapping from a JSON file exported by discover_inaproc_instansi"

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="Path to JSON file")
        parser.add_argument("--deactivate-missing", action="store_true", help="Deactivate active rows not present in JSON")

    def handle(self, *args, **options):
        path = Path(options["file_path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        rows = payload.get("instansi") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CommandError("JSON must be a list or an object with an 'instansi' list")

        created = 0
        updated = 0
        skipped = 0
        seen = set()

        with transaction.atomic():
            for row in rows:
                if not isinstance(row, dict):
                    skipped += 1
                    continue
                kode = str(row.get("kode") or "").strip()
                nama = str(row.get("nama") or "").strip()
                jenis_klpd = str(row.get("jenis_klpd") or "").strip()
                if not kode or not nama or jenis_klpd not in VALID_JENIS_KLPD:
                    skipped += 1
                    continue

                _, was_created = InaprocInstansi.objects.update_or_create(
                    jenis_klpd=jenis_klpd,
                    kode=kode,
                    defaults={
                        "nama": nama,
                        "is_active": bool(row.get("is_active", True)),
                    },
                )
                seen.add((jenis_klpd, kode))
                if was_created:
                    created += 1
                else:
                    updated += 1

            deactivated = 0
            if options["deactivate_missing"]:
                for jenis_klpd in VALID_JENIS_KLPD:
                    seen_codes = [kode for seen_jenis, kode in seen if seen_jenis == jenis_klpd]
                    deactivated += InaprocInstansi.objects.filter(
                        jenis_klpd=jenis_klpd,
                        is_active=True,
                    ).exclude(kode__in=seen_codes).update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"IMPORT INSTANSI JSON DONE rows={len(rows)} created={created} "
                f"updated={updated} skipped={skipped} deactivated={deactivated}"
            )
        )
