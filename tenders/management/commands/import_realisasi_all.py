import random
import time

from django.core.management.base import BaseCommand, CommandError

from tenders.models import InaprocInstansi
from tenders.services.inaproc_realisasi_client import (
    DETAIL_CSV_MAPPING,
    JENIS_KLPD_LABELS,
    MAIN_CSV_MAPPING,
    VALID_STATUS,
    InaprocRequestError,
    InaprocRealisasiClient,
    normalize_status,
)
from tenders.services.inaproc_realisasi_importer import apply_detail_row, upsert_realisasi_row


class Command(BaseCommand):
    help = "Import INAPROC Realisasi CSV for all discovered active instansi"

    def add_arguments(self, parser):
        parser.add_argument("--tahun", type=int, required=True, help="Tahun anggaran")
        parser.add_argument("--status", help="BERLANGSUNG or SELESAI. Default: both")
        parser.add_argument("--limit-instansi", type=int, help="Limit number of active instansi")
        parser.add_argument("--limit-row", type=int, help="Limit rows per instansi/status")
        parser.add_argument("--dry-run", action="store_true", help="Fetch and parse without writing database")
        parser.add_argument("--skip-detail", action="store_true", help="Do not enrich detail rows")
        parser.add_argument("--with-detail", action="store_true", help="Download detail CSV after each main row")
        parser.add_argument("--debug-http", action="store_true", help="Print safe HTTP debug information")
        parser.add_argument("--browser-fallback", action="store_true", help="Use Playwright if requests receives 403")

    def handle(self, *args, **options):
        if options.get("limit_instansi") is not None and options["limit_instansi"] < 0:
            raise CommandError("--limit-instansi must be zero or greater")
        if options.get("limit_row") is not None and options["limit_row"] < 0:
            raise CommandError("--limit-row must be zero or greater")

        statuses = [normalize_status(options["status"])] if options.get("status") else VALID_STATUS
        with_detail = options["with_detail"] and not options["skip_detail"]
        instansi_rows = list(
            InaprocInstansi.objects.filter(is_active=True)
            .order_by("jenis_klpd", "nama")
        )
        if options.get("limit_instansi") is not None:
            instansi_rows = instansi_rows[: options["limit_instansi"]]
        if not instansi_rows:
            raise CommandError(
                "Tidak ada InaprocInstansi aktif. Jalankan discover_inaproc_instansi dulu."
            )

        client = InaprocRealisasiClient(
            referer_tahun=options["tahun"],
            debug_callback=self.write_http_debug if options["debug_http"] else None,
        )

        totals = {"row_count": 0, "created": 0, "updated": 0, "enriched": 0, "skipped": 0, "error": 0}
        self.stdout.write(
            f"IMPORT REALISASI ALL START tahun={options['tahun']} "
            f"instansi_count={len(instansi_rows)} statuses={','.join(statuses)} "
            f"dry_run={options['dry_run']}"
        )

        for index, instansi in enumerate(instansi_rows, start=1):
            for status in statuses:
                result = self.import_one(client, instansi, status, options, with_detail)
                for key in totals:
                    totals[key] += result[key]

            if index < len(instansi_rows):
                time.sleep(random.uniform(1, 3))

        self.stdout.write(
            self.style.SUCCESS(
                "IMPORT REALISASI ALL DONE "
                f"row_count={totals['row_count']} created={totals['created']} "
                f"updated={totals['updated']} enriched={totals['enriched']} "
                f"skipped={totals['skipped']} error={totals['error']}"
            )
        )

    def import_one(self, client, instansi, status, options, with_detail):
        counters = {"row_count": 0, "created": 0, "updated": 0, "enriched": 0, "skipped": 0, "error": 0}
        jenis_label = JENIS_KLPD_LABELS.get(instansi.jenis_klpd, instansi.jenis_klpd)
        try:
            csv_text = client.download_realisasi_csv(
                tahun=options["tahun"],
                jenis_klpd=instansi.jenis_klpd,
                instansi=instansi.kode,
                status=status,
                browser_fallback=options["browser_fallback"],
            )
            rows = client.parse_csv(csv_text, MAIN_CSV_MAPPING)
            if options.get("limit_row") is not None:
                rows = rows[: options["limit_row"]]
            counters["row_count"] = len(rows)

            for row in rows:
                try:
                    result, tender = upsert_realisasi_row(row, dry_run=options["dry_run"])
                    if result == "created":
                        counters["created"] += 1
                    elif result == "updated":
                        counters["updated"] += 1
                    else:
                        counters["skipped"] += 1

                    if with_detail and result in {"created", "updated"}:
                        detail_result = self.enrich_row_detail(
                            client,
                            tender,
                            row.get("kode_paket"),
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
                    self.stderr.write(
                        self.style.WARNING(
                            f"ROW ERROR jenisKlpd={instansi.jenis_klpd} instansi={instansi.kode} "
                            f"status={status} kode_paket={row.get('kode_paket') or '-'} error={exc}"
                        )
                    )
        except (InaprocRequestError, ValueError) as exc:
            counters["error"] += 1
            self.stderr.write(
                self.style.WARNING(
                    f"INSTANSI ERROR jenisKlpd={instansi.jenis_klpd} instansi={instansi.kode} "
                    f"status={status} error={exc}"
                )
            )

        self.stdout.write(
            "IMPORT INSTANSI "
            f"jenisKlpd={instansi.jenis_klpd}({jenis_label}) "
            f"kode={instansi.kode} nama=\"{instansi.nama}\" status={status} "
            f"row_count={counters['row_count']} created={counters['created']} "
            f"updated={counters['updated']} enriched={counters['enriched']} "
            f"skipped={counters['skipped']} error={counters['error']}"
        )
        return counters

    def enrich_row_detail(self, client, tender, kode_paket, dry_run, browser_fallback=False):
        if not kode_paket:
            return "skipped"
        if tender is None and dry_run:
            return "skipped"
        detail_csv = client.download_detail_csv(kode_paket, browser_fallback=browser_fallback)
        detail_rows = client.parse_csv(detail_csv, DETAIL_CSV_MAPPING)
        if not detail_rows:
            return "failed"
        result, _ = apply_detail_row(tender, detail_rows[0], dry_run=dry_run)
        return result

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
