from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from tenders.models import Tender
from tenders.services.inaproc_realisasi_client import (
    DETAIL_CSV_MAPPING,
    InaprocRealisasiClient,
)
from tenders.services.inaproc_realisasi_importer import (
    apply_detail_row,
    build_missing_detail_filter,
)


class Command(BaseCommand):
    help = "Enrich INAPROC Realisasi rows with detail CSV data"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Limit rows for testing")
        parser.add_argument("--kode", help="One kode_paket or kode_tender")
        parser.add_argument("--tahun", type=int, help="Filter tahun_anggaran")
        parser.add_argument("--dry-run", action="store_true", help="Fetch and parse without writing database")
        parser.add_argument("--debug-http", action="store_true", help="Print safe HTTP debug information")
        parser.add_argument("--browser-fallback", action="store_true", help="Use Playwright if requests receives 403")

    def handle(self, *args, **options):
        if options.get("limit") is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater")

        queryset = self.get_queryset(options)
        total_candidates = queryset.count()
        if options.get("limit") is not None:
            queryset = queryset[: options["limit"]]

        client = InaprocRealisasiClient(
            referer_tahun=options.get("tahun"),
            debug_callback=self.write_http_debug if options["debug_http"] else None,
        )
        counters = {
            "total": 0,
            "created": 0,
            "updated": 0,
            "enriched": 0,
            "skipped": 0,
            "error": 0,
        }
        self.stdout.write(
            "ENRICH REALISASI DETAIL START "
            f"candidates={total_candidates} dry_run={options['dry_run']}"
        )

        for tender in queryset:
            kode = tender.kode_paket or tender.kode_tender
            counters["total"] += 1
            try:
                detail_csv = client.download_detail_csv(
                    kode,
                    browser_fallback=options["browser_fallback"],
                )
                detail_rows = client.parse_csv(detail_csv, DETAIL_CSV_MAPPING)
                if not detail_rows:
                    counters["skipped"] += 1
                    self.stderr.write(self.style.WARNING(f"{kode} detail CSV empty"))
                    continue
                result, _ = apply_detail_row(tender, detail_rows[0], dry_run=options["dry_run"])
                if result == "enriched":
                    counters["enriched"] += 1
                    counters["updated"] += 1
                else:
                    counters["skipped"] += 1
            except Exception as exc:
                counters["error"] += 1
                self.stderr.write(self.style.WARNING(f"{kode} {exc}"))
                continue

        self.write_summary(counters, dry_run=options["dry_run"])

    def get_queryset(self, options):
        queryset = Tender.objects.filter(build_missing_detail_filter()).order_by("id")
        if options.get("kode"):
            kode = str(options["kode"]).strip()
            queryset = queryset.filter(Q(kode_paket=kode) | Q(kode_tender=kode))
        if options.get("tahun"):
            queryset = queryset.filter(tahun_anggaran__contains=str(options["tahun"]))
        return queryset

    def write_summary(self, counters, dry_run=False):
        prefix = "DRY RUN " if dry_run else ""
        self.stdout.write(f"{prefix}TOTAL ROW: {counters['total']}")
        self.stdout.write(f"{prefix}CREATED: {counters['created']}")
        self.stdout.write(f"{prefix}UPDATED: {counters['updated']}")
        self.stdout.write(f"{prefix}ENRICHED: {counters['enriched']}")
        self.stdout.write(f"{prefix}SKIPPED: {counters['skipped']}")
        self.stdout.write(f"{prefix}ERROR: {counters['error']}")
        self.stdout.write(self.style.SUCCESS(f"{prefix}ENRICH REALISASI DETAIL DONE"))

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
