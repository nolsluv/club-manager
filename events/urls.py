from django.urls import path
from . import views

urlpatterns = [
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/add/', views.event_create, name='event_create'),
    path('calendar/<int:pk>/edit/', views.event_edit, name='event_edit'),
    path('calendar/<int:pk>/delete/', views.event_delete, name='event_delete'),
    path('calendar/<int:pk>/rsvp/', views.rsvp_toggle, name='rsvp_toggle'),
]