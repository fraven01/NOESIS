from django.shortcuts import render


def home(request):
    return render(request, 'home.html')


def work(request):
    return render(request, 'work.html')


def personal(request):
    return render(request, 'personal.html')
