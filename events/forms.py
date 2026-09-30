from django import forms
from .models import Event

DT_FORMAT = '%Y-%m-%dT%H:%M'  # format the datetime-local input uses

class EventForm(forms.ModelForm):
    class Meta: #creates meta class that holds what form shoudl ask for
        model = Event
        fields = ['title', 'description', 'date', 'end_date', 'location', 'category', 'contact_email', 'capacity'] #fields coorespond to ones created in models.py
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DT_FORMAT),
            'end_date' : forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DT_FORMAT),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('date', 'end_date'):
            self.fields[name].input_formats = [DT_FORMAT]
    
    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', "End time cannot be before the start time...")
        return cleaned