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
        return f"{self.first_name} {self.last_name}

class Club(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    leader = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clubs_led'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name