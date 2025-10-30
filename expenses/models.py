# expenses/models.py
from __future__ import annotations

from decimal import Decimal

from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone

User = get_user_model()
PHONE = RegexValidator(r"^\+?\d{9,15}$", "Enter a valid phone number (9–15 digits).")


# -----------------------------------------------------------------------------
# ExpenseRequest (simple, dual-approval + paid boolean)
# -----------------------------------------------------------------------------
class ExpenseRequest(models.Model):
    class Approval(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class Category(models.TextChoices):
        AIRTIME_DATA = "AIRTIME_DATA", "Airtime/Data"
        TRANSPORT_FUEL = "TRANSPORT_FUEL", "Transport/Fuel"
        OFFICE_SUPPLIES = "OFFICE_SUPPLIES", "Office Supplies"
        MEALS_REFRESHMENTS = "MEALS_REFRESHMENTS", "Meals/Refreshments"
        ACCOMMODATION = "ACCOMMODATION", "Accommodation"
        OTHER = "OTHER", "Other Expenses"

    reference     = models.CharField(max_length=20, unique=True, editable=False)   # EXP-YYYY-000001
    requester  = models.ForeignKey(User, on_delete=models.PROTECT, related_name="expenses")

    category      = models.CharField(max_length=32, choices=Category.choices)
    amount        = models.DecimalField(max_digits=12, decimal_places=2,
                                        validators=[MinValueValidator(Decimal("2000"))])
    description   = models.TextField()
    phone_number  = models.CharField(max_length=15, validators=[PHONE])

    finance_status = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)
    admin_status   = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)

    is_paid       = models.BooleanField(default=False)
    paid_at       = models.DateTimeField(null=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes  = [models.Index(fields=["created_at"]), models.Index(fields=["reference"])]

    # ---------- tiny helpers ----------
    def __str__(self) -> str:
        return f"{self.reference} · {self.get_category_display()} · UGX {int(self.amount):,}"

    @property
    def overall_status(self) -> str:
        if self.finance_status == self.Approval.REJECTED or self.admin_status == self.Approval.REJECTED:
            return "Rejected"
        if self.finance_status == self.Approval.APPROVED and self.admin_status == self.Approval.APPROVED:
            return "Fully Approved" if not self.is_paid else "Paid"
        if self.finance_status == self.Approval.APPROVED or self.admin_status == self.Approval.APPROVED:
            return "Partially Approved"
        return "Pending"

    # ---------- lifecycle ----------
    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            with transaction.atomic():
                last = (
                    ExpenseRequest.objects.select_for_update()
                    .filter(reference__startswith=f"EXP-{year}-")
                    .order_by("-reference")
                    .first()
                )
                n = int(last.reference.split("-")[-1]) + 1 if last else 1
                self.reference = f"EXP-{year}-{n:06d}"
        super().save(*args, **kwargs)

    # ---------- simple workflow ----------
    def approve_finance(self): self._set_finance(self.Approval.APPROVED)
    def reject_finance(self):  self._set_finance(self.Approval.REJECTED)
    def approve_admin(self):   self._set_admin(self.Approval.APPROVED)
    def reject_admin(self):    self._set_admin(self.Approval.REJECTED)

    def _set_finance(self, status):
        self.finance_status = status
        self.save(update_fields=["finance_status", "updated_at"])

    def _set_admin(self, status):
        self.admin_status = status
        self.save(update_fields=["admin_status", "updated_at"])

    def mark_as_paid(self):
        """Only after both approvals; sets a boolean and timestamp—nothing fancy."""
        if not (self.finance_status == self.Approval.APPROVED and self.admin_status == self.Approval.APPROVED):
            raise ValueError("Needs both Finance and Admin approvals before payment.")
        self.is_paid = True
        self.paid_at = timezone.now()
        self.save(update_fields=["is_paid", "paid_at", "updated_at"])


# -----------------------------------------------------------------------------
# SalaryRequest (simple, same pattern; month normalized to 1st)
# -----------------------------------------------------------------------------
class SalaryRequest(models.Model):
    class PaymentType(models.TextChoices):
        MID_SALARY       = "MID_SALARY", "Mid Salary"
        EMERGENCY_SALARY = "EMERGENCY_SALARY", "Emergency Salary"

    class Approval(models.TextChoices):
        PENDING  = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    reference    = models.CharField(max_length=20, unique=True, editable=False)    # SAL-YYYY-000001
    employee     = models.ForeignKey(User, on_delete=models.PROTECT, related_name="salary_requests")

    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    amount       = models.DecimalField(max_digits=12, decimal_places=2,
                                       validators=[MinValueValidator(Decimal("10000"))])
    phone_number = models.CharField(max_length=15, validators=[PHONE])
    reason       = models.TextField()
    month        = models.DateField(help_text="Normalized to the first day of the month.")

    finance_status = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)
    admin_status   = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)

    is_paid     = models.BooleanField(default=False)
    paid_at     = models.DateTimeField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "-created_at"]
        indexes  = [models.Index(fields=["employee", "month"]), models.Index(fields=["reference"])]
        # Keep the simplest uniqueness rule (reject duplicates explicitly if needed)
        unique_together = ("employee", "payment_type", "month")

    # ---------- tiny helpers ----------
    def __str__(self) -> str:
        return f"{self.reference} · {self.get_payment_type_display()} · UGX {int(self.amount):,}"

    @property
    def overall_status(self) -> str:
        if self.finance_status == self.Approval.REJECTED or self.admin_status == self.Approval.REJECTED:
            return "Rejected"
        if self.is_paid:
            return "Paid"
        if self.finance_status == self.Approval.APPROVED and self.admin_status == self.Approval.APPROVED:
            return "Fully Approved"
        if self.finance_status == self.Approval.APPROVED or self.admin_status == self.Approval.APPROVED:
            return "Partially Approved"
        return "Pending"

    # ---------- lifecycle ----------
    def save(self, *args, **kwargs):
        # normalize month to the first day
        if self.month:
            self.month = self.month.replace(day=1)
        if not self.reference:
            year = timezone.now().year
            with transaction.atomic():
                last = (
                    SalaryRequest.objects.select_for_update()
                    .filter(reference__startswith=f"SAL-{year}-")
                    .order_by("-reference")
                    .first()
                )
                n = int(last.reference.split("-")[-1]) + 1 if last else 1
                self.reference = f"SAL-{year}-{n:06d}"
        super().save(*args, **kwargs)

    # ---------- simple workflow ----------
    def approve_finance(self): self._set_finance(self.Approval.APPROVED)
    def reject_finance(self):  self._set_finance(self.Approval.REJECTED)
    def approve_admin(self):   self._set_admin(self.Approval.APPROVED)
    def reject_admin(self):    self._set_admin(self.Approval.REJECTED)

    def _set_finance(self, status):
        self.finance_status = status
        self.save(update_fields=["finance_status", "updated_at"])

    def _set_admin(self, status):
        self.admin_status = status
        self.save(update_fields=["admin_status", "updated_at"])

    def mark_as_paid(self):
        if not (self.finance_status == self.Approval.APPROVED and self.admin_status == self.Approval.APPROVED):
            raise ValueError("Needs both Finance and Admin approvals before payment.")
        self.is_paid = True
        self.paid_at = timezone.now()
        self.save(update_fields=["is_paid", "paid_at", "updated_at"])



class Requisition(models.Model):
    class Approval(models.TextChoices):
        PENDING  = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class Category(models.TextChoices):
        IT_EQUIPMENT      = "IT_EQUIPMENT", "IT Equipment"
        OFFICE_SUPPLIES   = "OFFICE_SUPPLIES", "Office Supplies"
        SERVICES          = "SERVICES", "Services"
        MARKETING         = "MARKETING", "Marketing"
        OTHER             = "OTHER", "Other"

    reference     = models.CharField(max_length=20, unique=True, editable=False)  # REQ-YYYY-000001
    requester  = models.ForeignKey(User, on_delete=models.PROTECT, related_name="requisitions")

    title         = models.CharField(max_length=120)
    category      = models.CharField(max_length=32, choices=Category.choices)
    amount        = models.DecimalField(max_digits=12, decimal_places=2,
                                        validators=[MinValueValidator(Decimal("2000"))])
    description   = models.TextField()

    finance_status = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)
    admin_status   = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)

    is_ordered    = models.BooleanField(default=False)
    ordered_at    = models.DateTimeField(null=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes  = [models.Index(fields=["created_at"]), models.Index(fields=["reference"])]

    def __str__(self) -> str:
        return f"{self.reference} · {self.title} · UGX {int(self.amount):,}"

    @property
    def overall_status(self) -> str:
        if self.finance_status == self.Approval.REJECTED or self.admin_status == self.Approval.REJECTED:
            return "Rejected"
        if self.is_ordered:
            return "Ordered"
        if self.finance_status == self.Approval.APPROVED and self.admin_status == self.Approval.APPROVED:
            return "Fully Approved"
        if self.finance_status == self.Approval.APPROVED or self.admin_status == self.Approval.APPROVED:
            return "Partially Approved"
        return "Pending"

    # reference auto-number
    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            with transaction.atomic():
                last = (
                    Requisition.objects.select_for_update()
                    .filter(reference__startswith=f"REQ-{year}-")
                    .order_by("-reference")
                    .first()
                )
                n = int(last.reference.split("-")[-1]) + 1 if last else 1
                self.reference = f"REQ-{year}-{n:06d}"
        super().save(*args, **kwargs)

    # workflow
    def approve_finance(self): self._set_finance(self.Approval.APPROVED)
    def reject_finance(self):  self._set_finance(self.Approval.REJECTED)
    def approve_admin(self):   self._set_admin(self.Approval.APPROVED)
    def reject_admin(self):    self._set_admin(self.Approval.REJECTED)

    def _set_finance(self, status):
        self.finance_status = status
        self.save(update_fields=["finance_status", "updated_at"])

    def _set_admin(self, status):
        self.admin_status = status
        self.save(update_fields=["admin_status", "updated_at"])

    def mark_ordered(self):
        if not (self.finance_status == self.Approval.APPROVED and self.admin_status == self.Approval.APPROVED):
            raise ValueError("Needs both Finance and Admin approvals before ordering.")
        self.is_ordered = True
        self.ordered_at = timezone.now()
        self.save(update_fields=["is_ordered", "ordered_at", "updated_at"])
