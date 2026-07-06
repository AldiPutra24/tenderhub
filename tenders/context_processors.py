from tenders.services.notifications import get_notifications, get_unread_count


def tender_notifications(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return {
            "tender_notifications": [],
            "tender_notifications_count": 0,
        }

    notifications = get_notifications(request.user)
    return {
        "tender_notifications": notifications,
        "tender_notifications_count": get_unread_count(request.user, generate=False),
    }
