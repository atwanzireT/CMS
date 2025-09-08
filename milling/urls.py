from django.urls import path
from .views import *

urlpatterns = [
    # Customer URLs
    path('customers/', customer_list, name='customer_list'),
    path('customers/<int:pk>/', customer_detail, name='customer_detail'),
    
    # Milling Process URLs
    path('milling/', milling_list, name='milling_list'),
    path('milling/<int:pk>/', milling_detail, name='milling_detail'),
    path("<int:pk>/payments/create/", create_milling_payment, name="create_milling_payment"),
   
    # Search URLs
    path('customer-search/', customer_search, name='customer_search'),
]