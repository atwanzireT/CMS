from decimal import Decimal, ROUND_HALF_UP
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings
from store.models import CoffeePurchase


def clamp2(x: Decimal | float | None) -> Decimal | None:
    if x is None:
        return None
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Assessment(models.Model):
    """
    One assessment per purchase. Views/templates expect:
    - assessment.coffee (OneToOne to CoffeePurchase)
    - assessment.assessed_by (FK to user)
    - final_price / decision / decision_reasons
    """

    # Make coffee REQUIRED so signals (and any logic elsewhere) never see None.
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

    # Core inputs
    ref_price = models.DecimalField("Reference Price (UGX)", max_digits=12, decimal_places=2,
                                    validators=[MinValueValidator(Decimal("0"))])
    discretion = models.DecimalField("Discretion (UGX)", max_digits=12, decimal_places=2,
                                     default=Decimal("0.00"), blank=True)
    moisture_content = models.DecimalField("Moisture (%)", max_digits=5, decimal_places=2,
                                           validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    group1_defects = models.DecimalField("Group 1 Defects (%)", max_digits=5, decimal_places=2,
                                         validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    group2_defects = models.DecimalField("Group 2 Defects (%)", max_digits=5, decimal_places=2,
                                         validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    below_screen_12 = models.DecimalField("Below Screen 12 (%)", max_digits=5, decimal_places=2,
                                          validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    pods = models.DecimalField("Pods (%)", max_digits=5, decimal_places=2,
                               validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    husks = models.DecimalField("Husks (%)", max_digits=5, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    stones = models.DecimalField("Stones (%)", max_digits=5, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    fm = models.DecimalField("Foreign Matter (%)", max_digits=5, decimal_places=2, default=Decimal("0.00"), blank=True,
                             validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    offered_price = models.DecimalField("Offered Price (UGX)", max_digits=12, decimal_places=2,
                                        default=Decimal("0.00"), blank=True,
                                        validators=[MinValueValidator(Decimal("0"))])

    # Cached results/snapshots
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

    # ---------- Validation ----------
    def clean(self):
        # Enforce required coffee (defensive even though null/blank are False)
        from django.core.exceptions import ValidationError
        if self.coffee is None:
            raise ValidationError({"coffee": "Select the Coffee Purchase to assess."})

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
        return clamp2(value)

    def compute_derived_outturn(self) -> Decimal | None:
        """
        Reject gate: if BelowScreen12 > 3 → reject (no B12).
        Otherwise:
        DerivedOutturn = 100
          - max(0, Moisture-14)
          - max(0, G1-4)
          - max(0, G2-10)
          - Pods - Husks - Stones
          - max(0, Below12-1)
        """
        if (self.below_screen_12 or Decimal("0")) > Decimal("3"):
            return None

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
        return clamp2(val)

    def compute_rejection_reasons(self) -> list[str]:
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
        if phs_sum > 6:           reasons.append(f"Pods+Husks+Stones {clamp2(phs_sum)}% > 6%")
        return reasons

    def compute_final_price(self) -> Decimal | None:
        """
        Implements the "Price Preview" rules.
        Returns None if rejected or lacking derived_outturn.
        """
        reasons = self.compute_rejection_reasons()
        derived_outturn = self.compute_derived_outturn()
        if reasons or derived_outturn is None or self.ref_price is None:
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
        bonus = (group1 <= 1 and group2 <= 5 and moisture <= 13 and derived_outturn >= 80
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

        price = max(Decimal("0.00"), clamp2(price))
        return price

    # ---------- Lifecycle ----------
    def refresh_computed_fields(self):
        self.clean_outturn = self.compute_clean_outturn()
        self.derived_outturn = self.compute_derived_outturn()
        reasons = self.compute_rejection_reasons()
        if reasons:
            self.decision = "Rejected"
        else:
            self.decision = "Accepted" if self.derived_outturn is not None else "Pending"
        self.decision_reasons = "\n".join(reasons)
        self.final_price = self.compute_final_price()

    def save(self, *args, **kwargs):
        # Ensure strong validation before computing/saving
        self.full_clean()
        self.refresh_computed_fields()
        self.fm = self.stones + self.husks + self.pods
        super().save(*args, **kwargs)

    # ---------- Handy aliases for templates ----------
    @property
    def phs_sum(self) -> Decimal:
        return clamp2((self.pods or 0) + (self.husks or 0) + (self.stones or 0)) or Decimal("0.00")

    @property
    def is_rejected(self) -> bool:
        return self.decision == "Rejected"

    @property
    def analysis_price_ugx(self):
        # Back-compat for existing templates
        return self.offered_price

    @property
    def analysis_outturn_pct(self):
        # Back-compat alias used by your table
        return self.derived_outturn

    def __str__(self):
        return f"Assessment #{self.pk or '—'}"
