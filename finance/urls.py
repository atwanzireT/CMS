from django.urls import path
from finance.views import create_supplier_payment
from accounts.permissions import module_required
from finance import views


app_name = 'finance'

urlpatterns = [
    path("dashboard/", module_required("access_finance")(views.finance_dashboard), name="finance_dashboard"),
    path("purchases/<int:pk>/pay/", create_supplier_payment, name="create_supplier_payment")
]