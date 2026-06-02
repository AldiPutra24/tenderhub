from tenders.services.notifications import get_notifications, get_unread_count


def tender_notifications(request):
    notifications = get_notifications(request.user)
    return {
        "tender_notifications": notifications,
        "tender_notifications_count": get_unread_count(request.user, generate=False),
    }
