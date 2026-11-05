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

from django.urls import reverse
from events.models import Attendance, RSVP


class AttendanceTests(TestCase):
    def make_member(self, username, role, club=None):
        user = User.objects.create_user(username, password="x")
        m = Member.objects.create(user=user, first_name=username.title(), last_name="T",
                                  email=f"{username}@example.com", role=role)
        if club:
            club.members.add(m)
        return m

    def setUp(self):
        self.pres = self.make_member("pres", "president")
        self.club = Club.objects.create(name="Chess", leader=self.pres, status=Club.Status.APPROVED)
        self.club.members.add(self.pres)
        self.alice = self.make_member("alice", "member", self.club)
        self.bob = self.make_member("bob", "member", self.club)
        self.event = Event.objects.create(title="Meetup", club=self.club, created_by=self.pres,
                                          date=timezone.now() - timedelta(hours=1))
        self.url = reverse("event_attendance", args=[self.event.pk])

    def login(self, username):
        self.client.login(username=username, password="x")

    # Acceptance criterion 1: attendance is saved
    def test_leader_can_record_attendance(self):
        self.login("pres")
        resp = self.client.post(self.url, {"attendees": [self.alice.id, self.bob.id]})
        self.assertRedirects(resp, self.url)
        self.assertEqual(
            set(self.event.attendance.values_list("member_id", flat=True)),
            {self.alice.id, self.bob.id},
        )
        self.assertEqual(Attendance.objects.get(member=self.alice).recorded_by, self.pres)

    def test_unchecking_removes_record(self):
        Attendance.objects.create(event=self.event, member=self.alice, recorded_by=self.pres)
        Attendance.objects.create(event=self.event, member=self.bob, recorded_by=self.pres)
        self.login("pres")
        self.client.post(self.url, {"attendees": [self.alice.id]})
        self.assertEqual(list(self.event.attendance.values_list("member_id", flat=True)), [self.alice.id])

    def test_resaving_does_not_duplicate(self):
        self.login("pres")
        self.client.post(self.url, {"attendees": [self.alice.id]})
        self.client.post(self.url, {"attendees": [self.alice.id]})
        self.assertEqual(self.event.attendance.count(), 1)

    # Acceptance criterion 2: recorded participants are displayed
    def test_page_shows_recorded_participants(self):
        Attendance.objects.create(event=self.event, member=self.alice, recorded_by=self.pres)
        RSVP.objects.create(event=self.event, member=self.bob)
        self.login("pres")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1 of 3 members recorded present")
        self.assertContains(resp, "Recorded by Pres")
        self.assertEqual(resp.context["attended_ids"], {self.alice.id})
        self.assertIn(self.bob.id, resp.context["rsvp_ids"])

    # Permissions
    def test_plain_member_cannot_access(self):
        self.login("alice")
        resp = self.client.post(self.url, {"attendees": [self.alice.id]})
        self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(self.event.attendance.count(), 0)

    def test_officer_in_club_can_manage(self):
        self.make_member("off", "officer", self.club)
        self.login("off")
        self.client.post(self.url, {"attendees": [self.bob.id]})
        self.assertEqual(self.event.attendance.count(), 1)

    def test_officer_outside_club_is_denied(self):
        self.make_member("outsider", "officer")
        self.login("outsider")
        resp = self.client.post(self.url, {"attendees": [self.bob.id]})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.event.attendance.count(), 0)

    def test_other_clubs_president_is_denied(self):
        other = self.make_member("other", "president")
        Club.objects.create(name="Drama", leader=other, status=Club.Status.APPROVED)
        self.login("other")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_admin_can_manage_any_event(self):
        self.make_member("boss", "admin")
        self.login("boss")
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_cannot_mark_non_club_member_present(self):
        stranger = self.make_member("stranger", "member")
        self.login("pres")
        resp = self.client.post(self.url, {"attendees": [stranger.id]})
        self.assertEqual(resp.status_code, 200)  # form re-rendered with an error
        self.assertEqual(self.event.attendance.count(), 0)

    def test_calendar_shows_attendance_link_only_to_managers(self):
        local = timezone.localtime(self.event.date)
        cal = reverse("calendar") + f"?year={local.year}&month={local.month}"
        self.login("pres")
        self.assertIn(self.event.id, self.client.get(cal).context["attendance_ids"])
        self.client.logout()
        self.login("alice")
        self.assertEqual(self.client.get(cal).context["attendance_ids"], set())


class RSVPLockTests(TestCase):
    def setUp(self):
        pres_user = User.objects.create_user("pres", password="x")
        self.pres = Member.objects.create(user=pres_user, first_name="P", last_name="R",
                                          email="pres@example.com", role="president")
        self.club = Club.objects.create(name="Chess", leader=self.pres, status=Club.Status.APPROVED)
        user = User.objects.create_user("alice", password="x")
        self.alice = Member.objects.create(user=user, first_name="Alice", last_name="T",
                                           email="alice@example.com", role="member")
        self.club.members.add(self.pres, self.alice)
        self.client.login(username="alice", password="x")

    def make_event(self, hours_from_now):
        return Event.objects.create(title="E", club=self.club, created_by=self.pres,
                                    date=timezone.now() + timedelta(hours=hours_from_now))

    def test_can_rsvp_and_cancel_before_start(self):
        event = self.make_event(24)
        url = reverse("rsvp_toggle", args=[event.pk])
        self.client.post(url)
        self.assertTrue(RSVP.objects.filter(event=event, member=self.alice).exists())
        self.client.post(url)
        self.assertFalse(RSVP.objects.filter(event=event, member=self.alice).exists())

    def test_cannot_cancel_after_start(self):
        event = self.make_event(-1)
        RSVP.objects.create(event=event, member=self.alice)
        self.client.post(reverse("rsvp_toggle", args=[event.pk]))
        self.assertTrue(RSVP.objects.filter(event=event, member=self.alice).exists())

    def test_cannot_rsvp_after_start(self):
        event = self.make_event(-1)
        self.client.post(reverse("rsvp_toggle", args=[event.pk]))
        self.assertFalse(RSVP.objects.filter(event=event).exists())

    def test_calendar_marks_started_events(self):
        past, future = self.make_event(-1), self.make_event(1)
        local = timezone.localtime(past.date)
        resp = self.client.get(reverse("calendar") + f"?year={local.year}&month={local.month}")
        self.assertIn(past.id, resp.context["started_ids"])
        self.assertNotIn(future.id, resp.context["started_ids"])
