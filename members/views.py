from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegisterForm
from .models import Member
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.contrib import messages


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # user=user links this profile to the account for role checks later
            Member.objects.create(
                user=user,
                first_name=request.POST.get('first_name', ''),
                last_name=request.POST.get('last_name', ''),
                email=user.email,
            )
            login(request, user)
            return redirect('home')

    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form})

#have to login to access home page
@login_required
def home(request):
    return render(request, 'home.html')

def intro(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'intro.html')


#club management dashboard
@role_required('officer', 'president', 'treasurer', 'admin')
def dashboard(request):
    members = Member.objects.all().order_by('last_name')
    return render(request, 'dashboard.html', {'members': members})

#ADMIN ONLY DASHBOARD INFO
@role_required('admin')
def user_management(request):
    users = User.objects.select_related('member').order_by('username')
    return render(request, 'user_management.html', {'users': users})


@role_required('admin')
def delete_user(request, user_id):
    if request.method == 'POST':
        target = get_object_or_404(User, id=user_id)
        if target == request.user:
            messages.error(request, "You can't delete your own account.")
        else:
            target.delete()  # cascades to delete the linked Member row too
            messages.success(request, f"Deleted user {target.username}.")
    return redirect('user_management')