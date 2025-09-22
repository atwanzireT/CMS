from datetime import timedelta
from decimal import Decimal
from accounts.permissions import module_required
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Sum, Avg, Count, Q, F, Value, DecimalField
)
from django.db.models.functions import Coalesce, Cast
from django.db.models.expressions import ExpressionWrapper
from django.shortcuts import render
from django.utils import timezone
from assessment.models import Assessment
from inventory.models import CoffeeInventory
from store.models import CoffeePurchase
from sales.models import CoffeeSale  # adjust import if CoffeeSale lives elsewhere


@module_required("access_inventory")
def inventory_dashboard(request):
    """
    Dashboard using CoffeeInventory(quantity, average_unit_cost, current_value, coffee_type, coffee_category, unit).
    We expose the same keys the template expects.
    """
    now = timezone.now()
    today = now.date()
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    d90 = now - timedelta(days=90)
    d365 = now - timedelta(days=365)

    # Reusable Decimal output fields
    DEC_QTY = DecimalField(max_digits=20, decimal_places=2)
    DEC_VAL = DecimalField(max_digits=24, decimal_places=2)

    # ---------- INVENTORY TOTALS ----------
    inv_totals = CoffeeInventory.objects.aggregate(
        # Cast sum to Decimal and coalesce with a Decimal zero
        total_qty=Coalesce(
            Cast(Sum("quantity"), DEC_QTY),
            Value(Decimal("0.00"), output_field=DEC_QTY)
        ),
        total_value_explicit=Coalesce(
            Cast(Sum("current_value"), DEC_VAL),
            Value(Decimal("0.00"), output_field=DEC_VAL)
        ),
        avg_cost=Avg("average_unit_cost"),
        items=Count("id"),
    )

    # Compute total value:
    # Prefer explicit current_value; otherwise approximate Sum(quantity * average_unit_cost)
    if inv_totals["total_value_explicit"] and inv_totals["total_value_explicit"] > Decimal("0.00"):
        inv_total_value = inv_totals["total_value_explicit"]
    else:
        qty_dec = Cast(F("quantity"), DEC_QTY)
        cost_dec = Coalesce(
            F("average_unit_cost"),
            Value(Decimal("0.00"), output_field=DEC_QTY),
            output_field=DEC_QTY,
        )
        line_val = ExpressionWrapper(qty_dec * cost_dec, output_field=DEC_VAL)
        inv_total_value = (
            CoffeeInventory.objects
            .annotate(_val=line_val)
            .aggregate(v=Coalesce(Sum("_val"), Value(Decimal("0.00"), output_field=DEC_VAL)))["v"]
        )

    # ---------- BREAKDOWNS ----------
    inv_by_type = (
        CoffeeInventory.objects
        .values("coffee_type")
        .annotate(
            received_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
            available_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
            lots=Count("id"),
        )
        .order_by("coffee_type")
    )

    inv_by_category = (
        CoffeeInventory.objects
        .values("coffee_category")
        .annotate(
            received_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
            available_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
            lots=Count("id"),
        )
        .order_by("coffee_category")
    )

    # No lot/status/age fields in CoffeeInventory; keep these empty/None
    inv_status_counts = []
    avg_open_age_days = None

    # ---------- MOVEMENT (last 30 days) ----------
    # Inflow = accepted purchases
    accepted_purchases_30 = (
        CoffeePurchase.objects
        .filter(assessment__decision="Accepted", purchase_date__gte=d30)
        .aggregate(total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)))
    )
    inflow_30_kg = accepted_purchases_30["total_kg"]

    # Outflow & Revenue = sales
    sales_30 = CoffeeSale.objects.filter(sale_date__gte=d30)

    outflow_approx_30_kg = sales_30.aggregate(
        total_kg=Coalesce(
            Cast(Sum("quantity_kg"), DEC_QTY),
            Value(Decimal("0.00"), output_field=DEC_QTY)
        )
    )["total_kg"]

    qty_dec = Cast(F("quantity_kg"), DEC_QTY)
    price_dec = Cast(F("unit_price_ugx"), DEC_QTY)
    line_total = ExpressionWrapper(qty_dec * price_dec, output_field=DEC_VAL)

    revenue_30 = sales_30.annotate(line_total=line_total).aggregate(
        total=Coalesce(Sum("line_total"), Value(Decimal("0.00"), output_field=DEC_VAL))
    )["total"]

    # ---------- QUALITY ----------
    assessments = Assessment.objects.all()
    assess_totals = assessments.aggregate(
        total=Count("id"),
        accepted=Count("id", filter=Q(decision="Accepted")),
        rejected=Count("id", filter=Q(decision="Rejected")),
        pending=Count("id", filter=Q(decision="Pending")),
        avg_final_price=Avg("final_price"),
        avg_derived_outturn=Avg("derived_outturn"),
    )
    assess_total = assess_totals["total"] or 0
    acceptance_rate = round(100.0 * (assess_totals["accepted"] or 0) / assess_total, 1) if assess_total else 0.0

    recent_rejections = (
        assessments.filter(decision="Rejected")
        .select_related("coffee__supplier")
        .order_by("-created_at")[:10]
        .values(
            "id", "created_at", "decision_reasons",
            "coffee__id", "coffee__supplier__name", "coffee__quantity",
            "moisture_content", "group1_defects", "group2_defects", "below_screen_12",
            "pods", "husks", "stones"
        )
    )

    # ---------- PURCHASING WINDOWS & SUPPLIERS ----------
    accepted_purchases = CoffeePurchase.objects.filter(assessment__decision="Accepted")

    accepted_last_7 = accepted_purchases.filter(purchase_date__gte=d7).aggregate(
        purchases=Count("id"),
        total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
    )
    accepted_last_30 = accepted_purchases.filter(purchase_date__gte=d30).aggregate(
        purchases=Count("id"),
        total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
    )
    accepted_last_365 = accepted_purchases.filter(purchase_date__gte=d365).aggregate(
        purchases=Count("id"),
        total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
    )

    pending_assessment_purchases = (
        CoffeePurchase.objects
        .filter(Q(assessment__isnull=True) | Q(assessment__decision="Pending"))
        .aggregate(
            purchases=Count("id"),
            total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
        )
    )

    top_suppliers_90 = (
        accepted_purchases.filter(purchase_date__gte=d90)
        .values("supplier__id", "supplier__name")
        .annotate(total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)))
        .order_by("-total_kg")[:10]
    )

    payment_mix = (
        CoffeePurchase.objects
        .values("payment_status")
        .annotate(
            n=Count("id"),
            total_kg=Coalesce(Cast(Sum("quantity"), DEC_QTY), Value(Decimal("0.00"), output_field=DEC_QTY)),
        )
        .order_by("payment_status")
    )

    # ---------- CONTEXT ----------
    context = {
        "today": today,

        # Inventory totals for summary cards
        "inv_total_available_kg": inv_totals["total_qty"],    # using quantity as available
        "inv_total_received_kg": inv_totals["total_qty"],     # mirror since no separate received field
        "avg_final_price": assess_totals["avg_final_price"],
        "assess_acceptance_rate": acceptance_rate,

        # Movement 30d
        "inflow_30_kg": inflow_30_kg,
        "outflow_approx_30_kg": outflow_approx_30_kg,
        "movement": {
            "revenue_30d": revenue_30,
        },

        # Breakdowns
        "inv_by_type": list(inv_by_type),
        "inv_by_category": list(inv_by_category),
        "inv_status_counts": list(inv_status_counts),  # empty -> "No lots."
        "avg_open_age_days": avg_open_age_days,

        # Quality snapshot
        "assess_total": assess_total,
        "assess_accepted": assess_totals["accepted"] or 0,
        "assess_rejected": assess_totals["rejected"] or 0,
        "assess_pending": assess_totals["pending"] or 0,
        "avg_derived_outturn": assess_totals["avg_derived_outturn"],
        "recent_rejections": list(recent_rejections),

        # Purchasing windows & suppliers
        "accepted_last_7": accepted_last_7,
        "accepted_last_30": accepted_last_30,
        "accepted_last_365": accepted_last_365,
        "pending_assessment_purchases": pending_assessment_purchases,
        "payment_mix": list(payment_mix),
        "top_suppliers_90": list(top_suppliers_90),

        # (Optional) total inventory value if you want to show it later
        "inv_total_value": inv_total_value,
    }

    return render(request, "inventory_dashboard.html", context)
