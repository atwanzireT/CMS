from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Sum, Count, Avg, Q, F, Case, When, Value, IntegerField, Max, CharField, Prefetch
)
from django.contrib.postgres.aggregates import ArrayAgg
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from assessment.models import Assessment
from .models import Supplier, CoffeePurchase, SupplierTransaction, SupplierAccount
from .forms import SupplierForm, CoffeePurchaseForm
from sales.models import CoffeeSale
from inventory.models import CoffeeInventory
from sales.forms import CoffeeSaleForm
from accounts.permissions import module_required
from django.db.models import ExpressionWrapper, DecimalField

# ========== UTILITY FUNCTIONS ==========
def get_base_context(request, page_title='Default Page Title'):
    return {
        'page_title': page_title,
        'user': request.user
    }

# ========== DASHBOARD ==============
@module_required("access_store")
def store_dashboard(request):
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)

    # ---------- Purchases ----------
    recent_purchases_qs = CoffeePurchase.objects.filter(purchase_date__gte=thirty_days_ago)

    total_purchase_quantity = recent_purchases_qs.aggregate(total=Sum('quantity'))['total'] or 0
    total_purchase_bags = recent_purchases_qs.aggregate(total=Sum('bags'))['total'] or 0

    # Breakdowns as dicts
    raw_payment_status = list(
        recent_purchases_qs.values('payment_status').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity'),
        )
    )

    # ---------- Sales ----------
    recent_sales_qs = CoffeeSale.objects.filter(sale_date__gte=thirty_days_ago)

    total_amount_expr = ExpressionWrapper(
        F('quantity_kg') * F('unit_price_ugx'),
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )

    total_sale_quantity = recent_sales_qs.aggregate(total=Sum('quantity_kg'))['total'] or 0
    total_revenue = recent_sales_qs.aggregate(total=Sum(total_amount_expr))['total'] or Decimal('0.00')

    # ---------- Inventory ----------
    inventory_items = CoffeeInventory.objects.all()
    total_inventory_value = inventory_items.aggregate(total=Sum('current_value'))['total'] or Decimal('0.00')
    total_inventory_quantity = inventory_items.aggregate(total=Sum('quantity'))['total'] or Decimal('0.00')
    low_stock_items = inventory_items.filter(quantity__lt=100)

    # ---------- Recent lists ----------
    recent_purchases_list = (
        CoffeePurchase.objects.select_related('supplier')
        .order_by('-purchase_date')[:5]
    )

    recent_sales_list = list(
        CoffeeSale.objects.select_related('customer')
        .annotate(total_amount=total_amount_expr)
        .order_by('-sale_date', '-created_at')[:5]
    )

    # ---------- Supplier stats ----------
    active_suppliers = (
        Supplier.objects.annotate(
            purchase_count=Count('purchases'),
            total_quantity=Sum('purchases__quantity'),
        )
        .filter(purchase_count__gt=0)
        .order_by('-total_quantity')[:5]
    )

    # ---------- Coffee type breakdowns ----------
    raw_coffee_type_purchases = list(
        recent_purchases_qs.values('coffee_type').annotate(
            total_quantity=Sum('quantity'),
            count=Count('id'),
        ).order_by('-total_quantity')
    )
    raw_coffee_type_sales = list(
        recent_sales_qs.values('coffee_type').annotate(
            total_quantity=Sum('quantity_kg'),
            total_revenue=Sum(total_amount_expr),
        ).order_by('-total_quantity')
    )

    # ---------- Build label maps ----------
    coffee_type_labels = dict(CoffeePurchase.COFFEE_TYPES)
    payment_status_labels = dict(CoffeePurchase.PAYMENT_STATUS_CHOICES)

    # Attach labels so the template only does dot lookups (no dict indexing)
    payment_status = []
    for row in raw_payment_status:
        payment_status.append({
            **row,
            'status_label': payment_status_labels.get(row['payment_status'], 'Unknown')
        })

    coffee_type_purchases = []
    for row in raw_coffee_type_purchases:
        coffee_type_purchases.append({
            **row,
            'label': coffee_type_labels.get(row['coffee_type'], row['coffee_type']),
        })

    coffee_type_sales = []
    for row in raw_coffee_type_sales:
        coffee_type_sales.append({
            **row,
            'label': coffee_type_labels.get(row['coffee_type'], row['coffee_type']),
        })

    # For recent sales (model instances), add a convenient label attribute
    for s in recent_sales_list:
        if hasattr(s, 'get_coffee_type_display'):
            s.coffee_type_label = s.get_coffee_type_display()
        else:
            s.coffee_type_label = coffee_type_labels.get(getattr(s, 'coffee_type', None), '—')

    context = {
        'today': today,
        'total_purchases': CoffeePurchase.objects.count(),
        'total_purchase_quantity': total_purchase_quantity,
        'total_purchase_bags': total_purchase_bags,
        'total_sales': CoffeeSale.objects.count(),
        'total_sale_quantity': total_sale_quantity,
        'total_revenue': total_revenue,
        'total_inventory_value': total_inventory_value,
        'total_inventory_quantity': total_inventory_quantity,

        'payment_status': payment_status,                # now has .status_label
        'inventory_items': inventory_items,
        'low_stock_items': low_stock_items,
        'recent_purchases': recent_purchases_list,
        'recent_sales': recent_sales_list,               # each has .coffee_type_label
        'active_suppliers': active_suppliers,

        'coffee_type_purchases': coffee_type_purchases,  # each has .label
        'coffee_type_sales': coffee_type_sales,          # each has .label
    }
    return render(request, 'store_dashboard.html', context)

# ========== SUPPLIER VIEWS ==========
PER_PAGE_OPTIONS = [10, 20, 50, 100]


@module_required("access_store")
def supplier_list(request):
    """
    Supplier list with:
    - GET ?q= search (name/phone/id)
    - Annotated last assessed delivery & distinct coffee types (Arabica/Robusta)
    - POST create/update Supplier OR create CoffeePurchase (same page)
    - Pagination with Paginator.get_page()
    """
    # --- inputs
    q = (request.GET.get("q") or "").strip()
    try:
        per_page = int(request.GET.get("per_page", 20))
    except ValueError:
        per_page = 20
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 20

    # --- base queryset + search
    base_qs = Supplier.objects.all()
    if q:
        base_qs = base_qs.filter(
            Q(name__icontains=q) |
            Q(phone__icontains=q) |
            Q(id__icontains=q)
        )

    # Only consider purchases that have an assessment for annotations
    assessed_filter = Q(purchases__assessment__isnull=False)

    suppliers_qs = (
        base_qs
        .annotate(
            last_supply=Max('purchases__delivery_date', filter=assessed_filter),
            coffee_types=ArrayAgg(
                Case(
                    When(purchases__coffee_type=CoffeePurchase.ARABICA, then=Value('Arabica')),
                    When(purchases__coffee_type=CoffeePurchase.ROBUSTA, then=Value('Robusta')),
                    default=Value('Unknown'),
                    output_field=CharField(),
                ),
                filter=assessed_filter,
                distinct=True,
            ),
        )
        .order_by('name')
    )

    # --- handle POSTs (two cases): SupplierForm OR CoffeePurchaseForm
    if request.method == 'POST':
        # Heuristic: if purchase fields are present, treat it as a purchase submission
        is_purchase_post = any(k in request.POST for k in ("coffee_category", "coffee_type", "quantity"))

        if is_purchase_post:
            supplier_id = request.POST.get('supplier_id')
            supplier = get_object_or_404(Supplier, id=supplier_id)

            purchase_form = CoffeePurchaseForm(request.POST)
            if purchase_form.is_valid():
                obj: CoffeePurchase = purchase_form.save(commit=False)
                obj.supplier = supplier
                obj.recorded_by = request.user
                obj.assessment_needed = True
                if not obj.purchase_date:
                    obj.purchase_date = timezone.now().date()
                if not obj.delivery_date:
                    obj.delivery_date = timezone.now().date()
                obj.save()
                messages.success(request, f"Purchase recorded for {supplier.name}.")
                # Preserve query context on redirect
                return redirect(f"{request.path}?q={q}&per_page={per_page}")
            else:
                # Show a concise error message; keep UI simple
                messages.error(request, "Please correct the errors in the purchase form.")
                return redirect(f"{request.path}?q={q}&per_page={per_page}")

        # Otherwise, it’s a Supplier create/update
        supplier_id = request.POST.get('supplier_id')  # may be blank for create
        instance = get_object_or_404(Supplier, id=supplier_id) if supplier_id else None
        form = SupplierForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            supplier = form.save(commit=False)
            if instance is None:
                supplier.created_by = request.user
            supplier.save()
            messages.success(request, f"Supplier {'updated' if instance else 'created'} successfully!")
            return redirect(f"{request.path}?q={q}&per_page={per_page}")
    else:
        form = SupplierForm(user=request.user)

    # --- pagination (robust & simple)
    paginator = Paginator(suppliers_qs, per_page)
    suppliers_page = paginator.get_page(request.GET.get('page'))

    return render(request, 'supplier_list.html', {
        'form': form,                       # supplier form
        'suppliers': suppliers_page,        # page object
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
    })


@module_required("access_store")
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    context = get_base_context(request, f'Supplier Details - {supplier.name}')
    
    purchases = supplier.purchases.all().order_by('-purchase_date')[:10]
    context.update({
        'supplier': supplier,
        'purchases': purchases,
        'total_purchases': supplier.purchases.count(),
        'total_quantity': supplier.purchases.aggregate(Sum('quantity'))['quantity__sum'] or 0,
        'total_spent': sum(purchase.total_cost for purchase in purchases)
    })
    return render(request, 'supplier_detail.html', context)

# ========== COFFEE PURCHASE VIEWS ==========
@module_required("access_store")
def purchase_list(request):
    purchases = CoffeePurchase.objects.select_related('supplier')
    instance = None
    action = 'created'

    if request.method == 'POST':
        purchase_id = request.POST.get('purchase_id')
        if purchase_id:
            instance = get_object_or_404(CoffeePurchase, id=purchase_id)
            action = 'updated'

        form = CoffeePurchaseForm(request.POST, instance=instance, user=request.user)

        if form.is_valid():
            try:
                with transaction.atomic():
                    purchase = form.save(commit=False)
                    if not instance:
                        purchase.recorded_by = request.user
                    purchase.save()
                    messages.success(request, f'Purchase {action} successfully!')
                    return redirect('purchase_list')
            except Exception as e:
                messages.error(request, f'Error saving purchase: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CoffeePurchaseForm(user=request.user)

    context = {
        'form': form,
        'purchases': purchases,
        'current_page': 'purchases',
    }
    return render(request, 'purchase_list.html', context)



Q2 = Decimal("0.01")
def _q2(x): return (x or Decimal("0")).quantize(Q2)

STATUS_BADGES = {
    "P": ("Pending", "bg-amber-100 text-amber-800"),
    "T": ("Partial", "bg-blue-100 text-blue-800"),
    "D": ("Paid",    "bg-emerald-100 text-emerald-800"),
}


@module_required("access_store")
def purchase_detail(request, pk: int):
    # Base queryset (NO slice here)
    tx_base = (
        SupplierTransaction.objects
        .select_related("account", "created_by")
        .only(
            "id", "created_at", "transaction_type", "amount", "reference",
            "account_id", "purchase_id",
            "created_by__username", "created_by__first_name", "created_by__last_name",
        )
        .order_by("-created_at")
    )

    purchase = get_object_or_404(
        CoffeePurchase.objects
        .select_related("supplier")
        .prefetch_related(Prefetch("supplier_transactions", queryset=tx_base, to_attr="txns_sorted")),
        pk=pk,
    )

    # Use prefetched list and slice in Python
    purchase_txns = getattr(purchase, "txns_sorted", [])[:50]

    account, _ = SupplierAccount.objects.get_or_create(supplier=purchase.supplier)
    assessment = getattr(purchase, "assessment", None)

    status_label, status_class = STATUS_BADGES.get(
        purchase.payment_status, ("Unknown", "bg-gray-100 text-gray-700")
    )

    ctx = {
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

        "purchase_txns": purchase_txns,  # already ordered & sliced
    }

    if assessment:
        # Helpers
        def d(x):
            return Decimal(str(x)) if x is not None else Decimal("0")

        def over(x, base):
            x = d(x)
            base = d(base)
            return x - base if x > base else Decimal("0")

        qty = d(purchase.quantity)
        price = d(assessment.analysis_price_ugx)  # final_price from model (may be None -> 0)
        ref_price = d(assessment.ref_price)
        moisture = d(assessment.moisture_content)

        # Moisture penalty per model rule: (moisture - 14) * ref_price * 0.002, only if moisture >= 14
        moisture_penalty = Decimal("0")
        if moisture >= Decimal("14") and ref_price > 0:
            moisture_penalty = (moisture - Decimal("14")) * ref_price * Decimal("0.002")

        # Quantize and update top figures
        price_q = _q2(price) if price else None
        total_payable_q = _q2(price * qty) if price and qty else None

        ctx.update({
            "price_per_kg": price_q,
            "total_payable": total_payable_q,
            "moisture_penalty": _q2(moisture_penalty),
            "is_rejected": assessment.is_rejected,
            "analysis_outturn_pct": assessment.analysis_outturn_pct,
        })

        # Rates (align with compute_final_price logic)
        RATE_GP1      = Decimal("50")   # over 4%
        RATE_GP2      = Decimal("20")   # over 10%
        RATE_BELOW12  = Decimal("30")   # over 1%
        RATE_PODS     = Decimal("10")   # full %
        RATE_HUSKS    = Decimal("10")   # full %
        RATE_STONES   = Decimal("20")   # full %
        RATE_FM       = Decimal("0")    # not priced in compute_final_price()

        gp1 = d(assessment.group1_defects)
        gp2 = d(assessment.group2_defects)
        b12 = d(assessment.below_screen_12)
        pods = d(assessment.pods)
        husks = d(assessment.husks)
        stones = d(assessment.stones)
        fm = d(assessment.fm)

        # For display we show the raw %; for deduction we apply thresholds where applicable
        rows = [
            ("Group 1 defects", gp1, RATE_GP1, over(gp1, Decimal("4"))),
            ("Group 2 defects", gp2, RATE_GP2, over(gp2, Decimal("10"))),
            ("< Screen 12",     b12, RATE_BELOW12, over(b12, Decimal("1"))),
            ("Pods",            pods, RATE_PODS, pods),
            ("Husks",           husks, RATE_HUSKS, husks),
            ("Stones/Sticks",   stones, RATE_STONES, stones),
            ("Foreign Matter",  fm, RATE_FM, fm),
        ]

        ctx["defects_breakdown"] = [
            {
                "label": label,
                "pct":   pct,                         # raw percentage shown in UI
                "rate":  rate,                        # UGX per %
                "deduction": _q2(pct_for_calc * rate) # computed deduction
            }
            for (label, pct, rate, pct_for_calc) in rows
        ]

    return render(request, "purchase_detail.html", ctx)



# ========== COFFEE SALE VIEWS ==========
@module_required("access_store")
def sale_list(request):
    sales = CoffeeSale.objects.select_related('recorded_by').order_by('-sale_date')
    instance = None
    action = 'created'

    if request.method == 'POST':
        sale_id = request.POST.get('sale_id')
        if sale_id:
            instance = get_object_or_404(CoffeeSale, id=sale_id)
            action = 'updated'

        form = CoffeeSaleForm(request.POST, instance=instance, user=request.user)

        if form.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    if not instance:
                        sale.recorded_by = request.user
                    sale.save()
                    
                    messages.success(request, f'Sale {action} successfully!')
                    return redirect('sale_list')
            except Exception as e:
                messages.error(request, f'Error saving sale: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CoffeeSaleForm(user=request.user)

    context = {
        'form': form,
        'sales': sales,
        'current_page': 'sales',  # Added for consistent navigation
    }
    return render(request, 'sale_list.html', context)


@module_required("access_store")
def sale_detail(request, pk):
    sale = get_object_or_404(CoffeeSale, pk=pk)
    context = get_base_context(request, 'Sale Details')
    
    context.update({
        'sale': sale
    })
    return render(request, 'sale_detail.html', context)
