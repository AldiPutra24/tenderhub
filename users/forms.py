from django import forms
from django.contrib.auth.models import User
from .models import VendorProfile


class VendorRegisterForm(forms.Form):
    full_name = forms.CharField(label="Nama Lengkap", max_length=150)
    whatsapp_number = forms.CharField(label="Nomor WA", max_length=30)
    institution_email = forms.EmailField(label="Email Instansi")

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
            self.fields["preferred_procurement_types_text"].initial = "\n".join(
                self.instance.preferred_procurement_types or []
            )
            self.fields["preferred_locations_text"].initial = "\n".join(
                self.instance.preferred_locations or []
            )

    def save(self, commit=True):
        instance = super().save(commit=False)

        instance.preferred_procurement_types = [
            x.strip()
            for x in self.cleaned_data.get("preferred_procurement_types_text", "").splitlines()
            if x.strip()
        ]

        instance.preferred_locations = [
            x.strip()
            for x in self.cleaned_data.get("preferred_locations_text", "").splitlines()
            if x.strip()
        ]

        if commit:
            instance.save()

        return instance