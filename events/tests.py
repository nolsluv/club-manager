
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.forms import DT_FORMAT, EventForm
from events.models import RSVP, Event
from events.views import check_and_send_event_reminders
from members.models import Club, Member, Notification


# ----------------------------------------------------------------- helpers
def make_member(username, role="member"):
    email = f"{username}@example.com"
    user = User.objects.create_user(username, email=email, password="pw12345!")
    return Member.objects.create(
        user=user, first_name=username.title(), last_name="Test",
        email=email, role=role,
    )


def make_club(name, leader):
    club = Club.objects.create(name=name, leader=leader, status=Club.Status.APPROVED)
    club.members.add(leader)
    return club


def fmt(dt):
    """Format a datetime the way the datetime-local input submits it."""
    return timezone.localtime(dt).strftime(DT_FORMAT)


def messages_of(resp):
    return [m.message for m in get_messages(resp.wsgi_request)]


def calendar_url():
    return reverse("calendar")


def create_url():
    return reverse("event_create")


def edit_url(event):
    return reverse("event_edit", args=[event.pk])


def delete_url(event):
    return reverse("event_delete", args=[event.pk])


def rsvp_url(event):
    return reverse("rsvp_toggle", args=[event.pk])


class EventTestBase(TestCase):
    def setUp(self):
        self.pres = make_member("pres", "president")
        self.other_pres = make_member("otherpres", "president")
        self.admin = make_member("admin1", "admin")      # belongs to NO club
        self.plain = make_member("plain", "member")
        self.outsider = make_member("outsider", "member")

        self.club = make_club("Chess", self.pres)
        self.other_club = make_club("Robotics", self.other_pres)
        self.club.members.add(self.plain)

    def login(self, member):
        self.client.force_login(member.user)

    def make_event(self, club=None, **kw):
        defaults = dict(
            title="Event",
            club=club or self.club,
            created_by=self.pres,
            date=(timezone.now() + timedelta(days=7)).replace(second=0, microsecond=0),
        )
        defaults.update(kw)
        return Event.objects.create(**defaults)

    def payload(self, **overrides):
        data = {
            "club": self.club.id,
            "title": "Chess Night",
            "description": "",
            "date": fmt(timezone.now() + timedelta(days=5)),
            "end_date": "",
            "location": "",
            "category": "meeting",
            "contact_email": "",
            "capacity": "",
        }
        data.update(overrides)
        return data


# ------------------------------------------------------------------ models
class EventModelTests(EventTestBase):
    def test_str_is_title(self):
        self.assertEqual(str(self.make_event(title="Bake Sale")), "Bake Sale")

    def test_defaults(self):
        e = self.make_event()
        self.assertEqual(e.category, "other")
        self.assertFalse(e.reminder_sent)
        self.assertIsNone(e.capacity)

    def test_deleting_club_deletes_events(self):
        self.make_event()
        self.club.delete()
        self.assertEqual(Event.objects.count(), 0)

    def test_deleting_creator_keeps_event(self):
        e = self.make_event()
        self.pres.delete()
        e.refresh_from_db()
        self.assertIsNone(e.created_by)

    def test_rsvp_unique_per_member_per_event(self):
        e = self.make_event()
        RSVP.objects.create(event=e, member=self.plain)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RSVP.objects.create(event=e, member=self.plain)

    def test_rsvp_str(self):
        e = self.make_event(title="Bake Sale")
        self.assertEqual(str(RSVP.objects.create(event=e, member=self.plain)),
                         "Plain Test -> Bake Sale")

    def test_deleting_event_deletes_rsvps(self):
        e = self.make_event()
        RSVP.objects.create(event=e, member=self.plain)
        e.delete()
        self.assertEqual(RSVP.objects.count(), 0)


# -------------------------------------------------------------------- form
class EventFormTests(EventTestBase):
    def form(self, user=None, **overrides):
        return EventForm(self.payload(**overrides), user=user or self.pres.user)

    def test_valid(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)

    def test_club_required(self):
        form = self.form(club="")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["club"], ["Please select a club to host this event."])

    def test_club_choices_limited_to_users_clubs(self):
        qs = EventForm(user=self.pres.user).fields["club"].queryset
        self.assertIn(self.club, qs)
        self.assertNotIn(self.other_club, qs)

    def test_cannot_post_a_club_you_do_not_belong_to(self):
        form = self.form(club=self.other_club.id)
        self.assertFalse(form.is_valid())
        self.assertIn("club", form.errors)

    def test_no_user_means_no_clubs(self):
        form = EventForm(self.payload())
        self.assertFalse(form.is_valid())
        self.assertIn("club", form.errors)

    def test_user_without_member_profile_has_no_clubs(self):
        ghost = User.objects.create_user("ghost", password="x")
        self.assertEqual(EventForm(user=ghost).fields["club"].queryset.count(), 0)

    def test_end_before_start_rejected(self):
        start = timezone.now() + timedelta(days=5)
        form = self.form(date=fmt(start), end_date=fmt(start - timedelta(hours=1)))
        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)

    def test_end_after_start_ok(self):
        start = timezone.now() + timedelta(days=5)
        form = self.form(date=fmt(start), end_date=fmt(start + timedelta(hours=2)))
        self.assertTrue(form.is_valid(), form.errors)

    def test_end_date_optional(self):
        self.assertTrue(self.form(end_date="").is_valid())

    def test_bad_datetime_format_rejected(self):
        form = self.form(date="05/12/2026 3pm")
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)

    def test_bad_contact_email_rejected(self):
        form = self.form(contact_email="nope")
        self.assertFalse(form.is_valid())
        self.assertIn("contact_email", form.errors)

    def test_negative_capacity_rejected(self):
        form = self.form(capacity="-3")
        self.assertFalse(form.is_valid())
        self.assertIn("capacity", form.errors)

    def test_active_club_sets_initial_on_unbound_form(self):
        form = EventForm(user=self.pres.user, active_club=self.club.id)
        self.assertEqual(form.fields["club"].initial, self.club.id)

    def test_active_club_accepts_club_object(self):
        form = EventForm(user=self.pres.user, active_club=self.club)
        self.assertEqual(form.fields["club"].initial, self.club.pk)


# --------------------------------------------------------------- reminders
class ReminderTests(EventTestBase):
    def test_reminder_sent_once(self):
        self.make_event(date=timezone.now() + timedelta(hours=3))
        self.assertEqual(check_and_send_event_reminders(), 1)
        self.assertEqual(check_and_send_event_reminders(), 0)
        self.assertEqual(
            Notification.objects.filter(notification_type="reminder").count(), 1
        )

    def test_far_event_ignored(self):
        self.make_event(date=timezone.now() + timedelta(days=3))
        self.assertEqual(check_and_send_event_reminders(), 0)

    def test_past_event_ignored(self):
        self.make_event(date=timezone.now() - timedelta(hours=1))
        self.assertEqual(check_and_send_event_reminders(), 0)

    def test_event_without_club_ignored(self):
        Event.objects.create(title="Orphan", club=None, created_by=self.pres,
                             date=timezone.now() + timedelta(hours=3))
        self.assertEqual(check_and_send_event_reminders(), 0)

    def test_event_just_inside_24h_window_is_sent(self):
        self.make_event(date=timezone.now() + timedelta(hours=23, minutes=50))
        self.assertEqual(check_and_send_event_reminders(), 1)

    def test_notification_content(self):
        self.make_event(title="Soon", date=timezone.now() + timedelta(hours=3))
        check_and_send_event_reminders()
        n = Notification.objects.get(notification_type="reminder")
        self.assertEqual(n.club, self.club)
        self.assertEqual(n.sender, self.pres)
        self.assertIn("Soon", n.message)
        self.assertEqual(n.target_url, calendar_url())

    def test_event_flagged_after_reminder(self):
        e = self.make_event(date=timezone.now() + timedelta(hours=3))
        check_and_send_event_reminders()
        e.refresh_from_db()
        self.assertTrue(e.reminder_sent)

    def test_multiple_events_counted(self):
        for i in range(3):
            self.make_event(title=f"E{i}", date=timezone.now() + timedelta(hours=2 + i))
        self.assertEqual(check_and_send_event_reminders(), 3)


# ---------------------------------------------------------------- calendar
class CalendarViewTests(EventTestBase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.mid_month = timezone.make_aware(
            datetime(today.year, today.month, 15, 12, 0)
        )

    @staticmethod
    def all_events(resp):
        return [e for week in resp.context["grid"] for cell in week
                for e in cell["events"]]

    def test_login_required(self):
        resp = self.client.get(calendar_url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url.lower())

    def test_renders_with_template(self):
        self.login(self.plain)
        resp = self.client.get(calendar_url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "calendar.html")

    def test_grid_is_full_weeks_of_seven(self):
        self.login(self.plain)
        grid = self.client.get(calendar_url()).context["grid"]
        self.assertTrue(4 <= len(grid) <= 6)
        for week in grid:
            self.assertEqual(len(week), 7)

    def test_week_starts_on_sunday(self):
        self.login(self.plain)
        grid = self.client.get(calendar_url()).context["grid"]
        self.assertEqual(grid[0][0]["date"].weekday(), 6)

    def test_month_and_year_params(self):
        self.login(self.plain)
        resp = self.client.get(calendar_url(), {"year": 2030, "month": 2})
        self.assertEqual(resp.context["month_label"], "February 2030")
        self.assertEqual((resp.context["year"], resp.context["month"]), (2030, 2))

    def test_prev_and_next_month(self):
        self.login(self.plain)
        resp = self.client.get(calendar_url(), {"year": 2030, "month": 1})
        self.assertEqual(resp.context["prev_m"].isoformat(), "2029-12-01")
        self.assertEqual(resp.context["next_m"].isoformat(), "2030-02-01")

    def test_garbage_month_falls_back_to_current(self):
        self.login(self.plain)
        for params in ({"month": "abc"}, {"month": 13}, {"year": "x"}, {"month": 0}):
            resp = self.client.get(calendar_url(), params)
            self.assertEqual(resp.status_code, 200, params)
            self.assertEqual(resp.context["month"], timezone.localdate().month, params)

    def test_member_sees_events_from_their_clubs_only(self):
        mine = self.make_event(title="Mine", date=self.mid_month)
        self.make_event(title="Theirs", club=self.other_club, date=self.mid_month)
        self.login(self.plain)
        self.assertEqual(self.all_events(self.client.get(calendar_url())), [mine])

    def test_unapproved_club_events_hidden_without_active_club(self):
        self.club.status = Club.Status.PENDING
        self.club.save()
        self.make_event(date=self.mid_month)
        self.login(self.plain)
        self.assertEqual(self.all_events(self.client.get(calendar_url())), [])

    def test_club_param_filters_to_one_club(self):
        self.other_club.members.add(self.plain)
        a = self.make_event(title="A", date=self.mid_month)
        self.make_event(title="B", club=self.other_club, date=self.mid_month)
        self.login(self.plain)
        resp = self.client.get(calendar_url(), {"club": self.club.id})
        self.assertEqual(self.all_events(resp), [a])
        self.assertEqual(resp.context["active_club_id"], self.club.id)

    def test_garbage_club_param_does_not_crash(self):
        self.login(self.plain)
        resp = self.client.get(calendar_url(), {"club": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context["active_club_id"])

    def test_user_without_member_profile_sees_nothing(self):
        self.make_event(date=self.mid_month)
        ghost = User.objects.create_user("ghost", password="x")
        self.client.force_login(ghost)
        resp = self.client.get(calendar_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.all_events(resp), [])
        self.assertFalse(resp.context["can_edit"])

    def test_events_from_other_months_not_shown(self):
        far = self.mid_month + timedelta(days=90)
        self.make_event(date=far)
        self.login(self.plain)
        self.assertEqual(self.all_events(self.client.get(calendar_url())), [])

    def test_can_edit_flag_by_role(self):
        for member, expected in ((self.pres, True), (self.admin, True),
                                 (self.plain, False)):
            self.login(member)
            self.assertEqual(self.client.get(calendar_url()).context["can_edit"],
                             expected, member.role)

    def test_is_admin_flag(self):
        self.login(self.admin)
        self.assertTrue(self.client.get(calendar_url()).context["is_admin"])
        self.login(self.pres)
        self.assertFalse(self.client.get(calendar_url()).context["is_admin"])

    def test_rsvped_ids_contains_my_rsvps_only(self):
        mine = self.make_event(title="Going", date=self.mid_month)
        other = self.make_event(title="Not going", date=self.mid_month)
        RSVP.objects.create(event=mine, member=self.plain)
        RSVP.objects.create(event=other, member=self.pres)
        self.login(self.plain)
        self.assertEqual(self.client.get(calendar_url()).context["rsvped_ids"],
                         {mine.id})

    def test_viewing_calendar_triggers_reminders(self):
        self.make_event(date=timezone.now() + timedelta(hours=2))
        self.login(self.plain)
        self.client.get(calendar_url())
        self.assertEqual(
            Notification.objects.filter(notification_type="reminder").count(), 1)


# ------------------------------------------------------------------ create
class EventCreateTests(EventTestBase):
    def test_anonymous_blocked(self):
        resp = self.client.post(create_url(), self.payload())
        self.assertIn(resp.status_code, (302, 403))
        self.assertEqual(Event.objects.count(), 0)

    def test_plain_member_blocked(self):
        self.login(self.plain)
        resp = self.client.post(create_url(), self.payload())
        self.assertIn(resp.status_code, (302, 403))
        self.assertEqual(Event.objects.count(), 0)

    def test_president_sees_form(self):
        self.login(self.pres)
        resp = self.client.get(create_url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "event_form.html")

    def test_president_creates_event(self):
        self.login(self.pres)
        resp = self.client.post(create_url(), self.payload())
        self.assertRedirects(resp, calendar_url())
        e = Event.objects.get()
        self.assertEqual((e.club, e.created_by, e.title),
                         (self.club, self.pres, "Chess Night"))

    def test_success_message(self):
        self.login(self.pres)
        resp = self.client.post(create_url(), self.payload())
        self.assertIn("Event added successfully.", messages_of(resp))

    def test_creating_notifies_the_club(self):
        self.login(self.pres)
        self.client.post(create_url(), self.payload())
        n = Notification.objects.get(notification_type="event")
        self.assertEqual(n.club, self.club)
        self.assertEqual(n.sender, self.pres)
        self.assertIn("Chess Night", n.message)
        self.assertEqual(n.target_url, calendar_url())

    def test_cannot_create_for_club_you_are_not_in(self):
        self.login(self.pres)
        resp = self.client.post(create_url(), self.payload(club=self.other_club.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Event.objects.count(), 0)

    def test_invalid_form_rerenders(self):
        self.login(self.pres)
        resp = self.client.post(create_url(), self.payload(title=""))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_end_before_start_rejected(self):
        self.login(self.pres)
        start = timezone.now() + timedelta(days=5)
        resp = self.client.post(create_url(), self.payload(
            date=fmt(start), end_date=fmt(start - timedelta(hours=2))))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Event.objects.count(), 0)

    def test_admin_who_is_a_club_member_can_create(self):
        self.club.members.add(self.admin)
        self.login(self.admin)
        self.client.post(create_url(), self.payload())
        self.assertEqual(Event.objects.get().created_by, self.admin)


# -------------------------------------------------------------------- edit
class EventEditTests(EventTestBase):
    def setUp(self):
        super().setUp()
        self.event = self.make_event(title="Old title")

    def edit_payload(self, **overrides):
        base = self.payload(title="Old title", date=fmt(self.event.date))
        base.update(overrides)
        return base

    def test_plain_member_blocked(self):
        self.login(self.plain)
        resp = self.client.post(edit_url(self.event), self.edit_payload(title="Hacked"))
        self.assertIn(resp.status_code, (302, 403))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Old title")

    def test_creator_sees_form_prefilled(self):
        self.login(self.pres)
        resp = self.client.get(edit_url(self.event))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["form"].instance, self.event)

    def test_creator_can_edit(self):
        self.login(self.pres)
        resp = self.client.post(edit_url(self.event), self.edit_payload(title="New title"))
        self.assertRedirects(resp, calendar_url())
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "New title")
        self.assertIn("Your event has been successfully updated.", messages_of(resp))

    def test_edit_notifies_club_and_marks_read_for_editor(self):
        self.login(self.pres)
        self.client.post(edit_url(self.event), self.edit_payload(title="New title"))
        n = Notification.objects.get(club=self.club, notification_type="event")
        self.assertIn("Updated event: New title", n.message)
        self.assertIn("Title changed", n.message)
        self.assertIn(self.pres, n.read_by.all())

    def test_president_of_other_club_gets_403(self):
        self.login(self.other_pres)
        resp = self.client.post(edit_url(self.event), self.edit_payload(title="Hacked"))
        self.assertEqual(resp.status_code, 403)

    def test_second_president_in_same_club_cannot_edit_others_event(self):
        """Documents current design: only creator or admin may edit."""
        self.club.members.add(self.other_pres)
        self.login(self.other_pres)
        resp = self.client.post(edit_url(self.event), self.edit_payload(title="Hacked"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_in_the_club_can_edit(self):
        self.club.members.add(self.admin)
        self.login(self.admin)
        self.client.post(edit_url(self.event), self.edit_payload(title="By admin"))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "By admin")

    def test_admin_NOT_in_the_club_can_edit(self):
        self.login(self.admin)
        resp = self.client.post(edit_url(self.event), self.edit_payload(title="By admin"))
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "By admin")

    def test_changing_date_resets_reminder(self):
        self.event.reminder_sent = True
        self.event.save()
        self.login(self.pres)
        new_date = self.event.date + timedelta(days=1)
        self.client.post(edit_url(self.event), self.edit_payload(date=fmt(new_date)))
        self.event.refresh_from_db()
        self.assertFalse(self.event.reminder_sent)

    def test_keeping_date_keeps_reminder_flag(self):
        self.event.reminder_sent = True
        self.event.save()
        self.login(self.pres)
        self.client.post(edit_url(self.event), self.edit_payload(title="Only title"))
        self.event.refresh_from_db()
        self.assertTrue(self.event.reminder_sent)

    def test_moving_to_another_club_notifies_both(self):
        self.other_club.members.add(self.pres)
        self.login(self.pres)
        self.client.post(edit_url(self.event),
                         self.edit_payload(club=self.other_club.id))
        self.event.refresh_from_db()
        self.assertEqual(self.event.club, self.other_club)
        old = Notification.objects.get(club=self.club, notification_type="cancelation")
        self.assertIn("Robotics", old.message)
        new = Notification.objects.get(club=self.other_club, notification_type="event")
        self.assertIn("transferred in", new.message)

    def test_invalid_edit_rerenders_and_changes_nothing(self):
        self.login(self.pres)
        resp = self.client.post(edit_url(self.event), self.edit_payload(title=""))
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Old title")

    def test_missing_event_404(self):
        self.login(self.pres)
        self.assertEqual(self.client.get(reverse("event_edit", args=[9999])).status_code, 404)


# ------------------------------------------------------------------ delete
class EventDeleteTests(EventTestBase):
    def setUp(self):
        super().setUp()
        self.event = self.make_event(title="Doomed")

    def test_creator_can_delete_via_post(self):
        self.login(self.pres)
        resp = self.client.post(delete_url(self.event))
        self.assertRedirects(resp, calendar_url())
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())
        self.assertIn("Your event has been successfully deleted.", messages_of(resp))

    def test_get_not_allowed(self):
        self.login(self.pres)
        self.assertEqual(self.client.get(delete_url(self.event)).status_code, 405)
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_delete_notifies_club(self):
        self.login(self.pres)
        self.client.post(delete_url(self.event))
        n = Notification.objects.get(notification_type="cancelation")
        self.assertEqual(n.club, self.club)
        self.assertIn("Doomed", n.message)

    def test_delete_cascades_rsvps(self):
        RSVP.objects.create(event=self.event, member=self.plain)
        self.login(self.pres)
        self.client.post(delete_url(self.event))
        self.assertEqual(RSVP.objects.count(), 0)

    def test_other_president_gets_403(self):
        self.login(self.other_pres)
        self.assertEqual(self.client.post(delete_url(self.event)).status_code, 403)
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_plain_member_blocked(self):
        self.login(self.plain)
        resp = self.client.post(delete_url(self.event))
        self.assertIn(resp.status_code, (302, 403))
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_admin_can_delete_any_event(self):
        self.login(self.admin)
        self.client.post(delete_url(self.event))
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())

    def test_missing_event_404(self):
        self.login(self.pres)
        self.assertEqual(self.client.post(reverse("event_delete", args=[9999])).status_code, 404)


# -------------------------------------------------------------------- RSVP
class RSVPTests(EventTestBase):
    def setUp(self):
        super().setUp()
        self.event = self.make_event(title="Party")

    def test_anonymous_redirected(self):
        resp = self.client.post(rsvp_url(self.event))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url.lower())

    def test_get_not_allowed(self):
        self.login(self.plain)
        self.assertEqual(self.client.get(rsvp_url(self.event)).status_code, 405)

    def test_member_can_rsvp(self):
        self.login(self.plain)
        resp = self.client.post(rsvp_url(self.event))
        self.assertTrue(RSVP.objects.filter(event=self.event, member=self.plain).exists())
        self.assertIn("You're going to 'Party'.", messages_of(resp))

    def test_second_post_cancels(self):
        self.login(self.plain)
        self.client.post(rsvp_url(self.event))
        resp = self.client.post(rsvp_url(self.event))
        self.assertFalse(RSVP.objects.filter(event=self.event, member=self.plain).exists())
        self.assertIn("Your RSVP to 'Party' was cancelled.", messages_of(resp))

    def test_non_club_member_gets_403(self):
        self.login(self.outsider)
        self.assertEqual(self.client.post(rsvp_url(self.event)).status_code, 403)
        self.assertEqual(RSVP.objects.count(), 0)

    def test_user_without_member_profile_gets_403(self):
        ghost = User.objects.create_user("ghost", password="x")
        self.client.force_login(ghost)
        self.assertEqual(self.client.post(rsvp_url(self.event)).status_code, 403)

    def test_event_without_club_gets_403(self):
        orphan = Event.objects.create(title="Orphan", club=None,
                                      date=timezone.now() + timedelta(days=2))
        self.login(self.plain)
        self.assertEqual(self.client.post(rsvp_url(orphan)).status_code, 403)

    def test_past_event_rejected(self):
        past = self.make_event(title="Over", date=timezone.now() - timedelta(days=1))
        self.login(self.plain)
        resp = self.client.post(rsvp_url(past))
        self.assertEqual(RSVP.objects.count(), 0)
        self.assertIn("This event has already happened.", messages_of(resp))

    def test_full_event_rejected(self):
        self.event.capacity = 1
        self.event.save()
        RSVP.objects.create(event=self.event, member=self.pres)
        self.login(self.plain)
        resp = self.client.post(rsvp_url(self.event))
        self.assertFalse(RSVP.objects.filter(member=self.plain).exists())
        self.assertIn("Sorry, this event is full.", messages_of(resp))

    def test_can_cancel_even_when_full(self):
        self.event.capacity = 1
        self.event.save()
        RSVP.objects.create(event=self.event, member=self.plain)
        self.login(self.plain)
        self.client.post(rsvp_url(self.event))
        self.assertEqual(RSVP.objects.count(), 0)

    def test_unlimited_capacity_allows_many(self):
        self.club.members.add(self.outsider)
        for m in (self.plain, self.outsider, self.pres):
            self.login(m)
            self.client.post(rsvp_url(self.event))
        self.assertEqual(self.event.rsvps.count(), 3)

    def test_redirects_back_to_referer(self):
        self.login(self.plain)
        resp = self.client.post(rsvp_url(self.event), HTTP_REFERER="/somewhere/")
        self.assertRedirects(resp, "/somewhere/", fetch_redirect_response=False)

    def test_redirects_to_calendar_without_referer(self):
        self.login(self.plain)
        resp = self.client.post(rsvp_url(self.event))
        self.assertRedirects(resp, calendar_url())

    def test_missing_event_404(self):
        self.login(self.plain)
        self.assertEqual(self.client.post(reverse("rsvp_toggle", args=[9999])).status_code, 404)