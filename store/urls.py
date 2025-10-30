from django.urls import path
from . import dashboard_views
from .views import *
from reports.views import create_report

app_name = 'store'

urlpatterns = [
    path('', dashboard_views.dashboard, name="home"),
    path('store-dashboard/', store_dashboard, name="store_dashboard"),
    path("new/", create_report, name="report_create"),


    # Supplier URLs
    path('suppliers/', supplier_list, name='supplier_list'),
    path('suppliers/<str:pk>/', supplier_detail, name='supplier_detail'),
    
    # Coffee Purchase URLs
    path('purchases/', purchase_list, name='purchase_list'),
    path('purchases/<int:pk>/', purchase_detail, name='purchase_detail'),
    path("purchases/new/", purchase_create, name="purchase_create"),
    path("suppliers/<str:supplier_pk>/purchases/new/", purchase_create, name="supplier_purchase_create"),
    path('transactions/new/', transaction_create, name='transaction_create'),

]