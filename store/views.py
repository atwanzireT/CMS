from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Sum, Count, Avg, Q, F, Case, When, Value, IntegerField
)
from django.db.models import Q, Max, Case, When, Value, CharField
from django.contrib.postgres.aggregates import ArrayAgg
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Prefetch
from assessment.models import Assessment
from .models import *
from .forms import *
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.utils import timezone

# ========== UTILITY FUNCTIONS ==========
def get_base_context(request, page_title='Default Page Title'):
    return {
        'page_title': page_title,
        'user': request.user
    }

# ========== DASHBOARD ==============
@login_required
def store_dashboard(request):
    # Get date ranges
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)
    
    # Purchase statistics
    total_purchases = CoffeePurchase.objects.count()
    recent_purchases = CoffeePurchase.objects.filter(purchase_date__gte=thirty_days_ago)
    total_purchase_quantity = recent_purchases.aggregate(total=Sum('quantity'))['total'] or 0
    total_purchase_bags = recent_purchases.aggregate(total=Sum('bags'))['total'] or 0
    
    # Payment status breakdown
    payment_status = recent_purchases.values('payment_status').annotate(
        count=Count('id'),
        total_quantity=Sum('quantity')
    )
    
    # Sale statistics
    total_sales = CoffeeSale.objects.count()
    recent_sales = CoffeeSale.objects.filter(sale_date__gte=thirty_days_ago)
    total_sale_quantity = recent_sales.aggregate(total=Sum('quantity'))['total'] or 0
    total_revenue = recent_sales.aggregate(
        total=Sum(F('quantity') * F('unit_price'))
    )['total'] or Decimal('0.00')
    
    # Inventory overview
    inventory_items = CoffeeInventory.objects.all()
    total_inventory_value = inventory_items.aggregate(
        total=Sum('current_value')
    )['total'] or Decimal('0.00')
    total_inventory_quantity = inventory_items.aggregate(
        total=Sum('quantity')
    )['total'] or Decimal('0.00')
    
    # Low stock alerts (less than 100kg)
    low_stock_items = inventory_items.filter(quantity__lt=100)
    
    # Recent activities
    recent_purchases_list = CoffeePurchase.objects.select_related('supplier').order_by('-purchase_date')[:5]
    recent_sales_list = CoffeeSale.objects.order_by('-sale_date')[:5]
    
    # Supplier statistics
    active_suppliers = Supplier.objects.annotate(
        purchase_count=Count('purchases'),
        total_quantity=Sum('purchases__quantity')
    ).filter(purchase_count__gt=0).order_by('-total_quantity')[:5]
    
    # Coffee type breakdown
    coffee_type_purchases = recent_purchases.values('coffee_type').annotate(
        total_quantity=Sum('quantity'),
        count=Count('id')
    )
    
    coffee_type_sales = recent_sales.values('coffee_type').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('unit_price'))
    )
    
    context = {
        'today': today,
        'total_purchases': total_purchases,
        'total_purchase_quantity': total_purchase_quantity,
        'total_purchase_bags': total_purchase_bags,
        'total_sales': total_sales,
        'total_sale_quantity': total_sale_quantity,
        'total_revenue': total_revenue,
        'total_inventory_value': total_inventory_value,
        'total_inventory_quantity': total_inventory_quantity,
        'payment_status': payment_status,
        'inventory_items': inventory_items,
        'low_stock_items': low_stock_items,
        'recent_purchases': recent_purchases_list,
        'recent_sales': recent_sales_list,
        'active_suppliers': active_suppliers,
        'coffee_type_purchases': coffee_type_purchases,
        'coffee_type_sales': coffee_type_sales,
    }
    
    return render(request, 'store_dashboard.html', context)



# ========== SUPPLIER VIEWS ==========
@login_required
def supplier_list(request):
    # Include assessed-only purchases (change to decision="Accepted" if needed)
    assessed_filter = Q(purchases__assessment__isnull=False)
    # assessed_filter = Q(purchases__assessment__decision="Accepted")

    suppliers = (
        Supplier.objects
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

    supplier_id = request.POST.get('supplier_id') if request.method == 'POST' else None
    instance = get_object_or_404(Supplier, id=supplier_id) if supplier_id else None

    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            supplier = form.save(commit=False)
            if not instance:
                supplier.created_by = request.user
            supplier.save()
            messages.success(request, f'Supplier {"updated" if instance else "created"} successfully!')
            return redirect('supplier_list')
    else:
        form = SupplierForm(user=request.user)

    return render(request, 'supplier_list.html', {'form': form, 'suppliers': suppliers})



@login_required
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
@login_required
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


@login_required
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
@login_required
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


@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(CoffeeSale, pk=pk)
    context = get_base_context(request, 'Sale Details')
    
    context.update({
        'sale': sale
    })
    return render(request, 'sale_detail.html', context)


# ========== INVENTORY VIEWS ==========
@login_required
def inventory_dashboard(request):
    # Get all inventory items
    all_items = CoffeeInventory.objects.select_related().all()
    
    # Basic aggregates
    aggregates = all_items.aggregate(
        total_quantity=Sum('quantity'),
        total_value=Sum('current_value'),
        avg_cost=Avg('average_unit_cost')
    )
    
    # Inventory by category
    inventory_by_category = all_items.values(
        'coffee_category',
        'coffee_type'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_value=Sum('current_value'),
        average_cost=Avg('average_unit_cost'),
        item_count=Count('id')
    ).order_by('coffee_category', 'coffee_type')
    
    # Calculate percentages for each category
    total_quantity = aggregates['total_quantity'] or 1  # Avoid division by zero
    for category in inventory_by_category:
        category['percentage'] = (category['total_quantity'] / total_quantity) * 100
        category['coffee_category_display'] = dict(CoffeeInventory.COFFEE_CATEGORIES).get(
            category['coffee_category'], 'Unknown'
        )
        category['coffee_type_display'] = dict(CoffeeInventory.COFFEE_TYPE_CHOICES).get(
            category['coffee_type'], 'Unknown'
        )
    
    # Quality assessment summary - modified to avoid using is_rejected as a filter
    quality_summary = Assessment.objects.annotate(
        is_rejected_case=Case(
            When(
                Q(moisture_content__gt=20) | 
                Q(below_screen_12__gt=3) |
                Q(outturn__isnull=True) |
                Q(outturn=0),
                then=Value(1)
            ),
            default=Value(0),
            output_field=IntegerField()
        )
    ).values(
        'coffee__coffee_category',
        'coffee__coffee_type'
    ).annotate(
        total_assessed=Count('id'),
        avg_moisture=Avg('moisture_content'),
        avg_outturn=Avg('outturn'),
        rejected_count=Sum('is_rejected_case')
    ).order_by('coffee__coffee_category', 'coffee__coffee_type')
    
    # Stock status breakdown
    stock_status = {
        'low': all_items.filter(quantity__lt=10).count(),
        'medium': all_items.filter(quantity__gte=10, quantity__lt=50).count(),
        'high': all_items.filter(quantity__gte=50).count()
    }
    
    # Recent purchases (last 30 days)
    recent_purchases = CoffeePurchase.objects.filter(
        purchase_date__gte=timezone.now() - timezone.timedelta(days=30)
    ).select_related('supplier').order_by('-purchase_date')[:5]
    
    context = {
        'page_title': 'Inventory Dashboard',
        'inventory_items': all_items,
        'total_items': all_items.count(),
        'total_quantity': aggregates['total_quantity'] or 0,
        'total_value': aggregates['total_value'] or 0,
        'average_cost_per_kg': aggregates['avg_cost'] or 0,
        'inventory_by_category': inventory_by_category,
        'quality_summary': quality_summary,
        'stock_status': stock_status,
        'recent_purchases': recent_purchases,
        'low_stock_items': all_items.filter(quantity__lt=10),
    }
    return render(request, 'inventory_dashboard.html', context)



@login_required
def inventory_detail(request, pk):
    inventory = get_object_or_404(CoffeeInventory, pk=pk)
    context = get_base_context(request, 'Inventory Details')
    
    context.update({
        'inventory': inventory,
        'purchases': CoffeePurchase.objects.filter(
            coffee_type=inventory.coffee_type
        ).order_by('-purchase_date')[:10],
        'sales': CoffeeSale.objects.filter(
            coffee_type=inventory.coffee_type
        ).order_by('-sale_date')[:10]
    })
    return render(request, 'inventory_detail.html', context)

