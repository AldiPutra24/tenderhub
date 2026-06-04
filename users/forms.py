from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.cache import cache
import logging
from .models import VendorProfile


logger = logging.getLogger(__name__)


class ApprovedAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Login gagal. Periksa kembali email/username dan password.",
        "inactive": "Login gagal. Akun anda belum aktif atau masih menunggu approval admin.",
        "locked": "Terlalu banyak percobaan login gagal. Silakan coba lagi beberapa menit.",
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        cache_key = self.get_cache_key(username)

        if cache.get(f"{cache_key}:locked"):
            logger.warning("Login blocked by throttle for username=%s ip=%s", username, self.get_client_ip())
            raise forms.ValidationError(
                self.error_messages["locked"],
                code="locked",
            )

        if username and User.objects.filter(username=username, is_active=False).exists():
            self.record_failed_attempt(username, reason="inactive")
            raise forms.ValidationError(
                self.error_messages["inactive"],
                code="inactive",
            )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            self.record_failed_attempt(username, reason="invalid")
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
            )

        self.reset_failed_attempts(username)
        return cleaned_data

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

    def record_failed_attempt(self, username, reason):
        cache_key = self.get_cache_key(username)
        attempts = cache.get(cache_key, 0) + 1
        cache.set(cache_key, attempts, settings.LOGIN_LOCKOUT_SECONDS)
        logger.warning(
            "Login failed reason=%s username=%s ip=%s attempts=%s",
            reason,
            username,
            self.get_client_ip(),
            attempts,
        )

        if attempts >= settings.LOGIN_FAILURE_LIMIT:
            cache.set(f"{cache_key}:locked", True, settings.LOGIN_LOCKOUT_SECONDS)
            logger.warning("Login locked username=%s ip=%s", username, self.get_client_ip())

    def reset_failed_attempts(self, username):
        cache_key = self.get_cache_key(username)
        cache.delete(cache_key)
        cache.delete(f"{cache_key}:locked")


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
        ]

        labels = {
            "min_project_value": "Minimal Nilai Proyek",
            "max_project_value": "Maksimal Nilai Proyek",
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
