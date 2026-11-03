from django.urls import path

from . import views

urlpatterns = [
    path("clubs/<int:club_id>/polls/new/", views.poll_create, name="poll_create"),
    path("polls/<int:poll_id>/", views.poll_detail, name="poll_detail"),
    path("polls/<int:poll_id>/vote/", views.poll_vote, name="poll_vote"),
    path("polls/<int:poll_id>/close/", views.poll_close, name="poll_close"),
]