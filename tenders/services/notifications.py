from datetime import timedelta

from django.db import IntegrityError
from django.db.models import Q
from django.template.defaultfilters import slugify
from django.utils import timezone

from tenders.models import LPSEWatchlist, Tender, TenderNotification
from tenders.services.matching import calculate_tender_match


def get_vendor_profile(user):
    if not user.is_authenticated:
        return None

    try:
        return user.vendor_profile
    except Exception:
        return None


def infer_slug_from_urls(*urls):
    for url in urls:
        if not url:
            continue
        parts = str(url).split("spse.inaproc.id/", 1)
        if len(parts) != 2:
            continue
        slug = parts[1].split("/lelang/", 1)[0].strip("/")
        if slug:
            return slug
    return ""


def get_tender_lpse_key(tender):
    slug = getattr(tender, "lpse_slug", "") or infer_slug_from_urls(
        getattr(tender, "detail_url", ""),
        getattr(tender, "lpse_detail_url", ""),
    )
    if slug:
        return slug
    return slugify(getattr(tender, "lpse_name", "") or getattr(tender, "instansi", ""))


def build_watchlist_filter(watchlists):
    watchlist_slugs = {watchlist.lpse_slug for watchlist in watchlists if watchlist.lpse_slug}
    watchlist_names = {watchlist.lpse_name for watchlist in watchlists if watchlist.lpse_name}

    filters = Q()
    if watchlist_slugs:
        filters |= Q(lpse_slug__in=watchlist_slugs)
    if watchlist_names:
        filters |= Q(lpse_name__in=watchlist_names)
    return filters, watchlist_slugs


def get_recent_tenders(days=7):
    cutoff_date = timezone.localdate() - timedelta(days=days)
    return (
        Tender.objects.filter(tanggal_pembuatan__isnull=False, tanggal_pembuatan__gte=cutoff_date)
        .only(
            "id",
            "kode_tender",
            "nama_paket",
            "instansi",
            "klpd_instansi",
            "lpse_slug",
            "lpse_name",
            "detail_url",
            "lpse_detail_url",
            "jenis_pengadaan",
            "lokasi_pekerjaan",
            "nilai_hps",
            "nilai_pagu",
            "tanggal_pembuatan",
        )
        .order_by("-tanggal_pembuatan", "-id")
    )


def create_notification(user, tender, notification_type):
    title = tender.nama_paket or f"Tender {tender.kode_tender}"
    try:
        TenderNotification.objects.get_or_create(
            user=user,
            tender=tender,
            notification_type=notification_type,
            defaults={"title": title[:255]},
        )
    except IntegrityError:
        pass


def generate_user_tender_notifications(user, days=7, ai_threshold=80, ai_candidate_limit=100):
    if not user.is_authenticated:
        return

    recent_tenders = get_recent_tenders(days)
    watchlists = list(
        LPSEWatchlist.objects.filter(user=user).only("lpse_slug", "lpse_name")
    )
    watchlist_filter, watchlist_slugs = build_watchlist_filter(watchlists)

    watchlist_tender_ids = set()
    if watchlist_filter:
        for tender in recent_tenders.filter(watchlist_filter):
            watchlist_tender_ids.add(tender.id)
            create_notification(user, tender, TenderNotification.WATCHLIST_LPSE)

    vendor_profile = get_vendor_profile(user)
    ai_candidates = recent_tenders.exclude(id__in=watchlist_tender_ids)[:ai_candidate_limit]
    for tender in ai_candidates:
        if get_tender_lpse_key(tender) in watchlist_slugs:
            continue

        match_data = calculate_tender_match(tender, vendor_profile)
        score = match_data.get("score") or 0
        if score >= ai_threshold:
            create_notification(user, tender, TenderNotification.AI_MATCH_HIGH)


def notification_priority(notification):
    return 1 if notification.notification_type == TenderNotification.WATCHLIST_LPSE else 0


def attach_display_fields(notification, vendor_profile=None):
    notification.label = dict(TenderNotification.NOTIFICATION_TYPE_CHOICES).get(
        notification.notification_type,
        notification.notification_type,
    )
    notification.score = None
    if notification.notification_type == TenderNotification.AI_MATCH_HIGH:
        match_data = calculate_tender_match(notification.tender, vendor_profile)
        notification.score = match_data.get("score")
    return notification


def get_deduped_notifications(user, limit=None):
    if not user.is_authenticated:
        return []

    notifications = list(
        TenderNotification.objects.filter(user=user)
        .select_related("tender")
        .order_by("is_read", "-created_at")[: max(limit or 20, 100)]
    )
    by_tender = {}
    for notification in notifications:
        current = by_tender.get(notification.tender_id)
        if not current:
            by_tender[notification.tender_id] = notification
            continue
        if notification_priority(notification) > notification_priority(current):
            by_tender[notification.tender_id] = notification

    deduped = list(by_tender.values())
    deduped.sort(
        key=lambda item: (
            not item.is_read,
            item.created_at,
            notification_priority(item),
        ),
        reverse=True,
    )
    if limit:
        return deduped[:limit]
    return deduped


def get_unread_count(user, generate=True):
    if not user.is_authenticated:
        return 0
    if generate:
        generate_user_tender_notifications(user)
    return TenderNotification.objects.filter(user=user, is_read=False).count()


def get_notifications(user, limit=20):
    generate_user_tender_notifications(user)
    vendor_profile = get_vendor_profile(user)
    return [
        attach_display_fields(notification, vendor_profile)
        for notification in get_deduped_notifications(user, limit=limit)
    ]


def mark_notification_read(notification_id, user=None):
    if user is not None and not user.is_authenticated:
        return None

    queryset = TenderNotification.objects.filter(id=notification_id)
    if user is not None:
        queryset = queryset.filter(user=user)
    notification = queryset.select_related("tender").first()
    if not notification:
        return None
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at"])
    return notification


def mark_all_read(user):
    if not user.is_authenticated:
        return 0
    return TenderNotification.objects.filter(user=user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )


def get_user_tender_notifications(user, days=7, ai_threshold=80, limit=20):
    generate_user_tender_notifications(user, days=days, ai_threshold=ai_threshold)
    return get_notifications(user, limit=limit)
