from django import forms
from .models import Event

DT_FORMAT = '%Y-%m-%dT%H:%M'  # format the datetime-local input uses

class EventForm(forms.ModelForm):
    class Meta: #creates meta class that holds what form shoudl ask for
        model = Event
        fields = ['title', 'description', 'date', 'location']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DT_FORMAT),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].input_formats = [DT_FORMAT]