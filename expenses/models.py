from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


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
        return self.exclude(
            models.Q(finance_status=ExpenseRequest.ApprovalStatus.REJECTED)
            | models.Q(admin_status=ExpenseRequest.ApprovalStatus.REJECTED)
            | (
                models.Q(finance_status=ExpenseRequest.ApprovalStatus.APPROVED)
                & models.Q(admin_status=ExpenseRequest.ApprovalStatus.APPROVED)
            )
        )


# ------------------------------ Main model -----------------------------------

class ExpenseRequest(models.Model):
    # Expense category choices (order here is how they’ll show in the select)
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

    # Request metadata
    reference = models.CharField(max_length=20, unique=True, editable=False)  # e.g. EXP-2025-000123
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="expense_requests",
    )

    # Replaces the old FK: now a CharField with choices
    expense_type = models.CharField(
        max_length=40,
        choices=ExpenseCategory.choices,
    )

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

    description = models.TextField()
    business_reason = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)

    # Dual approvals
    finance_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    finance_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="finance_approved_expenses",
    )
    finance_decision_at = models.DateTimeField(null=True, blank=True)
    finance_note = models.TextField(blank=True, default="")

    admin_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    admin_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="admin_approved_expenses",
    )
    admin_decision_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True, default="")

    # Payment info
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.NOT_PAID
    )
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    paid_at = models.DateTimeField(null=True, blank=True)
    receipt_number = models.CharField(max_length=40, blank=True, default="")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Convenience
    requires_admin_approval = models.BooleanField(
        default=False,
        help_text="Auto-true for bank transfers, can be used by workflows/guards.",
    )

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
        # Use display label for the category
        label = self.get_expense_type_display()
        amt = f"{int(self.amount):,}" if self.amount == self.amount.to_integral() else f"{self.amount:,.2f}"
        return f"{label} Request - UGX {amt}"

    # --------- Domain actions ---------

    def mark_finance_decision(self, reviewer, status: str, note: str = ""):
        assert status in self.ApprovalStatus.values
        self.finance_status = status
        self.finance_reviewer = reviewer
        self.finance_decision_at = timezone.now()
        self.finance_note = note
        ApprovalLog.objects.create(
            expense=self, role=ApprovalLog.Role.FINANCE, status=status, note=note, acted_by=reviewer
        )
        self.save(update_fields=[
            "finance_status", "finance_reviewer", "finance_decision_at", "finance_note", "updated_at"
        ])

    def mark_admin_decision(self, reviewer, status: str, note: str = ""):
        assert status in self.ApprovalStatus.values
        self.admin_status = status
        self.admin_reviewer = reviewer
        self.admin_decision_at = timezone.now()
        self.admin_note = note
        ApprovalLog.objects.create(
            expense=self, role=ApprovalLog.Role.ADMIN, status=status, note=note, acted_by=reviewer
        )
        self.save(update_fields=[
            "admin_status", "admin_reviewer", "admin_decision_at", "admin_note", "updated_at"
        ])

    def register_payment(
        self,
        amount: Decimal,
        method: str | None = None,
        receipt_number: str | None = None,
        paid_at: timezone.datetime | None = None,
    ):
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
        self.save(update_fields=[
            "payment_method", "paid_amount", "payment_status", "receipt_number", "paid_at", "updated_at"
        ])

    # --------- Lifecycle ---------

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            last = ExpenseRequest.objects.filter(reference__startswith=f"EXP-{year}-").order_by("-reference").first()
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
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expense_approval_actions")
    acted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acted_at"]

    def __str__(self) -> str:
        return f"{self.expense.reference} · {self.role} · {self.status}"


class ExpenseAttachment(models.Model):
    expense = models.ForeignKey(ExpenseRequest, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="expense_attachments/%Y/%m/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.expense.reference} · {self.file.name}"
