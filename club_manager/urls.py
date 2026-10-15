"""
URL configuration for club_manager project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from members import views as member_views
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', member_views.intro, name='intro'),
    path('home/', member_views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name="login.html"), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'), 
    path('register/', member_views.register, name='register'), 
    path('dashboard/', member_views.dashboard, name='dashboard'),
    path('club-requests/', member_views.club_requests, name='club_requests'),
    path('club-requests/<int:club_id>/review/', member_views.review_club, name='review_club'),
    path('clubs/', member_views.clubs, name='clubs'),
    path('clubs/<int:club_id>/', member_views.club_detail, name='club_detail'),
    path('users/', member_views.user_management, name='user_management'),
    path('users/delete/<int:user_id>/', member_views.delete_user, name='delete_user'),
    path('', include('events.urls')),
    path('clubs/<int:club_id>/join/', member_views.request_membership, name='request_membership'),
    path('clubs/<int:club_id>/members/',member_views.club_members,name='club_members'),
    path('clubs/<int:club_id>/members/<int:member_id>/remove/',member_views.remove_club_member,name='remove_club_member'),
    path('membership-requests/<int:request_id>/review/', member_views.review_membership, name='review_membership'),
    path('clubs/<int:club_id>/notify/', member_views.send_notification, name='send_notification'),
    path('notifications/<int:note_id>/read/', member_views.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', member_views.mark_all_read, name='mark_all_read'),
    path('clubs/<int:club_id>/leave/', member_views.leave_club, name='leave_club'),
]