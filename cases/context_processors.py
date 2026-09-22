from cases.models import Notification


def notification_context(request):
    """
    Globally provides unread notifications count to templates
    for authenticated users without unnecessary database queries.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'unread_notifications_count': 0,
        }

    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return {
        'unread_notifications_count': unread_count,
    }
