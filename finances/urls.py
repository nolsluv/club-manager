from django.urls import path
from . import views

urlpatterns = [
    path("clubs/<int:club_id>/finance/", views.finance_home, name="finance_home"),
    path("clubs/<int:club_id>/finance/account/add/", views.account_add, name="finance_account_add"),
    path("clubs/<int:club_id>/finance/entry/add/", views.entry_add, name="finance_entry_add"),
    path("clubs/<int:club_id>/finance/entry/<int:entry_id>/delete/", views.entry_delete, name="finance_entry_delete"),
]