from datetime import timedelta

from django import template
from django.contrib.auth.models import User
from django.utils import timezone

from tenders.models import LPSEWatchlist, Tender, TenderBookmark
from users.models import VendorProfile


register = template.Library()


@register.simple_tag(takes_context=True)
def admin_dashboard_stats(context):
    user = context["request"].user

    can_view_users = user.has_perm("auth.view_user")
    can_view_tenders = user.has_perm("tenders.view_tender")
    can_view_watchlists = user.has_perm("tenders.view_lpsewatchlist")
    can_view_bookmarks = user.has_perm("tenders.view_tenderbookmark")
    can_view_profiles = user.has_perm("users.view_vendorprofile")
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())

    return [
        {
            "label": "Total Tender",
            "value": Tender.objects.count() if can_view_tenders else None,
            "tone": "emerald",
        },
        {
            "label": "Total LPSE",
            "value": (
                Tender.objects.exclude(lpse_slug="")
                .values("lpse_slug")
                .distinct()
                .count()
                if can_view_tenders
                else None
            ),
            "tone": "slate",
        },
        {
            "label": "Total User",
            "value": User.objects.count() if can_view_users else None,
            "tone": "slate",
        },
        {
            "label": "User Aktif",
            "value": User.objects.filter(is_active=True).count() if can_view_users else None,
            "tone": "emerald",
        },
        {
            "label": "Total Watchlist",
            "value": LPSEWatchlist.objects.count() if can_view_watchlists else None,
            "tone": "amber",
        },
        {
            "label": "Total Bookmark",
            "value": TenderBookmark.objects.count() if can_view_bookmarks else None,
            "tone": "amber",
        },
        {
            "label": "Notification Enabled",
            "value": (
                VendorProfile.objects.filter(email_notifications_enabled=True).count()
                if can_view_profiles
                else None
            ),
            "tone": "emerald",
        },
        {
            "label": "Notification Disabled",
            "value": (
                VendorProfile.objects.filter(email_notifications_enabled=False).count()
                if can_view_profiles
                else None
            ),
            "tone": "slate",
        },
        {
            "label": "Daily Users",
            "value": (
                VendorProfile.objects.filter(email_digest_frequency=VendorProfile.DAILY).count()
                if can_view_profiles
                else None
            ),
            "tone": "slate",
        },
        {
            "label": "Every 3 Days Users",
            "value": (
                VendorProfile.objects.filter(email_digest_frequency=VendorProfile.THREE_DAYS).count()
                if can_view_profiles
                else None
            ),
            "tone": "amber",
        },
        {
            "label": "Weekly Users",
            "value": (
                VendorProfile.objects.filter(email_digest_frequency=VendorProfile.WEEKLY).count()
                if can_view_profiles
                else None
            ),
            "tone": "slate",
        },
        {
            "label": "Email Digest Sent Today",
            "value": (
                VendorProfile.objects.filter(last_digest_sent_at__date=today).count()
                if can_view_profiles
                else None
            ),
            "tone": "emerald",
        },
        {
            "label": "Email Digest Sent This Week",
            "value": (
                VendorProfile.objects.filter(last_digest_sent_at__date__gte=week_start).count()
                if can_view_profiles
                else None
            ),
            "tone": "amber",
        },
    ]
