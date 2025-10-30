# expenses/admin.py
from django.contrib import admin
from .models import ExpenseRequest, SalaryRequest


class ExpenseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "requester",
        "category",
        "amount",
        "finance_status",
        "admin_status",
        "is_paid",
        "created_at",
    )
    list_filter = (
        "category",
        "finance_status",
        "admin_status",
        "is_paid",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "reference",
        "description",
        "requester__username",
        "requester__first_name",
        "requester__last_name",
        "phone_number",
    )
    autocomplete_fields = ("requester",)
    readonly_fields = (
        "reference",
        "overall_status",
        "created_at",
        "updated_at",
        "paid_at",
    )

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "reference",
                "requester",
                "created_at",
                "updated_at",
            )
        }),
        ("Expense Details", {
            "fields": (
                "category",
                "amount",
                "description",
                "phone_number",
            )
        }),
        ("Approval Status", {
            "fields": (
                "finance_status",
                "admin_status",
                "overall_status",
            )
        }),
        ("Payment Status", {
            "fields": (
                "is_paid",
                "paid_at",
            )
        }),
    )

    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    # Add action methods for bulk operations
    actions = ['approve_finance_selected', 'approve_admin_selected', 'mark_as_paid_selected']

    def approve_finance_selected(self, request, queryset):
        for expense in queryset:
            if expense.finance_status == ExpenseRequest.Approval.PENDING:
                expense.approve_finance()
        self.message_user(request, f"Finance approval processed for {queryset.count()} expenses.")

    def approve_admin_selected(self, request, queryset):
        for expense in queryset:
            if expense.admin_status == ExpenseRequest.Approval.PENDING:
                expense.approve_admin()
        self.message_user(request, f"Admin approval processed for {queryset.count()} expenses.")

    def mark_as_paid_selected(self, request, queryset):
        count = 0
        for expense in queryset:
            if (expense.finance_status == ExpenseRequest.Approval.APPROVED and 
                expense.admin_status == ExpenseRequest.Approval.APPROVED and
                not expense.is_paid):
                expense.mark_as_paid()
                count += 1
        self.message_user(request, f"Marked {count} expenses as paid.")


class SalaryRequestAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "employee",
        "payment_type",
        "amount",
        "month",
        "finance_status",
        "admin_status",
        "is_paid",
        "created_at",
    )
    list_filter = (
        "payment_type",
        "finance_status",
        "admin_status",
        "is_paid",
        "month",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "reference",
        "reason",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
        "phone_number",
    )
    autocomplete_fields = ("employee",)
    readonly_fields = (
        "reference",
        "overall_status",
        "created_at",
        "updated_at",
        "paid_at",
    )

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "reference",
                "employee",
                "created_at",
                "updated_at",
            )
        }),
        ("Salary Request Details", {
            "fields": (
                "payment_type",
                "amount",
                "reason",
                "phone_number",
                "month",
            )
        }),
        ("Approval Status", {
            "fields": (
                "finance_status",
                "admin_status",
                "overall_status",
            )
        }),
        ("Payment Status", {
            "fields": (
                "is_paid",
                "paid_at",
            )
        }),
    )

    ordering = ("-month", "-created_at")
    date_hierarchy = "created_at"

    # Add action methods for bulk operations
    actions = ['approve_finance_selected', 'approve_admin_selected', 'mark_as_paid_selected']

    def approve_finance_selected(self, request, queryset):
        for salary in queryset:
            if salary.finance_status == SalaryRequest.Approval.PENDING:
                salary.approve_finance()
        self.message_user(request, f"Finance approval processed for {queryset.count()} salary requests.")

    def approve_admin_selected(self, request, queryset):
        for salary in queryset:
            if salary.admin_status == SalaryRequest.Approval.PENDING:
                salary.approve_admin()
        self.message_user(request, f"Admin approval processed for {queryset.count()} salary requests.")

    def mark_as_paid_selected(self, request, queryset):
        count = 0
        for salary in queryset:
            if (salary.finance_status == SalaryRequest.Approval.APPROVED and 
                salary.admin_status == SalaryRequest.Approval.APPROVED and
                not salary.is_paid):
                salary.mark_as_paid()
                count += 1
        self.message_user(request, f"Marked {count} salary requests as paid.")


# Register your models
admin.site.register(ExpenseRequest, ExpenseRequestAdmin)
admin.site.register(SalaryRequest, SalaryRequestAdmin)