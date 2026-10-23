from members.models import Notification
from django.urls import reverse
import calendar
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from members.decorators import role_required  # finds decorator method
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from .forms import EventForm
from .models import Event, RSVP
from members.models import Club

EVENT_EDITORS = ('president', 'admin')  # roles allowed to add/edit

def check_and_send_event_reminders():
    now = timezone.now()
    twenty_four_hours_later = now + timedelta(hours=24)

    upcoming_events = Event.objects.filter(
        date__gte=now,
        date__lte=twenty_four_hours_later,
        reminder_sent=False,
        club__isnull=False
    ).select_related('club', 'created_by')

    sent_count = 0
    for event in upcoming_events:
        event_time_str = timezone.localtime(event.date).strftime("%b %d at %I:%M %p")

        Notification.objects.create(
            club=event.club,
            sender=event.created_by,
            message=f"Reminder: '{event.title}' is happening in less than 24 hours ({event_time_str})",
            notification_type='reminder',
            target_url=reverse('calendar'),
        )

        event.reminder_sent = True
        event.save(update_fields=['reminder_sent'])
        sent_count += 1
    return sent_count

def _get_active_club(request, member):
    return (
        request.GET.get('club')
        or request.session.get('active_club_id')
        or request.session.get('current_club_id')
        or request.session.get('club_id')
        or getattr(member, 'active_club', None)
        or getattr(member, 'current_club', None)
    )

@login_required
def calendar_view(request):
    check_and_send_event_reminders()
    # Pick the month from ?year=&month=, falling back to the current month
    today = timezone.localdate()
    try:
        first = date(int(request.GET.get('year', today.year)),
                     int(request.GET.get('month', today.month)), 1)
    except ValueError:
        first = today.replace(day=1)

    # Full weeks (Sunday start), including days spilling in from adjacent months
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(first.year, first.month)

    member = getattr(request.user, 'member', None)
    active_club_val = _get_active_club(request, member)

    # Normalize active club to an INT ID
    active_club_id = getattr(active_club_val, 'pk', active_club_val)
    if active_club_id is not None:
        try:
            active_club_id = int(active_club_id)
        except (ValueError, TypeError):
            active_club_id = None

    # Initialize the base queryset
    events_qs = Event.objects.filter(
        date__date__range=(weeks[0][0], weeks[-1][-1])
    ).select_related('club')

    # Strict Club Filter:
    # If an active club is selected display only that clubs events
    # If no active club is chosen, display all events
    if active_club_id:
        events_qs = events_qs.filter(club_id=active_club_id)
    elif member:
        my_clubs = member.clubs.filter(status=Club.Status.APPROVED)
        events_qs = events_qs.filter(club__in=my_clubs)
    else:
        events_qs = Event.objects.none()

    events = events_qs.order_by('date')
    
    # Group events by local date
    by_day = defaultdict(list)
    for e in events:
        by_day[timezone.localtime(e.date).date()].append(e)

    grid = [
        [{
            'date': d,
            'in_month': d.month == first.month,
            'is_today': d == today,
            'events': by_day.get(d, []),
        } for d in week]
        for week in weeks
    ]
    
    month = first.month
    year = first.year

    member = getattr(request.user, 'member', None)
    return render(request, 'calendar.html', {
        'grid': grid,
        'month_label': first.strftime('%B %Y'), #label month
        'prev_m': (first - timedelta(days=1)).replace(day=1), #select prev month
        'next_m': (first + timedelta(days=32)).replace(day=1), #select next month
        'can_edit': bool(member and member.role in EVENT_EDITORS),  # UI only; views enforce it
        "current_member_id": member.id if member else None, #returns current member id, or none if member delted
        'is_admin': bool(member and member.role == 'admin'), #returns if member is admin
        'weekdays': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], #week day abreviations
        'month': month,
        'year': year,
        'months': list(enumerate(calendar.month_name))[1:],
        'years': range(first.year - 2, first.year + 4),
        'active_club_id': active_club_id,
        })

def _can_modify(request, event):
    """Admins can create,remove,edit any event. Presidents only their own"""
    member = getattr(request.user, 'member', None)
    if not member:
        return False
    return member.role == 'admin' or event.created_by_id == member.id #check for adming or same id as creator

@role_required(*EVENT_EDITORS) #required role of admin or president
def event_create(request):
    member = getattr(request.user, 'member', None)
    active_club = _get_active_club(request, member)

    form = EventForm(request.POST or None, user=request.user, active_club=active_club)
    if request.method == 'POST' and form.is_valid():
        event = form.save(commit=False)
        creator_member = member
        event.created_by = creator_member

        selected_club = form.cleaned_data.get('club')
        if selected_club:
            event.club = selected_club
        event.save()
        form.save_m2m()  # save any many-to-many relationships if present

        # --- CREATE INBOX NOTIFICATION FOR THE CLUB ---
        if selected_club:
            event_name = getattr(event, 'title', None) or getattr(event, 'name', 'New Event')
            event_date_str = (
                timezone.localtime(event.date).strftime('%b %d')
                if hasattr(event, 'date') and event.date 
                else ''
            )

            note = Notification.objects.create(
                club=selected_club,
                sender=creator_member,
                message=f"New event: {event_name} on {event_date_str}".strip(),
                notification_type='event',
                target_url=reverse('calendar'),
            )
            #if creator_member:
            #    note.read_by.add(creator_member)  # mark as read for the creator
        
        messages.success(request, "Event added successfully.")
        return redirect('calendar')
    return render(request, 'event_form.html', {'form': form, 'heading': 'Add event'})


@role_required(*EVENT_EDITORS)
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not _can_modify(request,event):
        raise PermissionDenied("You can only edit events you created.")
    
    # Get original values before changing
    old_club = getattr(event, 'club', None)
    old_title = event.title
    old_date = event.date

    form = EventForm(request.POST or None, instance=event, user=request.user, active_club = getattr(event, 'club_id', None))
    if request.method == 'POST' and form.is_valid():
        updated_event = form.save(commit=False)
        # Ensure selected club is bound to the event
        selected_club = form.cleaned_data.get('club')
        if selected_club:
            updated_event.club = selected_club
        # Reset reminder flag
        if old_date != updated_event.date:
            updated_event.reminder_sent = False
        updated_event.save()
        form.save_m2m()  # save any many-to-many relationships if present

        editor_member = getattr(request.user, 'member', None)
        event_name = updated_event.title
        event_date_str = (
            timezone.localtime(updated_event.date).strftime("%b %d at %I:%M %p")
            if getattr(updated_event, 'date', None) else ""
        )
        old_date_str = (
            timezone.localtime(old_date).strftime("%b %d at %I:%M %p")
            if old_date else ""
        )
        # Determine what changed
        changes = []
        if old_title != updated_event.title:
            changes.append(f"Title changed from {old_title} to '{updated_event.title}'")
        if old_date != updated_event.date:
            changes.append(f"Date changed to {event_date_str}")
        if old_club != updated_event.club:
            changes.append(f"Club changed to '{updated_event.club.name}'")

        change_summary = f" ({', '.join(changes)})" if changes else ""

        # Case A: The event changed clubs 
        if old_club and selected_club and old_club != selected_club:
            Notification.objects.create(
                club=old_club,
                sender=editor_member,
                message=f"Event relocated: '{old_title}' has moved to {selected_club.name}.",
                notification_type='cancelation',
                target_url=reverse('calendar'),
            )
            note = Notification.objects.create(
                club=selected_club,
                sender=editor_member,
                message=f"New event transferred in: {event_name} scheduled for {event_date_str}.",
                notification_type='event',
                target_url=reverse('calendar'),
            )
            if editor_member:
                note.read_by.add(editor_member)
        # Standard edit
        elif selected_club:
            note = Notification.objects.create(
                club=selected_club,
                sender=editor_member,
                message=f"Updated event: {event_name}{change_summary}".strip(),
                notification_type='event',
                target_url=reverse('calendar'),
            )
            if editor_member:
                note.read_by.add(editor_member)
        messages.success(request, "Your event has been successfully updated.")
        active_club_id = _get_active_club(request, editor_member)
        if active_club_id:
            return redirect(f"{reverse('calendar')}?club={active_club_id}")
        return redirect('calendar')
    return render(request, 'event_form.html', {
        'form': form, 'heading': 'Edit event', 'event': event,
        })


@role_required(*EVENT_EDITORS)
@require_POST  # deleting via a plain link (GET) would be unsafe
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not _can_modify(request,event):
        raise PermissionDenied("You can only delete events you created.")

    member = request.user.member
    club = getattr(event, 'club', None)
    if not club and hasattr(member, 'clubs'):
        club = member.clubs.first()  # default to first club if not specified

    event_name = getattr(event, 'title', None) or getattr(event, 'name', 'Event')
    event_date_str = ""
    if hasattr(event, 'date') and event.date:
        event_date_str = f" scheduled for {timezone.localtime(event.date).strftime('%b %d')}"
    
    event.delete()  # also deletes that event's RSVPs (CASCADE)

    if club:
        cancel_note = Notification.objects.create(
            club=club,
            sender=request.user.member,
            message=f"Event canceled: {event.title} on {event.date.strftime('%b %d')}",
            notification_type='cancelation',
            target_url=reverse('calendar'),
        )

    messages.success(request, "Your event has been successfully deleted.")
    return redirect('calendar')

@login_required
@require_POST
def rsvp_toggle(request, pk):
    event = get_object_or_404(Event, pk=pk)
    member = getattr(request.user, 'member', None)

    if not member:
        raise PermissionDenied("No member profile.")
    # only members of the hosting club can RSVP
    if not event.club or not event.club.members.filter(id=member.id).exists():
        raise PermissionDenied("Only club members can RSVP to this event.")

    existing = RSVP.objects.filter(event=event, member=member)
    if existing.exists():
        existing.delete()
        messages.success(request, f"Your RSVP to '{event.title}' was cancelled.")
    else:
        if event.date < timezone.now():
            messages.error(request, "This event has already happened.")
        elif event.capacity and event.rsvps.count() >= event.capacity:
            messages.error(request, "Sorry, this event is full.")
        else:
            RSVP.objects.create(event=event, member=member)
            messages.success(request, f"You're going to '{event.title}'.")

    return redirect(request.META.get('HTTP_REFERER') or 'calendar')