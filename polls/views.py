from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from members.models import Club, Notification
from members.views import can_notify  # leader of this club, or an admin
from .forms import MAX_OPTIONS, PollForm, clean_options
from .models import Poll, PollOption, Vote


def _member(request):
    member = getattr(request.user, "member", None)
    if member is None:
        raise PermissionDenied("No member profile.")
    return member


@login_required
def poll_create(request, club_id):
    club = get_object_or_404(Club, id=club_id, status=Club.Status.APPROVED)
    member = _member(request)
    if not can_notify(member, club):
        raise PermissionDenied("Only the club's president or an admin can create polls.")

    form = PollForm(request.POST or None)
    options = request.POST.getlist("options") if request.method == "POST" else ["", ""]

    if request.method == "POST" and form.is_valid():
        cleaned, error = clean_options(options)
        if error:
            form.add_error(None, error)
        else:
            with transaction.atomic():
                poll = form.save(commit=False)
                poll.club = club
                poll.created_by = member
                poll.save()
                PollOption.objects.bulk_create(
                    [PollOption(poll=poll, text=t, order=i) for i, t in enumerate(cleaned)]
                )

                # the poll rides on the notification system: this puts it in every
                # member's inbox and triggers the browser popup
                note = Notification.objects.create(
                    club=club,
                    sender=member,
                    message=f"New poll: {poll.question}",
                    notification_type="poll",
                    target_url=reverse("poll_detail", args=[poll.id]),
                )
                note.read_by.add(member)  # the sender doesn't need an unread badge
                poll.notification = note
                poll.save(update_fields=["notification"])

            messages.success(request, "Poll sent to club members.")
            return redirect("poll_detail", poll_id=poll.id)

    return render(request, "poll_form.html", {
        "form": form,
        "club": club,
        "options": options or ["", ""],
        "max_options": MAX_OPTIONS,
    })


@login_required
def poll_detail(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("club"), id=poll_id)
    club = poll.club
    member = _member(request)

    is_member = club.members.filter(id=member.id).exists()
    can_manage = can_notify(member, club)
    if not (is_member or can_manage):
        raise Http404  # don't reveal that the poll exists

    my_vote = Vote.objects.filter(poll=poll, member=member).first()
    options, total = poll.results()

    return render(request, "poll_detail.html", {
        "poll": poll,
        "club": club,
        "options": options,
        "total": total,
        "my_option_id": my_vote.option_id if my_vote else None,
        "can_vote": is_member and poll.is_open,
        "can_manage": can_manage,
        # members see results after voting (or once it closes); managers always do
        "show_results": bool(my_vote) or not poll.is_open or can_manage,
    })


@login_required
@require_POST
def poll_vote(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("club"), id=poll_id)
    member = _member(request)

    if not poll.club.members.filter(id=member.id).exists():
        raise PermissionDenied("Only club members can vote.")

    if not poll.is_open:
        messages.error(request, "This poll has closed.")
        return redirect("poll_detail", poll_id=poll.id)

    try:
        option_id = int(request.POST.get("option", ""))
    except ValueError:
        option_id = None
    # filtering through poll.options stops votes for another poll's option
    option = poll.options.filter(id=option_id).first() if option_id else None
    if option is None:
        messages.error(request, "Please choose one of the answers.")
        return redirect("poll_detail", poll_id=poll.id)

    Vote.objects.update_or_create(poll=poll, member=member, defaults={"option": option})
    messages.success(request, "Your vote was recorded.")
    return redirect("poll_detail", poll_id=poll.id)


@login_required
@require_POST
def poll_close(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("club"), id=poll_id)
    member = _member(request)
    if not can_notify(member, poll.club):
        raise PermissionDenied("Only the club's president or an admin can close polls.")

    if poll.is_open:
        poll.expires_at = timezone.now()
        poll.save(update_fields=["expires_at"])
        messages.success(request, "Poll closed.")
    return redirect("poll_detail", poll_id=poll.id)