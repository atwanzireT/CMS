# apps/finance/admin.py
from __future__ import annotations

from decimal import Decimal
from django.contrib import admin, messages
from django.contrib.admin.filters import DateFieldListFilter
from django.utils import timezone

from .models import ExpenseRequest, ApprovalLog, ExpenseAttachment


# ------------------------- Inlines -------------------------

class ExpenseAttachmentInline(admin.TabularInline):
    model = ExpenseAttachment
    extra = 0
    fields = ("file", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_at",)


class ApprovalLogInline(admin.TabularInline):
    model = ApprovalLog
    extra = 0
    fields = ("acted_at", "role", "status", "acted_by", "note")
    readonly_fields = ("acted_at", "role", "status", "acted_by", "note")
    can_delete = False


# ------------------------- Actions -------------------------

@admin.action(description="Finance: Approve selected")
def action_finance_approve(modeladmin, request, queryset):
    n = 0
    for obj in queryset:
        obj.mark_finance_decision(
            reviewer=request.user,
            status=ExpenseRequest.ApprovalStatus.APPROVED,
            note="Approved via admin action",
        )
        n += 1
    messages.success(request, f"Finance approved {n} expense(s).")


@admin.action(description="Finance: Reject selected")
def action_finance_reject(modeladmin, request, queryset):
    n = 0
    for obj in queryset:
        obj.mark_finance_decision(
            reviewer=request.user,
            status=ExpenseRequest.ApprovalStatus.REJECTED,
            note="Rejected via admin action",
        )
        n += 1
    messages.warning(request, f"Finance rejected {n} expense(s).")


@admin.action(description="Admin: Approve selected")
def action_admin_approve(modeladmin, request, queryset):
    n = 0
    for obj in queryset:
        obj.mark_admin_decision(
            reviewer=request.user,
            status=ExpenseRequest.ApprovalStatus.APPROVED,
            note="Approved via admin action",
        )
        n += 1
    messages.success(request, f"Admin approved {n} expense(s).")


@admin.action(description="Admin: Reject selected")
def action_admin_reject(modeladmin, request, queryset):
    n = 0
    for obj in queryset:
        obj.mark_admin_decision(
            reviewer=request.user,
            status=ExpenseRequest.ApprovalStatus.REJECTED,
            note="Rejected via admin action",
        )
        n += 1
    messages.warning(request, f"Admin rejected {n} expense(s).")


@admin.action(description="Mark as fully paid (set paid_amount = amount)")
def action_mark_fully_paid(modeladmin, request, queryset):
    n = 0
    for obj in queryset:
        delta = (obj.amount or Decimal("0")) - (obj.paid_amount or Decimal("0"))
        if delta > 0:
            obj.register_payment(amount=delta)  # keeps method, sets paid_at, status
            n += 1
    messages.success(request, f"Marked {n} expense(s) as fully paid.")


# ------------------------- ModelAdmins -------------------------

@admin.register(ExpenseRequest)
class ExpenseRequestAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = (
        "reference",
        "get_expense_label",
        "amount",
        "requested_by",
        "finance_status",
        "admin_status",
        "payment_status",
        "created_at",
    )
    list_filter = (
        "expense_type",                # choices field
        "priority",
        "finance_status",
        "admin_status",
        "payment_status",
        ("created_at", DateFieldListFilter),
    )
    search_fields = (
        "reference",
        "description",
        "business_reason",
        "phone_msisdn",
        "requested_by__username",
        "requested_by__first_name",
        "requested_by__last_name",
    )
    readonly_fields = (
        "reference",
        "created_at",
        "updated_at",
        "finance_decision_at",
        "admin_decision_at",
        "requires_admin_approval",
        "overall_status_display",
        "title_preview",
    )
    fields = (
        ("reference", "created_at", "updated_at"),
        ("requested_by", "expense_type", "priority"),
        ("amount", "currency", "payment_method"),
        ("phone_msisdn",),
        "description",
        "business_reason",
        "title_preview",
        "overall_status_display",
        # Approvals
        ("finance_status", "finance_reviewer", "finance_decision_at"),
        "finance_note",
        ("admin_status", "admin_reviewer", "admin_decision_at"),
        "admin_note",
        # Payment
        ("payment_status", "paid_amount", "paid_at", "receipt_number"),
        "requires_admin_approval",
    )
    inlines = [ExpenseAttachmentInline, ApprovalLogInline]
    actions = [
        action_finance_approve,
        action_finance_reject,
        action_admin_approve,
        action_admin_reject,
        action_mark_fully_paid,
    ]
    autocomplete_fields = ("requested_by", "finance_reviewer", "admin_reviewer")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("requested_by")

    @admin.display(description="Expense Type")
    def get_expense_label(self, obj: ExpenseRequest):
        return obj.get_expense_type_display()

    @admin.display(description="Overall Status")
    def overall_status_display(self, obj: ExpenseRequest):
        return obj.overall_status

    @admin.display(description="Title Preview")
    def title_preview(self, obj: ExpenseRequest):
        return obj.title

    def save_model(self, request, obj: ExpenseRequest, form, change):
        # If created from admin and requested_by not set, default to current user
        if not change and not obj.requested_by_id:
            obj.requested_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    date_hierarchy = "acted_at"
    list_display = ("expense", "role", "status", "acted_by", "acted_at")
    list_filter = ("role", "status", ("acted_at", DateFieldListFilter))
    search_fields = ("expense__reference", "acted_by__username", "note")
    autocomplete_fields = ("expense", "acted_by")
    ordering = ("-acted_at",)


@admin.register(ExpenseAttachment)
class ExpenseAttachmentAdmin(admin.ModelAdmin):
    date_hierarchy = "uploaded_at"
    list_display = ("expense", "file", "uploaded_by", "uploaded_at")
    list_filter = (("uploaded_at", DateFieldListFilter),)
    search_fields = ("expense__reference", "file")
    autocomplete_fields = ("expense", "uploaded_by")
    ordering = ("-uploaded_at",)
