from datetime import timedelta
from decimal import Decimal
from django.db.models import (
    Sum, Count, Avg, F, DecimalField, ExpressionWrapper
)
from django.db.models.functions import Coalesce, Cast, NullIf, TruncDate
from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import module_required
from .models import MillingProcess, MillingTransaction, CustomerAccount


@module_required("access_milling")
def milling_dashboard(request):
    """
    Milling dashboard with:
      - Today & month KPIs (processes, hulled kg, revenue, avg yield)
      - Status counts
      - Top customers by revenue
      - Recent processes & transactions
      - 7-day daily revenue & hulled series
    All monetary/ratio calculations use Decimal output fields to avoid mixed-type errors.
    """
    today = timezone.localdate()
    start_month = today.replace(day=1)
    seven_days_ago = today - timedelta(days=6)

    # ---- Safe expressions ----
    hulled_dec = Cast(F("hulled_weight"), DecimalField(max_digits=12, decimal_places=2))
    init_dec = Cast(F("initial_weight"), DecimalField(max_digits=12, decimal_places=2))
    rate_dec = Coalesce(Cast(F("milling_rate"), DecimalField(max_digits=12, decimal_places=2)), Decimal("0.00"))

    revenue_expr = ExpressionWrapper(
        hulled_dec * rate_dec,
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    yield_expr = ExpressionWrapper(
        100 * hulled_dec / NullIf(init_dec, 0),
        output_field=DecimalField(max_digits=6, decimal_places=2),
    )

    base_qs = MillingProcess.objects.all()

    # ---- Today KPIs ----
    today_qs = base_qs.filter(created_at__date=today)
    today_agg = today_qs.aggregate(
        processes=Coalesce(Count("id"), 0),
        hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
        avg_yield=Avg(yield_expr),
    )

    # ---- Month KPIs ----
    month_qs = base_qs.filter(created_at__date__gte=start_month, created_at__date__lte=today)
    month_agg = month_qs.aggregate(
        processes=Coalesce(Count("id"), 0),
        hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
        avg_yield=Avg(yield_expr),
    )

    # ---- Status counts (all time or this month – pick what you prefer) ----
    status_counts = dict(
        base_qs.values("status").annotate(c=Count("id")).values_list("status", "c")
    )

    # ---- Top customers by revenue (this month for relevance) ----
    top_customers = (
        month_qs
        .values("customer__id", "customer__name")
        .annotate(revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")))
        .order_by("-revenue")[:5]
    )

    # ---- Recent processes (with per-row revenue & yield) ----
    recent_processes = (
        base_qs.select_related("customer")
        .annotate(row_revenue=revenue_expr, row_yield=yield_expr)
        .order_by("-created_at")[:8]
    )

    # ---- Recent transactions (payments) ----
    recent_txns = (
        MillingTransaction.objects
        .select_related("account__customer", "created_by", "milling_process")
        .order_by("-created_at")[:8]
    )

    # ---- Totals / balances ----
    totals = {
        "customers": CustomerAccount.objects.count(),
        "total_balance": CustomerAccount.objects.aggregate(
            v=Coalesce(Sum("balance"), Decimal("0.00"))
        )["v"],
    }

    # ---- 7-day series (inclusive) ----
    last_7_qs = base_qs.filter(created_at__date__gte=seven_days_ago, created_at__date__lte=today)
    daily = (
        last_7_qs
        .annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(
            revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
            hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        )
        .order_by("d")
    )
    # Normalize to all 7 days
    daily_map = {row["d"]: row for row in daily}
    daily_series = []
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        row = daily_map.get(d, {"d": d, "revenue": Decimal("0.00"), "hulled_kg": 0})
        daily_series.append(row)

    context = {
        "today": today,
        "today_kpis": {
            "processes": today_agg["processes"],
            "hulled_kg": today_agg["hulled_kg"],
            "revenue": today_agg["revenue"],
            "avg_yield": today_agg["avg_yield"],  # may be None if no data
        },
        "month_kpis": {
            "processes": month_agg["processes"],
            "hulled_kg": month_agg["hulled_kg"],
            "revenue": month_agg["revenue"],
            "avg_yield": month_agg["avg_yield"],  # may be None if no data
        },
        "status_counts": status_counts,          # keys: 'C', 'P', 'X'
        "top_customers": top_customers,          # [{customer__id, customer__name, revenue}, ...]
        "recent_processes": recent_processes,    # has row_revenue, row_yield
        "recent_txns": recent_txns,
        "totals": totals,                        # customers, total_balance
        "daily_series": daily_series,            # last 7 days: date, revenue, hulled_kg
    }
    return render(request, "milling_dashboard.html", context)
