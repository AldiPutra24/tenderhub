from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenders.models import InaprocInstansi
from tenders.services.inaproc_realisasi_client import (
    JENIS_KLPD_LABELS,
    VALID_JENIS_KLPD,
    InaprocRealisasiClient,
)


class Command(BaseCommand):
    help = "Discover INAPROC instansi options used by the Realisasi dashboard filters"

    def add_arguments(self, parser):
        parser.add_argument("--tahun", type=int, default=2026, help="Tahun anggaran for dashboard options")
        parser.add_argument("--jenis-klpd", help="One jenisKlpd code: 1, 2, 3, 4, or 5")
        parser.add_argument("--debug-http", action="store_true", help="Print safe HTTP debug information")

    def handle(self, *args, **options):
        tahun = options["tahun"]
        jenis_values = [options["jenis_klpd"]] if options.get("jenis_klpd") else VALID_JENIS_KLPD
        invalid = [value for value in jenis_values if value not in VALID_JENIS_KLPD]
        if invalid:
            raise CommandError(f"Invalid --jenis-klpd: {', '.join(invalid)}")

        client = InaprocRealisasiClient(
            referer_tahun=tahun,
            debug_callback=self.write_http_debug if options["debug_http"] else None,
        )

        total_created = 0
        total_updated = 0
        total_deactivated = 0
        total_error = 0

        for jenis_klpd in jenis_values:
            label = JENIS_KLPD_LABELS.get(jenis_klpd, jenis_klpd)
            self.stdout.write(f"DISCOVER jenisKlpd={jenis_klpd} {label}")
            try:
                rows = client.fetch_instansi_options(tahun=tahun, jenis_klpd=jenis_klpd)
                created, updated, deactivated = self.upsert_rows(jenis_klpd, rows)
            except Exception as exc:
                total_error += 1
                self.stderr.write(self.style.WARNING(f"ERROR jenisKlpd={jenis_klpd}: {exc}"))
                continue

            total_created += created
            total_updated += updated
            total_deactivated += deactivated
            self.stdout.write(
                f"DONE jenisKlpd={jenis_klpd} row_count={len(rows)} "
                f"created={created} updated={updated} deactivated={deactivated}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "DISCOVER DONE "
                f"created={total_created} updated={total_updated} "
                f"deactivated={total_deactivated} error={total_error}"
            )
        )

    def upsert_rows(self, jenis_klpd, rows):
        seen_codes = {row["kode"] for row in rows}
        created = 0
        updated = 0

        with transaction.atomic():
            for row in rows:
                _, was_created = InaprocInstansi.objects.update_or_create(
                    jenis_klpd=jenis_klpd,
                    kode=row["kode"],
                    defaults={
                        "nama": row["nama"],
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            deactivated = InaprocInstansi.objects.filter(
                jenis_klpd=jenis_klpd,
                is_active=True,
            ).exclude(kode__in=seen_codes).update(is_active=False)

        return created, updated, deactivated

    def write_http_debug(self, event):
        self.stdout.write(
            "HTTP "
            f"{event['method']} {event['url']} "
            f"status={event['status_code']} "
            f"content_type={event['content_type'] or '-'}"
        )
        if event.get("body_preview"):
            self.stdout.write(f"HTTP error body preview: {event['body_preview']}")
