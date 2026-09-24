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
    path('users/', member_views.user_management, name='user_management'),
    path('users/delete/<int:user_id>/', member_views.delete_user, name='delete_user'),
    path('', include('events.urls')),
]