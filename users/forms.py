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
from .services.locations import validate_indonesia_location


logger = logging.getLogger(__name__)


COUNTRY_CHOICES = [
    ("Indonesia", "Indonesia"),
    ("Malaysia", "Malaysia"),
    ("Singapore", "Singapura"),
    ("Thailand", "Thailand"),
    ("Vietnam", "Vietnam"),
    ("Philippines", "Filipina"),
    ("Brunei Darussalam", "Brunei Darussalam"),
    ("Australia", "Australia"),
    ("China", "China"),
    ("Japan", "Jepang"),
    ("South Korea", "Korea Selatan"),
    ("Other", "Lainnya"),
]


class CountryField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 100)
        kwargs.setdefault("required", False)
        kwargs.setdefault("initial", "Indonesia")
        kwargs.setdefault("widget", forms.Select(choices=COUNTRY_CHOICES))
        super().__init__(*args, **kwargs)
        self.choices = COUNTRY_CHOICES


def is_indonesia(country):
    return (country or "").strip().casefold() == "indonesia"


def add_country_choice(field, country):
    country = (country or "").strip()
    if not country:
        return

    choices = list(field.widget.choices)
    if country not in [value for value, _label in choices]:
        choices.append((country, country))
        field.widget.choices = choices
        field.choices = choices


class DynamicLocationFormMixin:
    def clean_dynamic_location(self, cleaned_data):
        country = (cleaned_data.get("country") or "").strip()
        location_type = cleaned_data.get("location_type") or "indonesia"

        if not country and location_type == "indonesia":
            country = "Indonesia"

        if is_indonesia(country):
            cleaned_data["location_type"] = "indonesia"
            location = validate_indonesia_location(
                cleaned_data.get("province_id"),
                cleaned_data.get("city_id"),
                cleaned_data.get("province_name") or cleaned_data.get("province"),
                cleaned_data.get("city_name") or cleaned_data.get("city_or_regency"),
            )
            if not location:
                if not cleaned_data.get("province_id") and not cleaned_data.get("province"):
                    self.add_error("province_id", "Provinsi wajib diisi.")
                if not cleaned_data.get("city_id") and not cleaned_data.get("city_or_regency"):
                    self.add_error("city_id", "Kota/Kabupaten wajib diisi.")
                if cleaned_data.get("province_id") or cleaned_data.get("city_id"):
                    raise forms.ValidationError("Data lokasi Indonesia tidak valid atau belum tersedia.")
                return cleaned_data

            cleaned_data.update(location)
            cleaned_data["province"] = location["province_name"]
            cleaned_data["city_or_regency"] = location["city_name"]
            cleaned_data["country"] = "Indonesia"
            cleaned_data["international_location"] = ""
            return cleaned_data

        cleaned_data["location_type"] = "international"
        cleaned_data["country"] = country
        international_location = (cleaned_data.get("international_location") or "").strip()
        if not country:
            self.add_error("country", "Negara wajib diisi.")
        if not international_location:
            self.add_error("international_location", "Lokasi internasional wajib diisi.")

        cleaned_data["province_id"] = ""
        cleaned_data["province_name"] = ""
        cleaned_data["city_id"] = ""
        cleaned_data["city_name"] = ""
        cleaned_data["province"] = ""
        cleaned_data["city_or_regency"] = ""
        return cleaned_data


class ApprovedAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Gagal masuk. Periksa kembali email dan kata sandi.",
        "inactive": "Akun kakak belum aktif atau masih menunggu approval admin.",
        "unverified": "Email belum diverifikasi. Silakan lakukan verifikasi melalui tautan yang telah dikirim ke alamat email Anda.",
        "locked": "Terlalu banyak percobaan login gagal.",
    }
    remember_me = forms.BooleanField(label="Ingat saya", required=False)

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
            password = self.cleaned_data.get("password")
            if inactive_user and password and inactive_user.check_password(password):
                if self.record_failed_attempt(username, reason="inactive"):
                    raise self.get_locked_error()
                raise forms.ValidationError(
                    self.error_messages["inactive"],
                    code="inactive",
                )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError as exc:
            if self.has_error_code(exc, {"inactive", "unverified"}):
                raise
            if self.record_failed_attempt(username, reason="invalid"):
                raise self.get_locked_error()
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
            )

        self.reset_failed_attempts(username)
        return cleaned_data

    def confirm_login_allowed(self, user):
        if user.is_staff or user.is_superuser:
            return
        if not user.is_active:
            raise forms.ValidationError(
                self.error_messages["inactive"],
                code="inactive",
            )
        if self.is_email_verified(user):
            return
        raise forms.ValidationError(
            self.error_messages["unverified"],
            code="unverified",
        )

    def has_error_code(self, error, codes):
        return any(getattr(item, "code", None) in codes for item in getattr(error, "error_list", []))

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


class VendorRegisterForm(DynamicLocationFormMixin, forms.Form):
    full_name = forms.CharField(label="Nama Lengkap", max_length=150)
    whatsapp_number = forms.CharField(label="Nomor WA", max_length=30)
    institution_email = forms.EmailField(label="Email Aktif")

    password = forms.CharField(label="Kata Sandi", widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="Konfirmasi Kata Sandi", widget=forms.PasswordInput)

    company_name = forms.CharField(label="Nama Perusahaan", max_length=200)
    business_field = forms.CharField(label="Bidang Usaha", max_length=200)

    location_type = forms.ChoiceField(
        label="Jenis Lokasi",
        choices=VendorProfile.LOCATION_TYPE_CHOICES,
        initial="indonesia",
        widget=forms.HiddenInput,
    )

    province = forms.CharField(label="Provinsi", max_length=100, required=False)
    city_or_regency = forms.CharField(label="Kota/Kabupaten", max_length=100, required=False)
    country = CountryField(label="Negara")
    province_id = forms.CharField(label="Provinsi", max_length=20, required=False)
    province_name = forms.CharField(max_length=100, required=False)
    city_id = forms.CharField(label="Kota/Kabupaten", max_length=20, required=False)
    city_name = forms.CharField(max_length=100, required=False)
    international_location = forms.CharField(label="Lokasi Internasional", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_country_choice(self.fields["country"], self.data.get("country") if self.is_bound else self.initial.get("country"))

    def clean_institution_email(self):
        email = self.cleaned_data["institution_email"]

        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Email ini sudah terdaftar.")

        return email

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Kata sandi dan konfirmasi kata sandi tidak sama.")

        return self.clean_dynamic_location(cleaned_data)


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(label="Email Aktif")


class VendorProfileForm(DynamicLocationFormMixin, forms.ModelForm):
    country = CountryField(label="Negara")
    province_id = forms.CharField(label="Provinsi", max_length=20, required=False)
    city_id = forms.CharField(label="Kota/Kabupaten", max_length=20, required=False)
    international_location = forms.CharField(label="Lokasi Internasional", max_length=255, required=False)

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
            "province_id",
            "province_name",
            "city_id",
            "city_name",
            "international_location",
            "min_project_value",
            "max_project_value",
            "email_notifications_enabled",
            "email_digest_frequency",
        ]

        labels = {
            "min_project_value": "Minimal Nilai Proyek",
            "max_project_value": "Maksimal Nilai Proyek",
            "email_notifications_enabled": "Aktifkan Notifikasi Email",
            "email_digest_frequency": "Frekuensi Ringkasan Email",
        }

        widgets = {
            "location_type": forms.HiddenInput,
            "province": forms.HiddenInput,
            "city_or_regency": forms.HiddenInput,
            "province_name": forms.HiddenInput,
            "city_name": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_country = self.data.get("country") if self.is_bound else getattr(self.instance, "country", None)
        add_country_choice(self.fields["country"], current_country)

        if self.instance:
            self.fields["preferred_procurement_types_text"].initial = (
                self.instance.preferred_procurement_types or ""
            )
            self.fields["preferred_locations_text"].initial = (
                self.instance.preferred_locations or ""
            )
            if not self.fields["province_name"].initial:
                self.fields["province_name"].initial = self.instance.province_name or self.instance.province
            if not self.fields["city_name"].initial:
                self.fields["city_name"].initial = self.instance.city_name or self.instance.city_or_regency

    def clean(self):
        cleaned_data = super().clean()
        return self.clean_dynamic_location(cleaned_data)

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
