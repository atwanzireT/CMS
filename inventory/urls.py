from django.urls import path
from .views import inventory_dashboard

app_name = 'inventory'

urlpatterns = [
    path("", inventory_dashboard, name="inventory_home"),
]