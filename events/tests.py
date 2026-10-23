from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from events.models import Event
from events.views import check_and_send_event_reminders
from members.models import Club, Member, Notification
from django.contrib.auth.models import User

class ReminderTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("pres", password="x")
        self.member = Member.objects.create(user=user, first_name="P", last_name="R", role="president")
        self.club = Club.objects.create(name="Chess", leader=self.member, status=Club.Status.APPROVED)

    def test_reminder_sent_once(self):
        Event.objects.create(title="Soon", club=self.club, created_by=self.member,
                             date=timezone.now() + timedelta(hours=3))
        self.assertEqual(check_and_send_event_reminders(), 1)
        self.assertEqual(check_and_send_event_reminders(), 0)
        self.assertEqual(Notification.objects.filter(notification_type="reminder").count(), 1)

    def test_far_event_ignored(self):
        Event.objects.create(title="Later", club=self.club, created_by=self.member,
                             date=timezone.now() + timedelta(days=3))
        self.assertEqual(check_and_send_event_reminders(), 0)