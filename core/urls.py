from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('work/', views.work, name='work'),
    path('personal/', views.personal, name='personal'),
]
