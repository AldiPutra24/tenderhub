from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
import logging

from .models import VendorProfile


logger = logging.getLogger(__name__)


def build_login_url(request):
    if request:
        return request.build_absolute_uri(reverse("login"))
    return f"{getattr(settings, 'APP_BASE_URL', 'https://inaprochub.gpfe.id').rstrip('/')}{reverse('login')}"


def send_account_approved_email(user, request=None):
    recipient = user.email or getattr(getattr(user, "vendor_profile", None), "institution_email", "")
    if not recipient:
        return False

    body = render_to_string(
        "users/account_approved_email.txt",
        {"user": user, "login_url": build_login_url(request)},
    )
    try:
        send_mail(
            subject="Akun GPFE PROC HUB Telah Disetujui",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send account approval email for user_id=%s", user.pk)
        return False
    return True


@admin.action(description="Approve selected users")
def approve_users(modeladmin, request, queryset):
    users_to_notify = list(queryset.filter(is_active=False).select_related("vendor_profile"))
    updated = queryset.filter(pk__in=[user.pk for user in users_to_notify]).update(is_active=True)
    sent_count = 0
    for user in users_to_notify:
        user.is_active = True
        if send_account_approved_email(user, request=request):
            sent_count += 1
    modeladmin.message_user(
        request,
        f"{updated} user berhasil diaktifkan. Email persetujuan terkirim ke {sent_count} user.",
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


@admin.action(description="Aktifkan Notifikasi Email")
def enable_email_notifications(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_notifications_enabled=True)
    modeladmin.message_user(request, f"{updated} profil berhasil diaktifkan email digest-nya.", messages.SUCCESS)


@admin.action(description="Nonaktifkan Notifikasi Email")
def disable_email_notifications(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_notifications_enabled=False)
    modeladmin.message_user(request, f"{updated} profil berhasil dinonaktifkan email digest-nya.", messages.SUCCESS)


@admin.action(description="Atur Frekuensi: Harian")
def set_digest_daily(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_digest_frequency=VendorProfile.DAILY)
    modeladmin.message_user(request, f"{updated} profil diatur ke digest harian.", messages.SUCCESS)


@admin.action(description="Atur Frekuensi: 3 Hari")
def set_digest_three_days(modeladmin, request, queryset):
    updated = VendorProfile.objects.filter(user__in=queryset).update(email_digest_frequency=VendorProfile.THREE_DAYS)
    modeladmin.message_user(request, f"{updated} profil diatur ke digest 3 hari.", messages.SUCCESS)


@admin.action(description="Atur Frekuensi: Mingguan")
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
        "country",
        "province_name",
        "city_name",
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
        "vendor_profile__country",
        "vendor_profile__province_name",
        "vendor_profile__city_name",
        "vendor_profile__international_location",
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

    def save_model(self, request, obj, form, change):
        was_inactive = False
        if change and obj.pk:
            was_inactive = not User.objects.filter(pk=obj.pk, is_active=True).exists()

        super().save_model(request, obj, form, change)

        if was_inactive and obj.is_active:
            send_account_approved_email(obj, request=request)

    @admin.display(description="Nama perusahaan")
    def company_name(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.company_name if profile else "-"

    @admin.display(description="Negara")
    def country(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.country if profile else "-"

    @admin.display(description="Provinsi")
    def province_name(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.province_name or profile.province if profile else "-"

    @admin.display(description="Kota/Kabupaten")
    def city_name(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.city_name or profile.city_or_regency if profile else "-"

    @admin.display(boolean=True, description="Email verified")
    def email_verified(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return bool(profile and profile.email_verified)

    @admin.display(description="Email verified at")
    def email_verified_at(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.email_verified_at if profile else None

    @admin.display(boolean=True, description="Notifikasi Email Aktif")
    def email_notifications_enabled(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return bool(profile and profile.email_notifications_enabled)

    @admin.display(description="Frekuensi Ringkasan")
    def email_digest_frequency(self, obj):
        profile = getattr(obj, "vendor_profile", None)
        return profile.get_email_digest_frequency_display() if profile else "-"

    @admin.display(description="Ringkasan Terakhir Dikirim")
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
        "country",
        "province_name",
        "city_name",
        "international_location",
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
        "country",
        "province_name",
        "city_name",
        "international_location",
    )

    list_filter = (
        "email_notifications_enabled",
        "email_digest_frequency",
        "location_type",
        "country",
        "province_name",
        "city_name",
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
            "Notifikasi Email",
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
                    "country",
                    "province_id",
                    "province_name",
                    "city_id",
                    "city_name",
                    "international_location",
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
