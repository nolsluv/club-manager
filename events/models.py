from django.db import models
from members.models import Member

# events/models.py
from django.db import models
from members.models import Member

class Event(models.Model):
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
    created_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_events'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class RSVP(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='rsvps')
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    responded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'member')

    def __str__(self):
        return f"{self.member} -> {self.event}"