from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from typing import Optional
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.permissions import module_required

User = get_user_model()


UGX = "UGX"


# ----------------------------- QuerySet helpers ------------------------------

class ExpenseRequestQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(requested_by=user)

    def fully_approved(self):
        return self.filter(
            finance_status=ExpenseRequest.ApprovalStatus.APPROVED,
            admin_status=ExpenseRequest.ApprovalStatus.APPROVED,
        )

    def rejected(self):
        return self.filter(
            models.Q(finance_status=ExpenseRequest.ApprovalStatus.REJECTED)
            | models.Q(admin_status=ExpenseRequest.ApprovalStatus.REJECTED)
        )

    def pending(self):
        # Anything not rejected and not fully approved
        return self.exclude(
            models.Q(finance_status=ExpenseRequest.ApprovalStatus.REJECTED)
            | models.Q(admin_status=ExpenseRequest.ApprovalStatus.REJECTED)
            | (
                models.Q(finance_status=ExpenseRequest.ApprovalStatus.APPROVED)
                & models.Q(admin_status=ExpenseRequest.ApprovalStatus.APPROVED)
            )
        )

    def finance_inbox(self):
        return self.filter(finance_status=ExpenseRequest.ApprovalStatus.PENDING)

    def admin_inbox(self):
        return self.filter(admin_status=ExpenseRequest.ApprovalStatus.PENDING)


# ------------------------------ Main model -----------------------------------

class ExpenseRequest(models.Model):
    # Expense category choices (order controls select display)
    class ExpenseCategory(models.TextChoices):
        AIRTIME_DATA = "AIRTIME_DATA", "Airtime/Data"
        OVERTIME_PAYMENT = "OVERTIME_PAYMENT", "Overtime Payment"
        FIELD_OPERATIONS = "FIELD_OPERATIONS", "Field Operations"
        TRANSPORT_FUEL = "TRANSPORT_FUEL", "Transport/Fuel"
        OFFICE_SUPPLIES = "OFFICE_SUPPLIES", "Office Supplies"
        MEALS_REFRESHMENTS = "MEALS_REFRESHMENTS", "Meals/Refreshments"
        ACCOMMODATION = "ACCOMMODATION", "Accommodation"
        EQUIP_VEH_MAINT = "EQUIP_VEH_MAINT", "Equipment/Vehicle Maintenance"
        UTILITIES_PAYMENT = "UTILITIES_PAYMENT", "Utilities Payment"
        OTHER_EXPENSES = "OTHER_EXPENSES", "Other Expenses"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        CHEQUE = "CHEQUE", "Cheque"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        MOBILE_MONEY = "MOBILE_MONEY", "Mobile money"

    class PaymentStatus(models.TextChoices):
        NOT_PAID = "NOT_PAID", "Not paid"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"

    # Core
    reference = models.CharField(max_length=20, unique=True, editable=False)  # e.g. EXP-2025-000123
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expense_requests"
    )
    expense_type = models.CharField(max_length=40, choices=ExpenseCategory.choices)

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("2000"))],  # Minimum UGX 2,000
        help_text="Minimum: UGX 2,000",
    )
    currency = models.CharField(max_length=3, default=UGX, editable=False)

    phone_msisdn = models.CharField(
        max_length=15,
        help_text="Mobile money number (E.164 or local e.g. 0700xxxxxx)",
        validators=[RegexValidator(r"^\+?\d{9,15}$", "Enter a valid phone number.")],
    )

    # NOTE: 'description' removed as requested
    business_reason = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)

    # Dual approvals
    finance_status = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    finance_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="finance_approved_expenses",
    )
    finance_decision_at = models.DateTimeField(null=True, blank=True)
    finance_note = models.TextField(blank=True, default="")

    admin_status = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    admin_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="admin_approved_expenses",
    )
    admin_decision_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True, default="")

    # Payment info
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.NOT_PAID)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    paid_at = models.DateTimeField(null=True, blank=True)
    receipt_number = models.CharField(max_length=40, blank=True, default="")

    # Convenience
    requires_admin_approval = models.BooleanField(
        default=False, help_text="Auto-true for bank transfers; usable by workflows/guards."
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ExpenseRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["finance_status", "admin_status"]),
            models.Index(fields=["requested_by", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=Decimal("2000")), name="expense_amount_min_2000"
            ),
            models.CheckConstraint(
                check=models.Q(paid_amount__gte=Decimal("0.00")), name="expense_paid_amount_nonneg"
            ),
            models.CheckConstraint(
                check=models.Q(paid_amount__lte=models.F("amount")),
                name="expense_paid_amount_lte_amount",
            ),
        ]
        verbose_name = "Expense Request"
        verbose_name_plural = "Expense Requests"

    # --------- Derived helpers ---------

    @property
    def is_fully_approved(self) -> bool:
        return (
            self.finance_status == self.ApprovalStatus.APPROVED
            and self.admin_status == self.ApprovalStatus.APPROVED
        )

    @property
    def overall_status(self) -> str:
        if self.finance_status == self.ApprovalStatus.REJECTED or self.admin_status == self.ApprovalStatus.REJECTED:
            return "Rejected"
        if self.is_fully_approved:
            return "Fully Approved"
        if self.finance_status == self.ApprovalStatus.APPROVED or self.admin_status == self.ApprovalStatus.APPROVED:
            return "Partially Approved"
        return "Pending"

    @property
    def title(self) -> str:
        label = self.get_expense_type_display()
        amt = f"{int(self.amount):,}" if self.amount == self.amount.to_integral() else f"{self.amount:,.2f}"
        return f"{label} Request - UGX {amt}"

    # --------- Validation & domain actions ---------

    def clean(self):
        # Paid amount integrity (extra safety over DB constraints)
        if self.paid_amount and self.paid_amount < 0:
            raise ValidationError("Paid amount cannot be negative.")
        if self.paid_amount and self.paid_amount > self.amount:
            raise ValidationError("Paid amount cannot exceed requested amount.")

        # No payment status changes unless fully approved
        if (self.paid_amount and self.paid_amount > 0) or (self.payment_status != self.PaymentStatus.NOT_PAID):
            if not self.is_fully_approved:
                raise ValidationError("Payments are only allowed after Admin AND Finance approvals.")

    def _assert_valid_transition(self, new_status: str):
        if new_status not in self.ApprovalStatus.values:
            raise ValidationError("Invalid status.")

    def mark_finance_decision(self, reviewer, status: str, note: str = ""):
        self._assert_valid_transition(status)
        if not reviewer.has_perm("accounts.access_finance"):
            raise PermissionDenied("You do not have permission to act as Finance.")
        self.finance_status = status
        self.finance_reviewer = reviewer
        self.finance_decision_at = timezone.now()
        self.finance_note = note
        ApprovalLog.objects.create(
            expense=self, role=ApprovalLog.Role.FINANCE, status=status, note=note, acted_by=reviewer
        )
        self.full_clean()
        self.save(update_fields=["finance_status", "finance_reviewer", "finance_decision_at", "finance_note", "updated_at"])

    def mark_admin_decision(self, reviewer, status: str, note: str = ""):
        self._assert_valid_transition(status)
        # Adjust this permission to your project's "admin" policy
        if not (reviewer.is_superuser or reviewer.has_perm("accounts.access_expenses")):
            raise PermissionDenied("You do not have permission to act as Admin.")
        self.admin_status = status
        self.admin_reviewer = reviewer
        self.admin_decision_at = timezone.now()
        self.admin_note = note
        ApprovalLog.objects.create(
            expense=self, role=ApprovalLog.Role.ADMIN, status=status, note=note, acted_by=reviewer
        )
        self.full_clean()
        self.save(update_fields=["admin_status", "admin_reviewer", "admin_decision_at", "admin_note", "updated_at"])

    def register_payment(
        self,
        amount: Decimal,
        method: str | None = None,
        receipt_number: str | None = None,
        paid_at: timezone.datetime | None = None,
    ):
        if not self.is_fully_approved:
            raise ValidationError("Cannot register payment before Admin AND Finance approvals.")
        if Decimal(amount) <= 0:
            raise ValidationError("Payment amount must be positive.")

        if method:
            self.payment_method = method

        self.paid_amount = (self.paid_amount or Decimal("0")) + Decimal(amount)
        self.payment_status = (
            self.PaymentStatus.PAID
            if self.paid_amount >= self.amount
            else self.PaymentStatus.PARTIALLY_PAID
        )
        self.receipt_number = receipt_number or self.receipt_number
        self.paid_at = paid_at or timezone.now()

        self.full_clean()
        self.save(update_fields=["payment_method", "paid_amount", "payment_status", "receipt_number", "paid_at", "updated_at"])

    # --------- Lifecycle ---------

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            # Race-safe sequence per year
            with transaction.atomic():
                last = (
                    ExpenseRequest.objects.select_for_update()
                    .filter(reference__startswith=f"EXP-{year}-")
                    .order_by("-reference")
                    .first()
                )
                next_num = int(last.reference.split("-")[-1]) + 1 if last else 1
                self.reference = f"EXP-{year}-{next_num:06d}"

        self.requires_admin_approval = self.payment_method == self.PaymentMethod.BANK_TRANSFER
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.reference} · {self.title}"


# ------------------------- Audit log & attachments ---------------------------

class ApprovalLog(models.Model):
    class Role(models.TextChoices):
        FINANCE = "FINANCE", "Finance"
        ADMIN = "ADMIN", "Admin"

    expense = models.ForeignKey(ExpenseRequest, on_delete=models.CASCADE, related_name="approval_logs")
    role = models.CharField(max_length=10, choices=Role.choices)
    status = models.CharField(max_length=10, choices=ExpenseRequest.ApprovalStatus.choices)
    note = models.TextField(blank=True, default="")
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expense_approval_actions"
    )
    acted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acted_at"]
        verbose_name = "Approval Log"
        verbose_name_plural = "Approval Logs"

    def __str__(self) -> str:
        return f"{self.expense.reference} · {self.role} · {self.status}"


class ExpenseAttachment(models.Model):
    expense = models.ForeignKey(ExpenseRequest, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="expense_attachments/%Y/%m/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Expense Attachment"
        verbose_name_plural = "Expense Attachments"

    def __str__(self) -> str:
        return f"{self.expense.reference} · {self.file.name}"


def _parse_decimal(val: Optional[str]) -> Optional[Decimal]:
    if not val:
        return None
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        return None


@login_required
@module_required("access_expenses")  # or a more restrictive perm, if you prefer
def expenses_all(request):
    """
    Global expense listing (for Finance/Admin).
    - Filters via GET:
        q=search (reference / expense_type / business_reason / requester)
        category (expense_type value)
        priority (LOW/NORMAL/HIGH/URGENT)
        finance_status (PENDING/APPROVED/REJECTED)
        admin_status (PENDING/APPROVED/REJECTED)
        payment_status (NOT_PAID/PARTIALLY_PAID/PAID)
        payment_method (CASH/CHEQUE/BANK_TRANSFER/MOBILE_MONEY)
        requester (user id)
        date_from (YYYY-MM-DD), date_to (YYYY-MM-DD)
        min_amount, max_amount (numbers)
        requires_admin (true/false)
        export=csv  -> exports current filtered set
    """
    qs = (
        ExpenseRequest.objects
        .select_related("requested_by", "finance_reviewer", "admin_reviewer")
        .order_by("-created_at")
    )

    # ---- Filters -------------------------------------------------------------
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(expense_type__icontains=q.replace(" ", "_"))
            | Q(business_reason__icontains=q)
            | Q(requested_by__username__icontains=q)
            | Q(requested_by__first_name__icontains=q)
            | Q(requested_by__last_name__icontains=q)
        )

    category = request.GET.get("category")
    if category:
        qs = qs.filter(expense_type=category)

    priority = request.GET.get("priority")
    if priority:
        qs = qs.filter(priority=priority)

    finance_status = request.GET.get("finance_status")
    if finance_status:
        qs = qs.filter(finance_status=finance_status)

    admin_status = request.GET.get("admin_status")
    if admin_status:
        qs = qs.filter(admin_status=admin_status)

    payment_status = request.GET.get("payment_status")
    if payment_status:
        qs = qs.filter(payment_status=payment_status)

    payment_method = request.GET.get("payment_method")
    if payment_method:
        qs = qs.filter(payment_method=payment_method)

    requester = request.GET.get("requester")
    if requester:
        qs = qs.filter(requested_by_id=requester)

    requires_admin = request.GET.get("requires_admin")
    if requires_admin in {"true", "false"}:
        qs = qs.filter(requires_admin_approval=(requires_admin == "true"))

    date_from = parse_date(request.GET.get("date_from") or "")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = parse_date(request.GET.get("date_to") or "")
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    min_amount = _parse_decimal(request.GET.get("min_amount"))
    if min_amount is not None:
        qs = qs.filter(amount__gte=min_amount)

    max_amount = _parse_decimal(request.GET.get("max_amount"))
    if max_amount is not None:
        qs = qs.filter(amount__lte=max_amount)

    # ---- CSV export ----------------------------------------------------------
    if request.GET.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="expenses.csv"'
        writer = csv.writer(resp)
        writer.writerow([
            "Reference", "Type", "Amount(UGX)", "Priority",
            "Finance Status", "Admin Status",
            "Payment Status", "Payment Method",
            "Requester", "Created At", "Business Reason"
        ])
        for e in qs:
            writer.writerow([
                e.reference,
                e.get_expense_type_display(),
                f"{e.amount:.0f}",
                e.get_priority_display(),
                e.get_finance_status_display(),
                e.get_admin_status_display(),
                e.get_payment_status_display(),
                e.get_payment_method_display(),
                getattr(e.requested_by, "get_full_name", lambda: e.requested_by.username)() or e.requested_by.username,
                e.created_at.strftime("%Y-%m-%d %H:%M"),
                (e.business_reason or "").replace("\n", " ").strip(),
            ])
        return resp

    # ---- Pagination ----------------------------------------------------------
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Requester options for the filter form
    requester_options = User.objects.filter(expense_requests__isnull=False).distinct().order_by("first_name", "last_name", "username")

    context = {
        "page_obj": page_obj,
        "total": qs.count(),
        "requester_options": requester_options,
        "filters": {
            "q": q,
            "category": category,
            "priority": priority,
            "finance_status": finance_status,
            "admin_status": admin_status,
            "payment_status": payment_status,
            "payment_method": payment_method,
            "requester": requester,
            "date_from": request.GET.get("date_from") or "",
            "date_to": request.GET.get("date_to") or "",
            "min_amount": request.GET.get("min_amount") or "",
            "max_amount": request.GET.get("max_amount") or "",
            "requires_admin": requires_admin or "",
        },
        "choices": {
            "categories": ExpenseRequest.ExpenseCategory.choices,
            "priorities": ExpenseRequest.Priority.choices,
            "approval": ExpenseRequest.ApprovalStatus.choices,
            "payment_statuses": ExpenseRequest.PaymentStatus.choices,
            "payment_methods": ExpenseRequest.PaymentMethod.choices,
        },
    }
    return render(request, "expenses_all.html", context)
