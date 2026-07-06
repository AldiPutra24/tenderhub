from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.utils import timezone
import logging
import math
from .models import VendorProfile


logger = logging.getLogger(__name__)


class ApprovedAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Login gagal. Periksa kembali email/username dan password.",
        "inactive": "Login gagal. Akun anda belum aktif atau masih menunggu approval admin.",
        "unverified": "Email kakak belum diverifikasi. Silakan cek email untuk verifikasi akun.",
        "locked": "Terlalu banyak percobaan login gagal.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lockout_remaining_seconds = 0

    def clean(self):
        username = self.cleaned_data.get("username")
        cache_key = self.get_cache_key(username)
        lockout_remaining = self.get_lockout_remaining_seconds(cache_key)

        if lockout_remaining > 0:
            self.lockout_remaining_seconds = lockout_remaining
            logger.warning("Login blocked by throttle for username=%s ip=%s", username, self.get_client_ip())
            raise self.get_locked_error()

        if username:
            inactive_user = User.objects.filter(username=username, is_active=False).first()
            if inactive_user and not self.is_email_verified(inactive_user):
                if self.record_failed_attempt(username, reason="unverified"):
                    raise self.get_locked_error()
                raise forms.ValidationError(
                    self.error_messages["unverified"],
                    code="unverified",
                )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            if self.record_failed_attempt(username, reason="invalid"):
                raise self.get_locked_error()
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
            )

        self.reset_failed_attempts(username)
        return cleaned_data

    def confirm_login_allowed(self, user):
        if user.is_active or self.is_email_verified(user):
            return
        raise forms.ValidationError(
            self.error_messages["unverified"],
            code="unverified",
        )

    def is_email_verified(self, user):
        try:
            return bool(user.vendor_profile.email_verified)
        except ObjectDoesNotExist:
            return False

    def get_client_ip(self):
        if not self.request:
            return "unknown"

        forwarded_for = self.request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        return self.request.META.get("REMOTE_ADDR", "unknown")

    def get_cache_key(self, username):
        normalized_username = (username or "").strip().casefold() or "anonymous"
        return f"login-fail:{self.get_client_ip()}:{normalized_username}"

    def get_now_timestamp(self):
        return timezone.now().timestamp()

    def get_throttle_state(self, cache_key):
        state = cache.get(cache_key) or {}
        if not isinstance(state, dict):
            return {"failed_attempts": int(state or 0), "locked_until": None}
        return {
            "failed_attempts": int(state.get("failed_attempts") or 0),
            "locked_until": state.get("locked_until"),
        }

    def get_lockout_remaining_seconds(self, cache_key):
        state = self.get_throttle_state(cache_key)
        locked_until = state.get("locked_until")
        if not locked_until:
            return 0

        remaining = int(math.ceil(float(locked_until) - self.get_now_timestamp()))
        if remaining <= 0:
            cache.delete(cache_key)
            return 0
        return remaining

    def get_locked_error(self):
        return forms.ValidationError(
            self.error_messages["locked"],
            code="locked",
        )

    def record_failed_attempt(self, username, reason):
        cache_key = self.get_cache_key(username)
        state = self.get_throttle_state(cache_key)
        attempts = state["failed_attempts"] + 1
        locked_until = None

        if attempts >= settings.LOGIN_FAILURE_LIMIT:
            locked_until = self.get_now_timestamp() + settings.LOGIN_LOCKOUT_SECONDS
            self.lockout_remaining_seconds = settings.LOGIN_LOCKOUT_SECONDS

        cache.set(
            cache_key,
            {
                "failed_attempts": attempts,
                "locked_until": locked_until,
            },
            settings.LOGIN_LOCKOUT_SECONDS,
        )
        logger.warning(
            "Login failed reason=%s username=%s ip=%s attempts=%s",
            reason,
            username,
            self.get_client_ip(),
            attempts,
        )

        if locked_until:
            logger.warning("Login locked username=%s ip=%s", username, self.get_client_ip())
            return True
        return False

    def reset_failed_attempts(self, username):
        cache_key = self.get_cache_key(username)
        cache.delete(cache_key)


class VendorRegisterForm(forms.Form):
    full_name = forms.CharField(label="Nama Lengkap", max_length=150)
    whatsapp_number = forms.CharField(label="Nomor WA", max_length=30)
    institution_email = forms.EmailField(label="Email Aktif")

    password = forms.CharField(label="Password", widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="Konfirmasi Password", widget=forms.PasswordInput)

    company_name = forms.CharField(label="Nama Perusahaan", max_length=200)
    business_field = forms.CharField(label="Bidang Usaha", max_length=200)

    location_type = forms.ChoiceField(
        label="Jenis Lokasi",
        choices=VendorProfile.LOCATION_TYPE_CHOICES
    )

    province = forms.CharField(label="Provinsi", max_length=100, required=False)
    city_or_regency = forms.CharField(label="Kota/Kabupaten", max_length=100, required=False)
    country = forms.CharField(label="Negara", max_length=100, required=False)

    def clean_institution_email(self):
        email = self.cleaned_data["institution_email"]

        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Email ini sudah terdaftar.")

        return email

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        location_type = cleaned_data.get("location_type")

        province = cleaned_data.get("province")
        city_or_regency = cleaned_data.get("city_or_regency")
        country = cleaned_data.get("country")

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Password dan konfirmasi password tidak sama.")

        if location_type == "indonesia":
            if not province:
                self.add_error("province", "Provinsi wajib diisi.")
            if not city_or_regency:
                self.add_error("city_or_regency", "Kota/Kabupaten wajib diisi.")

        if location_type == "international":
            if not country:
                self.add_error("country", "Negara wajib diisi.")

        return cleaned_data


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(label="Email Aktif")


class VendorProfileForm(forms.ModelForm):
    preferred_procurement_types_text = forms.CharField(
        label="Jenis Pengadaan yang Diminati",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Contoh:\nPekerjaan Konstruksi\nPengadaan Barang\nJasa Konsultansi"
        })
    )

    preferred_locations_text = forms.CharField(
        label="Lokasi Tender yang Diminati",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Contoh:\nJawa Timur\nNganjuk\nSurabaya"
        })
    )

    class Meta:
        model = VendorProfile
        fields = [
            "full_name",
            "whatsapp_number",
            "institution_email",
            "company_name",
            "business_field",
            "location_type",
            "province",
            "city_or_regency",
            "country",
            "min_project_value",
            "max_project_value",
            "email_notifications_enabled",
            "email_digest_frequency",
        ]

        labels = {
            "min_project_value": "Minimal Nilai Proyek",
            "max_project_value": "Maksimal Nilai Proyek",
            "email_notifications_enabled": "Enable Email Notification",
            "email_digest_frequency": "Email Digest Frequency",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance:
            self.fields["preferred_procurement_types_text"].initial = (
                self.instance.preferred_procurement_types or ""
            )
            self.fields["preferred_locations_text"].initial = (
                self.instance.preferred_locations or ""
            )

    def save(self, commit=True):
        instance = super().save(commit=False)

        instance.preferred_procurement_types = self.cleaned_data.get(
            "preferred_procurement_types_text", ""
        ).strip()

        instance.preferred_locations = self.cleaned_data.get(
            "preferred_locations_text", ""
        ).strip()

        if commit:
            instance.save()

        return instance
