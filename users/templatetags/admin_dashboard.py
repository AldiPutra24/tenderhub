from django import template
from django.contrib.auth.models import User

from tenders.models import LPSEWatchlist, Tender, TenderBookmark


register = template.Library()


@register.simple_tag(takes_context=True)
def admin_dashboard_stats(context):
    user = context["request"].user

    can_view_users = user.has_perm("auth.view_user")
    can_view_tenders = user.has_perm("tenders.view_tender")
    can_view_watchlists = user.has_perm("tenders.view_lpsewatchlist")
    can_view_bookmarks = user.has_perm("tenders.view_tenderbookmark")

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
    ]
