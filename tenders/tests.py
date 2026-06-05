from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
