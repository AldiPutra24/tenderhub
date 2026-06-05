from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from .models import VendorProfile


@admin.action(description="Approve selected users")
def approve_users(modeladmin, request, queryset):
    updated = queryset.filter(is_active=False).update(is_active=True)
    modeladmin.message_user(
        request,
        f"{updated} user berhasil diaktifkan.",
        messages.SUCCESS,
    )


@admin.action(description="Deactivate selected users")
def deactivate_users(modeladmin, request, queryset):
    safe_queryset = queryset.exclude(pk=request.user.pk).exclude(is_superuser=True)
    updated = safe_queryset.filter(is_active=True).update(is_active=False)
    skipped = queryset.count() - safe_queryset.count()
    modeladmin.message_user(
        request,
        f"{updated} user berhasil dinonaktifkan."
        + (f" {skipped} akun dilindungi dan dilewati." if skipped else ""),
        messages.WARNING if skipped else messages.SUCCESS,
    )


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
    list_per_page = 50
    ordering = ("-date_joined",)

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
        "user",
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
        "user__username",
        "user__email",
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
    list_select_related = ("user",)
    list_per_page = 50
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    fieldsets = (
        ("Account", {"fields": ("user", "created_at")}),
        (
            "Company",
            {
                "fields": (
                    "company_name",
                    "business_field",
                    "institution_email",
                    "full_name",
                    "whatsapp_number",
                )
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "location_type",
                    "province",
                    "city_or_regency",
                    "country",
                )
            },
        ),
        (
            "Tender Preferences",
            {
                "classes": ("collapse",),
                "fields": (
                    "min_project_value",
                    "max_project_value",
                    "preferred_procurement_types",
                    "preferred_locations",
                ),
            },
        ),
    )
