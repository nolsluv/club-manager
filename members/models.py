from django.db import models

# Create your models here.
class Member(models.Model):
    ROLE_CHOICES = [
        ('member', 'General Member'),
        ('officer', 'Officer'),
        ('president', 'President'),
        ('treasurer', 'Treasurer'),
    ]

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    date_joined = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"