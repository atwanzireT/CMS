# views.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from accounts.permissions import module_required
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import F, Sum, ExpressionWrapper, DecimalField, Q
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date
from .forms import CoffeeSaleForm
from .models import CoffeeSale, SaleCustomer

PER_PAGE_OPTIONS = [10, 25, 50, 100, 200]
DEFAULT_PER_PAGE = 25


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return parse_date(s)
    except Exception:
        return None


@module_required("access_sales")
def sales_list_create(request):
    """
    Safe view:
      - If tables are missing, DO NOT query or render DB-backed widgets.
      - Shows setup/help cards only.
    """
    # --- Introspect once; no queries ---
    try:
        tables = set(connection.introspection.table_names())
    except Exception:
        tables = set()

    sales_ready = CoffeeSale._meta.db_table in tables
    customers_ready = SaleCustomer._meta.db_table in tables
    can_list = sales_ready           # listing needs CoffeeSale table
    can_create = sales_ready and customers_ready  # creating needs both

    # If creation is disabled, ignore POST entirely to avoid validation/queries
    if request.method == "POST" and not can_create:
        messages.warning(request, "Sales setup not complete yet. Run migrations to enable creating sales.")
        return redirect("sales_list_create")

    # Build form only when safe; otherwise keep None (template hides it)
    form = None
    if can_create:
        if request.method == "POST":
            form = CoffeeSaleForm(request.POST, request.FILES, request=request)
            # No need to tweak queryset; tables exist
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                    messages.success(request, "Sale record created successfully.")
                    return redirect("sales_list_create")
                except Exception as e:
                    messages.error(request, f"Could not save sale: {e}")
            else:
                messages.error(request, "There was an error creating the sale record.")
        else:
            form = CoffeeSaleForm(request=request)

    # Filters (only used when listing is enabled)
    q = (request.GET.get("q") or "").strip()
    coffee_type = (request.GET.get("coffee_type") or "").strip().upper()
    date_from = _parse_date(request.GET.get("date_from"))
    date_to = _parse_date(request.GET.get("date_to"))

    totals = {"total_qty": Decimal("0.00"), "total_amount": Decimal("0.00")}
    page_obj = None
    paginator = None
    sales = []

    if can_list:
        qs = (
            CoffeeSale.objects
            .select_related("customer")
            .order_by("-sale_date", "-created_at")
        )
        if q:
            qs = qs.filter(
                Q(customer__name__icontains=q)
                | Q(truck_details__icontains=q)
                | Q(driver_details__icontains=q)
                | Q(notes__icontains=q)
            )
        if coffee_type in {"AR", "RB"}:
            qs = qs.filter(coffee_type=coffee_type)
        if date_from:
            qs = qs.filter(sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale_date__lte=date_to)

        total_amount_expr = ExpressionWrapper(
            F("quantity_kg") * F("unit_price_ugx"),
            output_field=DecimalField(max_digits=20, decimal_places=2),
        )
        agg = qs.aggregate(
            total_qty=Sum("quantity_kg"),
            total_amount=Sum(total_amount_expr),
        )
        totals = {
            "total_qty": agg.get("total_qty") or Decimal("0.00"),
            "total_amount": agg.get("total_amount") or Decimal("0.00"),
        }

        try:
            per_page = int(request.GET.get("per_page") or DEFAULT_PER_PAGE)
        except ValueError:
            per_page = DEFAULT_PER_PAGE
        if per_page not in PER_PAGE_OPTIONS:
            per_page = DEFAULT_PER_PAGE

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(request.GET.get("page"))
        sales = list(page_obj.object_list)

    context = {
        "form": form,
        "can_create": can_create,
        "can_list": can_list,
        "per_page_options": PER_PAGE_OPTIONS,
        "current_per_page": int(request.GET.get("per_page") or DEFAULT_PER_PAGE),
        "filters": {
            "q": q,
            "coffee_type": coffee_type,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        },
        "totals": totals,
        "page_obj": page_obj,
        "paginator": paginator,
        "sales": sales,
    }

    # Friendly setup hints (pure UI; no DB work)
    if not customers_ready:
        messages.info(request, "Customers not set up yet. Run migrations to enable the customer dropdown.")
    if not sales_ready:
        messages.info(request, "Sales not set up yet. Run migrations to enable listing and totals.")

    return render(request, "sales.html", context)
