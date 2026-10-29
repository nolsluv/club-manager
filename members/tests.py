
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
 
from members.forms import (
    ClubAppearanceForm,
    ClubRequestForm,
    NotificationForm,
    RegisterForm,
)
from members.models import Club, Member, MembershipRequest, Notification
 
 
def make_member(username, role="member"):
    email = f"{username}@example.com"
    user = User.objects.create_user(username, email=email, password="pw12345!")
    return Member.objects.create(
        user=user,
        first_name=username.title(),
        last_name="Test",
        email=email,
        role=role,
    )
 
 
# ------------------------------------------------------------------ Member
class MemberModelTests(TestCase):
    def test_str_is_full_name(self):
        m = make_member("alice")
        self.assertEqual(str(m), "Alice Test")
 
    def test_defaults(self):
        m = make_member("bob")
        self.assertEqual(m.role, "member")
        self.assertTrue(m.is_active)
        self.assertIsNotNone(m.date_joined)
 
    def test_email_must_be_unique(self):
        make_member("carol")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Member.objects.create(
                first_name="Dup", last_name="Email", email="carol@example.com"
            )
 
    def test_user_link_is_one_to_one(self):
        m = make_member("dave")
        self.assertEqual(m.user.member, m)
 
    def test_member_without_user_is_allowed(self):
        m = Member.objects.create(
            first_name="Old", last_name="Row", email="old@example.com"
        )
        self.assertIsNone(m.user)
 
    def test_deleting_user_deletes_member(self):
        m = make_member("erin")
        m.user.delete()
        self.assertFalse(Member.objects.filter(pk=m.pk).exists())
 
 
# -------------------------------------------------------------------- Club
class ClubModelTests(TestCase):
    def setUp(self):
        self.leader = make_member("lead", "president")
 
    def test_defaults(self):
        club = Club.objects.create(name="Chess", leader=self.leader)
        self.assertEqual(club.status, Club.Status.PENDING)
        self.assertEqual(club.icon, "stars")
        self.assertEqual(club.theme_color, "copper")
        self.assertIsNone(club.reviewed_by)
        self.assertIsNone(club.reviewed_at)
 
    def test_str_is_name(self):
        self.assertEqual(str(Club.objects.create(name="Chess")), "Chess")
 
    def test_name_must_be_unique(self):
        Club.objects.create(name="Chess")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Club.objects.create(name="Chess")
 
    def test_members_related_name(self):
        club = Club.objects.create(name="Chess", leader=self.leader)
        club.members.add(self.leader)
        self.assertIn(club, self.leader.clubs.all())
 
    def test_leader_related_name(self):
        club = Club.objects.create(name="Chess", leader=self.leader)
        self.assertIn(club, self.leader.clubs_led.all())
 
    def test_deleting_leader_keeps_club(self):
        club = Club.objects.create(name="Chess", leader=self.leader)
        self.leader.delete()
        club.refresh_from_db()
        self.assertIsNone(club.leader)
 
 
# ------------------------------------------------------------ Notification
class NotificationModelTests(TestCase):
    def setUp(self):
        self.sender = make_member("sender", "president")
        self.club = Club.objects.create(
            name="Chess", leader=self.sender, status=Club.Status.APPROVED
        )
 
    def make(self, message="Hello", **kw):
        return Notification.objects.create(
            club=self.club, sender=self.sender, message=message, **kw
        )
 
    def test_defaults(self):
        n = self.make()
        self.assertEqual(n.notification_type, "announcement")
        self.assertEqual(n.target_url, "")
 
    def test_str_truncates_message_to_40_chars(self):
        n = self.make("x" * 100)
        self.assertEqual(str(n), f"Chess: {'x' * 40}")
 
    def test_newest_first_ordering(self):
        first = self.make("first")
        second = self.make("second")
        self.assertEqual(list(Notification.objects.all()), [second, first])
 
    def test_read_and_hidden_are_tracked_per_member(self):
        reader = make_member("reader")
        n = self.make()
        n.read_by.add(reader)
        self.assertIn(reader, n.read_by.all())
        self.assertNotIn(reader, n.hidden_by.all())
 
    def test_deleting_club_deletes_notifications(self):
        self.make()
        self.club.delete()
        self.assertEqual(Notification.objects.count(), 0)
 
    def test_deleting_sender_keeps_notification(self):
        n = self.make()
        self.sender.delete()
        n.refresh_from_db()
        self.assertIsNone(n.sender)
 
 
# ------------------------------------------------------ MembershipRequest
class MembershipRequestModelTests(TestCase):
    def setUp(self):
        self.leader = make_member("lead", "president")
        self.joiner = make_member("joiner")
        self.club = Club.objects.create(
            name="Chess", leader=self.leader, status=Club.Status.APPROVED
        )
 
    def test_default_status_is_pending(self):
        req = MembershipRequest.objects.create(member=self.joiner, club=self.club)
        self.assertEqual(req.status, MembershipRequest.Status.PENDING)
 
    def test_str(self):
        req = MembershipRequest.objects.create(member=self.joiner, club=self.club)
        self.assertEqual(str(req), "Joiner Test -> Chess (pending)")
 
    def test_only_one_pending_request_per_member_per_club(self):
        MembershipRequest.objects.create(member=self.joiner, club=self.club)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MembershipRequest.objects.create(member=self.joiner, club=self.club)
 
    def test_can_re_request_after_rejection(self):
        old = MembershipRequest.objects.create(member=self.joiner, club=self.club)
        old.status = MembershipRequest.Status.REJECTED
        old.save()
        new = MembershipRequest.objects.create(member=self.joiner, club=self.club)
        self.assertEqual(new.status, MembershipRequest.Status.PENDING)
 
    def test_same_member_can_have_pending_requests_to_different_clubs(self):
        other = Club.objects.create(name="Robotics", status=Club.Status.APPROVED)
        MembershipRequest.objects.create(member=self.joiner, club=self.club)
        MembershipRequest.objects.create(member=self.joiner, club=other)
        self.assertEqual(self.joiner.membership_requests.count(), 2)
 
    def test_deleting_club_deletes_requests(self):
        MembershipRequest.objects.create(member=self.joiner, club=self.club)
        self.club.delete()
        self.assertEqual(MembershipRequest.objects.count(), 0)
 
 
# ------------------------------------------------------------------- forms
class RegisterFormTests(TestCase):
    def payload(self, **overrides):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "S0me-long-pass!",
            "password2": "S0me-long-pass!",
        }
        data.update(overrides)
        return data
 
    def test_valid(self):
        form = RegisterForm(self.payload())
        self.assertTrue(form.is_valid(), form.errors)
 
    def test_email_required(self):
        form = RegisterForm(self.payload(email=""))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
 
    def test_invalid_email_rejected(self):
        form = RegisterForm(self.payload(email="not-an-email"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
 
    def test_passwords_must_match(self):
        form = RegisterForm(self.payload(password2="different-pass-1!"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)
 
    def test_duplicate_username_rejected(self):
        User.objects.create_user("newuser", password="x")
        form = RegisterForm(self.payload())
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)
 
    def test_save_stores_email_on_user(self):
        form = RegisterForm(self.payload())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.username, "newuser")
        self.assertTrue(user.check_password("S0me-long-pass!"))
        # NOTE: ModelForm saves 'email' because it's in Meta.fields.
        self.assertEqual(user.email, "new@example.com")
 
 
class ClubRequestFormTests(TestCase):
    def test_only_expected_fields(self):
        self.assertEqual(
            list(ClubRequestForm().fields),
            ["name", "short_description", "description"],
        )
 
    def test_name_required(self):
        form = ClubRequestForm({"name": "", "short_description": "x"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
 
    def test_description_fields_optional(self):
        form = ClubRequestForm({"name": "Chess"})
        self.assertTrue(form.is_valid(), form.errors)
 
    def test_duplicate_name_rejected(self):
        Club.objects.create(name="Chess")
        form = ClubRequestForm({"name": "Chess"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
 
    def test_short_description_max_length(self):
        form = ClubRequestForm({"name": "Chess", "short_description": "x" * 201})
        self.assertFalse(form.is_valid())
        self.assertIn("short_description", form.errors)
 
    def test_cannot_set_status_through_form(self):
        form = ClubRequestForm({"name": "Chess", "status": "approved"})
        self.assertTrue(form.is_valid(), form.errors)
        club = form.save()
        self.assertEqual(club.status, Club.Status.PENDING)
 
 
class NotificationFormTests(TestCase):
    def test_message_required(self):
        form = NotificationForm({"message": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
 
    def test_valid_message(self):
        self.assertTrue(NotificationForm({"message": "Meeting at 5"}).is_valid())
 
    def test_message_max_length_300(self):
        self.assertTrue(NotificationForm({"message": "x" * 300}).is_valid())
        form = NotificationForm({"message": "x" * 301})
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
 
    def test_only_message_field_exposed(self):
        self.assertEqual(list(NotificationForm().fields), ["message"])
 
 
class ClubAppearanceFormTests(TestCase):
    def test_valid_choices(self):
        form = ClubAppearanceForm({"icon": "book", "theme_color": "lake"})
        self.assertTrue(form.is_valid(), form.errors)
 
    def test_invalid_icon_rejected(self):
        form = ClubAppearanceForm({"icon": "bogus", "theme_color": "lake"})
        self.assertFalse(form.is_valid())
        self.assertIn("icon", form.errors)
 
    def test_invalid_color_rejected(self):
        form = ClubAppearanceForm({"icon": "book", "theme_color": "neon"})
        self.assertFalse(form.is_valid())
        self.assertIn("theme_color", form.errors)
 
    def test_saves_to_existing_club(self):
        club = Club.objects.create(name="Chess")
        form = ClubAppearanceForm(
            {"icon": "trophy", "theme_color": "sage"}, instance=club
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        club.refresh_from_db()
        self.assertEqual((club.icon, club.theme_color), ("trophy", "sage"))