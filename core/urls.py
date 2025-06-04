from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('work/', views.work, name='work'),
    path('personal/', views.personal, name='personal'),
    path('account/', views.account, name='account'),
    path('recording/<str:bereich>/', views.recording_page, name='recording_page'),
    path('start-recording/<str:bereich>/', views.start_recording_view, name='start_recording'),
    path('stop-recording/<str:bereich>/', views.stop_recording_view, name='stop_recording'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]
