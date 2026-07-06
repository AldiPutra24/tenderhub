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


@admin.action(description="Enable Email Notification")
def enable_email_notifications(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_notifications_enabled=True)
    modeladmin.message_user(request, f"{updated} profil berhasil diaktifkan email digest-nya.", messages.SUCCESS)


@admin.action(description="Disable Email Notification")
def disable_email_notifications(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_notifications_enabled=False)
    modeladmin.message_user(request, f"{updated} profil berhasil dinonaktifkan email digest-nya.", messages.SUCCESS)


@admin.action(description="Set Frequency: Daily")
def set_digest_daily(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_digest_frequency=VendorProfile.DAILY)
    modeladmin.message_user(request, f"{updated} profil diatur ke digest harian.", messages.SUCCESS)


@admin.action(description="Set Frequency: 3 Hari")
def set_digest_three_days(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_digest_frequency=VendorProfile.THREE_DAYS)
    modeladmin.message_user(request, f"{updated} profil diatur ke digest 3 hari.", messages.SUCCESS)


@admin.action(description="Set Frequency: Weekly")
def set_digest_weekly(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_digest_frequency=VendorProfile.WEEKLY)
    modeladmin.message_user(request, f"{updated} profil diatur ke digest mingguan.", messages.SUCCESS)


def _profile_action(action):
    def wrapped(modeladmin, request, queryset):
        return action(modeladmin, request, User.objects.filter(vendor_profile__in=queryset))

    wrapped.__name__ = f"profile_{action.__name__}"
    wrapped.short_description = action.short_description
    return wrapped


class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "company_name",
        "email_notifications_enabled",
        "email_digest_frequency",
        "last_digest_sent_at",
        "email_verified",
        "email_verified_at",
        "is_active",
        "date_joined",
        "last_login",
    )
    list_filter = (
        "vendor_profile__email_notifications_enabled",
        "vendor_profile__email_digest_frequency",
        "vendor_profile__email_verified",
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
        "last_login",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "vendor_profile__company_name",
        "vendor_profile__full_name",
    )
    actions = [
        approve_users,
        deactivate_users,
        enable_email_notifications,
        disable_email_notifications,
        set_digest_daily,
        set_digest_three_days,
        set_digest_weekly,
    ]
    list_per_page = 50
    ordering = ("-date_joined",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("vendor_profile")

    @admin.display(description="Nama perusahaan")
    def company_name(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.company_name if profile else "-"

    @admin.display(boolean=True, description="Email verified")
    def email_verified(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return bool(profile and profile.email_verified)

    @admin.display(description="Email verified at")
    def email_verified_at(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.email_verified_at if profile else None

    @admin.display(boolean=True, description="Notification Enabled")
    def email_notifications_enabled(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return bool(profile and profile.email_notifications_enabled)

    @admin.display(description="Digest Frequency")
    def email_digest_frequency(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.get_email_digest_frequency_display() if profile else "-"

    @admin.display(description="Last Digest Sent")
    def last_digest_sent_at(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.last_digest_sent_at if profile else None


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
        "email_notifications_enabled",
        "email_digest_frequency",
        "last_digest_sent_at",
        "email_verified",
        "email_verified_at",
        "whatsapp_number",
        "business_field",
        "location_type",
        "province",
        "city_or_regency",
        "country",
        "created_at",
        "email_verified_at",
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
        "email_notifications_enabled",
        "email_digest_frequency",
        "location_type",
        "province",
        "country",
        "created_at",
        "email_verified",
    )
    list_select_related = ("user",)
    list_per_page = 50
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "email_verified_at")
    actions = [
        _profile_action(enable_email_notifications),
        _profile_action(disable_email_notifications),
        _profile_action(set_digest_daily),
        _profile_action(set_digest_three_days),
        _profile_action(set_digest_weekly),
    ]
    fieldsets = (
        ("Account", {"fields": ("user", "created_at", "email_verified", "email_verified_at")}),
        (
            "Email Notifications",
            {
                "fields": (
                    "email_notifications_enabled",
                    "email_digest_frequency",
                    "last_digest_sent_at",
                )
            },
        ),
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
