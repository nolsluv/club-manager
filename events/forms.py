from django import forms
from django.db.models import Q
from .models import Event
from members.models import Club

DT_FORMAT = '%Y-%m-%dT%H:%M'  # format the datetime-local input uses

class EventForm(forms.ModelForm):
    club = forms.ModelChoiceField(
        queryset=Club.objects.none(),
        empty_label="Select a club",
        required=True,
        error_messages={'required': 'Please select a club to host this event.'},
        widget=forms.Select(attrs={'required': 'required'})
    )
    class Meta: #creates meta class that holds what form shoudl ask for
        model = Event
        fields = ['club', 'title', 'description', 'date', 'end_date', 'location', 'category', 'contact_email', 'capacity'] #fields coorespond to ones created in models.py
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DT_FORMAT),
            'end_date' : forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DT_FORMAT),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('date', 'end_date'):
            self.fields[name].input_formats = [DT_FORMAT]

        if user is not None and getattr(user, 'is_authenticated', False):
            member = getattr(user, 'member', None)
            if member:
                self.fields['club'].queryset = Club.objects.filter(members=member).distinct()
            else:
                self.fields['club'].queryset = Club.objects.none()
        else:
            self.fields['club'].queryset = Club.objects.none()
                
    
    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', "End time cannot be before the start time...")
        return cleaned