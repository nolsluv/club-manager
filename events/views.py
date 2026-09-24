from django.shortcuts import render
import calendar
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from members.decorators import role_required  # finds decorator method
from django.views.decorators.http import require_POST
from .forms import EventForm
from .models import Event

EVENT_EDITORS = ('president', 'admin')  # roles allowed to add/edit


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

    member = getattr(request.user, 'member', None)
    return render(request, 'calendar.html', {
        'grid': grid,
        'month_label': first.strftime('%B %Y'), #label month
        'prev_m': (first - timedelta(days=1)).replace(day=1), #select prev month
        'next_m': (first + timedelta(days=32)).replace(day=1), #select next month
        'can_edit': bool(member and member.role in EVENT_EDITORS),  # UI only; views enforce it
        'weekdays': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], #week day abreviations
    })


@role_required(*EVENT_EDITORS) #required role of admin or president
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Event added.")
        return redirect('calendar')
    return render(request, 'event_form.html', {'form': form, 'heading': 'Add event'})


@role_required(*EVENT_EDITORS)
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventForm(request.POST or None, instance=event)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Event updated.")
        return redirect('calendar')
    return render(request, 'event_form.html', {
        'form': form, 'heading': 'Edit event', 'event': event,
        })


@role_required(*EVENT_EDITORS)
@require_POST  # deleting via a plain link (GET) would be unsafe
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.delete()  # also deletes that event's RSVPs (CASCADE)
    messages.success(request, "Event deleted.")
    return redirect('calendar')