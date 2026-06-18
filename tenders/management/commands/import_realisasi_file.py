from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tenders.services.inaproc_realisasi_client import (
    MAIN_CSV_MAPPING,
    InaprocRealisasiClient,
    normalize_status,
)
from tenders.services.inaproc_realisasi_importer import upsert_realisasi_row


class Command(BaseCommand):
    help = "Import INAPROC Realisasi data from a local CSV file"

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="Path to INAPROC Realisasi CSV file")
        parser.add_argument("--tahun", type=int, required=True, help="Tahun anggaran")
        parser.add_argument("--jenis-klpd", required=True, help="jenisKlpd code used when downloading the CSV")
        parser.add_argument("--instansi", required=True, help="Instansi code used when downloading the CSV")
        parser.add_argument("--status", required=True, help="BERLANGSUNG or SELESAI")
        parser.add_argument("--limit", type=int, help="Limit rows for testing")
        parser.add_argument("--dry-run", action="store_true", help="Parse without writing database")

    def handle(self, *args, **options):
        path = Path(options["file_path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        if options.get("limit") is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater")

        status = normalize_status(options["status"])
        client = InaprocRealisasiClient()
        csv_content = path.read_bytes()
        rows = client.parse_csv(csv_content, MAIN_CSV_MAPPING)
        if options.get("limit") is not None:
            rows = rows[: options["limit"]]

        counters = {"total": 0, "created": 0, "updated": 0, "skipped": 0, "error": 0}
        self.stdout.write(
            "IMPORT REALISASI FILE START "
            f"path={path} tahun={options['tahun']} jenisKlpd={options['jenis_klpd']} "
            f"instansi={options['instansi']} status={status} dry_run={options['dry_run']}"
        )

        for row in rows:
            counters["total"] += 1
            kode_paket = row.get("kode_paket") or "-"
            try:
                if not row.get("tahun_anggaran"):
                    row["tahun_anggaran"] = str(options["tahun"])
                if not row.get("status_paket"):
                    row["status_paket"] = status
                row["_import_context"] = {
                    "tahun": options["tahun"],
                    "jenis_klpd": options["jenis_klpd"],
                    "instansi": options["instansi"],
                    "status": status,
                    "file_path": str(path),
                }
                result, _ = upsert_realisasi_row(row, dry_run=options["dry_run"])
                if result == "created":
                    counters["created"] += 1
                elif result == "updated":
                    counters["updated"] += 1
                else:
                    counters["skipped"] += 1
            except Exception as exc:
                counters["error"] += 1
                self.stderr.write(self.style.WARNING(f"{kode_paket} {exc}"))

        self.stdout.write(f"TOTAL ROW: {counters['total']}")
        self.stdout.write(f"CREATED: {counters['created']}")
        self.stdout.write(f"UPDATED: {counters['updated']}")
        self.stdout.write(f"SKIPPED: {counters['skipped']}")
        self.stdout.write(f"ERROR: {counters['error']}")
        self.stdout.write(self.style.SUCCESS("IMPORT REALISASI FILE DONE"))
