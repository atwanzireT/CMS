from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Avg, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce, Cast, NullIf, TruncDate
from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import module_required
from .models import MillingProcess, MillingTransaction, CustomerAccount


@module_required("access_milling")
def milling_dashboard(request):
    """
    Supplies:
      today_kpis, month_kpis, status_counts, daily_series,
      top_customers, recent_processes, recent_txns, totals
    Also includes (optional to use in template):
      week_kpis, all_time_kpis, used_all_time_fallback, month_range, week_range
    """
    today = timezone.localdate()
    start_month = today.replace(day=1)
    seven_days_ago = today - timedelta(days=6)

    # ---- Typed expressions (avoid mixed-type/math issues) ----
    hulled_dec = Cast(F("hulled_weight"), DecimalField(max_digits=12, decimal_places=2))
    init_dec   = Cast(F("initial_weight"), DecimalField(max_digits=12, decimal_places=2))
    rate_dec   = Coalesce(Cast(F("milling_rate"), DecimalField(max_digits=12, decimal_places=2)),
                          Decimal("0.00"))

    revenue_expr = ExpressionWrapper(hulled_dec * rate_dec,
                                     output_field=DecimalField(max_digits=14, decimal_places=2))
    yield_expr   = ExpressionWrapper(100 * hulled_dec / NullIf(init_dec, 0),
                                     output_field=DecimalField(max_digits=6, decimal_places=2))

    base_qs = MillingProcess.objects.select_related("customer", "created_by")

    # ---- Today KPIs ----
    today_qs = base_qs.filter(created_at__date=today)
    today_kpis = today_qs.aggregate(
        processes=Coalesce(Count("id"), 0),
        hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
        avg_yield=Avg(yield_expr),
    )

    # ---- Month KPIs (with all-time fallback for e.g. first load) ----
    month_qs = base_qs.filter(created_at__date__gte=start_month, created_at__date__lte=today)
    month_kpis = month_qs.aggregate(
        processes=Coalesce(Count("id"), 0),
        hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
        avg_yield=Avg(yield_expr),
    )
    used_all_time_fallback = not month_qs.exists()

    # ---- (Optional) All-time & Last 7 days KPIs ----
    all_time_kpis = base_qs.aggregate(
        processes=Coalesce(Count("id"), 0),
        hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
        avg_yield=Avg(yield_expr),
    )
    week_qs = base_qs.filter(created_at__date__gte=seven_days_ago, created_at__date__lte=today)
    week_kpis = week_qs.aggregate(
        processes=Coalesce(Count("id"), 0),
        hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
        avg_yield=Avg(yield_expr),
    )

    # ---- Status counts (all-time) ----
    status_counts = dict(
        base_qs.values("status").annotate(c=Count("id")).values_list("status", "c")
    )
    # Ensure keys exist so {{ status_counts.C|default:0 }} works
    for key in ("C", "P", "X"):
        status_counts.setdefault(key, 0)

    # ---- Top customers (month, fallback to all-time if month empty) ----
    top_source = month_qs if month_qs.exists() else base_qs
    top_customers = (
        top_source
        .values("customer__id", "customer__name")
        .annotate(revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")))
        .order_by("-revenue")[:5]
    )

    # ---- Recent processes (annotated with row totals) ----
    recent_processes = (
        base_qs.annotate(row_revenue=revenue_expr, row_yield=yield_expr)
        .order_by("-created_at")[:8]
    )

    # ---- Recent transactions ----
    recent_txns = (
        MillingTransaction.objects
        .select_related("account__customer", "created_by", "milling_process")
        .order_by("-created_at")[:8]
    )

    # ---- Totals (customers & balances) ----
    totals = {
        "customers": CustomerAccount.objects.count(),
        "total_balance": CustomerAccount.objects.aggregate(
            v=Coalesce(Sum("balance"), Decimal("0.00"))
        )["v"],
    }

    # ---- 7-day series (inclusive, fill missing dates with zeros) ----
    daily = (
        week_qs
        .annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(
            revenue=Coalesce(Sum(revenue_expr), Decimal("0.00")),
            hulled_kg=Coalesce(Sum("hulled_weight"), 0),
        )
        .order_by("d")
    )
    daily_map = {row["d"]: row for row in daily}
    daily_series = []
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        daily_series.append(daily_map.get(d, {"d": d, "revenue": Decimal("0.00"), "hulled_kg": 0}))

    context = {
        "today": today,
        "today_kpis": today_kpis,
        "month_kpis": month_kpis,
        "status_counts": status_counts,
        "daily_series": daily_series,
        "top_customers": top_customers,
        "recent_processes": recent_processes,
        "recent_txns": recent_txns,
        "totals": totals,

        # Optional extras if you want them:
        "all_time_kpis": all_time_kpis,
        "week_kpis": week_kpis,
        "used_all_time_fallback": used_all_time_fallback,
        "month_range": {"start": start_month, "end": today},
        "week_range": {"start": seven_days_ago, "end": today},
    }
    return render(request, "milling_dashboard.html", context)
