# views.py (finance)

from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.humanize.templatetags.humanize import intcomma  # ✅ needed for balance_html
from accounts.permissions import module_required
from store.models import CoffeePurchase, SupplierAccount, SupplierTransaction
from assessment.models import Assessment
from sales.models import CoffeeSale


# ---- helpers ----

def _month_bounds(dt):
    first = dt.replace(day=1)
    if first.month == 12:
        next_month = first.replace(year=first.year + 1, month=1, day=1)
    else:
        next_month = first.replace(month=first.month + 1, day=1)
    return first, next_month


def _purchase_payable_amount(purchase: CoffeePurchase) -> Decimal:
    """
    analysis_price_ugx (per-kg) × purchase.quantity_kg
    Falls back to 0 if no assessment or missing inputs.
    """
    try:
        a = purchase.assessment  # OneToOne
    except Assessment.DoesNotExist:
        return Decimal("0")

    qty = getattr(purchase, "quantity_kg", None)
    if not a or a.analysis_price_ugx is None or qty is None:
        return Decimal("0")

    per_kg = Decimal(a.analysis_price_ugx)
    qty = Decimal(qty)
    return per_kg * qty


def _q2(x):
    if x is None:
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---- views ----
@module_required("access_finance")
def finance_dashboard(request):
    """
    Finance overview:
    - Monthly revenue (sales): sum(quantity_kg * unit_price_ugx) within current month
    - Pending supplier payments (only assessed purchases)
    - Cash flow this month: cash_in (sales) vs cash_out (paid purchases)
    - Available cash: cash_in - cash_out (this month)
    """
    today = timezone.localdate()
    month_start, month_next = _month_bounds(today)

    # ---- Revenue (Sales) — current month ----
    sales_this_month = (
        CoffeeSale.objects
        .filter(sale_date__gte=month_start, sale_date__lt=month_next)
        .annotate(
            line_total=ExpressionWrapper(
                F("quantity_kg") * F("unit_price_ugx"),   # ✅ correct field names
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        )
    )
    monthly_revenue = sales_this_month.aggregate(total=Sum("line_total"))["total"] or Decimal("0")

    # Cash inflow this month (proxy: all sales recognized as cash in)
    cash_inflow = monthly_revenue

    # ---- Supplier Payments (Purchases) ----
    assessed_purchases_qs = (
        CoffeePurchase.objects
        .select_related("supplier", "assessment")
        .filter(assessment__isnull=False)
    )

    pending_purchases_qs = assessed_purchases_qs.filter(
        Q(payment_status=CoffeePurchase.PAYMENT_PENDING) |
        Q(payment_status=CoffeePurchase.PAYMENT_PARTIAL)
    )
    completed_purchases_qs = assessed_purchases_qs.filter(
        payment_status=CoffeePurchase.PAYMENT_PAID
    )

    # Pending total (all-time)
    pending_payments_total = Decimal("0")
    pending_payments = []
    for p in pending_purchases_qs:
        amount = _purchase_payable_amount(p)
        pending_payments_total += amount
        pending_payments.append({
            "id": p.id,
            "supplier": p.supplier,
            "purchase": p,
            "amount": amount,
            "purchase_date": p.purchase_date,
            "coffee_type": p.get_coffee_type_display(),
            "coffee_category": p.get_coffee_category_display(),
            "quantity": getattr(p, "quantity_kg", None),   # ✅ show kg
            "status": p.get_payment_status_display(),
        })

    # Completed totals & cash outflow (this month)
    completed_payments_total = Decimal("0")
    cash_outflow = Decimal("0")
    completed_payments = []
    for p in completed_purchases_qs:
        amount = _purchase_payable_amount(p)
        completed_payments_total += amount
        if month_start <= p.purchase_date < month_next:
            cash_outflow += amount  # proxy: paid this month ~ purchase_date in month

        completed_payments.append({
            "id": p.id,
            "supplier": p.supplier,
            "purchase": p,
            "amount": amount,
            "purchase_date": p.purchase_date,
            "coffee_type": p.get_coffee_type_display(),
            "coffee_category": p.get_coffee_category_display(),
            "quantity": getattr(p, "quantity_kg", None),   # ✅
            "status": p.get_payment_status_display(),
        })

    available_cash = cash_inflow - cash_outflow
    net_cash_flow = available_cash

    context = {
        "page_title": "Finance Dashboard",
        "period": {
            "month_start": month_start,
            "month_end": month_next - timezone.timedelta(days=1),
        },
        "metrics": {
            "monthly_revenue": monthly_revenue,
            "pending_payments_total": pending_payments_total,
            "completed_payments_total": completed_payments_total,
            "cash_inflow": cash_inflow,
            "cash_outflow": cash_outflow,
            "available_cash": available_cash,
            "net_cash_flow": net_cash_flow,
        },
        "lists": {
            "pending_payments": pending_payments,
            "completed_payments": completed_payments,
        },
    }
    return render(request, "finance_dashboard.html", context)


@module_required("access_finance")
@require_POST
def create_supplier_payment(request, pk: int):
    """
    POST a CREDIT SupplierTransaction for the purchase's supplier.
    Body: amount, reference (optional), notes (optional).
    Returns JSON: ok, balance_html, row_html
    """
    purchase = get_object_or_404(
        CoffeePurchase.objects.select_related("supplier"),
        pk=pk
    )

    raw_amount = request.POST.get("amount") or request.POST.get("amount_ugx")
    reference = (request.POST.get("reference") or "").strip() or None
    notes = (request.POST.get("notes") or "").strip()

    try:
        amount = _q2(raw_amount)
    except Exception:
        return HttpResponseBadRequest("Invalid amount.")

    if amount <= 0:
        return HttpResponseBadRequest("Amount must be greater than zero.")

    account, _ = SupplierAccount.objects.get_or_create(supplier=purchase.supplier)

    tx = SupplierTransaction.objects.create(
        account=account,
        amount=amount,
        transaction_type=SupplierTransaction.CREDIT,
        reference=reference,
        created_by=request.user,
        purchase=purchase,
        notes=notes,
    )

    row_html = render_to_string(
        "store/partials/_purchase_txn_row.html",
        {"t": tx},
        request=request,
    )

    # ✅ intcomma import fixed above
    balance_html = f"UGX {intcomma(SupplierAccount.objects.get(pk=account.pk).balance)}"

    return JsonResponse({
        "ok": True,
        "balance_html": balance_html,
        "row_html": row_html,
        "created_at": tx.created_at.strftime("%b %d, %Y %H:%M"),
    })
