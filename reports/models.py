# app/models.py
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


def report_upload_to(instance, filename):
    # e.g. store_reports/2025/09/08/<filename>
    return f"store_reports/{instance.date:%Y/%m/%d}/{filename}"


class CoffeeType(models.TextChoices):
    DRUGAR = "DRUGAR", "Drugar (Arabica FAQ)"
    WASHED = "WASHED", "Washed (Parchment)"
    ROBUSTA_FAQ = "ROBUSTA_FAQ", "Robusta FAQ"
    ROBUSTA_SCREEN15 = "ROBUSTA_SCR15", "Robusta Screen 15+"
    OTHER = "OTHER", "Other"


class DailyStoreReport(models.Model):
    # Core
    date = models.DateField(db_index=True)
    coffee_type = models.CharField(
        max_length=32,
        choices=CoffeeType.choices,
        default=CoffeeType.DRUGAR,
    )

    # Prices & transactions
    average_buying_price_ugx_per_kg = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="UGX per kg"
    )
    kilograms_bought = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    kilograms_sold = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    number_of_bags_sold = models.PositiveIntegerField(default=0)

    # Inventory snapshot
    bags_left_in_store = models.PositiveIntegerField(default=0)
    kilograms_left_in_store = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    kilograms_unbought_in_store = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Coffee present but not yet bought/processed"
    )

    # Parties & cash
    sold_to = models.CharField(max_length=255, blank=True)
    advances_given_ugx = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )

    # Meta / UX
    input_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="daily_store_reports",
        help_text="The staff user who entered this report"
    )
    attachment = models.FileField(
        upload_to=report_upload_to, blank=True, null=True
    )
    comments = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("date", "coffee_type")
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date", "coffee_type"]),
        ]

    def __str__(self):
        return f"{self.date:%Y-%m-%d} • {self.get_coffee_type_display()}"

    # Optional safety checks
    def clean(self):
        from django.core.exceptions import ValidationError
        fields_nonneg = {
            "kilograms_bought": self.kilograms_bought,
            "kilograms_sold": self.kilograms_sold,
            "kilograms_left_in_store": self.kilograms_left_in_store,
            "kilograms_unbought_in_store": self.kilograms_unbought_in_store,
            "average_buying_price_ugx_per_kg": self.average_buying_price_ugx_per_kg,
            "advances_given_ugx": self.advances_given_ugx,
        }
        for fname, val in fields_nonneg.items():
            if val is not None and val < 0:
                raise ValidationError({fname: "Must be ≥ 0"})
