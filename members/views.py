from django.shortcuts import render
from django.contrib.auth import login
from .forms import RegisterForm
from .models import Member


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
