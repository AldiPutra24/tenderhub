from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from tenders.management.commands.scrape_spse_live import (
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
