from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegisterForm
from .models import Member
from django.contrib.admin.views.decorators import staff_member_required
from .decorators import role_required


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

@role_required('officer', 'president', 'treasurer')
def dashboard(request):
    members = Member.objects.all().order_by('last_name')
    return render(request, 'dashboard.html', {'members': members})