from django.urls import path
from . import dashboard_views
from .views import *


urlpatterns = [
    path('', dashboard_views.dashboard, name="home"),
    path('store-dashboard/', store_dashboard, name="store_dashboard"),

    # Supplier URLs
    path('suppliers/', supplier_list, name='supplier_list'),
    path('suppliers/<int:pk>/', supplier_detail, name='supplier_detail'),
    
    # Coffee Purchase URLs
    path('purchases/', purchase_list, name='purchase_list'),
    path('purchases/<int:pk>/', purchase_detail, name='purchase_detail'),
    
    # Coffee Sale URLs
    path('sales/', sale_list, name='sale_list'),
    path('sales/<int:pk>/', sale_detail, name='sale_detail'),

    # Inventory URLs
    path('inventory/', inventory_dashboard, name='inventory_list'),
    path('inventory/<int:pk>/', inventory_detail, name='inventory_detail'),
]