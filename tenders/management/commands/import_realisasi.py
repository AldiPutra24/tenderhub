from django.core.management.base import BaseCommand, CommandError

from tenders.services.inaproc_realisasi_client import (
    DETAIL_CSV_MAPPING,
    InaprocRequestError,
    MAIN_CSV_MAPPING,
    InaprocRealisasiClient,
    normalize_status,
)
from tenders.services.inaproc_realisasi_importer import (
    apply_detail_row,
    upsert_realisasi_row,
)


class Command(BaseCommand):
    help = "Import tender data from INAPROC Realisasi CSV export API"

    def add_arguments(self, parser):
        parser.add_argument("--tahun", type=int, help="Tahun anggaran. Default: current year")
        parser.add_argument("--status", help="BERLANGSUNG or SELESAI")
        parser.add_argument("--all-status", action="store_true", help="Import BERLANGSUNG and SELESAI")
        parser.add_argument("--limit", type=int, help="Limit rows for testing")
        parser.add_argument("--dry-run", action="store_true", help="Fetch and parse without writing database")
        parser.add_argument("--with-detail", action="store_true", help="Download detail CSV after each main row")
        parser.add_argument("--instansi", default="", help="Filter instansi")
        parser.add_argument("--jenis-klpd", default="", help="Comma-separated jenisKlpd filter")
        parser.add_argument("--search-kode", default="", help="Search kode paket")
        parser.add_argument("--search-paket", default="", help="Search nama paket")
        parser.add_argument("--search-penyedia", default="", help="Search nama penyedia")
        parser.add_argument("--debug-http", action="store_true", help="Print safe HTTP debug information")
        parser.add_argument("--browser-fallback", action="store_true", help="Use Playwright if requests receives 403")

    def handle(self, *args, **options):
        tahun = options.get("tahun") or __import__("datetime").date.today().year
        all_status = options["all_status"]
        status = None if all_status or not options.get("status") else normalize_status(options["status"])

        if options.get("limit") is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater")
        if not options["jenis_klpd"] or not options["instansi"]:
            raise CommandError(
                "Export CSV wajib memakai --jenis-klpd dan --instansi. "
                "Jalankan discover_inaproc_instansi dulu untuk melihat kode instansi."
            )

        client = InaprocRealisasiClient(
            referer_tahun=tahun,
            debug_callback=self.write_http_debug if options["debug_http"] else None,
        )
        self.stdout.write(
            "IMPORT REALISASI START "
            f"tahun={tahun} jenisKlpd={options['jenis_klpd']} instansi={options['instansi']} "
            f"status={'ALL' if all_status else (status or 'NONE')} dry_run={options['dry_run']}"
        )

        try:
            csv_text = client.download_realisasi_csv(
                tahun=tahun,
                status=status,
                all_status=all_status,
                instansi=options["instansi"],
                jenis_klpd=options["jenis_klpd"],
                search_kode=options["search_kode"],
                search_paket=options["search_paket"],
                search_penyedia=options["search_penyedia"],
                browser_fallback=options["browser_fallback"],
            )
        except InaprocRequestError as exc:
            raise CommandError(str(exc)) from exc
        rows = client.parse_csv(csv_text, MAIN_CSV_MAPPING)
        if options.get("limit") is not None:
            rows = rows[: options["limit"]]

        counters = {
            "total": 0,
            "created": 0,
            "updated": 0,
            "enriched": 0,
            "skipped": 0,
            "error": 0,
        }

        for row in rows:
            kode_paket = row.get("kode_paket") or "-"
            counters["total"] += 1
            try:
                if row.get("status_paket"):
                    normalize_status(row["status_paket"])
                result, tender = upsert_realisasi_row(row, dry_run=options["dry_run"])
                if result == "created":
                    counters["created"] += 1
                elif result == "updated":
                    counters["updated"] += 1
                else:
                    counters["skipped"] += 1

                if options["with_detail"] and result in {"created", "updated"}:
                    detail_result = self.enrich_row_detail(
                        client,
                        tender,
                        kode_paket,
                        options["dry_run"],
                        options["browser_fallback"],
                    )
                    if detail_result == "enriched":
                        counters["enriched"] += 1
                    elif detail_result == "skipped":
                        counters["skipped"] += 1
                    else:
                        counters["error"] += 1
            except Exception as exc:
                counters["error"] += 1
                self.stderr.write(self.style.WARNING(f"{kode_paket} {exc}"))
                continue

        self.write_summary(counters, dry_run=options["dry_run"])

    def enrich_row_detail(self, client, tender, kode_paket, dry_run, browser_fallback=False):
        if tender is None and dry_run:
            return "skipped"
        detail_csv = client.download_detail_csv(kode_paket, browser_fallback=browser_fallback)
        detail_rows = client.parse_csv(detail_csv, DETAIL_CSV_MAPPING)
        if not detail_rows:
            self.stderr.write(self.style.WARNING(f"{kode_paket} detail CSV empty"))
            return "failed"
        result, _ = apply_detail_row(tender, detail_rows[0], dry_run=dry_run)
        return result

    def write_summary(self, counters, dry_run=False):
        prefix = "DRY RUN " if dry_run else ""
        self.stdout.write(f"{prefix}TOTAL ROW: {counters['total']}")
        self.stdout.write(f"{prefix}CREATED: {counters['created']}")
        self.stdout.write(f"{prefix}UPDATED: {counters['updated']}")
        self.stdout.write(f"{prefix}ENRICHED: {counters['enriched']}")
        self.stdout.write(f"{prefix}SKIPPED: {counters['skipped']}")
        self.stdout.write(f"{prefix}ERROR: {counters['error']}")
        self.stdout.write(self.style.SUCCESS(f"{prefix}IMPORT REALISASI DONE"))

    def write_http_debug(self, event):
        self.stdout.write(
            "HTTP "
            f"{event['method']} {event['url']} "
            f"status={event['status_code']} "
            f"content_type={event['content_type'] or '-'}"
        )
        if event.get("body_preview"):
            self.stdout.write(f"HTTP error body preview: {event['body_preview']}")
        if event.get("request_body"):
            self.stdout.write(f"HTTP request body: {event['request_body']}")
