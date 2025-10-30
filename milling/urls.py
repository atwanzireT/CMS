# milling/urls.py
from django.urls import path
from .views import (
    customer_list,
    customer_detail,
    customer_search,
    milling_detail,
    create_milling_payment,
)
from .milling_list_view import milling_list
from .dashboard_view import milling_dashboard

app_name = "milling"

urlpatterns = [
    # --- Customers ---
    path("customers/", customer_list, name="customer_list"),
    # Customer.id is a CharField like "GPC-CUS001", so use <str:pk>
    path("customers/<str:pk>/", customer_detail, name="customer_detail"),
    path("customer-search/", customer_search, name="customer_search"),

    # --- Milling Processes ---
    path("milling-dashboard/", milling_dashboard, name="milling_dashboard"),
    path("milling/", milling_list, name="milling_list"),
    # MillingProcess.id is an integer primary key, so <int:pk> is correct
    path("milling/<int:pk>/", milling_detail, name="milling_detail"),

    # --- Payments ---
    # Used by template: {% url 'milling:create_milling_payment' process.id %}
    path("<int:pk>/payments/create/", create_milling_payment, name="create_milling_payment"),
]
