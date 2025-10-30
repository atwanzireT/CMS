# views.py
from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.contrib import messages
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Q, Count, Max, F, Sum, Value, DecimalField, IntegerField
)
from django.db.models.functions import Coalesce
from django.http import (
    HttpResponse, HttpResponseBadRequest, JsonResponse
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import module_required
from .forms import CustomerForm
from .models import Customer, CustomerAccount, MillingProcess, MillingTransaction


# ======================================================================
# UTILITIES
# ======================================================================

def get_base_context(request, page_title: str = "Default Page Title") -> dict:
    return {"page_title": page_title, "user": request.user}


def _parse_decimal(val: str | None) -> Decimal | None:
    if not val:
        return None
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        return None


def _q2(x) -> Decimal:
    """
    Quantize to 2dp with HALF_UP.
    Accepts Decimal | str | int | float | None.
    """
    if x is None or x == "":
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ======================================================================
# CUSTOMERS
# ======================================================================

@module_required("access_milling")
def customer_list(request):
    """
    List + create/update Customers.

    Features:
      - Create/Update on POST (ensures CustomerAccount exists)
      - Filters: q (search in id/name/phone)
      - Pagination: ?per=20|50|100|200
      - CSV export: ?export=csv (respects current filters)
      - Totals (respect current filters):
          * total_hulled (Completed only)
          * total_balance
      - Per-row annotations:
          * balance (CustomerAccount.balance or 0)
          * hulled_total (sum of hulled_weight for Completed processes)
          * milling_count, last_milling
    """
    # ---------- Create/Update ----------
    if request.method == "POST":
        customer_id = (request.POST.get("customer_id") or "").strip()
        instance = get_object_or_404(Customer, id=customer_id) if customer_id else None
        form = CustomerForm(request.POST, instance=instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    customer = form.save(commit=False)
                    if instance is None:
                        customer.created_by = request.user
                    customer.save()
                    CustomerAccount.objects.get_or_create(customer=customer)
                messages.success(request, "Customer saved successfully!")
                return redirect("milling:customer_list")
            except Exception as e:
                messages.error(request, f"Error saving customer: {e}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = CustomerForm()

    # ---------- Base queryset + annotations ----------
    qs = (
        Customer.objects
        .select_related("created_by")
        .annotate(
            balance=Coalesce(F("account__balance"), Decimal("0.00")),
            milling_count=Count("milling_processes", distinct=True),
            last_milling=Max("milling_processes__created_at"),
            hulled_total=Coalesce(
                Sum(
                    "milling_processes__hulled_weight",
                    filter=Q(milling_processes__status=MillingProcess.COMPLETED),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
        )
        .order_by("-created_at")
    )

    # ---------- Filters ----------
    f = request.GET
    q = (f.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(id__icontains=q) |
            Q(name__icontains=q) |
            Q(phone__icontains=q)
        )

    # ---------- Aggregates (respect current filters) ----------
    aggregates = qs.aggregate(
        total_balance=Coalesce(
            Sum("account__balance"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        total_hulled=Coalesce(
            Sum(
                "milling_processes__hulled_weight",
                filter=Q(milling_processes__status=MillingProcess.COMPLETED),
            ),
            Value(0),
            output_field=IntegerField(),
        ),
    )

    # ---------- CSV Export ----------
    if f.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="customers.csv"'
        writer = csv.writer(resp)
        writer.writerow([
            "Customer ID", "Name", "Phone",
            "Hulled (kg)", "Balance (UGX)",
            "Milling Count", "Last Milling",
            "Created At", "Created By",
        ])
        for c in qs:
            writer.writerow([
                c.id,
                c.name,
                c.phone or "",
                int(c.hulled_total or 0),
                f"{(c.balance or Decimal('0')):.2f}",
                c.milling_count or 0,
                (c.last_milling.strftime("%Y-%m-%d %H:%M") if c.last_milling else ""),
                c.created_at.strftime("%Y-%m-%d %H:%M"),
                (
                    c.created_by.get_full_name() if getattr(c.created_by, "get_full_name", None)
                    else (c.created_by.username if c.created_by else "")
                ),
            ])
        return resp

    # ---------- Pagination ----------
    allowed_per = [20, 50, 100, 200]
    try:
        per = int(f.get("per") or 20)
        if per not in allowed_per:
            per = 20
    except ValueError:
        per = 20

    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(f.get("page"))

    context = {
        "form": form,
        "page_obj": page_obj,
        "filters": {"q": q, "per": str(per)},
        "per_options": allowed_per,
        "totals": {
            "customers": paginator.count,
            "with_milling": qs.filter(milling_count__gt=0).count(),
            "total_balance": aggregates["total_balance"] or Decimal("0.00"),
            "total_hulled": aggregates["total_hulled"] or 0,
        },
    }
    return render(request, "customer_list.html", context)


@module_required("access_milling")
def customer_detail(request, pk):
    """
    Customer drill-down with aggregates, recent milling & transactions.

    Query params (optional):
      - per_m: milling rows per page (default 10)
      - per_t: transaction rows per page (default 10)
      - mpage: milling page number
      - tpage: transaction page number
      - export=csv&scope=milling|transactions  -> CSV export for chosen scope
    """
    # -------- Base objects --------
    customer = get_object_or_404(Customer.objects.select_related("created_by"), pk=pk)
    account, _ = CustomerAccount.objects.get_or_create(customer=customer)

    # -------- Querysets --------
    milling_qs = (
        MillingProcess.objects
        .filter(customer=customer)
        .select_related("customer", "created_by")
        .order_by("-created_at")
    )

    tx_qs = (
        MillingTransaction.objects
        .filter(account=account)
        .select_related("created_by", "milling_process")
        .order_by("-created_at")
    )

    # -------- Aggregates (per-customer) --------
    # Total hulled for COMPLETED processes only
    hulled_agg = MillingProcess.objects.filter(
        customer=customer,
        status=MillingProcess.COMPLETED
    ).aggregate(
        total_hulled=Coalesce(Sum("hulled_weight"), Value(0), output_field=IntegerField())
    )

    # Credits / Debits totals
    tx_agg = tx_qs.aggregate(
        total_credits=Coalesce(
            Sum("amount", filter=Q(transaction_type=MillingTransaction.CREDIT)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        total_debits=Coalesce(
            Sum("amount", filter=Q(transaction_type=MillingTransaction.DEBIT)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )

    # -------- CSV export (optional) --------
    if request.GET.get("export") == "csv":
        scope = (request.GET.get("scope") or "").lower()
        resp = HttpResponse(content_type="text/csv")
        if scope == "milling":
            resp["Content-Disposition"] = f'attachment; filename="{customer.id}_milling.csv"'
            w = csv.writer(resp)
            w.writerow(["Date", "Initial (kg)", "Hulled (kg)", "Rate (UGX)", "Cost (UGX)", "Status", "Notes"])
            for m in milling_qs:
                w.writerow([
                    m.created_at.strftime("%Y-%m-%d %H:%M"),
                    m.initial_weight,
                    m.hulled_weight,
                    f"{(m.milling_rate or 0):.2f}",
                    f"{(m.milling_cost or 0):.2f}",
                    dict(MillingProcess.STATUS_CHOICES).get(m.status, ""),
                    (m.notes or "").replace("\n", " ").strip(),
                ])
            return resp

        if scope == "transactions":
            resp["Content-Disposition"] = f'attachment; filename="{customer.id}_transactions.csv"'
            w = csv.writer(resp)
            w.writerow(["Date", "Type", "Amount (UGX)", "Reference", "Milling ID"])
            for t in tx_qs:
                w.writerow([
                    t.created_at.strftime("%Y-%m-%d %H:%M"),
                    t.get_transaction_type_display(),
                    f"{t.amount:.2f}",
                    t.reference or "",
                    t.milling_process_id or "",
                ])
            return resp

    # -------- Pagination (independent per section) --------
    try:
        per_m = int(request.GET.get("per_m") or 10)
    except ValueError:
        per_m = 10
    try:
        per_t = int(request.GET.get("per_t") or 10)
    except ValueError:
        per_t = 10

    m_paginator = Paginator(milling_qs, per_m)
    t_paginator = Paginator(tx_qs, per_t)

    m_page = m_paginator.get_page(request.GET.get("mpage"))
    t_page = t_paginator.get_page(request.GET.get("tpage"))

    # -------- Context --------
    context = {
        "page_title": f"Customer Details - {customer.name}",
        "user": request.user,
        "customer": customer,
        "account": account,
        "stats": {
            "total_hulled": hulled_agg["total_hulled"] or 0,
            "total_credits": tx_agg["total_credits"] or Decimal("0.00"),
            "total_debits": tx_agg["total_debits"] or Decimal("0.00"),
            "current_balance": account.balance or Decimal("0.00"),
        },
        "milling_page": m_page,
        "transactions_page": t_page,
        "per_opts": [10, 20, 50, 100],
        "per_m": per_m,
        "per_t": per_t,
    }
    return render(request, "customer_detail.html", context)


@module_required("access_milling")
def customer_search(request):
    """
    Lightweight AJAX select2-style search:
      GET ?q=term
      -> {results: [{id, text, name, phone}]}
    """
    search_term = (request.GET.get("q") or "").strip()
    if not search_term:
        return JsonResponse({"error": "No search term provided"}, status=400)

    customers = (
        Customer.objects
        .filter(Q(name__icontains=search_term) | Q(phone__icontains=search_term))
        .order_by("name")[:10]
    )

    results = [{
        "id": c.id,
        "text": f"{c.name} ({c.phone})" if c.phone else c.name,
        "name": c.name,
        "phone": c.phone,
    } for c in customers]

    return JsonResponse({"results": results})


# ======================================================================
# MILLING
# ======================================================================

@module_required("access_milling")
def milling_detail(request, pk):
    """
    View a single milling process + its transactions.
    """
    milling = get_object_or_404(MillingProcess.objects.select_related("customer"), pk=pk)
    context = get_base_context(request, "Milling Process Details")
    context.update({
        "milling": milling,
        "transactions": milling.transactions.all().order_by("-created_at"),
    })
    return render(request, "milling_detail.html", context)


@module_required("access_milling")
@require_POST
def create_milling_payment(request, pk: int):
    """
    Record a CREDIT transaction (customer pays us) for a milling process.

    POST body:
      - amount or amount_ugx
      - reference (optional)
      - notes (optional)  [kept for future use]

    Returns:
      JSON { ok: bool, balance_html: "UGX 12,345" }
    """
    process = get_object_or_404(
        MillingProcess.objects.select_related("customer"),
        pk=pk
    )

    raw_amount = request.POST.get("amount") or request.POST.get("amount_ugx")
    reference = (request.POST.get("reference") or "").strip() or None
    # notes currently unused downstream, but parsed for future-proofing
    _notes = (request.POST.get("notes") or "").strip()

    try:
        amount = _q2(raw_amount)
    except Exception:
        return HttpResponseBadRequest("Invalid amount.")

    if amount <= 0:
        return HttpResponseBadRequest("Amount must be greater than zero.")

    account, _ = CustomerAccount.objects.get_or_create(customer=process.customer)

    MillingTransaction.objects.create(
        account=account,
        amount=amount,
        transaction_type=MillingTransaction.CREDIT,
        reference=reference,
        created_by=request.user,
        milling_process=process,
    )

    # Reload a fresh balance (assumes balance maintenance elsewhere/signals)
    fresh_balance = CustomerAccount.objects.get(pk=account.pk).balance

    return JsonResponse({
        "ok": True,
        "balance_html": f"UGX {intcomma(fresh_balance)}",
    })
