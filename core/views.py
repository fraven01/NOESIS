from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def home(request):
    return render(request, 'home.html')


@login_required
def work(request):
    return render(request, 'work.html')


@login_required
def personal(request):
    return render(request, 'personal.html')


@login_required
def account(request):
    return render(request, 'account.html')
