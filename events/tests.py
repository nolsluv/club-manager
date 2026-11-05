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


# ---------------------------------------------------------------- public vs club events
# own helpers (distinct names) so this block doesn't depend on other test files' helpers
from django.urls import reverse  # noqa: E402
from events.forms import DT_FORMAT  # noqa: E402
from events.models import RSVP  # noqa: E402


def _vis_member(username, role="member"):
    user = User.objects.create_user(username, password="pw12345!")
    return Member.objects.create(user=user, first_name=username.title(), last_name="Test",
                                 email=f"{username}@example.com", role=role)


def _vis_club(name, leader):
    club = Club.objects.create(name=name, leader=leader, status=Club.Status.APPROVED)
    club.members.add(leader)
    return club


def _vis_fmt(dt):
    return timezone.localtime(dt).strftime(DT_FORMAT)


class EventVisibilityTests(TestCase):
    def setUp(self):
        self.pres = _vis_member("vpres", "president")
        self.club = _vis_club("Robotics", self.pres)
        self.insider = _vis_member("insider")
        self.club.members.add(self.insider)
        self.outsider = _vis_member("outsider")
        when = timezone.now() + timedelta(days=1)
        self.club_event = Event.objects.create(title="Members Meeting", club=self.club,
                                               created_by=self.pres, date=when)
        self.public_event = Event.objects.create(title="Open House", club=self.club,
                                                 created_by=self.pres, date=when,
                                                 visibility="public")
        local = timezone.localtime(when)
        self.cal = reverse("calendar") + f"?year={local.year}&month={local.month}"

    def calendar_titles(self, url=None):
        resp = self.client.get(url or self.cal)
        return {e.title for week in resp.context["grid"] for day in week for e in day["events"]}

    def test_default_visibility_is_club(self):
        e = Event.objects.create(title="X", club=self.club, date=timezone.now())
        self.assertEqual(e.visibility, "club")

    def test_outsider_sees_only_public_events(self):
        self.client.force_login(self.outsider.user)
        titles = self.calendar_titles()
        self.assertIn("Open House", titles)
        self.assertNotIn("Members Meeting", titles)

    def test_member_sees_both(self):
        self.client.force_login(self.insider.user)
        self.assertEqual(self.calendar_titles() & {"Open House", "Members Meeting"},
                         {"Open House", "Members Meeting"})

    def test_club_filter_hides_club_events_from_outsiders(self):
        self.client.force_login(self.outsider.user)
        titles = self.calendar_titles(self.cal + f"&club={self.club.id}")
        self.assertEqual(titles, {"Open House"})

    def test_outsider_can_rsvp_to_public_event(self):
        self.client.force_login(self.outsider.user)
        self.client.post(reverse("rsvp_toggle", args=[self.public_event.pk]))
        self.assertTrue(RSVP.objects.filter(event=self.public_event, member=self.outsider).exists())

    def test_outsider_cannot_rsvp_to_club_event(self):
        self.client.force_login(self.outsider.user)
        resp = self.client.post(reverse("rsvp_toggle", args=[self.club_event.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(RSVP.objects.filter(event=self.club_event).exists())

    def test_rsvp_button_flags(self):
        self.client.force_login(self.outsider.user)
        ids = self.client.get(self.cal).context["rsvpable_ids"]
        self.assertIn(self.public_event.id, ids)
        self.assertNotIn(self.club_event.id, ids)

    def test_public_event_roster_includes_outside_rsvps(self):
        RSVP.objects.create(event=self.public_event, member=self.outsider)
        roster = set(self.public_event.attendance_roster())
        self.assertEqual(roster, {self.pres, self.insider, self.outsider})
        # and the leader can mark the outsider present
        self.public_event.date = timezone.now() - timedelta(hours=1)
        self.public_event.save()
        self.client.force_login(self.pres.user)
        url = reverse("event_attendance", args=[self.public_event.pk])
        self.client.post(url, {"attendees": [self.outsider.id]})
        self.assertTrue(self.public_event.attendance.filter(member=self.outsider).exists())

    def test_club_event_roster_is_club_members_only(self):
        RSVP.objects.create(event=self.club_event, member=self.outsider)  # shouldn't happen, but guard anyway
        self.assertEqual(set(self.club_event.attendance_roster()), {self.pres, self.insider})

    def test_visibility_saved_from_form(self):
        self.client.force_login(self.pres.user)
        start = timezone.now() + timedelta(days=2)
        self.client.post(reverse("event_create"), {
            "club": self.club.id, "title": "Bake Sale", "date": _vis_fmt(start),
            "category": "fundraiser", "visibility": "public",
        })
        self.assertEqual(Event.objects.get(title="Bake Sale").visibility, "public")
