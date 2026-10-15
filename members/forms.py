from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Club, Notification

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    
class ClubRequestForm(forms.ModelForm):
    class Meta:
        model = Club
        fields = ["name", "short_description", "description"]

#sends message notif POST
class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ['message']
        widgets = {'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Message to all club members'})}