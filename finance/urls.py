from django.urls import path
from finance.views import finance_dashboard, create_supplier_payment

urlpatterns = [
    path('dashboard/', finance_dashboard, name='finance_dashboard'),
    path("purchases/<int:pk>/pay/", create_supplier_payment, name="create_supplier_payment")
]