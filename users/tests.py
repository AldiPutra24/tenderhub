from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class UserAdminTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_superuser(
            username="operator",
            email="operator@example.com",
            password="test-password",
        )
        self.client.force_login(self.operator)

    def test_user_admin_renders_with_gpfe_branding(self):
        response = self.client.get(reverse("admin:auth_user_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GPFE PROC HUB")
        self.assertContains(response, "gpfe_admin")

    def test_deactivate_action_protects_superusers(self):
        protected_superuser = User.objects.create_superuser(
            username="protected",
            email="protected@example.com",
            password="test-password",
        )
        regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="test-password",
            is_active=True,
        )

        response = self.client.post(
            reverse("admin:auth_user_changelist"),
            {
                "action": "deactivate_users",
                "_selected_action": [
                    self.operator.pk,
                    protected_superuser.pk,
                    regular_user.pk,
                ],
                "select_across": "0",
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.operator.refresh_from_db()
        protected_superuser.refresh_from_db()
        regular_user.refresh_from_db()
        self.assertTrue(self.operator.is_active)
        self.assertTrue(protected_superuser.is_active)
        self.assertFalse(regular_user.is_active)
