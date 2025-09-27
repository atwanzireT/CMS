from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expenses_all, name='expenses_all'),
    # Core
    path("expense/", views.expense_list, name="expense_list"),
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),

    # Inboxes
    path("expenses/inbox/finance/", views.finance_inbox, name="finance_inbox"),
    path("expenses/inbox/admin/", views.admin_inbox, name="admin_inbox"),

    # Actions
    path("expenses/<int:pk>/finance-decide/", views.finance_decide, name="finance_decide"),
    path("expenses/<int:pk>/admin-decide/", views.admin_decide, name="admin_decide"),
    path("expenses/<int:pk>/pay/", views.expense_pay, name="expense_pay"),
]
