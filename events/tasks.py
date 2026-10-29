import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)
User = get_user_model()

def send_welcome_email_task(user_id):
    """ Sends a welcome email when a user creates an account """
    try:
        user = User.objects.get(id=user_id)
        if not user.email:
            return 

        subject = "Welcome to Club Manager"
        context = {'user': user}
        html_content = render_to_string('emails/welcome_email.html', context)
        text_content = strip_tags(html_content)

        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
    except User.DoesNotExist:
        pass
    except Exception as exc:
        logger.error(f"Failed to send welcome email to User ID {user_id}: {exc}")

def send_event_created_email_task(recepient_ids, title, message, action_url=None, club_name=None):
    """ Sends an email to all active club members when an event is created """
    recipients = (
        User.objects.filter(id__in=recepient_ids, is_active=True)
        .exclude(email__isNull=True)
        .exclue(email__exact="")
    )

    if not recipients.exists():
        return

    subject = f"[{club_name or 'Club Manager'}] {title}"

    for user in recipients:
        context = {
            'user': user,
            'title': title,
            'message': message,
            'action_url': action_url,
            'club_name': club_name,
        }

        html_content = render_to_string('emails/notification_email.html', context)
        text_content = strip_tags(html_content)

        try:
            send_mail(
                subject=subject,
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_content,
                fail_silently=False,
            )
        except Exception as exc:
            logger.error(f"Failed to send event email to {user.email}: {exc}")