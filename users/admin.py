# from django.contrib import admin
# from .models import Company

# admin.site.register(Company)

from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from .models import VendorProfile


@admin.action(description="Approve selected users")
def approve_users(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description="Deactivate selected users")
def deactivate_users(modeladmin, request, queryset):
    queryset.update(is_active=False)


class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "company_name",
        "is_active",
        "is_staff",
        "date_joined",
        "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "date_joined", "last_login")
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "vendor_profile__company_name",
        "vendor_profile__full_name",
    )
    actions = [approve_users, deactivate_users]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("vendor_profile")

    @admin.display(description="Nama perusahaan")
    def company_name(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.company_name if profile else "-"


try:
    admin.site.unregister(User)
except NotRegistered:
    pass
admin.site.register(User, UserAdmin)


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
