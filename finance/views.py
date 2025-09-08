from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST
from store.models import CoffeePurchase, CoffeeSale, SupplierAccount, SupplierTransaction
from assessment.models import Assessment
from decimal import Decimal, ROUND_HALF_UP


def _month_bounds(dt):
    """Return (start_date, end_date_exclusive) for the given date's calendar month."""
    first = dt.replace(day=1)
    if first.month == 12:
        next_month = first.replace(year=first.year + 1, month=1, day=1)
    else:
        next_month = first.replace(month=first.month + 1, day=1)
    return first, next_month


def _purchase_payable_amount(purchase: CoffeePurchase) -> Decimal:
    """
    Compute the supplier payment for a single purchase:
    analysis_price_ugx (per-kg) × purchase.quantity.
    Falls back to 0 if no assessment or missing inputs.
    """
    try:
        a = purchase.assessment  # OneToOne
    except Assessment.DoesNotExist:
        return Decimal("0")

    if not a or a.analysis_price_ugx is None or purchase.quantity is None:
        return Decimal("0")

    # Ensure Decimal math
    per_kg = Decimal(a.analysis_price_ugx)
    qty = Decimal(purchase.quantity)
    total = per_kg * qty
    # Optional quantize if you prefer whole shillings:
    return total


@login_required
def finance_dashboard(request):
    """
    Finance overview:
    - Monthly revenue (sales): sum(quantity * unit_price) within current month
    - Pending supplier payments (only assessed purchases)
    - Cash flow this month: cash_in (sales) vs cash_out (paid purchases)
    - Available cash: cash_in - cash_out (this month)
    - Lists: pending vs completed payments (supplier side)
    """
    today = timezone.localdate()
    month_start, month_next = _month_bounds(today)

    # ---- Revenue (Sales) — current month ----
    # Revenue recognized by sale_date (no sales payment status in model yet)
    sales_this_month = (
        CoffeeSale.objects
        .filter(sale_date__gte=month_start, sale_date__lt=month_next)
        .annotate(line_total=ExpressionWrapper(
            F("quantity") * F("unit_price"),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        ))
    )
    monthly_revenue = sales_this_month.aggregate(total=Sum("line_total"))["total"] or Decimal("0")

    # Cash inflow this month (assumption: all sales = cash in)
    cash_inflow = monthly_revenue

    # ---- Supplier Payments (Purchases) ----
    # Only assessed purchases are payable
    assessed_purchases_qs = (
        CoffeePurchase.objects
        .select_related("supplier", "assessment")
        .filter(assessment__isnull=False)
    )

    # Pending = Pending or Partial
    pending_purchases_qs = assessed_purchases_qs.filter(
        Q(payment_status=CoffeePurchase.PAYMENT_PENDING) |
        Q(payment_status=CoffeePurchase.PAYMENT_PARTIAL)
    )

    # Completed = Paid
    completed_purchases_qs = assessed_purchases_qs.filter(
        payment_status=CoffeePurchase.PAYMENT_PAID
    )

    # ---- Compute totals in Python (analysis_price_ugx is a property) ----
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
            "quantity": p.quantity,
            "status": p.get_payment_status_display(),
        })

    # Completed total (all-time) and cash outflow for *this month*
    completed_payments_total = Decimal("0")
    cash_outflow = Decimal("0")

    completed_payments = []
    for p in completed_purchases_qs:
        amount = _purchase_payable_amount(p)
        completed_payments_total += amount
        if month_start <= p.purchase_date < month_next:
            cash_outflow += amount  # proxy: paid this month ~ purchase_date in this month

        completed_payments.append({
            "id": p.id,
            "supplier": p.supplier,
            "purchase": p,
            "amount": amount,
            "purchase_date": p.purchase_date,
            "coffee_type": p.get_coffee_type_display(),
            "coffee_category": p.get_coffee_category_display(),
            "quantity": p.quantity,
            "status": p.get_payment_status_display(),
        })

    # ---- Available cash (this month) ----
    available_cash = cash_inflow - cash_outflow
    net_cash_flow = available_cash  # alias, in case you want both

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
            "pending_payments": pending_payments,     # list of dicts (supplier, purchase, amount, etc.)
            "completed_payments": completed_payments, # list of dicts
        },
    }
    return render(request, "finance_dashboard.html", context)


def _q2(x):
    if x is None:
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@login_required
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

    # Ensure account exists
    account, _ = SupplierAccount.objects.get_or_create(supplier=purchase.supplier)

    # Create CREDIT transaction
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

    balance_html = f"UGX {intcomma(SupplierAccount.objects.get(pk=account.pk).balance)}"

    return JsonResponse({
        "ok": True,
        "balance_html": balance_html,
        "row_html": row_html,
        "created_at": tx.created_at.strftime("%b %d, %Y %H:%M"),
    })
