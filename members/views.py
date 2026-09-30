from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegisterForm
from .models import Member, Club
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count


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

@login_required
def clubs(request):
    search = request.GET.get("search", "")
    members_filter = request.GET.get("members", "")
    sort = request.GET.get("sort", "az")
    clubs = Club.objects.annotate(
        member_count=Count("members")
    )

    # Search by club name or description
    if search:
        clubs = clubs.filter(
            Q(name__icontains=search) |
            Q(short_description__icontains=search)
        )

    # Filter by number of members 
    if members_filter == "1-10":
        clubs = clubs.filter(member_count__gte=1, member_count__lte=10)
    elif members_filter == "11-25":
        clubs = clubs.filter(member_count__gte=11, member_count__lte=25)
    elif members_filter == "26-50":
        clubs = clubs.filter(member_count__gte=26, member_count__lte=50)
    elif members_filter == "50+":
        clubs = clubs.filter(member_count__gte=50)

    # Sort Results
    if sort == "za":
        clubs = clubs.order_by("-name")
    elif sort == "most":
        clubs = clubs.order_by("-member_count", "name")
    elif sort == "least":
        clubs = clubs.order_by("member_count", "name")
    else:
        clubs = clubs.order_by("name")

    return render(request, "clubs.html", {
        "clubs": clubs, 
        "search": search,
        "members_filter": members_filter,
        "sort": sort,
    })

def club_detail(request, club_id):
    club = get_object_or_404(Club, id=club_id)
    return render(request, 'club_detail.html', {'club': club})