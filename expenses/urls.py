# expenses/urls.py
from django.urls import path
from . import views as v

app_name = "expenses"

urlpatterns = [
    path("", v.requests_all, name="requests_all"),
    path("approved/", v.requests_approved, name="requests_approved"),
    path("requests/<str:kind>/<int:pk>/finance/", v.request_finance_decide, name="request_finance_decide"),
    path("requests/<str:kind>/<int:pk>/admin/",   v.request_admin_decide,   name="request_admin_decide"),
    path("requests/<str:kind>/<int:pk>/paid/",    v.request_mark_paid,      name="request_mark_paid"),
    # Expenses
    path("expenses/", v.expense_list, name="expense_list"),
    path("expenses/<int:pk>/", v.expense_detail, name="expense_detail"),

    # Salaries
    path("salaries/", v.salary_list, name="salary_list"),
    path("salaries/<int:pk>/", v.salary_detail, name="salary_detail"),

    # Requisitions
    path("requisitions/", v.requisition_list, name="requisition_list"),
    path("requisitions/<int:pk>/", v.requisition_detail, name="requisition_detail"),
]
