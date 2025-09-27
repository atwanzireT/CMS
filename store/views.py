# store/views.py
from __future__ import annotations
from datetime import timedelta
from decimal import Decimal
from typing import Any
from django.contrib import messages
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Sum, Count, Max, CharField, DecimalField, IntegerField, ExpressionWrapper,
    F, Q, Value, Case, When, Prefetch
)
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.permissions import module_required
from assessment.models import Assessment
from inventory.models import CoffeeInventory
from sales.forms import CoffeeSaleForm
from sales.models import CoffeeSale
from .forms import CoffeePurchaseForm, SupplierForm
from .models import CoffeePurchase, Supplier, SupplierAccount, SupplierTransaction

# -----------------------------
# Helpers
# -----------------------------
DEC2 = Decimal("0.01")


def _q2(x: Decimal | None) -> Decimal:
    x = x or Decimal("0")
    return x.quantize(DEC2)


def get_base_context(request: HttpRequest, page_title: str = "Default Page Title") -> dict[str, Any]:
    return {"page_title": page_title, "user": request.user}


# -----------------------------
# Dashboard
# -----------------------------
DECIMAL_OF = lambda: DecimalField(max_digits=20, decimal_places=2)


@module_required("access_store")
def store_dashboard(request):
    today = timezone.now().date()
    since = today - timedelta(days=30)

    # ---------- Purchases (30d)
    rp = CoffeePurchase.objects.filter(purchase_date__gte=since)

    totals_purchases = rp.aggregate(
        qty=Coalesce(
            Sum("quantity", output_field=DECIMAL_OF()),
            Value(Decimal("0.00"), output_field=DECIMAL_OF()),
        ),
        bags=Coalesce(
            Sum("bags", output_field=IntegerField()),
            Value(0, output_field=IntegerField()),
        ),
        count=Coalesce(
            Count("id"),
            Value(0, output_field=IntegerField()),
        ),
    )

    payment_status_rows = list(
        rp.values("payment_status").annotate(
            count=Coalesce(
                Count("id"),
                Value(0, output_field=IntegerField()),
            ),
            total_quantity=Coalesce(
                Sum("quantity", output_field=DECIMAL_OF()),
                Value(Decimal("0.00"), output_field=DECIMAL_OF()),
            ),
        )
    )
    payment_status_map = dict(CoffeePurchase.PAYMENT_STATUS_CHOICES)
    payment_status = [
        {**row, "status_label": payment_status_map.get(row["payment_status"], "Unknown")}
        for row in payment_status_rows
    ]

    # ---------- Sales (30d)
    total_amount_expr = ExpressionWrapper(
        F("quantity_kg") * F("unit_price_ugx"),
        output_field=DECIMAL_OF(),
    )
    rs = CoffeeSale.objects.filter(sale_date__gte=since)

    totals_sales = rs.aggregate(
        qty=Coalesce(
            Sum("quantity_kg", output_field=DECIMAL_OF()),
            Value(Decimal("0.00"), output_field=DECIMAL_OF()),
        ),
        revenue=Coalesce(
            Sum(total_amount_expr, output_field=DECIMAL_OF()),
            Value(Decimal("0.00"), output_field=DECIMAL_OF()),
        ),
        count=Coalesce(
            Count("id"),
            Value(0, output_field=IntegerField()),
        ),
    )

    # ---------- Inventory
    inv = CoffeeInventory.objects.all()
    inventory_totals = inv.aggregate(
        value=Coalesce(
            Sum("current_value", output_field=DECIMAL_OF()),
            Value(Decimal("0.00"), output_field=DECIMAL_OF()),
        ),
        qty=Coalesce(
            Sum("quantity", output_field=DECIMAL_OF()),
            Value(Decimal("0.00"), output_field=DECIMAL_OF()),
        ),
    )
    low_stock_items = inv.filter(quantity__lt=100)

    # ---------- Recent lists
    recent_purchases = (
        CoffeePurchase.objects.select_related("supplier")
        .order_by("-purchase_date", "-id")[:5]
    )
    recent_sales = list(
        CoffeeSale.objects.select_related("customer")
        .annotate(total_amount=total_amount_expr)
        .order_by("-sale_date", "-created_at")[:5]
    )
    type_label_map = dict(CoffeePurchase.COFFEE_TYPES)
    for s in recent_sales:
        s.coffee_type_label = getattr(
            s, "get_coffee_type_display",
            lambda: type_label_map.get(getattr(s, "coffee_type", None), "—"),
        )()

    # ---------- Top suppliers
    active_suppliers = (
        Supplier.objects.annotate(
            purchase_count=Count("purchases"),
            total_quantity=Coalesce(
                Sum("purchases__quantity", output_field=DECIMAL_OF()),
                Value(Decimal("0.00"), output_field=DECIMAL_OF()),
            ),
        )
        .filter(purchase_count__gt=0)
        .order_by("-total_quantity")[:5]
    )

    # ---------- Coffee type breakdowns
    raw_type_purchases = list(
        rp.values("coffee_type").annotate(
            total_quantity=Coalesce(
                Sum("quantity", output_field=DECIMAL_OF()),
                Value(Decimal("0.00"), output_field=DECIMAL_OF()),
            ),
            count=Coalesce(Count("id"), Value(0, output_field=IntegerField())),
        ).order_by("-total_quantity")
    )
    coffee_type_purchases = [
        {**row, "label": type_label_map.get(row["coffee_type"], row["coffee_type"])}
        for row in raw_type_purchases
    ]

    raw_type_sales = list(
        rs.values("coffee_type").annotate(
            total_quantity=Coalesce(
                Sum("quantity_kg", output_field=DECIMAL_OF()),
                Value(Decimal("0.00"), output_field=DECIMAL_OF()),
            ),
            total_revenue=Coalesce(
                Sum(total_amount_expr, output_field=DECIMAL_OF()),
                Value(Decimal("0.00"), output_field=DECIMAL_OF()),
            ),
        ).order_by("-total_quantity")
    )
    coffee_type_sales = [
        {**row, "label": type_label_map.get(row["coffee_type"], row["coffee_type"])}
        for row in raw_type_sales
    ]

    context = {
        "today": today,
        "total_purchases": totals_purchases["count"],
        "total_purchase_quantity": totals_purchases["qty"],
        "total_purchase_bags": totals_purchases["bags"],
        "total_sales": totals_sales["count"],
        "total_sale_quantity": totals_sales["qty"],
        "total_revenue": totals_sales["revenue"],
        "total_inventory_value": inventory_totals["value"],
        "total_inventory_quantity": inventory_totals["qty"],
        "payment_status": payment_status,
        "inventory_items": inv,
        "low_stock_items": low_stock_items,
        "recent_purchases": recent_purchases,
        "recent_sales": recent_sales,
        "active_suppliers": active_suppliers,
        "coffee_type_purchases": coffee_type_purchases,
        "coffee_type_sales": coffee_type_sales,
    }
    return render(request, "store_dashboard.html", context)


# -----------------------------
# Suppliers
# -----------------------------
PER_PAGE_OPTIONS = [10, 20, 50, 100]


@module_required("access_store")
def supplier_list(request: HttpRequest) -> HttpResponse:
    """
    - Search (?q=) on name/phone/id
    - Annotate last assessed delivery & distinct coffee types supplied
    - Same page can handle POST to create/update supplier OR create a purchase for a chosen supplier
    - Pagination
    """
    q = (request.GET.get("q") or "").strip()
    try:
        per_page = int(request.GET.get("per_page", 20))
    except ValueError:
        per_page = 20
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 20

    base_qs = Supplier.objects.all()
    if q:
        base_qs = base_qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(id__icontains=q))

    # Only consider purchases that have an assessment when annotating last_supply/types
    assessed = Q(purchases__assessment__isnull=False)

    suppliers_qs = (
        base_qs.annotate(
            last_supply=Max("purchases__delivery_date", filter=assessed),
            coffee_types=ArrayAgg(
                Case(
                    When(purchases__coffee_type=CoffeePurchase.ARABICA, then=Value("Arabica")),
                    When(purchases__coffee_type=CoffeePurchase.ROBUSTA, then=Value("Robusta")),
                    default=Value("Unknown"),
                    output_field=CharField(),
                ),
                filter=assessed,
                distinct=True,
            ),
        )
        .order_by("name")
    )

    if request.method == "POST":
        # Heuristic: if purchase fields exist → record a purchase for an existing supplier
        is_purchase_post = any(k in request.POST for k in ("coffee_category", "coffee_type", "quantity"))

        if is_purchase_post:
            supplier_id = request.POST.get("supplier_id")
            supplier = get_object_or_404(Supplier, id=supplier_id)

            form = CoffeePurchaseForm(request.POST, user=request.user)
            if form.is_valid():
                obj: CoffeePurchase = form.save(commit=False)
                obj.supplier = supplier
                obj.recorded_by = request.user
                obj.assessment_needed = True
                obj.purchase_date = obj.purchase_date or timezone.now().date()
                obj.delivery_date = obj.delivery_date or timezone.now().date()
                obj.save()
                messages.success(request, f"Purchase recorded for {supplier.name}.")
                return redirect(f"{request.path}?q={q}&per_page={per_page}")
            messages.error(request, "Please correct the errors in the purchase form.")
            return redirect(f"{request.path}?q={q}&per_page={per_page}")

        # Otherwise create/update Supplier
        supplier_id = request.POST.get("supplier_id")
        instance = get_object_or_404(Supplier, id=supplier_id) if supplier_id else None
        form = SupplierForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            supplier = form.save(commit=False)
            if instance is None:
                supplier.created_by = request.user
            supplier.save()
            messages.success(request, f"Supplier {'updated' if instance else 'created'} successfully!")
            return redirect(f"{request.path}?q={q}&per_page={per_page}")
        messages.error(request, "Please correct the errors below.")
    else:
        form = SupplierForm(user=request.user)

    paginator = Paginator(suppliers_qs, per_page)
    suppliers_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "supplier_list.html",
        {
            "form": form,
            "suppliers": suppliers_page,
            "q": q,
            "per_page": per_page,
            "per_page_options": PER_PAGE_OPTIONS,
        },
    )


@module_required("access_store")
def supplier_detail(request: HttpRequest, pk: str) -> HttpResponse:
    """
    NOTE: Ensure urls.py uses <str:pk> for Supplier ID.
    """
    supplier = get_object_or_404(Supplier.objects, pk=pk)
    ctx = get_base_context(request, f"Supplier Details - {supplier.name}")

    # Pull last 10 purchases and annotate a computed total_cost using Assessment.final_price
    purchases_qs = (
        supplier.purchases.select_related("assessment")
        .annotate(
            price_per_kg=Coalesce(F("assessment__final_price"), Decimal("0.00")),
            total_cost=ExpressionWrapper(
                F("quantity") * Coalesce(F("assessment__final_price"), Decimal("0.00")),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
        )
        .order_by("-purchase_date")
    )
    purchases = list(purchases_qs[:10])

    aggregates = supplier.purchases.aggregate(
        total_purchases=Coalesce(Count("id"), 0),
        total_quantity=Coalesce(Sum("quantity"), 0),
    )
    total_spent = purchases_qs.aggregate(ts=Coalesce(Sum("total_cost"), Decimal("0.00")))["ts"]

    ctx.update(
        {
            "supplier": supplier,
            "purchases": purchases,
            "total_purchases": aggregates["total_purchases"],
            "total_quantity": aggregates["total_quantity"],
            "total_spent": _q2(total_spent),
        }
    )
    return render(request, "supplier_detail.html", ctx)


# -----------------------------
# Purchases
# -----------------------------
@module_required("access_store")
def purchase_list(request: HttpRequest) -> HttpResponse:
    """
    List & create/update CoffeePurchase.
    Adds simple filtering (supplier q, date range, type/category) and pagination.
    """
    # Filters
    q = (request.GET.get("q") or "").strip()
    date_from = request.GET.get("from") or ""
    date_to = request.GET.get("to") or ""
    coffee_type = (request.GET.get("ctype") or "").strip()  # 'AR'/'RB'
    coffee_category = (request.GET.get("ccat") or "").strip()  # 'GR'/'PA'/'KB'

    purchases = CoffeePurchase.objects.select_related("supplier").all()

    if q:
        purchases = purchases.filter(
            Q(supplier__name__icontains=q) | Q(supplier__phone__icontains=q) | Q(supplier__id__icontains=q)
        )
    if date_from:
        purchases = purchases.filter(purchase_date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__lte=date_to)
    if coffee_type:
        purchases = purchases.filter(coffee_type=coffee_type)
    if coffee_category:
        purchases = purchases.filter(coffee_category=coffee_category)

    purchases = purchases.order_by("-purchase_date", "-id")

    # Form handling (create/update)
    instance = None
    action = "created"
    if request.method == "POST":
        purchase_id = request.POST.get("purchase_id")
        if purchase_id:
            instance = get_object_or_404(CoffeePurchase, id=purchase_id)
            action = "updated"

        form = CoffeePurchaseForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    obj = form.save(commit=False)
                    if not instance:
                        obj.recorded_by = request.user
                    obj.save()
                    messages.success(request, f"Purchase {action} successfully!")
                    return redirect("store:purchase_list")
            except Exception as e:
                messages.error(request, f"Error saving purchase: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CoffeePurchaseForm(user=request.user)

    # Pagination
    try:
        per_page = int(request.GET.get("per_page", 20))
    except ValueError:
        per_page = 20
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 20

    paginator = Paginator(purchases, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "form": form,
        "purchases": page_obj,
        "current_page": "purchases",
        # keep current filters in template
        "q": q,
        "date_from": date_from,
        "date_to": date_to,
        "coffee_type": coffee_type,
        "coffee_category": coffee_category,
        "per_page": per_page,
        "per_page_options": PER_PAGE_OPTIONS,
    }
    return render(request, "purchase_list.html", context)


STATUS_BADGES = {
    "P": ("Pending", "bg-amber-100 text-amber-800"),
    "T": ("Partial", "bg-blue-100 text-blue-800"),
    "D": ("Paid", "bg-emerald-100 text-emerald-800"),
}


@module_required("access_store")
def purchase_detail(request: HttpRequest, pk: int) -> HttpResponse:
    # Preload related transactions (capped to 50 in Python after prefetch)
    tx_base = (
        SupplierTransaction.objects.select_related("account", "created_by")
        .only(
            "id",
            "created_at",
            "transaction_type",
            "amount",
            "reference",
            "account_id",
            "purchase_id",
            "created_by__username",
            "created_by__first_name",
            "created_by__last_name",
        )
        .order_by("-created_at")
    )

    purchase = get_object_or_404(
        CoffeePurchase.objects.select_related("supplier").prefetch_related(
            Prefetch("supplier_transactions", queryset=tx_base, to_attr="txns_sorted")
        ),
        pk=pk,
    )
    purchase_txns = getattr(purchase, "txns_sorted", [])[:50]

    account, _ = SupplierAccount.objects.get_or_create(supplier=purchase.supplier)
    assessment: Assessment | None = getattr(purchase, "assessment", None)

    status_label, status_class = STATUS_BADGES.get(purchase.payment_status, ("Unknown", "bg-gray-100 text-gray-700"))

    ctx: dict[str, Any] = {
        "purchase": purchase,
        "account": account,
        "assessment": assessment,
        "status_label": status_label,
        "status_class": status_class,
        "now": timezone.now(),
        "price_per_kg": None,
        "total_payable": None,
        "moisture_penalty": Decimal("0.00"),
        "defects_breakdown": [],
        "is_rejected": False,
        "analysis_outturn_pct": None,
        "purchase_txns": purchase_txns,
    }

    if assessment:
        # Convert helpers
        def d(val) -> Decimal:
            return Decimal(str(val)) if val is not None else Decimal("0")

        def over(x: Decimal, base: Decimal) -> Decimal:
            return x - base if x > base else Decimal("0")

        qty = d(purchase.quantity)
        price = d(assessment.final_price)  # final computed price per kg
        ref_price = d(assessment.ref_price)
        moisture = d(assessment.moisture_content)

        # Moisture penalty per model rule (only if moisture >= 14)
        moisture_penalty = Decimal("0")
        if moisture >= Decimal("14") and ref_price > 0:
            moisture_penalty = (moisture - Decimal("14")) * ref_price * Decimal("0.002")

        price_q = _q2(price) if price else None
        total_payable_q = _q2(price * qty) if price and qty else None

        ctx.update(
            {
                "price_per_kg": price_q,
                "total_payable": total_payable_q,
                "moisture_penalty": _q2(moisture_penalty),
                "is_rejected": assessment.is_rejected,
                "analysis_outturn_pct": assessment.derived_outturn,
            }
        )

        # Deduction/bonus breakdown aligned with compute_final_price
        RATE_GP1 = Decimal("50")  # over 4%
        RATE_GP2 = Decimal("20")  # over 10%
        RATE_BELOW12 = Decimal("30")  # over 1%
        RATE_PODS = Decimal("10")  # full %
        RATE_HUSKS = Decimal("10")  # full %
        RATE_STONES = Decimal("20")  # full %
        RATE_FM = Decimal("0")  # not priced

        gp1 = d(assessment.group1_defects)
        gp2 = d(assessment.group2_defects)
        b12 = d(assessment.below_screen_12)
        pods = d(assessment.pods)
        husks = d(assessment.husks)
        stones = d(assessment.stones)
        fm = d(assessment.fm)

        rows = [
            ("Group 1 defects", gp1, RATE_GP1, over(gp1, Decimal("4"))),
            ("Group 2 defects", gp2, RATE_GP2, over(gp2, Decimal("10"))),
            ("< Screen 12", b12, RATE_BELOW12, over(b12, Decimal("1"))),
            ("Pods", pods, RATE_PODS, pods),
            ("Husks", husks, RATE_HUSKS, husks),
            ("Stones/Sticks", stones, RATE_STONES, stones),
            ("Foreign Matter", fm, RATE_FM, fm),
        ]
        ctx["defects_breakdown"] = [
            {"label": label, "pct": pct, "rate": rate, "deduction": _q2(pct_for_calc * rate)}
            for (label, pct, rate, pct_for_calc) in rows
        ]

    return render(request, "purchase_detail.html", ctx)


# -----------------------------
# Sales
# -----------------------------
@module_required("access_store")
def sale_list(request: HttpRequest) -> HttpResponse:
    """
    List & create/update CoffeeSale with pagination and quick totals.
    """
    sales_qs = CoffeeSale.objects.select_related("recorded_by", "customer").order_by("-sale_date", "-created_at")

    # Create/Update
    instance = None
    action = "created"
    if request.method == "POST":
        sale_id = request.POST.get("sale_id")
        if sale_id:
            instance = get_object_or_404(CoffeeSale, id=sale_id)
            action = "updated"

        form = CoffeeSaleForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    if not instance:
                        sale.recorded_by = request.user
                    sale.save()
                    messages.success(request, f"Sale {action} successfully!")
                    return redirect("store:sale_list")
            except Exception as e:
                messages.error(request, f"Error saving sale: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CoffeeSaleForm(user=request.user)

    # Pagination
    try:
        per_page = int(request.GET.get("per_page", 20))
    except ValueError:
        per_page = 20
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 20

    paginator = Paginator(sales_qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Quick totals (visible in header)
    total_amount_expr = ExpressionWrapper(
        F("quantity_kg") * F("unit_price_ugx"), output_field=DecimalField(max_digits=20, decimal_places=2)
    )
    totals = sales_qs.aggregate(
        cnt=Coalesce(Count("id"), 0),
        qty=Coalesce(Sum("quantity_kg"), 0),
        revenue=Coalesce(Sum(total_amount_expr), Decimal("0.00")),
    )

    context = {
        "form": form,
        "sales": page_obj,
        "current_page": "sales",
        "total_sales": totals["cnt"],
        "total_sale_quantity": totals["qty"],
        "total_revenue": totals["revenue"],
        "per_page": per_page,
        "per_page_options": PER_PAGE_OPTIONS,
    }
    return render(request, "sale_list.html", context)


@module_required("access_store")
def sale_detail(request: HttpRequest, pk: int) -> HttpResponse:
    sale = get_object_or_404(CoffeeSale.objects.select_related("customer", "recorded_by"), pk=pk)
    ctx = get_base_context(request, "Sale Details")
    ctx.update({"sale": sale})
    return render(request, "sale_detail.html", ctx)
