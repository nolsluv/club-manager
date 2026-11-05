# events/models.py
from django.db import models
from members.models import Member
from members.models import Club

class Event(models.Model):
    club = models.ForeignKey(
        Club, 
        on_delete=models.CASCADE,
        related_name='events',
        null=True,
        blank=False
    )
    CATEGORY_CHOICES = [
        ('meeting', 'Meeting'),
        ('social', 'Social'),
        ('fundraiser', 'Fundraiser'),
        ('service', 'Service'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=150, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    contact_email = models.EmailField(blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)  # blank = unlimited
    VISIBILITY_CHOICES = [
        ('club', 'Club members only'),
        ('public', 'Public (anyone can see and RSVP)'),
    ]
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default='club',
        help_text="Public events show on everyone's calendar and anyone can RSVP.",
    )
    created_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_events'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reminder_sent = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    @property
    def is_public(self):
        return self.visibility == 'public'

    def can_rsvp(self, member):
        """Public events: any member. Club events: members of the hosting club."""
        if not member or not self.club_id:
            return False
        return self.is_public or self.club.members.filter(id=member.id).exists()

    def attendance_roster(self):
        """Who can be marked present: the club's members, plus anyone who
        RSVP'd if the event is public."""
        if not self.club_id:
            return Member.objects.none()
        people = models.Q(clubs=self.club)
        if self.is_public:
            people |= models.Q(rsvp__event=self)
        return Member.objects.filter(people).distinct()

class RSVP(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='rsvps')
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    responded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'member')

    def __str__(self):
        return f"{self.member} -> {self.event}"

class Attendance(models.Model):
    """One row = this member was present at this event."""
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='attendance')
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendance_records')
    recorded_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'member')

    def __str__(self):
        return f"{self.member} attended {self.event}"
