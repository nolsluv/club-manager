from django.contrib import admin
from .models import Member, Club, MembershipRequest

# Register your models here.
admin.site.register(Member)
admin.site.register(Club)
admin.site.register(MembershipRequest)
