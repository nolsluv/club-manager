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

class AdminUserEditForm(forms.Form):
    field_order = ["first_name", "last_name", "username", "email", "role", "is_active"]

    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=50)
    last_name = forms.CharField(max_length=50)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Member.ROLE_CHOICES)
    is_active = forms.BooleanField(
        required=False,
        label="Account status",
        widget=forms.Select(choices=[(True, "Active"), (False, "Deactivated")]),
    )
    def __init__(self, *args, target_user, target_member, acting_user, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_user = target_user
        self.target_member = target_member
        self.acting_user = acting_user
        for name, field in self.fields.items():
            if name != "is_active":
                field.widget.attrs["class"] = "user-edit-input"

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        User.username_validator(username)
        taken = User.objects.filter(username__iexact=username).exclude(pk=self.target_user.pk)
        if taken.exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        in_users = User.objects.filter(email__iexact=email).exclude(pk=self.target_user.pk)
        in_members = Member.objects.filter(email__iexact=email)
        if self.target_member.pk:
            in_members = in_members.exclude(pk=self.target_member.pk)
        if in_users.exists() or in_members.exists():
            raise forms.ValidationError("This email is already used by another account.")
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")

        # An admin can't lock themselves out
        if self.target_user.pk == self.acting_user.pk:
            if role and role != "admin":
                self.add_error("role", "You can't change your own role.")
            if not cleaned.get("is_active"):
                self.add_error("is_active", "You can't deactivate your own account.")

        # Demoting a club's president would orphan the club
        if (
            role and role != "president"
            and self.target_member.pk
            and Club.objects.filter(leader=self.target_member).exists()
        ):
            self.add_error(
                "role",
                "This user leads one or more clubs. Reassign or remove those clubs first.",
            )
        return cleaned