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
from .models import Event

EVENT_EDITORS = ('president', 'admin')  # roles allowed to add/edit

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
    # Pick the month from ?year=&month=, falling back to the current month
    today = timezone.localdate()
    try:
        first = date(int(request.GET.get('year', today.year)),
                     int(request.GET.get('month', today.month)), 1)
    except ValueError:
        first = today.replace(day=1)

    # Full weeks (Sunday start), including days spilling in from adjacent months
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(first.year, first.month)

    # One query for everything visible on the grid, grouped by local date
    #this will be updated later to add user filter options
    events = Event.objects.filter(
        date__date__range=(weeks[0][0], weeks[-1][-1])
    ).order_by('date')
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
            if creator_member:
                note.read_by.add(creator_member)  # mark as read for the creator
        
        messages.success(request, "Event added successfully.")
        return redirect('calendar')
    return render(request, 'event_form.html', {'form': form, 'heading': 'Add event'})


@role_required(*EVENT_EDITORS)
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not _can_modify(request,event):
        raise PermissionDenied("You can only edit events you created.")
    form = EventForm(request.POST or None, instance=event, user=request.user, active_club=event.club_id)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Your event has been successfully updated.")
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