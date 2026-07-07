from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from tenders.models import TenderNotification, TenderNotificationEmailLog
from users.models import VendorProfile


DIGEST_LIMIT = 20
FREQUENCY_DAYS = {
    VendorProfile.DAILY: 1,
    VendorProfile.THREE_DAYS: 3,
    VendorProfile.WEEKLY: 7,
}


def get_app_base_url():
    return getattr(settings, "APP_BASE_URL", "https://inaprochub.gpfe.id").rstrip("/")


def is_digest_due(profile, now=None):
    if not profile.email_notifications_enabled:
        return False
    if not profile.last_digest_sent_at:
        return True

    now = now or timezone.now()
    required_days = FREQUENCY_DAYS.get(profile.email_digest_frequency, 3)
    return profile.last_digest_sent_at <= now - timedelta(days=required_days)


def get_unsent_notifications(user):
    logged_notification_ids = TenderNotificationEmailLog.objects.filter(
        user=user,
    ).values("notification_id")
    return (
        TenderNotification.objects.filter(user=user)
        .exclude(id__in=logged_notification_ids)
        .select_related("tender")
        .order_by("-created_at", "-id")
    )


def tender_display(notification, base_url):
    tender = notification.tender
    return {
        "title": notification.title or tender.nama_paket or f"Tender {tender.kode_tender}",
        "kode_tender": tender.kode_tender,
        "lpse_name": tender.lpse_name or tender.instansi or "-",
        "instansi": tender.instansi or tender.klpd_instansi or "-",
        "tanggal": tender.tanggal_pembuatan,
        "nilai_hps": tender.nilai_hps or tender.nilai_pagu,
        "url": f"{base_url}{reverse('tender_detail', kwargs={'pk': tender.pk})}",
    }


def build_digest_context(user, notifications):
    base_url = get_app_base_url()
    displayed_notifications = notifications[:DIGEST_LIMIT]
    watchlist_items = []
    ai_match_items = []

    for notification in displayed_notifications:
        item = tender_display(notification, base_url)
        if notification.notification_type == TenderNotification.WATCHLIST_LPSE:
            watchlist_items.append(item)
        elif notification.notification_type == TenderNotification.AI_MATCH_HIGH:
            ai_match_items.append(item)

    total_count = len(notifications)
    return {
        "nama": user.get_full_name() or getattr(user.vendor_profile, "full_name", "") or user.username,
        "jumlah": total_count,
        "watchlist_items": watchlist_items,
        "ai_match_items": ai_match_items,
        "extra_count": max(total_count - DIGEST_LIMIT, 0),
        "tender_list_url": f"{base_url}{reverse('tender_list')}",
    }


def send_digest_email(user, notifications):
    recipient = user.email or getattr(user.vendor_profile, "institution_email", "")
    if not recipient:
        return False

    context = build_digest_context(user, notifications)
    text_body = render_to_string("emails/tender_digest.txt", context)
    html_body = render_to_string("emails/tender_digest.html", context)
    email = EmailMultiAlternatives(
        subject="Ringkasan Tender Terbaru - GPFE PROC HUB",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    email.attach_alternative(html_body, "text/html")
    return email.send() > 0


def send_digest_for_user(user, now=None):
    profile = getattr(user, "vendor_profile", None)
    if not profile or not is_digest_due(profile, now=now):
        return {"sent": False, "reason": "not_due", "count": 0}

    notifications = list(get_unsent_notifications(user))
    if not notifications:
        return {"sent": False, "reason": "empty", "count": 0}

    if not send_digest_email(user, notifications):
        return {"sent": False, "reason": "email_failed", "count": len(notifications)}

    now = now or timezone.now()
    with transaction.atomic():
        TenderNotificationEmailLog.objects.bulk_create(
            [
                TenderNotificationEmailLog(user=user, notification=notification)
                for notification in notifications
            ],
            ignore_conflicts=True,
        )
        profile.last_digest_sent_at = now
        profile.save(update_fields=["last_digest_sent_at"])

    return {"sent": True, "reason": "sent", "count": len(notifications), "total_count": len(notifications)}


def send_due_digests(now=None):
    now = now or timezone.now()
    users = User.objects.select_related("vendor_profile").filter(
        vendor_profile__email_notifications_enabled=True,
    )
    results = {
        "checked": 0,
        "sent": 0,
        "skipped": 0,
        "notifications_logged": 0,
    }

    for user in users.iterator():
        results["checked"] += 1
        result = send_digest_for_user(user, now=now)
        if result["sent"]:
            results["sent"] += 1
            results["notifications_logged"] += result["count"]
        else:
            results["skipped"] += 1

    return results
