from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegisterForm
from .models import Member, Club, MembershipRequest, Notification
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from django.http import Http404
from django.utils import timezone
from .forms import RegisterForm, ClubRequestForm, NotificationForm
from django.db.models import Exists, OuterRef



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
    member = request.user.member
    is_admin = member.role == 'admin'
    is_leader = club.leader_id == member.id
    can_manage = is_admin or is_leader

    if club.status != Club.Status.APPROVED and not can_manage:
        raise Http404

    is_member = club.members.filter(id=member.id).exists()
    pending_request = MembershipRequest.objects.filter(
        club=club, member=member, status=MembershipRequest.Status.PENDING
    ).first()

    can_see_inside = is_member or can_manage
    approved = club.status == Club.Status.APPROVED

    return render(request, 'club_detail.html', {
        'club': club,
        'is_member': is_member,
        'is_leader': is_leader,
        'pending_request': pending_request,
        'can_notify': can_notify(member, club),
        'notification_form': NotificationForm(),
        'club_members': club.members.order_by('last_name') if can_see_inside else None,
        'announcements': club.notifications.select_related('sender')[:5] if can_see_inside else None,
        'join_requests': (MembershipRequest.objects
                          .filter(club=club, status=MembershipRequest.Status.PENDING)
                          .select_related('member').order_by('requested_at')
                          if can_manage and approved else None),
    })


@login_required
def leave_club(request, club_id):
    club = get_object_or_404(Club, id=club_id, status=Club.Status.APPROVED)
    member = request.user.member

    if request.method == 'POST':
        if club.leader_id == member.id:
            messages.error(request, "A club's president can't leave their own club.")
        else:
            club.members.remove(member)
            messages.success(request, f"You left '{club.name}'.")
    return redirect('club_detail', club_id=club.id)

@role_required('member','officer', 'president', 'treasurer', 'admin')
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

    created_club_requests = Club.objects.filter(leader=member).order_by('-created_at')
    membership_requests = MembershipRequest.objects.filter(member=member).select_related('club').order_by('-requested_at')
    members = Member.objects.all().order_by('last_name')

    # clubs the current user is allowed to view members for
    if member.role == 'admin':
        managed_clubs = Club.objects.filter(
            status=Club.Status.APPROVED
        ).annotate(member_count=Count('members')).order_by('name')

    elif member.role == 'president':
        managed_clubs = Club.objects.filter(
            leader=member,
            status=Club.Status.APPROVED
        ).annotate(member_count=Count('members')).order_by('name')

    elif member.role in ('officer', 'treasurer'):
        managed_clubs = member.clubs.filter(
            status=Club.Status.APPROVED
        ).annotate(member_count=Count('members')).order_by('name')

    else:
        managed_clubs = member.clubs.filter(
        status=Club.Status.APPROVED
        ).annotate(member_count=Count('members')).order_by('name')


    if member.role == 'admin':
        pending_memberships = MembershipRequest.objects.filter(
            status=MembershipRequest.Status.PENDING
        ).select_related('member', 'club').order_by('requested_at')
    else:
        pending_memberships = MembershipRequest.objects.filter(
            club__leader=member,
            status=MembershipRequest.Status.PENDING
        ).select_related('member', 'club').order_by('requested_at')

    # pending club creation requests are visible to admins only
    if member.role == 'admin':
        pending_club_requests = (
            Club.objects
            .filter(status=Club.Status.PENDING)
            .select_related('leader')
            .order_by('created_at')
        )
    else:
        pending_club_requests = Club.objects.none()



    return render(request, 'dashboard.html', {
        'members': members,
        'form': form,
        'created_club_requests': created_club_requests,
        'membership_requests': membership_requests,
        'can_request': can_request,
        'pending_memberships': pending_memberships,
        'managed_clubs': managed_clubs,
        'pending_club_requests': pending_club_requests,
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
            return redirect('dashboard')

        club.reviewed_by = request.user.member
        club.reviewed_at = timezone.now()
        club.save()

        if club.status == Club.Status.APPROVED and club.leader:
            club.members.add(club.leader)   # leader is the first member
    return redirect('dashboard')

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
    my_clubs = member.clubs.filter(status=Club.Status.APPROVED).order_by('name')#init list of my clubs

    club_notes = Notification.objects.filter(club__in=my_clubs).exclude(hidden_by=member)
    read_through = Notification.read_by.through

    notifications = (club_notes
                    .select_related('club')
                     .annotate(is_read=Exists(
                         read_through.objects.filter(
                             notification_id=OuterRef('pk'), member_id=member.id)))
                     .order_by('-created_at')[:10])
    
    return render(request, 'home.html', { #render info
        'member': member,
        'my_clubs': my_clubs,
        'notifications': notifications,  # placeholder for the future inbox feature
        'unread_count': club_notes.exclude(read_by=member).count(),
        'is_manager': member.role in ('officer', 'president', 'treasurer'),
        'is_admin': member.role in ("admin"),
    })
#HELPER FUNCTIONS for read/undread notifs
@login_required
def mark_notification_read(request, note_id):
    member = request.user.member
    if request.method == 'POST':
        note = get_object_or_404(Notification, id=note_id, club__members=member)
        note.read_by.add(member)
    return redirect('home')


@login_required
def mark_all_read(request):
    member = request.user.member
    if request.method == 'POST':
        for note in Notification.objects.filter(club__members=member).exclude(read_by=member):
            note.read_by.add(member)
    return redirect('home')

@login_required
def delete_notification(request, note_id):
    member = request.user.member
    if request.method == 'POST':
        note = get_object_or_404(Notification, id=note_id, club__members=member)
        note.hidden_by.add(member)
        note.read_by.add(member)  # mark as read when deleted
    return redirect('home')

@login_required
def clear_all_notifications(request):
    """ Deletes all notifications for the current user. """
    member = request.user.member
    if request.method == 'POST':
        notes = Notification.objects.filter(club__members=member).exclude(hidden_by=member)
        for note in notes:
            note.hidden_by.add(member)
            note.read_by.add(member)  # mark as read when deleted
    return redirect('home')

##CHECKING CLUB MEMBERS
@login_required
def club_members(request, club_id):
    member = request.user.member
    club = get_object_or_404(
        Club,
        id=club_id,
        status=Club.Status.APPROVED
    )

    #check whether the current user is allowed to view this club's members
    if member.role == 'admin':
        can_view = True

    elif member.role == 'president':
        can_view = club.leader_id == member.id

    elif member.role in ('officer', 'treasurer'):
        can_view = club.members.filter(id=member.id).exists()

    else:
        can_view = False

    if not can_view:
        messages.error(request, "You don't have permission to view this club's members.")
        return redirect('dashboard')

    club_members_list = (
        club.members
        .select_related('user')
        .order_by('last_name', 'first_name')
    )

    can_manage = (
        member.role == 'admin'
        or (member.role == 'president' and club.leader_id == member.id)
    )

    return render(request, 'club_members.html', {
        'club': club,
        'club_members': club_members_list,
        'can_manage': can_manage,
        'current_member': member,
    })

##REMOVING CLUB MEMBERS
@login_required
def remove_club_member(request, club_id, member_id):
    if request.method != 'POST':
        return redirect('club_members', club_id=club_id)

    current_member = request.user.member

    club = get_object_or_404(
        Club,
        id=club_id,
        status=Club.Status.APPROVED
    )

    target_member = get_object_or_404(
        Member,
        id=member_id
    )

    #only admin or the president of this club can remove members
    if current_member.role == 'admin':
        can_remove = True

    elif (
        current_member.role == 'president'
        and club.leader_id == current_member.id
    ):
        can_remove = True

    else:
        can_remove = False

    if not can_remove:
        messages.error(request, "You don't have permission to remove club members.")
        return redirect('club_members', club_id=club.id)

    #target must actually belong to this club
    if not club.members.filter(id=target_member.id).exists():
        messages.error(request, "This user is not a member of this club.")
        return redirect('club_members', club_id=club.id)

    #club president cannot be removed through member management
    # This keeps Club.leader and Club.members consistent.
    if club.leader_id == target_member.id:
        messages.error(request, "The club president cannot be removed.")
        return redirect('club_members', club_id=club.id)

    #president cannot remove themselves, another president, or an admin
    if current_member.role == 'president':
        if target_member.id == current_member.id:
            messages.error(request, "You can't remove yourself.")
            return redirect('club_members', club_id=club.id)

        if target_member.role in ('president', 'admin'):
            messages.error(request, "You can't remove this member.")
            return redirect('club_members', club_id=club.id)

    club.members.remove(target_member)

    messages.success(
        request,
        f"Removed {target_member.first_name} {target_member.last_name} from {club.name}."
    )

    return redirect('club_members', club_id=club.id)


#returns whether this member can send notifs in this club
def can_notify(member, club):
    return member.role == 'admin' or (member.role == 'president' and club.leader_id == member.id)

#fun to send notif to club members
@login_required
def send_notification(request, club_id):
    club = get_object_or_404(Club, id=club_id, status=Club.Status.APPROVED)
    member = request.user.member

    if request.method == 'POST' and can_notify(member, club):
        form = NotificationForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.club = club
            note.sender = member
            note.save()
            messages.success(request, "Notification sent.")
        else:
            messages.error(request, "Message can't be empty.")
    elif request.method == 'POST':
        messages.error(request, "You can't send notifications for this club.")

    return redirect('club_detail', club_id=club.id)
