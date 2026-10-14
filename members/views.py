from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegisterForm
from .models import Member, Club, MembershipRequest
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from django.http import Http404
from django.utils import timezone
from .forms import RegisterForm, ClubRequestForm


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

    clubs = (Club.objects
             .filter(status=Club.Status.APPROVED)
             .select_related("leader")
             .annotate(member_count=Count("members")))

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

    # Name sorting
    if sort == "az":
        clubs = clubs.order_by("name")
    elif sort == "za":
        clubs = clubs.order_by("-name")
    # Member count sorting
    elif sort == "most":
        clubs = clubs.order_by("-member_count", "name")
    elif sort == "least":
        clubs = clubs.order_by("member_count")

    return render(request, "clubs.html", {
        "clubs": clubs, 
        "search": search,
        "members_filter": members_filter,
        "sort": sort,
    })

@login_required
def club_detail(request, club_id):
    club = get_object_or_404(Club, id=club_id)
    if club.status != Club.Status.APPROVED:
        member = request.user.member
        if not (member.role == 'admin' or club.leader_id == member.id):
            raise Http404

    member = request.user.member
    is_member = club.members.filter(id=member.id).exists()
    pending_request = MembershipRequest.objects.filter(
        club=club, member=member, status=MembershipRequest.Status.PENDING
    ).first()

    return render(request, 'club_detail.html', {
        'club': club,
        'is_member': is_member,
        'pending_request': pending_request,
    })

@role_required('officer', 'president', 'treasurer', 'admin')
def dashboard(request):
    member = request.user.member
    can_request = member.role in ('president', 'admin')
    form = ClubRequestForm()

    if request.method == 'POST' and can_request:
        form = ClubRequestForm(request.POST)
        if form.is_valid():
            club = form.save(commit=False)
            club.leader = member
            club.save()
            messages.success(request, f"'{club.name}' submitted for admin approval.")
            return redirect('dashboard')

    my_clubs = Club.objects.filter(leader=member).order_by('-created_at')
    members = Member.objects.all().order_by('last_name')

    if member.role == 'admin':
        pending_memberships = MembershipRequest.objects.filter(
            status=MembershipRequest.Status.PENDING
        ).select_related('member', 'club').order_by('requested_at')
    else:
        pending_memberships = MembershipRequest.objects.filter(
            club__leader=member,
            status=MembershipRequest.Status.PENDING
        ).select_related('member', 'club').order_by('requested_at')

    return render(request, 'dashboard.html', {
        'members': members,
        'form': form,
        'my_clubs': my_clubs,
        'can_request': can_request,
        'pending_memberships': pending_memberships,
    })

# only admin accountsa re allowed to view club creation requests
@role_required('admin')
def club_requests(request):
    pending = (Club.objects
               .filter(status=Club.Status.PENDING)
               .select_related('leader')
               .order_by('created_at'))
    return render(request, 'club_requests.html', {'pending': pending})

#only admin accounts can approve or deny reqquests
@role_required('admin')
def review_club(request, club_id):
    if request.method == 'POST':
        # only pending clubs match, so a double-click can't re-review
        club = get_object_or_404(Club, id=club_id, status=Club.Status.PENDING)
        action = request.POST.get('action')

        if action == 'approve':
            club.status = Club.Status.APPROVED
            messages.success(request, f"Approved '{club.name}'.")
        elif action == 'reject':
            club.status = Club.Status.REJECTED
            club.rejection_reason = request.POST.get('reason', '').strip()
            messages.success(request, f"Rejected '{club.name}'.")
        else:
            return redirect('club_requests')

        club.reviewed_by = request.user.member
        club.reviewed_at = timezone.now()
        club.save()

        if club.status == Club.Status.APPROVED and club.leader:
            club.members.add(club.leader)   # leader is the first member
    return redirect('club_requests')

@login_required
def request_membership(request, club_id):
    club = get_object_or_404(Club, id=club_id, status=Club.Status.APPROVED)
    member = request.user.member

    if request.method == 'POST':
        if club.members.filter(id=member.id).exists():
            messages.info(request, "You're already a member of this club.")
        elif MembershipRequest.objects.filter(club=club, member=member, status=MembershipRequest.Status.PENDING).exists():
            messages.info(request, "You already have a pending request for this club.")
        else:
            MembershipRequest.objects.create(club=club, member=member)
            messages.success(request, f"Requested to join '{club.name}'.")

    return redirect('club_detail', club_id=club.id)


@role_required('officer', 'president', 'treasurer', 'admin')
def review_membership(request, request_id):
    if request.method == 'POST':
        membership_request = get_object_or_404(
            MembershipRequest, id=request_id, status=MembershipRequest.Status.PENDING
        )
        # only the club's leader (or an admin) can review its requests
        reviewer = request.user.member
        if membership_request.club.leader_id != reviewer.id and reviewer.role != 'admin':
            messages.error(request, "You can't review requests for this club.")
            return redirect('club_detail', club_id=membership_request.club.id)

        action = request.POST.get('action')
        if action == 'approve':
            membership_request.status = MembershipRequest.Status.APPROVED
            membership_request.club.members.add(membership_request.member)
            messages.success(request, f"Approved {membership_request.member}.")
        elif action == 'reject':
            membership_request.status = MembershipRequest.Status.REJECTED
            messages.success(request, f"Rejected {membership_request.member}.")

        membership_request.reviewed_by = reviewer
        membership_request.reviewed_at = timezone.now()
        membership_request.save()

        return redirect('club_detail', club_id=membership_request.club.id)

    return redirect('home')

@login_required
def home(request):
    member = request.user.member #init member
    my_clubs = member.clubs.filter(status=Club.Status.APPROVED).order_by('name') #init list of my clubs

    return render(request, 'home.html', { #render info
        'member': member,
        'my_clubs': my_clubs,
        'notifications': [],  # placeholder for the future inbox feature
        'is_manager': member.role in ('officer', 'president', 'treasurer'),
        'is_admin': member.role in ("admin"),
    })