from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from tenders.management.commands.scrape_spse_live import (
    append_year_to_sumber_dana,
    normalize_status,
    parse_jenis_pengadaan_tahun,
    parse_year,
)
from tenders.year_utils import extract_budget_years, normalize_budget_years


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
        self.assertContains(response, "Kode tender")
        self.assertContains(response, "Nilai HPS")
