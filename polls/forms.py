from django import forms
from django.utils import timezone

from .models import Poll

DT_FORMAT = "%Y-%m-%dT%H:%M"  # what <input type="datetime-local"> sends

MIN_OPTIONS = 2
MAX_OPTIONS = 10


class PollForm(forms.ModelForm):
    class Meta:
        model = Poll
        fields = ["question", "expires_at"]
        widgets = {
            "question": forms.TextInput(attrs={"placeholder": "What should we vote on?"}),
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_FORMAT),
        }
        labels = {"expires_at": "Voting closes"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expires_at"].input_formats = [DT_FORMAT]

    def clean_question(self):
        return self.cleaned_data["question"].strip()

    def clean_expires_at(self):
        expires_at = self.cleaned_data["expires_at"]
        if expires_at <= timezone.now():
            raise forms.ValidationError("The closing time must be in the future.")
        return expires_at


def clean_options(raw_options):
    """Trim, drop blanks and duplicates. Returns (options, error_message)."""
    seen, cleaned = set(), []
    for text in raw_options:
        text = " ".join(text.split())  # collapse stray whitespace
        if not text:
            continue
        if len(text) > 100:
            return None, "Each answer must be 100 characters or fewer."
        key = text.lower()
        if key in seen:
            return None, f"'{text}' is listed more than once."
        seen.add(key)
        cleaned.append(text)

    if len(cleaned) < MIN_OPTIONS:
        return None, f"Add at least {MIN_OPTIONS} answer choices."
    if len(cleaned) > MAX_OPTIONS:
        return None, f"Polls can have at most {MAX_OPTIONS} answer choices."
    return cleaned, None