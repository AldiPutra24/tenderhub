from collections import OrderedDict
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management.base import CommandError
from django.core.management import call_command
from django.test import override_settings
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from tenders.management.commands.scrape_spse_live import (
    Command as ScrapeSpseLiveCommand,
    append_year_to_sumber_dana,
    normalize_status,
    parse_jenis_pengadaan_tahun,
    parse_year,
)
from tenders.services.inaproc_realisasi_client import (
    MAIN_CSV_MAPPING,
    InaprocRealisasiClient,
    parse_rupiah,
)
from tenders.services.inaproc_realisasi_importer import upsert_realisasi_row
from tenders.services.email_digest import send_digest_for_user
from tenders.services.spse_slug_mapping import merge_slug_mapping, parse_portal_entries
from tenders.models import Tender, TenderNotification, TenderNotificationEmailLog
from tenders.views import get_selected_filters
from users.models import VendorProfile
from tenders.year_utils import extract_budget_years, normalize_budget_years


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None, content_type="application/json"):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self):
        self.calls = []
        self.last_signature_payload = None
        self.last_export_body = None

    def mount(self, *args, **kwargs):
        pass

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, headers, None))
        return FakeResponse(text="<html></html>", content_type="text/html")

    def post(self, url, headers=None, data=None, timeout=None):
        body = data.decode("utf-8") if isinstance(data, bytes) else data
        self.calls.append(("POST", url, headers, body))
        if url.endswith("/dashboard-api/export/signature"):
            import json

            self.last_signature_payload = json.loads(body)
            return FakeResponse(
                text='{"time":"1","nonce":"2","signature":"3"}',
                payload={"time": "1", "nonce": "2", "signature": "3"},
            )
        self.last_export_body = body
        return FakeResponse(text="Kode Paket\n101\n", content_type="text/csv")


class BudgetYearParsingTests(SimpleTestCase):
    def test_multi_year_values_are_normalized(self):
        self.assertEqual(
            extract_budget_years("APBD 2027 APBD 2028 APBD 2026"),
            ["2026", "2027", "2028"],
        )
        self.assertEqual(
            normalize_budget_years("APBN 2026 APBN 2027 APBN 2028"),
            "2026, 2027, 2028",
        )
        self.assertEqual(parse_year("2027 2028 2026"), "2026, 2027, 2028")

    def test_list_parser_keeps_all_budget_years(self):
        procurement_type, years = parse_jenis_pengadaan_tahun(
            "Pengadaan Barang - TA 2027, 2028, 2026"
        )

        self.assertEqual(procurement_type, "Pengadaan Barang")
        self.assertEqual(years, "2026, 2027, 2028")

    def test_funding_source_only_appends_missing_years(self):
        self.assertEqual(
            append_year_to_sumber_dana(
                "APBN 2026 APBN 2027 APBN 2028",
                "2026, 2027, 2028",
            ),
            "APBN 2026 APBN 2027 APBN 2028",
        )


class TenderStatusNormalizationTests(SimpleTestCase):
    def test_cancelled_tender_and_selection_are_failed(self):
        self.assertEqual(normalize_status("Tender Batal"), "FAILED")
        self.assertEqual(normalize_status("Seleksi Batal"), "FAILED")

    def test_failed_tender_and_selection_are_failed(self):
        self.assertEqual(normalize_status("Tender Gagal"), "FAILED")
        self.assertEqual(normalize_status("Seleksi Gagal"), "FAILED")

    def test_active_stage_remains_ongoing(self):
        self.assertEqual(normalize_status("Evaluasi Penawaran"), "ONGOING")


class TenderFilterDefaultYearTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_year_defaults_to_current_year_when_missing(self):
        request = self.factory.get("/tenders/")

        selected = get_selected_filters(request)

        self.assertEqual(selected["tahun"], str(timezone.localdate().year))

    def test_empty_year_parameter_still_allows_all_years(self):
        request = self.factory.get("/tenders/", {"tahun": ""})

        selected = get_selected_filters(request)

        self.assertEqual(selected["tahun"], "")


class SpseSlugMappingTests(SimpleTestCase):
    def test_parse_portal_entries_extracts_safe_unique_slugs(self):
        script_text = (
            'let n=[{name:"LPSE Kota Test",oldUrl:"https://lpse.test.go.id",newUrlPath:"kotatest"},'
            '{name:"LPSE Kota Test Duplicate",oldUrl:"https://lpse.test.go.id",newUrlPath:"kotatest"},'
            '{name:"Govtech Dev",oldUrl:"https://spse-latihan.eproc.dev",newUrlPath:"latihan"},'
            '{name:"Unsafe",oldUrl:"https://unsafe.go.id",newUrlPath:"../unsafe"}];'
        )

        mapping = parse_portal_entries(script_text)

        self.assertEqual(mapping, OrderedDict([("kotatest", "LPSE Kota Test")]))

    def test_merge_slug_mapping_adds_new_and_updates_existing_names(self):
        existing = OrderedDict([
            ("jakarta", "Old Jakarta"),
            ("bandung", "LPSE Kota Bandung"),
        ])
        discovered = OrderedDict([
            ("jakarta", "Provinsi DKI Jakarta > LPSE Provinsi DKI Jakarta"),
            ("surabaya", "LPSE Kota Surabaya"),
        ])

        result = merge_slug_mapping(existing, discovered)

        self.assertEqual(result["mapping"]["jakarta"], "Provinsi DKI Jakarta > LPSE Provinsi DKI Jakarta")
        self.assertEqual(result["mapping"]["surabaya"], "LPSE Kota Surabaya")
        self.assertIn("jakarta", result["updated"])
        self.assertIn("surabaya", result["added"])


class ScrapeSpseLiveCommandOptionTests(SimpleTestCase):
    def setUp(self):
        self.command = ScrapeSpseLiveCommand()

    def base_options(self, **overrides):
        options = {
            "kode_tender": None,
            "slug": None,
            "all_slugs": True,
            "tahun": 2026,
            "detail_only": False,
            "then_detail_only": False,
        }
        options.update(overrides)
        return options

    def test_then_detail_only_can_follow_all_slugs_list_scrape(self):
        self.command.validate_options(self.base_options(then_detail_only=True))

    def test_then_detail_only_cannot_be_combined_with_detail_only(self):
        with self.assertRaisesMessage(CommandError, "--detail-only cannot be combined with --then-detail-only"):
            self.command.validate_options(self.base_options(detail_only=True, then_detail_only=True))


class InaprocRealisasiClientTests(SimpleTestCase):
    def test_parse_rupiah_common_formats(self):
        self.assertEqual(parse_rupiah("Rp1.234.567"), 1234567)
        self.assertEqual(parse_rupiah("1.234.567"), 1234567)
        self.assertEqual(parse_rupiah("1,234,567"), 1234567)

    def test_build_export_payload_defaults_to_empty_browser_filters(self):
        client = InaprocRealisasiClient()

        payload = client.build_export_payload(tahun=2026)

        self.assertEqual(payload["filters"]["jenisKlpd"], [])
        self.assertEqual(payload["filters"]["instansi"], "")
        self.assertEqual(payload["filters"]["statusPaket"], [])
        self.assertNotIn("Semua", client._body_text(payload))

    def test_build_export_payload_uses_explicit_realisasi_status(self):
        client = InaprocRealisasiClient()

        payload = client.build_export_payload(tahun=2026, status="berlangsung")
        self.assertEqual(payload["filters"]["statusPaket"], ["BERLANGSUNG"])

        payload = client.build_export_payload(tahun=2026, all_status=True)
        self.assertEqual(payload["filters"]["statusPaket"], ["BERLANGSUNG", "SELESAI"])

    def test_parse_csv_maps_main_columns(self):
        client = InaprocRealisasiClient()
        csv_text = (
            "Nama Instansi,Kode Paket,Nama Paket,Status Paket,Total Nilai (Rp)\n"
            "Kementerian X,10123076000,Paket Jalan,BERLANGSUNG,Rp1.234.567\n"
        )

        rows = client.parse_csv(csv_text, MAIN_CSV_MAPPING)

        self.assertEqual(rows[0]["nama_instansi"], "Kementerian X")
        self.assertEqual(rows[0]["kode_paket"], "10123076000")
        self.assertEqual(rows[0]["total_nilai"], 1234567)

    def test_signature_warmup_and_export_share_compact_body(self):
        session = RecordingSession()
        client = InaprocRealisasiClient(session=session, referer_tahun=2026)

        client.download_realisasi_csv(
            tahun=2026,
            status="BERLANGSUNG",
            jenis_klpd="1",
            instansi="K3",
        )

        self.assertEqual(session.calls[0][0], "GET")
        self.assertIn("/realisasi?tahun=2026&sumber=Tender", session.calls[0][1])
        self.assertEqual(session.calls[1][0], "POST")
        self.assertEqual(session.last_signature_payload["path"], "/dashboard-api/realisasi/export")
        self.assertEqual(session.last_signature_payload["body"], session.last_export_body)
        self.assertNotIn(" ", session.last_export_body)

    def test_download_realisasi_requires_export_geo_filters(self):
        client = InaprocRealisasiClient(session=RecordingSession(), referer_tahun=2026)

        with self.assertRaisesRegex(ValueError, "Export CSV wajib"):
            client.download_realisasi_csv(tahun=2026, status="BERLANGSUNG")


class InaprocRealisasiImporterTests(TestCase):
    def test_upsert_uses_kode_paket_and_fallback_kode_tender(self):
        row = {
            "kode_paket": "10123076000",
            "kode_rup": "999",
            "nama_paket": "Paket Jalan",
            "nama_instansi": "Kementerian X",
            "nama_satuan_kerja": "Satker X",
            "status_paket": "BERLANGSUNG",
            "tahun_anggaran": "2026",
            "total_nilai": 1234567,
        }

        result, tender = upsert_realisasi_row(row)

        self.assertEqual(result, "created")
        self.assertEqual(tender.kode_tender, "10123076000")
        self.assertEqual(tender.kode_paket, "10123076000")
        self.assertEqual(tender.status, "BERLANGSUNG")
        self.assertEqual(tender.nilai_hps, 1234567)

        row["nama_paket"] = "Paket Jalan Update"
        result, tender = upsert_realisasi_row(row)

        self.assertEqual(result, "updated")
        self.assertEqual(tender.nama_paket, "Paket Jalan Update")
        self.assertEqual(tender.raw_data["realisasi"]["kode_paket"], "10123076000")


class ProcurementAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="procurement-admin",
            email="procurement-admin@example.com",
            password="test-password",
        )
        self.client.force_login(self.admin_user)

    def test_admin_dashboard_renders_summary_cards(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Procurement Intelligence Administration")
        self.assertContains(response, "Total Tender")
        self.assertContains(response, "Total LPSE")
        self.assertContains(response, "Total Bookmark")

    def test_tender_admin_changelist_renders(self):
        response = self.client.get(reverse("admin:tenders_tender_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select tender to change")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="GPFE PROC HUB <noreply@inaprochub.gpfe.id>",
    APP_BASE_URL="https://inaprochub.gpfe.id",
)
class TenderDigestEmailTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(
            username="vendor@example.com",
            email="vendor@example.com",
            password="test-password",
            first_name="Vendor",
        )
        self.profile = VendorProfile.objects.create(
            user=self.user,
            full_name="Vendor Test",
            whatsapp_number="08123456789",
            institution_email="vendor@example.com",
            company_name="PT Vendor",
            business_field="Konstruksi",
            email_notifications_enabled=True,
            email_digest_frequency=VendorProfile.THREE_DAYS,
        )

    def create_notification(self, index=1, notification_type=TenderNotification.WATCHLIST_LPSE):
        tender = Tender.objects.create(
            kode_tender=f"TDR-{index}",
            kode_paket=f"PKT-{index}",
            nama_paket=f"Paket Tender {index}",
            instansi="Kementerian Test",
            lpse_slug=f"lpse-{index}",
            lpse_name="LPSE Test",
            tanggal_pembuatan=timezone.localdate(),
            status="OPEN",
        )
        return TenderNotification.objects.create(
            user=self.user,
            tender=tender,
            notification_type=notification_type,
            title=tender.nama_paket,
        )

    def test_notification_off_never_sends_digest(self):
        self.profile.email_notifications_enabled = False
        self.profile.save(update_fields=["email_notifications_enabled"])
        self.create_notification()

        result = send_digest_for_user(self.user, now=self.now)

        self.assertFalse(result["sent"])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(TenderNotificationEmailLog.objects.count(), 0)

    def test_daily_sends_max_once_per_day(self):
        self.profile.email_digest_frequency = VendorProfile.DAILY
        self.profile.last_digest_sent_at = self.now - timedelta(hours=12)
        self.profile.save(update_fields=["email_digest_frequency", "last_digest_sent_at"])
        self.create_notification()

        result = send_digest_for_user(self.user, now=self.now)

        self.assertFalse(result["sent"])
        self.assertEqual(len(mail.outbox), 0)

    def test_three_days_frequency_waits_three_days(self):
        self.profile.last_digest_sent_at = self.now - timedelta(days=2, hours=23)
        self.profile.save(update_fields=["last_digest_sent_at"])
        self.create_notification()

        result = send_digest_for_user(self.user, now=self.now)

        self.assertFalse(result["sent"])
        self.assertEqual(len(mail.outbox), 0)

        self.profile.last_digest_sent_at = self.now - timedelta(days=3, minutes=1)
        self.profile.save(update_fields=["last_digest_sent_at"])
        result = send_digest_for_user(self.user, now=self.now)

        self.assertTrue(result["sent"])
        self.assertEqual(len(mail.outbox), 1)

    def test_weekly_frequency_waits_seven_days(self):
        self.profile.email_digest_frequency = VendorProfile.WEEKLY
        self.profile.last_digest_sent_at = self.now - timedelta(days=6)
        self.profile.save(update_fields=["email_digest_frequency", "last_digest_sent_at"])
        self.create_notification()

        result = send_digest_for_user(self.user, now=self.now)

        self.assertFalse(result["sent"])
        self.assertEqual(len(mail.outbox), 0)

        self.profile.last_digest_sent_at = self.now - timedelta(days=7, minutes=1)
        self.profile.save(update_fields=["last_digest_sent_at"])
        result = send_digest_for_user(self.user, now=self.now)

        self.assertTrue(result["sent"])
        self.assertEqual(len(mail.outbox), 1)

    def test_no_new_notification_does_not_send_empty_email(self):
        result = send_digest_for_user(self.user, now=self.now)

        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "empty")
        self.assertEqual(len(mail.outbox), 0)

    def test_same_notification_is_never_sent_twice_and_last_sent_is_updated(self):
        notification = self.create_notification()

        result = send_digest_for_user(self.user, now=self.now)

        self.assertTrue(result["sent"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(TenderNotificationEmailLog.objects.filter(notification=notification).exists())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_digest_sent_at, self.now)

        self.profile.last_digest_sent_at = self.now - timedelta(days=4)
        self.profile.save(update_fields=["last_digest_sent_at"])
        result = send_digest_for_user(self.user, now=self.now)

        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "empty")
        self.assertEqual(len(mail.outbox), 1)

    def test_digest_email_limits_visible_tenders_and_logs_all_notifications(self):
        for index in range(1, 55):
            notification_type = (
                TenderNotification.WATCHLIST_LPSE
                if index % 2
                else TenderNotification.AI_MATCH_HIGH
            )
            self.create_notification(index=index, notification_type=notification_type)

        result = send_digest_for_user(self.user, now=self.now)

        self.assertTrue(result["sent"])
        self.assertEqual(TenderNotificationEmailLog.objects.count(), 54)
        self.assertIn("... dan 34 tender lainnya.", mail.outbox[0].body)
        self.assertIn("Watchlist LPSE", mail.outbox[0].body)
        self.assertIn("AI Match Tinggi", mail.outbox[0].body)

    def test_management_command_sends_due_digests(self):
        self.create_notification()

        call_command("send_tender_digest")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(TenderNotificationEmailLog.objects.count(), 1)
