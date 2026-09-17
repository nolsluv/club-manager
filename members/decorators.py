from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def role_required(*allowed_roles):
    """Restricts a view to users whose Member.role is in allowed_roles."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            member = getattr(request.user, 'member', None)
            if member and member.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            messages.error(request, "You don't have permission to access that page.")
            return redirect('home')
        return wrapper
    return decorator