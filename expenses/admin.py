from django.contrib import admin
from .models import ExpenseRequest, ApprovalLog, ExpenseAttachment


class ExpenseAttachmentInline(admin.TabularInline):
    model = ExpenseAttachment
    extra = 0
    autocomplete_fields = ("uploaded_by",)
    readonly_fields = ("uploaded_at",)


class ApprovalLogInline(admin.TabularInline):
    model = ApprovalLog
    extra = 0
    autocomplete_fields = ("acted_by",)
    readonly_fields = ("acted_at",)
    can_delete = False


@admin.register(ExpenseRequest)
class ExpenseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "requested_by",
        "expense_type",
        "amount",
        "overall_status",
        "payment_status",
        "created_at",
    )
    list_filter = (
        "expense_type",
        "priority",
        "finance_status",
        "admin_status",
        "payment_status",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "reference",
        "business_reason",  # description removed
        "requested_by__username",
        "requested_by__first_name",
        "requested_by__last_name",
        "phone_msisdn",
    )
    autocomplete_fields = ("requested_by", "finance_reviewer", "admin_reviewer")
    inlines = [ApprovalLogInline, ExpenseAttachmentInline]

    # IMPORTANT: include 'currency' in readonly_fields to avoid FieldError
    readonly_fields = (
        "reference",
        "currency",
        "overall_status",
        "requires_admin_approval",
        "paid_amount",
        "paid_at",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Meta", {
            "fields": (
                "reference",
                ("requested_by", "created_at", "updated_at"),
            )
        }),
        ("Expense", {
            "fields": (
                "expense_type",
                "amount",
                "currency",          # read-only
                "priority",
                "business_reason",   # description removed
                "phone_msisdn",
            )
        }),
        ("Approvals", {
            "fields": (
                ("finance_status", "finance_reviewer", "finance_decision_at"),
                "finance_note",
                ("admin_status", "admin_reviewer", "admin_decision_at"),
                "admin_note",
                "requires_admin_approval",
                "overall_status",
            )
        }),
        ("Payment", {
            "fields": (
                "payment_method",
                "payment_status",
                "paid_amount",
                "paid_at",
                "receipt_number",
            )
        }),
    )

    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    list_display = ("expense", "role", "status", "acted_by", "acted_at")
    list_filter = ("role", "status", ("acted_at", admin.DateFieldListFilter))
    search_fields = ("expense__reference", "note", "acted_by__username")
    autocomplete_fields = ("expense", "acted_by")
    ordering = ("-acted_at",)


@admin.register(ExpenseAttachment)
class ExpenseAttachmentAdmin(admin.ModelAdmin):
    list_display = ("expense", "file", "uploaded_by", "uploaded_at")
    list_filter = (("uploaded_at", admin.DateFieldListFilter),)
    search_fields = ("expense__reference", "file")
    autocomplete_fields = ("expense", "uploaded_by")
    ordering = ("-uploaded_at",)
