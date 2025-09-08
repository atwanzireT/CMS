from django.urls import path
from . import views
from .views import *
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('register/', register, name='register'),
    path('logout', views.logout_func, name='logout'),
    path('logoutpage', views.logout_page, name='logoutpage'),
    path('activities/', UserActivityListView.as_view(), name='user_activities'),
]