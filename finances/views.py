from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from members.decorators import role_required
from members.models import Club
from .forms import AccountForm, EntryForm
from .models import FinanceEntry
from datetime import date
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth

def _finance_club(request, club_id):
    """Only the club's president or an admin may see/edit its finances."""
    club = get_object_or_404(Club, id=club_id, status=Club.Status.APPROVED)
    member = request.user.member
    if not (member.role == "admin" or club.leader_id == member.id):
        raise PermissionDenied("Only the club president can manage finances.")
    return club, member

def _last_months(n=6):
    """First-of-month dates for the last n months, oldest first."""
    today = timezone.localdate()
    y, m, out = today.year, today.month, []
    for _ in range(n):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out[::-1]

@role_required("president", "admin")
def finance_home(request, club_id):
    club, member = _finance_club(request, club_id)

    entries = club.finance_entries.select_related("account")
    kind = request.GET.get("kind")
    if kind in FinanceEntry.Kind.values:
        entries = entries.filter(kind=kind)

    # --- totals From ALL ENTRY ---
    allq = club.finance_entries
    gross = allq.exclude(kind="expense").aggregate(t=Sum("amount"))["t"] or 0
    spending = allq.filter(kind="expense").aggregate(t=Sum("amount"))["t"] or 0
    fundraisers = allq.filter(kind="fundraiser").aggregate(t=Sum("amount"))["t"] or 0
    dues = allq.filter(kind="monthly").aggregate(t=Sum("amount"))["t"] or 0

    # --- last 6 months for the bar graph ---
    months = _last_months(6)
    rows = (
        allq.filter(date__gte=months[0])
        .annotate(m=TruncMonth("date"))
        .values("m")
        .annotate(
            inc=Sum("amount", filter=~Q(kind="expense")),
            exp=Sum("amount", filter=Q(kind="expense")),
        )
    )
    by_month = {r["m"]: r for r in rows}
    chart = []
    for m in months:
        r = by_month.get(m, {})
        chart.append({
            "label": m.strftime("%b"),
            "income": r.get("inc") or 0,
            "expense": r.get("exp") or 0,
        })
    peak = max([float(c["income"]) for c in chart] +
               [float(c["expense"]) for c in chart] + [1])
    for c in chart:
        c["income_pct"] = round(float(c["income"]) / peak * 100)
        c["expense_pct"] = round(float(c["expense"]) / peak * 100)

    return render(request, "finance_home.html", {
        "club": club,
        "accounts": club.finance_accounts.order_by("-is_active", "name"),
        "entries": entries,
        "gross": gross,
        "spending": spending,
        "net": gross - spending,
        "fundraisers": fundraisers,
        "dues": dues,
        "chart": chart,
        "kinds": FinanceEntry.Kind.choices,
        "selected_kind": kind,
    })


@role_required("president", "admin")
def account_add(request, club_id):
    club, member = _finance_club(request, club_id)
    form = AccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save(commit=False)
        account.club = club
        account.save()
        messages.success(request, "Account added.")
        return redirect("finance_home", club_id=club.id)
    return render(request, "finance_form.html", {"form": form, "club": club, "heading": "Add account"})


@role_required("president", "admin")
def entry_add(request, club_id):
    club, member = _finance_club(request, club_id)
    form = EntryForm(request.POST or None, club=club, initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.club = club
        entry.created_by = member
        entry.save()
        messages.success(request, "Entry added.")
        return redirect("finance_home", club_id=club.id)
    return render(request, "finance_form.html", {"form": form, "club": club, "heading": "Add entry"})


@role_required("president", "admin")
@require_POST
def entry_delete(request, club_id, entry_id):
    club, member = _finance_club(request, club_id)
    get_object_or_404(FinanceEntry, id=entry_id, club=club).delete()
    messages.success(request, "Entry deleted.")
    return redirect("finance_home", club_id=club.id)