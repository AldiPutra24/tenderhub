# from django.db import models

# class Company(models.Model):
#     nama_perusahaan = models.CharField(max_length=255)
#     bidang_usaha = models.CharField(max_length=255)
#     lokasi_operasional = models.CharField(max_length=255)
#     jenis_pengadaan = models.CharField(max_length=255, blank=True)
#     range_nilai_proyek = models.CharField(max_length=100, blank=True)

#     def __str__(self):
#         return self.nama_perusahaan
    
from django.db import models
from django.contrib.auth.models import User


class VendorProfile(models.Model):
    DAILY = "DAILY"
    THREE_DAYS = "THREE_DAYS"
    WEEKLY = "WEEKLY"
    EMAIL_DIGEST_FREQUENCY_CHOICES = [
        (DAILY, "Setiap Hari"),
        (THREE_DAYS, "Setiap 3 Hari"),
        (WEEKLY, "Mingguan"),
    ]

    LOCATION_TYPE_CHOICES = [
        ("indonesia", "Indonesia"),
        ("international", "Internasional"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vendor_profile")

    full_name = models.CharField(max_length=150)
    whatsapp_number = models.CharField(max_length=30)
    institution_email = models.EmailField(unique=True)

    company_name = models.CharField(max_length=200)
    business_field = models.CharField(max_length=200)

    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE_CHOICES, default="indonesia")

    province = models.CharField(max_length=100, blank=True, null=True)
    city_or_regency = models.CharField(max_length=100, blank=True, null=True)

    country = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    min_project_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        blank=True,
        null=True
    )

    max_project_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        blank=True,
        null=True
    )

    preferred_procurement_types = models.TextField(blank=True, default="")

    preferred_locations = models.TextField(blank=True, default="")

    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    email_notifications_enabled = models.BooleanField(default=True)
    email_digest_frequency = models.CharField(
        max_length=20,
        choices=EMAIL_DIGEST_FREQUENCY_CHOICES,
        default=THREE_DAYS,
    )
    last_digest_sent_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.company_name
