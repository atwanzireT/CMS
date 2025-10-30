# sales/models.py

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


def q2(x: Decimal | float | int | None) -> Decimal | None:
    """
    Quantize to 2 decimal places (UGX amounts / kg).
    Keeps None as None.
    """
    if x is None:
        return None
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SaleCustomer(models.Model):
    name = models.CharField("Customer Name", max_length=250)
    address = models.CharField("Address", max_length=150, blank=True, null=True)
    contact = models.CharField("Phone / Contact", max_length=50, blank=True, null=True)
    email = models.EmailField("Email", blank=True, null=True)
    notes = models.TextField("Notes", blank=True, null=True)

    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["contact"]),
            models.Index(fields=["email"]),
        ]
        constraints = [
            # Optional: enforce non-empty trimmed name
            models.CheckConstraint(
                check=~models.Q(name=""),
                name="salecustomer_name_not_empty",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class CoffeeSale(models.Model):
    # Coffee Types (matches the “Select coffee type” control)
    ARABICA = "AR"
    ROBUSTA = "RB"
    COFFEE_TYPES = [
        (ARABICA, "Arabica"),
        (ROBUSTA, "Robusta"),
    ]

    customer = models.ForeignKey(
        "SaleCustomer",  # same app, so no app label needed
        on_delete=models.PROTECT,
        related_name="coffee_sales",
        help_text="Buyer / consignee for this sale.",
    )

    sale_date = models.DateField(
        "Sale Date",
        default=timezone.now,
        help_text="Date the sale was recorded (local time).",
    )

    coffee_type = models.CharField(
        "Coffee Type",
        max_length=2,
        choices=COFFEE_TYPES,
        default=ARABICA,
        help_text="Select coffee type",
    )

    # Moisture (%)
    moisture_pct = models.DecimalField(
        "Moisture (%)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        blank=True,
        null=True,
        help_text="Enter moisture percentage (0–100).",
    )

    # Weight (kg)
    quantity_kg = models.DecimalField(
        "Weight (kg)",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Enter weight in kg.",
    )

    # Unit Price (UGX/kg)
    unit_price_ugx = models.DecimalField(
        "Unit Price (UGX/kg)",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Enter unit price.",
    )

    # Truck & Driver Details (required on the form)
    truck_details = models.CharField(
        "Truck Details",
        max_length=255,
        help_text="Truck number plate, capacity, etc.",
    )
    driver_details = models.CharField(
        "Driver Details",
        max_length=255,
        help_text="Driver name and phone number.",
    )

    # Optional: upload Sales GRN
    sales_grn = models.FileField(
        "Upload Sales GRN (Optional)",
        upload_to="sales_grn/",
        blank=True,
        null=True,
    )

    # Notes (not in the UI, but useful)
    notes = models.TextField("Notes", blank=True, default="")

    # Audit
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="coffee_sales",
        help_text="User who recorded this sale.",
    )
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        ordering = ["-sale_date", "-created_at"]
        verbose_name = "Coffee Sale"
        verbose_name_plural = "Coffee Sales"
        indexes = [
            models.Index(fields=["sale_date"]),
            models.Index(fields=["customer", "sale_date"]),
            models.Index(fields=["coffee_type"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity_kg__gt=0),
                name="coffeesale_quantity_kg_gt_0",
            ),
            models.CheckConstraint(
                check=models.Q(unit_price_ugx__gt=0),
                name="coffeesale_unit_price_ugx_gt_0",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Sale #{self.pk or '—'} • {self.get_coffee_type_display()} • {self.sale_date}"

    # Derived total (do not store; keep computed to avoid drift)
    @property
    def total_amount_ugx(self) -> Decimal:
        if self.quantity_kg is None or self.unit_price_ugx is None:
            return Decimal("0.00")
        return q2(self.quantity_kg * self.unit_price_ugx) or Decimal("0.00")

    # Optional: normalize decimals on save
    def save(self, *args, **kwargs):
        self.quantity_kg = q2(self.quantity_kg)
        self.unit_price_ugx = q2(self.unit_price_ugx)
        if self.moisture_pct is not None:
            # Keep two decimals for moisture too
            self.moisture_pct = q2(self.moisture_pct)
        super().save(*args, **kwargs)
