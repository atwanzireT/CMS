from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
from store.models import CoffeePurchase


def clamp1(x: Decimal | float | None) -> Decimal | None:
    """
    Quantize to 1 decimal place.
    """
    if x is None:
        return None
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


class Assessment(models.Model):
    # Kept as reference, not used for validation anymore
    MAX_MOISTURE = Decimal("16.5")
    MAX_G1 = Decimal("10")
    MAX_G2 = Decimal("25")
    MAX_B12 = Decimal("3")
    MAX_PODS = Decimal("6")
    MAX_HUSKS = Decimal("6")
    MAX_STONES = Decimal("6")
    MAX_PHS_SUM = Decimal("6")

    coffee = models.OneToOneField(
        CoffeePurchase,
        on_delete=models.PROTECT,
        related_name='assessment',
        null=False,
        blank=False,
    )
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='assessments',
        null=True,
        blank=True,
    )

    # ---------- Core inputs (defaults for an "accepted" sample) ----------
    ref_price = models.DecimalField(
        "Reference Price (UGX)",
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"),  # set your business default if you want
        blank=True,
    )
    discretion = models.DecimalField(
        "Discretion (UGX)",
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"),
        blank=True
    )
    moisture_content = models.DecimalField(
        "Moisture (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("14.0"),
        blank=True,
        help_text="Typical target ≲ 16.5%"
    )
    group1_defects = models.DecimalField(
        "Group 1 Defects (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("4.0"),
        blank=True,
        help_text="Typical target ≲ 10%"
    )
    group2_defects = models.DecimalField(
        "Group 2 Defects (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("10.0"),
        blank=True,
        help_text="Typical target ≲ 25%"
    )
    below_screen_12 = models.DecimalField(
        "Below Screen 12 (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("1.0"),
        blank=True,
        help_text="Typical target ≲ 3%"
    )
    pods = models.DecimalField(
        "Pods (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("0.0"),
        blank=True,
        help_text="P+H+S total typical target ≲ 6%"
    )
    husks = models.DecimalField(
        "Husks (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("0.0"),
        blank=True,
    )
    stones = models.DecimalField(
        "Stones (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("0.0"),
        blank=True,
    )
    fm = models.DecimalField(
        "Foreign Matter (%)",
        max_digits=5, decimal_places=2,
        default=Decimal("0.0"),
        blank=True,
        help_text="Auto = pods + husks + stones"
    )
    offered_price = models.DecimalField(
        "Offered Price (UGX)",
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
    )

    # ---------- Cached results/snapshots ----------
    clean_outturn = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    derived_outturn = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    final_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    decision = models.CharField(max_length=16, default="Pending")  # Pending | Accepted | Rejected
    decision_reasons = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quality Assessment"
        verbose_name_plural = "Quality Assessments"
        ordering = ['-created_at']

    # ---------- Removed model validation ----------
    # def clean(self):
    #     pass  # Intentionally no validation

    # ---------- Computations ----------
    def compute_clean_outturn(self) -> Decimal:
        """
        CleanOutturn = 100 - G1 - G2 - Pods - Husks - Stones - BelowScreen12
        """
        value = (Decimal("100")
                 - (self.group1_defects or 0)
                 - (self.group2_defects or 0)
                 - (self.pods or 0)
                 - (self.husks or 0)
                 - (self.stones or 0)
                 - (self.below_screen_12 or 0))
        return clamp1(value)

    def compute_derived_outturn(self) -> Decimal | None:
        """
        DerivedOutturn = 100
          - max(0, Moisture-14)
          - max(0, G1-4)
          - max(0, G2-10)
          - Pods - Husks - Stones
          - max(0, Below12-1)

        Note: We no longer hard-reject on Below12 > 3 here; return value regardless.
        """
        def excess(x: Decimal, base: Decimal) -> Decimal:
            return (x - base) if x > base else Decimal("0")

        val = (Decimal("100")
               - excess(self.moisture_content or 0, Decimal("14"))
               - excess(self.group1_defects or 0, Decimal("4"))
               - excess(self.group2_defects or 0, Decimal("10"))
               - (self.pods or 0)
               - (self.husks or 0)
               - (self.stones or 0)
               - excess(self.below_screen_12 or 0, Decimal("1")))
        return clamp1(val)

    def compute_rejection_reasons(self) -> list[str]:
        """
        Keep as a pure informational function (no validation is enforced).
        """
        reasons: list[str] = []
        moisture = self.moisture_content or 0
        group1 = self.group1_defects or 0
        group2 = self.group2_defects or 0
        below_screen = self.below_screen_12 or 0
        pods = self.pods or 0
        husks = self.husks or 0
        stones = self.stones or 0
        phs_sum = pods + husks + stones

        if below_screen > 3:      reasons.append(f"Below screen 12 {below_screen}% > 3%")
        if moisture > 16.5:       reasons.append(f"Moisture {moisture}% > 16.5%")
        if group1 > 10:           reasons.append(f"Group 1 defects {group1}% > 10%")
        if group2 > 25:           reasons.append(f"Group 2 defects {group2}% > 25%")
        if pods > 6:              reasons.append(f"Pods {pods}% > 6%")
        if husks > 6:             reasons.append(f"Husks {husks}% > 6%")
        if stones > 6:            reasons.append(f"Stones {stones}% > 6%")
        if phs_sum > 6:           reasons.append(f"Pods+Husks+Stones {clamp1(phs_sum)}% > 6%")
        return reasons

    def compute_final_price(self) -> Decimal | None:
        """
        "Price Preview" rules. Now runs without hard validation;
        if ref_price is None-like, return None.
        """
        derived_outturn = self.compute_derived_outturn()
        if self.ref_price in (None, ""):
            return None

        reference_price = self.ref_price
        price = Decimal(reference_price)

        moisture = self.moisture_content or 0
        group1 = self.group1_defects or 0
        group2 = self.group2_defects or 0
        below_screen = self.below_screen_12 or 0
        pods = self.pods or 0
        husks = self.husks or 0
        stones = self.stones or 0

        # Bonus +2000 UGX
        bonus = (group1 <= 1 and group2 <= 5 and moisture <= 13
                 and (derived_outturn or 0) >= 80
                 and pods == 0 and husks == 0 and stones == 0 and below_screen <= 1)
        if bonus:
            price += Decimal("2000")

        # Moisture penalty (>= 14)
        if moisture >= 14:
            price -= (Decimal(moisture) - Decimal("14")) * Decimal(reference_price) * Decimal("0.002")

        # Group 1 penalty over 4
        if group1 > 4:
            price -= (Decimal(group1) - Decimal("4")) * Decimal("50")

        # Group 2 penalty over 10
        if group2 > 10:
            price -= (Decimal(group2) - Decimal("10")) * Decimal("20")

        # Derived outturn adjustments
        if derived_outturn is not None:
            if derived_outturn < 78:
                price -= (Decimal("78") - Decimal(derived_outturn)) * Decimal("50")
            elif derived_outturn > 82:
                price += (Decimal(derived_outturn) - Decimal("82")) * Decimal("50")

        # Pods/Husks/Stones deductions
        price -= Decimal(pods) * Decimal("10")
        price -= Decimal(husks) * Decimal("10")
        price -= Decimal(stones) * Decimal("20")

        # Below screen 12 > 1 penalty
        if below_screen > 1:
            price -= (Decimal(below_screen) - Decimal("1")) * Decimal("30")

        # Discretion (can be negative or positive)
        if self.discretion is not None:
            price += Decimal(self.discretion)

        price = max(Decimal("0.0"), clamp1(price))
        return price

    # ---------- Lifecycle ----------
    def refresh_computed_fields(self):
        self.clean_outturn = clamp1(self.compute_clean_outturn())
        self.derived_outturn = self.compute_derived_outturn()
        # Decision no longer enforced by validation; keep it informative
        reasons = self.compute_rejection_reasons()
        if reasons:
            self.decision = "Rejected"
        else:
            self.decision = "Accepted" if self.derived_outturn is not None else "Pending"
        self.decision_reasons = "\n".join(reasons)
        self.final_price = self.compute_final_price()

    def save(self, *args, **kwargs):
        # No full_clean() -> no model validation
        self.refresh_computed_fields()
        # keep fm in sync (quantized to 1 dp)
        self.fm = clamp1((self.stones or 0) + (self.husks or 0) + (self.pods or 0)) or Decimal("0.0")
        super().save(*args, **kwargs)

    # ---------- Handy aliases for templates ----------
    @property
    def phs_sum(self) -> Decimal:
        return clamp1((self.pods or 0) + (self.husks or 0) + (self.stones or 0)) or Decimal("0.0")

    @property
    def is_rejected(self) -> bool:
        return self.decision == "Rejected"

    @property
    def analysis_price_ugx(self):
        return self.offered_price

    @property
    def analysis_outturn_pct(self):
        return self.derived_outturn

    def __str__(self):
        return f"Assessment #{self.pk or '—'}"
