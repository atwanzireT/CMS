from django.urls import path
from . import views

app_name = "expenses"

urlpatterns = [
    # Global expenses listing (admin/finance overview)
    path("", views.expenses_all, name="expenses_all"),

    # User's own expense requests
    path("list/", views.expense_list, name="expense_list"),
    path("<int:pk>/", views.expense_detail, name="expense_detail"),

    # Inboxes
    path("inbox/finance/", views.finance_inbox, name="finance_inbox"),
    path("inbox/admin/", views.admin_inbox, name="admin_inbox"),

    # Actions
    path("<int:pk>/finance-decide/", views.finance_decide, name="finance_decide"),
    path("<int:pk>/admin-decide/", views.admin_decide, name="admin_decide"),
    path("<int:pk>/pay/", views.expense_pay, name="expense_pay"),
]
