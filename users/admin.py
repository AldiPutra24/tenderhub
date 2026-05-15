# from django.contrib import admin
# from .models import Company

# admin.site.register(Company)

from django.contrib import admin
from .models import VendorProfile


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "company_name",
        "full_name",
        "institution_email",
        "whatsapp_number",
        "business_field",
        "location_type",
        "province",
        "city_or_regency",
        "country",
        "created_at",
    )

    search_fields = (
        "company_name",
        "full_name",
        "institution_email",
        "whatsapp_number",
        "business_field",
    )

    list_filter = (
        "location_type",
        "province",
        "country",
        "created_at",
    )