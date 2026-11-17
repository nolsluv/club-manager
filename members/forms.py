from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from django.contrib.auth.models import User
from .models import Club, Notification, Member
from django.template.loader import render_to_string
from django_q.tasks import async_task

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class ProfileUpdateForm(forms.Form):
    first_name = forms.CharField(
        max_length=50,
        required=True
    )

    last_name = forms.CharField(
        max_length=50,
        required=True
    )

    email = forms.EmailField(
        required=True
    )

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        existing_member = Member.objects.filter(
            email__iexact=email
        )

        if self.member:
            existing_member = existing_member.exclude(
                pk=self.member.pk
            )

        if existing_member.exists():
            raise forms.ValidationError(
                "This email is already being used by another account."
            )

        return email

    
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

class ClubAppearanceForm(forms.ModelForm):
    class Meta:
        model = Club
        fields = ['icon', 'theme_color']

class AsyncPasswordResetForm(PasswordResetForm):
    def send_mail(
            self,
            subject_template_name,
            email_template_name,
            context,
            from_email,
            to_email,
            html_email_template_name=None,
    ):
        subject = render_to_string(subject_template_name, context).strip()
        text_body = render_to_string(email_template_name, context)
        html_body = (
            render_to_string(html_email_template_name, context)
            if html_email_template_name
            else None
        )

        async_task(
            "members.tasks.send_password_reset_email",
            subject,
            text_body,
            html_body,
            from_email,
            to_email,
        )