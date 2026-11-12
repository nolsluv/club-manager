from types import SimpleNamespace
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings


class Command(BaseCommand):
    help = "Send test ClawConnect emails via Resend to verify templates and links"

    def add_arguments(self, parser):
        parser.add_argument("to_email", type=str, help="Recipient email address for test emails")

    def handle(self, *args, **options):
        to_email = options["to_email"]
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "ClawConnect <noreply@clawconnectuwm.me>")

        mock_user = SimpleNamespace(first_name="Ben", username="bdhess13")
        mock_club = SimpleNamespace(name="UWM AI & Robotics Club")

        tests = [
            {
                "subject": "[Test] Welcome to ClawConnect",
                "html_template": "emails/welcome_email.html",
                "txt_template": None,
                "context": {
                    "user": mock_user,
                    "dashboard_url": "https://clawconnectuwm.me",
                },
            },
            {
                "subject": "[Test] Club Event Notification",
                "html_template": "emails/notification_email.html",
                "txt_template": None,
                "context": {
                    "club_name": mock_club.name,
                    "title": "Spring Kickoff & Hackathon Prep",
                    "message": "Join us this Thursday at 6:00 PM in EMS E180 for project team matching and pizza.",
                    "action_url": "/events/1/",
                },
            },
            {
                "subject": f"[Test] Welcome to {mock_club.name}!",
                "html_template": "emails/club_acceptance_email.html",
                "txt_template": "emails/membership_approved.txt",
                "context": {
                    "recipient_name": "Ben",
                    "club": mock_club,
                    "club_url": "/clubs/1/",
                },
            },
        ]

        for test in tests:
            html_body = render_to_string(test["html_template"], test["context"])
            text_body = (
                render_to_string(test["txt_template"], test["context"])
                if test["txt_template"]
                else "Please view this email in an HTML-capable email client."
            )

            msg = EmailMultiAlternatives(
                subject=test["subject"],
                body=text_body,
                from_email=from_email,
                to=[to_email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()
            self.stdout.write(self.style.SUCCESS(f"Sent: {test['subject']} -> {to_email}"))