from django.db import models
from django.contrib.auth.models import User

class Member(models.Model):
    ROLE_CHOICES = [
        ('member', 'General Member'),
        ('officer', 'Officer'),
        ('president', 'President'),
        ('treasurer', 'Treasurer'),
        ('admin', 'Admin'),
    ]
    # Links this profile to the login account; nullable so old rows still work
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    date_joined = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Club(models.Model):    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=100, unique=True)

    short_description = models.CharField(
        max_length=200,
        blank=True
    )
    description = models.TextField(blank=True)

    leader = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clubs_led'
    )

    members = models.ManyToManyField(
        Member, 
        related_name='clubs', 
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=10, choices=Status.choices,
        default=Status.PENDING, db_index=True,
    )
    reviewed_by = models.ForeignKey(
        Member, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    def __str__(self):
        return self.name