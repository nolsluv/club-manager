from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finances.forms import EntryForm
from finances.models import FinancialAccount, FinanceEntry
from members.models import Club, Member

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


def make_club(name, leader):
    club = Club.objects.create(name=name, leader=leader, status=Club.Status.APPROVED)
    club.members.add(leader)
    return club


class FinanceTestBase(TestCase):
    """Two clubs, each with its own president, plus an admin and a plain member."""

    def setUp(self):
        self.pres = make_member("pres", "president")
        self.other_pres = make_member("otherpres", "president")
        self.admin = make_member("admin1", "admin")
        self.plain = make_member("plain", "member")

        self.club = make_club("Chess Club", self.pres)
        self.other_club = make_club("Robotics", self.other_pres)
        self.club.members.add(self.plain)

        self.account = FinancialAccount.objects.create(
            club=self.club, name="Main", opening_balance=Decimal("100.00")
        )
        self.today = timezone.localdate()

    def login(self, member):
        self.client.force_login(member.user)

    def add_entry(self, kind, amount, club=None, account=None, **kw):
        return FinanceEntry.objects.create(
            club=club or self.club,
            account=account,
            kind=kind,
            description=kw.pop("description", "test"),
            amount=Decimal(str(amount)),
            date=kw.pop("date", self.today),
            created_by=self.pres,
            **kw,
        )

    def entry_payload(self, **overrides):
        data = {
            "kind": FinanceEntry.Kind.FUNDRAISER,
            "description": "Bake sale",
            "amount": "50.00",
            "date": self.today.isoformat(),
            "account": self.account.id,
        }
        data.update(overrides)
        return data


# ------------------------------------------------------------------ models
class ModelTests(FinanceTestBase):
    def test_balance_starts_at_opening_balance(self):
        self.assertEqual(self.account.balance(), Decimal("100.00"))

    def test_balance_adds_income_and_subtracts_expenses(self):
        self.add_entry("fundraiser", 40, account=self.account)
        self.add_entry("monthly", 10, account=self.account)
        self.add_entry("expense", 25, account=self.account)
        # 100 + 40 + 10 - 25
        self.assertEqual(self.account.balance(), Decimal("125.00"))

    def test_balance_ignores_entries_on_other_accounts(self):
        other = FinancialAccount.objects.create(club=self.club, name="Savings")
        self.add_entry("fundraiser", 500, account=other)
        self.assertEqual(self.account.balance(), Decimal("100.00"))

    def test_is_expense_property(self):
        self.assertTrue(self.add_entry("expense", 5).is_expense)
        self.assertFalse(self.add_entry("fundraiser", 5).is_expense)
        self.assertFalse(self.add_entry("monthly", 5).is_expense)

    def test_deleting_account_keeps_entries(self):
        entry = self.add_entry("fundraiser", 20, account=self.account)
        self.account.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.account)


# forms
class FormTests(FinanceTestBase):
    def test_amount_must_be_positive(self):
        for bad in ("0", "-5"):
            form = EntryForm(self.entry_payload(amount=bad), club=self.club)
            self.assertFalse(form.is_valid(), bad)
            self.assertIn("amount", form.errors)

    def test_valid_entry_form(self):
        form = EntryForm(self.entry_payload(), club=self.club)
        self.assertTrue(form.is_valid(), form.errors)

    def test_account_choices_limited_to_this_club(self):
        foreign = FinancialAccount.objects.create(club=self.other_club, name="Theirs")
        form = EntryForm(club=self.club)
        qs = form.fields["account"].queryset
        self.assertIn(self.account, qs)
        self.assertNotIn(foreign, qs)

    def test_cannot_submit_another_clubs_account(self):
        foreign = FinancialAccount.objects.create(club=self.other_club, name="Theirs")
        form = EntryForm(self.entry_payload(account=foreign.id), club=self.club)
        self.assertFalse(form.is_valid())
        self.assertIn("account", form.errors)

    def test_account_is_optional(self):
        form = EntryForm(self.entry_payload(account=""), club=self.club)
        self.assertTrue(form.is_valid(), form.errors)


# -------------------------------------------------------------- permissions
class PermissionTests(FinanceTestBase):
    def urls(self):
        return {
            "home": reverse("finance_home", args=[self.club.id]),
            "account_add": reverse("finance_account_add", args=[self.club.id]),
            "entry_add": reverse("finance_entry_add", args=[self.club.id]),
        }

    def test_anonymous_redirected_to_login(self):
        for name, url in self.urls().items():
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn("login", resp.url.lower(), name)

    def test_plain_member_blocked(self):
        self.login(self.plain)
        for name, url in self.urls().items():
            resp = self.client.get(url)
            self.assertNotEqual(resp.status_code, 200, name)

    def test_president_of_other_club_gets_403(self):
        self.login(self.other_pres)
        for name, url in self.urls().items():
            self.assertEqual(self.client.get(url).status_code, 403, name)

    def test_unapproved_club_returns_404(self):
        self.club.status = Club.Status.PENDING
        self.club.save()
        self.login(self.pres)
        resp = self.client.get(reverse("finance_home", args=[self.club.id]))
        self.assertEqual(resp.status_code, 404)

    def test_other_president_cannot_post_entry(self):
        self.login(self.other_pres)
        resp = self.client.post(
            reverse("finance_entry_add", args=[self.club.id]), self.entry_payload()
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(FinanceEntry.objects.count(), 0)

    def test_other_president_cannot_post_account(self):
        self.login(self.other_pres)
        resp = self.client.post(
            reverse("finance_account_add", args=[self.club.id]),
            {"name": "Sneaky", "account_type": "checking", "opening_balance": "0"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(FinancialAccount.objects.filter(name="Sneaky").exists())


# ------------------------------------------------------------------- views
class FinanceHomeViewTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.pres)
        self.url = reverse("finance_home", args=[self.club.id])

    def test_totals_in_context(self):
        self.add_entry("fundraiser", 100)
        self.add_entry("monthly", 50)
        self.add_entry("other", 25)
        self.add_entry("expense", 60)
        ctx = self.client.get(self.url).context
        self.assertEqual(ctx["gross"], Decimal("175.00"))
        self.assertEqual(ctx["spending"], Decimal("60.00"))
        self.assertEqual(ctx["net"], Decimal("115.00"))
        self.assertEqual(ctx["fundraisers"], Decimal("100.00"))
        self.assertEqual(ctx["dues"], Decimal("50.00"))

    def test_empty_club_shows_zeros(self):
        ctx = self.client.get(self.url).context
        self.assertEqual(ctx["gross"], 0)
        self.assertEqual(ctx["spending"], 0)
        self.assertEqual(ctx["net"], 0)

    def test_negative_net(self):
        self.add_entry("expense", 30)
        self.assertEqual(self.client.get(self.url).context["net"], Decimal("-30.00"))

    def test_other_clubs_entries_not_counted_or_listed(self):
        self.add_entry("fundraiser", 999, club=self.other_club, description="LEAK")
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["gross"], 0)
        self.assertNotContains(resp, "LEAK")

    def test_kind_filter_changes_list_but_not_totals(self):
        self.add_entry("fundraiser", 100, description="fr")
        self.add_entry("expense", 40, description="ex")
        resp = self.client.get(self.url, {"kind": "expense"})
        self.assertEqual([e.description for e in resp.context["entries"]], ["ex"])
        self.assertEqual(resp.context["gross"], Decimal("100.00"))
        self.assertEqual(resp.context["spending"], Decimal("40.00"))

    def test_invalid_kind_filter_is_ignored(self):
        self.add_entry("fundraiser", 10)
        resp = self.client.get(self.url, {"kind": "nonsense"})
        self.assertEqual(len(resp.context["entries"]), 1)

    def test_chart_has_six_months_ending_this_month(self):
        chart = self.client.get(self.url).context["chart"]
        self.assertEqual(len(chart), 6)
        self.assertEqual(chart[-1]["label"], self.today.strftime("%b"))

    def test_chart_scales_to_largest_bar(self):
        self.add_entry("fundraiser", 200)
        self.add_entry("expense", 50)
        this_month = self.client.get(self.url).context["chart"][-1]
        self.assertEqual(this_month["income_pct"], 100)
        self.assertEqual(this_month["expense_pct"], 25)

    def test_chart_empty_months_are_zero(self):
        self.add_entry("fundraiser", 10)
        chart = self.client.get(self.url).context["chart"]
        for month in chart[:-1]:
            self.assertEqual(month["income_pct"], 0)
            self.assertEqual(month["expense_pct"], 0)

    def test_accounts_listed(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "Main")


class AccountAddTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.pres)
        self.url = reverse("finance_account_add", args=[self.club.id])

    def test_creates_account_for_this_club(self):
        resp = self.client.post(
            self.url,
            {
                "name": "Savings",
                "account_type": "savings",
                "institution": "UWM",
                "opening_balance": "250.00",
                "is_active": "on",
            },
        )
        self.assertRedirects(resp, reverse("finance_home", args=[self.club.id]))
        acct = FinancialAccount.objects.get(name="Savings")
        self.assertEqual(acct.club, self.club)
        self.assertEqual(acct.opening_balance, Decimal("250.00"))
        self.assertTrue(acct.is_active)

    def test_missing_name_rerenders_form(self):
        resp = self.client.post(
            self.url, {"name": "", "account_type": "checking", "opening_balance": "0"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FinancialAccount.objects.filter(club=self.club).count(), 1)

    def test_unchecked_active_creates_closed_account(self):
        self.client.post(
            self.url,
            {"name": "Old", "account_type": "cash", "opening_balance": "0"},
        )
        self.assertFalse(FinancialAccount.objects.get(name="Old").is_active)


class EntryAddTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.pres)
        self.url = reverse("finance_entry_add", args=[self.club.id])

    def test_creates_entry_with_club_and_creator(self):
        resp = self.client.post(self.url, self.entry_payload())
        self.assertRedirects(resp, reverse("finance_home", args=[self.club.id]))
        entry = FinanceEntry.objects.get()
        self.assertEqual(entry.club, self.club)
        self.assertEqual(entry.created_by, self.pres)
        self.assertEqual(entry.amount, Decimal("50.00"))
        self.assertEqual(entry.account, self.account)

    def test_admin_entry_is_attached_to_the_url_club(self):
        self.login(self.admin)
        self.client.post(self.url, self.entry_payload())
        entry = FinanceEntry.objects.get()
        self.assertEqual(entry.club, self.club)
        self.assertEqual(entry.created_by, self.admin)

    def test_negative_amount_rejected(self):
        resp = self.client.post(self.url, self.entry_payload(amount="-10"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FinanceEntry.objects.count(), 0)

    def test_foreign_account_rejected(self):
        foreign = FinancialAccount.objects.create(club=self.other_club, name="Theirs")
        resp = self.client.post(self.url, self.entry_payload(account=foreign.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FinanceEntry.objects.count(), 0)

    def test_entry_changes_account_balance(self):
        self.client.post(self.url, self.entry_payload(amount="40.00"))
        self.client.post(
            self.url,
            self.entry_payload(kind="expense", amount="15.00", description="Pizza"),
        )
        self.assertEqual(self.account.balance(), Decimal("125.00"))


class EntryDeleteTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.entry = self.add_entry("fundraiser", 20, account=self.account)
        self.url = reverse("finance_entry_delete", args=[self.club.id, self.entry.id])

    def test_leader_can_delete_via_post(self):
        self.login(self.pres)
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse("finance_home", args=[self.club.id]))
        self.assertFalse(FinanceEntry.objects.filter(id=self.entry.id).exists())

    def test_get_is_not_allowed(self):
        self.login(self.pres)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertTrue(FinanceEntry.objects.filter(id=self.entry.id).exists())

    def test_other_president_cannot_delete(self):
        self.login(self.other_pres)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(FinanceEntry.objects.filter(id=self.entry.id).exists())

    def test_plain_member_cannot_delete(self):
        self.login(self.plain)
        self.client.post(self.url)
        self.assertTrue(FinanceEntry.objects.filter(id=self.entry.id).exists())

    def test_cannot_delete_other_clubs_entry_through_own_club_url(self):
        theirs = self.add_entry("fundraiser", 5, club=self.other_club)
        self.login(self.pres)
        url = reverse("finance_entry_delete", args=[self.club.id, theirs.id])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(FinanceEntry.objects.filter(id=theirs.id).exists())

    def test_admin_can_delete(self):
        self.login(self.admin)
        self.client.post(self.url)
        self.assertFalse(FinanceEntry.objects.filter(id=self.entry.id).exists())


# ------------------------------------------------- club page button
class FinanceButtonVisibilityTests(FinanceTestBase):
    def finance_link(self):
        return reverse("finance_home", args=[self.club.id])

    def test_leader_sees_finances_button(self):
        self.login(self.pres)
        resp = self.client.get(reverse("club_detail", args=[self.club.id]))
        self.assertContains(resp, self.finance_link())

    def test_admin_sees_finances_button(self):
        self.login(self.admin)
        resp = self.client.get(reverse("club_detail", args=[self.club.id]))
        self.assertContains(resp, self.finance_link())

    def test_plain_member_does_not_see_button(self):
        self.login(self.plain)
        resp = self.client.get(reverse("club_detail", args=[self.club.id]))
        self.assertNotContains(resp, self.finance_link())

    def test_other_president_does_not_see_button(self):
        self.login(self.other_pres)
        resp = self.client.get(reverse("club_detail", args=[self.club.id]))
        self.assertNotContains(resp, self.finance_link())