import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from cases.models import Notification

logger = logging.getLogger(__name__)


def notify_user(recipient, verb, title, message, case=None, action_url='', send_email=True):
    """
    Dispatches a clinical notification to a single user.
    Creates an in-app Notification database row and optionally delivers
    a branded HTML/plaintext transactional email.
    """
    notification = Notification.objects.create(
        recipient=recipient,
        case=case,
        verb=verb,
        title=title,
        message=message,
        action_url=action_url,
        is_read=False,
    )

    if send_email and getattr(recipient, 'email', None):
        try:
            full_action_url = action_url
            # If relative URL and SITE_URL configured, build absolute
            site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
            if action_url and action_url.startswith('/'):
                full_action_url = f"{site_url.rstrip('/')}{action_url}"

            context = {
                'recipient': recipient,
                'verb': verb,
                'title': title,
                'message': message,
                'case': case,
                'action_url': full_action_url,
            }
            html_content = render_to_string('emails/notification_email.html', context)
            plain_content = render_to_string('emails/notification_email.txt', context)

            subject = f"[DOPA] {title}"
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'DOPA Clinical Platform <notifications@dopa.internal>')

            send_mail(
                subject=subject,
                message=plain_content,
                from_email=from_email,
                recipient_list=[recipient.email],
                html_message=html_content,
                fail_silently=False,
            )
        except Exception as e:
            # Gracefully catch email exceptions so clinical workflows are never blocked
            logger.warning(f"Failed to deliver email notification to {recipient.email}: {e}")

    return notification


def notify_case_team(case, verb, title, message, exclude_user=None, action_url='', send_email=True):
    """
    Broadcasts notifications to all active participants in a clinical case:
    the Primary Physician (case owner) and all admitted Specialists.
    Optionally excludes the user who performed the action.
    """
    participants = set()
    if case.owner:
        participants.add(case.owner)

    for team_entry in case.team_memberships.select_related('specialist').all():
        if team_entry.specialist:
            participants.add(team_entry.specialist)

    if exclude_user:
        participants = {u for u in participants if u.id != exclude_user.id}

    dispatched = []
    for user in participants:
        notif = notify_user(
            recipient=user,
            verb=verb,
            title=title,
            message=message,
            case=case,
            action_url=action_url,
            send_email=send_email,
        )
        dispatched.append(notif)

    return dispatched
