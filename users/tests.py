from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from unittest.mock import patch

from users.tokens import email_verification_token
from users.models import VendorProfile


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

    def test_admin_can_bulk_update_notification_preferences(self):
        user = User.objects.create_user(
            username="vendor-admin@example.com",
            email="vendor-admin@example.com",
            password="test-password",
            is_active=True,
        )
        VendorProfile.objects.create(
            user=user,
            full_name="Vendor Admin",
            whatsapp_number="08123456789",
            institution_email="vendor-admin@example.com",
            company_name="PT Vendor Admin",
            business_field="Konstruksi",
        )

        response = self.client.post(
            reverse("admin:auth_user_changelist"),
            {
                "action": "disable_email_notifications",
                "_selected_action": [user.pk],
                "select_across": "0",
                "index": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        user.vendor_profile.refresh_from_db()
        self.assertFalse(user.vendor_profile.email_notifications_enabled)

        response = self.client.post(
            reverse("admin:auth_user_changelist"),
            {
                "action": "set_digest_weekly",
                "_selected_action": [user.pk],
                "select_across": "0",
                "index": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        user.vendor_profile.refresh_from_db()
        self.assertEqual(user.vendor_profile.email_digest_frequency, VendorProfile.WEEKLY)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="GPFE PROC HUB <noreply@inaprochub.gpfe.id>",
    )
    def test_approve_action_sends_account_approved_email(self):
        user = User.objects.create_user(
            username="pending-approval@example.com",
            email="pending-approval@example.com",
            password="test-password",
            is_active=False,
        )
        VendorProfile.objects.create(
            user=user,
            full_name="Pending Approval",
            whatsapp_number="08123456789",
            institution_email="pending-approval@example.com",
            company_name="PT Pending Approval",
            business_field="Konstruksi",
            email_verified=True,
        )

        response = self.client.post(
            reverse("admin:auth_user_changelist"),
            {
                "action": "approve_users",
                "_selected_action": [user.pk],
                "select_across": "0",
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Akun GPFE PROC HUB Telah Disetujui")
        self.assertIn("Akun GPFE PROC HUB Anda telah disetujui.", mail.outbox[0].body)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="GPFE PROC HUB <noreply@inaprochub.gpfe.id>",
)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="active@example.com",
            email="active@example.com",
            password="OldStrongPass123!",
            is_active=True,
        )

    def test_active_user_can_request_reset_and_email_is_sent(self):
        response = self.client.post(reverse("password_reset"), {"email": self.user.email})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Reset Password - GPFE PROC HUB")
        self.assertEqual(message.from_email, "GPFE PROC HUB <noreply@inaprochub.gpfe.id>")
        self.assertIn("Halo,", message.body)
        self.assertIn("/accounts/reset/", message.body)
        self.assertIn("Apabila Anda tidak pernah mengajukan permintaan ini", message.body)

    def test_unknown_email_does_not_leak_registration_status(self):
        response = self.client.post(reverse("password_reset"), {"email": "unknown@example.com"})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

        done_response = self.client.get(reverse("password_reset_done"))
        self.assertContains(done_response, "Jika email terdaftar dan aktif")

    def test_invalid_token_cannot_be_used(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": "invalid-token"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tautan reset kata sandi tidak valid")

    def test_new_password_can_be_used_to_login(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
        )
        self.assertEqual(response.status_code, 302)

        set_password_url = reverse(
            "password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": "set-password"},
        )
        response = self.client.post(
            set_password_url,
            {
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, "Kata sandi berhasil diperbarui. Silakan masuk menggunakan kata sandi baru.")
        self.assertTrue(self.client.login(username=self.user.username, password="NewStrongPass123!"))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="GPFE PROC HUB <noreply@inaprochub.gpfe.id>",
)
class EmailVerificationTests(TestCase):
    def setUp(self):
        cache.clear()

    def get_registration_payload(self, email="vendor@example.com"):
        return {
            "full_name": "Vendor Test",
            "whatsapp_number": "08123456789",
            "institution_email": email,
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "company_name": "PT Vendor Test",
            "business_field": "Konstruksi",
            "location_type": "indonesia",
            "province": "Jawa Timur",
            "city_or_regency": "Surabaya",
        }

    def create_pending_user(self, email="pending@example.com", verified=False, active=False):
        user = User.objects.create_user(
            username=email,
            email=email,
            password="StrongPass123!",
            is_active=active,
        )
        VendorProfile.objects.create(
            user=user,
            full_name="Pending Vendor",
            whatsapp_number="08123456789",
            institution_email=email,
            company_name="PT Pending",
            business_field="Konstruksi",
            email_verified=verified,
        )
        return user

    def test_register_creates_unverified_inactive_user_and_sends_email(self):
        response = self.client.post(reverse("register"), self.get_registration_payload())

        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(username="vendor@example.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.vendor_profile.email_verified)
        self.assertIsNone(user.vendor_profile.email_verified_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Verifikasi Email - GPFE PROC HUB")
        self.assertIn("/accounts/verify-email/", mail.outbox[0].body)

    @patch("users.email_verification.send_mail", side_effect=Exception("SMTP down"))
    def test_register_does_not_500_when_verification_email_fails(self, mocked_send_mail):
        response = self.client.post(
            reverse("register"),
            self.get_registration_payload(email="smtp-fail@example.com"),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pendaftaran berhasil, tetapi email verifikasi gagal dikirim.")
        user = User.objects.get(username="smtp-fail@example.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.vendor_profile.email_verified)
        self.assertIsNone(user.vendor_profile.email_verified_at)
        self.assertEqual(len(mail.outbox), 0)
        mocked_send_mail.assert_called_once()

    def test_unverified_user_cannot_login(self):
        self.create_pending_user(verified=False)
        response = self.client.post(
            reverse("login"),
            {"username": "pending@example.com", "password": "StrongPass123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email belum diverifikasi")

    def test_valid_verification_link_marks_profile_verified(self):
        user = self.create_pending_user(verified=False)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        url = reverse("verify_email", kwargs={"uidb64": uidb64, "token": token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        user.vendor_profile.refresh_from_db()
        self.assertTrue(user.vendor_profile.email_verified)
        self.assertIsNotNone(user.vendor_profile.email_verified_at)

    def test_verified_pending_user_has_limited_access(self):
        self.create_pending_user(verified=True)
        self.assertTrue(self.client.login(username="pending@example.com", password="StrongPass123!"))

        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("vendor_profile")).status_code, 200)

        tender_response = self.client.get(reverse("tender_list"))
        self.assertRedirects(tender_response, reverse("dashboard"))

        lpse_response = self.client.get(reverse("lpse_list"))
        self.assertRedirects(lpse_response, reverse("dashboard"))

    def test_admin_approved_user_gets_full_access(self):
        user = self.create_pending_user(verified=True, active=False)
        user.is_active = True
        user.save(update_fields=["is_active"])

        self.assertTrue(self.client.login(username="pending@example.com", password="StrongPass123!"))
        self.assertEqual(self.client.get(reverse("tender_list")).status_code, 200)

    def test_resend_verification_is_neutral_and_rate_limited(self):
        self.create_pending_user(verified=False)

        response = self.client.post(reverse("resend_verification"), {"email": "pending@example.com"})
        self.assertRedirects(response, reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(reverse("resend_verification"), {"email": "pending@example.com"})
        self.assertRedirects(response, reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(reverse("resend_verification"), {"email": "unknown@example.com"})
        self.assertRedirects(response, reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 1)


class VendorProfilePreferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile@example.com",
            email="profile@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.profile = VendorProfile.objects.create(
            user=self.user,
            full_name="Profile Vendor",
            whatsapp_number="08123456789",
            institution_email="profile@example.com",
            company_name="PT Profile",
            business_field="Konstruksi",
            location_type="indonesia",
            province="Jawa Timur",
            city_or_regency="Surabaya",
            email_verified=True,
        )
        self.client.force_login(self.user)

    def profile_payload(self, **overrides):
        payload = {
            "full_name": "Profile Vendor",
            "whatsapp_number": "08123456789",
            "institution_email": "profile@example.com",
            "company_name": "PT Profile",
            "business_field": "Konstruksi",
            "location_type": "indonesia",
            "province": "Jawa Timur",
            "city_or_regency": "Surabaya",
            "country": "",
            "min_project_value": "",
            "max_project_value": "",
            "preferred_procurement_types_text": "Konstruksi",
            "preferred_locations_text": "Surabaya",
            "email_notifications_enabled": "on",
            "email_digest_frequency": VendorProfile.THREE_DAYS,
        }
        payload.update(overrides)
        return payload

    def test_user_can_update_own_notification_preferences(self):
        payload = self.profile_payload(email_digest_frequency=VendorProfile.WEEKLY)
        payload.pop("email_notifications_enabled")

        response = self.client.post(reverse("vendor_profile"), payload)

        self.assertRedirects(response, reverse("vendor_profile"))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_notifications_enabled)
        self.assertEqual(self.profile.email_digest_frequency, VendorProfile.WEEKLY)

    def test_profile_settings_renders_email_notification_section(self):
        response = self.client.get(reverse("vendor_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notifikasi Email")
        self.assertContains(response, "Setiap 3 Hari")
