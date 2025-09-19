from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator


def q2(x) -> Decimal:
    """Quantize to 2 decimal places."""
    if isinstance(x, Decimal):
        d = x
    else:
        d = Decimal(str(x))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CoffeeInventory(models.Model):
    # Coffee categories (form)
    GREEN = 'GR'
    PARCHMENT = 'PA'
    KIBOKO = 'KB'
    COFFEE_CATEGORIES = [
        (GREEN, 'Green Coffee'),
        (PARCHMENT, 'Parchment Coffee'),
        (KIBOKO, 'Kiboko Coffee'),
    ]

    # Coffee types
    COFFEE_TYPE_CHOICES = [
        ('ARABICA', 'Arabica'),
        ('ROBUSTA', 'Robusta'),
        ('BLEND', 'Blend'),
    ]

    coffee_category = models.CharField(
        max_length=2,
        choices=COFFEE_CATEGORIES,
        verbose_name="Coffee Form",
        blank=True,
    )
    coffee_type = models.CharField(
        max_length=20,
        choices=COFFEE_TYPE_CHOICES,
        default='ARABICA',
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="On-hand quantity.",
    )
    unit = models.CharField(max_length=10, default='kg')
    average_unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Weighted average (UGX per unit).",
    )
    current_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Auto-calculated: quantity × average_unit_cost.",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Coffee Inventory"
        unique_together = ["coffee_category", "coffee_type"]
        ordering = ["coffee_category", "coffee_type"]

    def __str__(self):
        cat = dict(self.COFFEE_CATEGORIES).get(self.coffee_category, "Unknown")
        return f"{cat} {self.get_coffee_type_display()} - {self.quantity}{self.unit}"

    # Keep value in sync; normalize to 2dp
    def save(self, *args, **kwargs):
        self.quantity = q2(self.quantity)
        self.average_unit_cost = q2(self.average_unit_cost)
        self.current_value = q2(self.quantity * self.average_unit_cost)
        super().save(*args, **kwargs)

    # Simple helpers
    def has_sufficient_stock(self, quantity) -> bool:
        return self.quantity >= q2(quantity)

    def update_inventory(self, quantity_change, cost_change=0):
        """
        - If quantity_change > 0 (purchase): cost_change is the TOTAL cost (UGX) for that quantity.
          Weighted-average cost is updated.
        - If quantity_change < 0 (issue/sale): cost_change is ignored, avg cost unchanged.
        - Raises ValueError if resulting stock would be negative.
        """
        q_delta = q2(quantity_change)
        new_qty = q2(self.quantity + q_delta)

        if new_qty < 0:
            raise ValueError(
                f"Insufficient stock. Available: {self.quantity}{self.unit}, "
                f"Requested: {-q_delta}{self.unit}"
            )

        # Purchase: recompute average using total cost provided
        if q_delta > 0:
            add_cost = q2(cost_change)
            if q_delta == 0:
                # No quantity change; nothing to do
                return
            if self.quantity <= 0:
                new_avg = q2(add_cost / q_delta) if add_cost > 0 else self.average_unit_cost
            else:
                total_existing_cost = q2(self.quantity * self.average_unit_cost)
                new_avg = q2((total_existing_cost + add_cost) / (self.quantity + q_delta))
            self.average_unit_cost = new_avg

        # Apply quantity and save (save() recalculates current_value)
        self.quantity = new_qty
        self.save()
