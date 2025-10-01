from __future__ import annotations

import csv
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Q, F, Sum, Count, DecimalField, ExpressionWrapper
)
from django.http import (
    HttpResponse, JsonResponse, HttpResponseBadRequest
)
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.permissions import module_required
from .models import Customer, MillingProcess, MillingTransaction, CustomerAccount
from .forms import CustomerForm, MillingProcessForm
from assessment.models import Assessment
from assessment.forms import AssessmentForm



# ========== UTILITY FUNCTIONS ==========
def get_base_context(request, page_title='Default Page Title'):
    return {
        'page_title': page_title,
        'user': request.user
    }


# ========== CUSTOMER VIEWS ==========
@module_required("access_milling")
def customer_list(request):
    customers = Customer.objects.all().order_by('-created_at')
    
    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        
        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
                form = CustomerForm(request.POST, instance=customer)
            except Customer.DoesNotExist:
                messages.error(request, 'Customer not found!')
                return redirect('customer_list')
        else:  # This is a create
            form = CustomerForm(request.POST)
        
        if form.is_valid():
            customer = form.save(commit=False)
            if not customer_id:
                customer.created_by = request.user
            customer.save()
            messages.success(request, 'Customer saved successfully!')
            return redirect('customer_list')
    else:
        form = CustomerForm()

    context = {
        'form': form,
        'customers': customers,
    }
    return render(request, 'customer_list.html', context)


@module_required("access_milling")
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    context = get_base_context(request, f'Customer Details - {customer.name}')
    
    context.update({
        'customer': customer,
        'milling_processes': customer.milling_processes.all().order_by('-created_at')[:5],
        'transactions': MillingTransaction.objects.filter(
            account__customer=customer
        ).order_by('-created_at')[:5]
    })
    return render(request, 'customer_detail.html', context)

# ========== MILLING PROCESS VIEWS ==========
def _parse_decimal(val: str | None) -> Decimal | None:
    if not val:
        return None
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        return None


@login_required
@module_required("access_milling")
def milling_list(request):
    """
    - GET: Show a full, filterable list of milling processes with totals and CSV export.
      Filters (all optional):
        q                -> search over customer id/name/phone and reference-like notes
        status           -> P/C/X
        customer         -> customer id (pk of Customer)
        date_from        -> YYYY-MM-DD (created_at >=)
        date_to          -> YYYY-MM-DD (created_at <=)
        min_initial/max_initial  -> kg
        min_hulled/max_hulled    -> kg
        min_rate/max_rate        -> milling_rate (money per kg)
        export=csv       -> export current filtered set to CSV

    - POST: Create/update a milling process (uses hidden 'milling_id' for updates).
    """

    # ----------------- Create/Update on POST -----------------
    if request.method == "POST":
        milling_id = request.POST.get("milling_id")
        instance = get_object_or_404(MillingProcess, id=milling_id) if milling_id else None
        form = MillingProcessForm(request.POST, instance=instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    milling = form.save(commit=False)
                    if not instance:
                        milling.created_by = request.user
                    milling.save()
                messages.success(request, "Milling process saved successfully!")
                return redirect("milling:milling_list")
            except Exception as e:
                messages.error(request, f"Error saving process: {e}")
        else:
            # surface form errors to messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = MillingProcessForm()

    # ----------------- Base Queryset & Annotation -----------------
    milling_cost_expr = ExpressionWrapper(
        F("hulled_weight") * F("milling_rate"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    qs = (
        MillingProcess.objects
        .select_related("customer", "created_by")
        .annotate(calc_cost=milling_cost_expr)
        .order_by("-created_at")
    )

    # ----------------- Filters -----------------
    f = request.GET  # shorthand

    q = (f.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(customer__id__icontains=q) |
            Q(customer__name__icontains=q) |
            Q(customer__phone__icontains=q) |
            Q(notes__icontains=q)
        )

    status = (f.get("status") or "").strip()
    if status in {MillingProcess.PENDING, MillingProcess.COMPLETED, MillingProcess.CANCELLED}:
        qs = qs.filter(status=status)

    customer_id = (f.get("customer") or "").strip()
    if customer_id:
        qs = qs.filter(customer__id=customer_id)

    date_from = parse_date(f.get("date_from") or "")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = parse_date(f.get("date_to") or "")
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # numeric filters
    min_initial = _parse_decimal(f.get("min_initial"))
    if min_initial is not None:
        qs = qs.filter(initial_weight__gte=min_initial)

    max_initial = _parse_decimal(f.get("max_initial"))
    if max_initial is not None:
        qs = qs.filter(initial_weight__lte=max_initial)

    min_hulled = _parse_decimal(f.get("min_hulled"))
    if min_hulled is not None:
        qs = qs.filter(hulled_weight__gte=min_hulled)

    max_hulled = _parse_decimal(f.get("max_hulled"))
    if max_hulled is not None:
        qs = qs.filter(hulled_weight__lte=max_hulled)

    min_rate = _parse_decimal(f.get("min_rate"))
    if min_rate is not None:
        qs = qs.filter(milling_rate__gte=min_rate)

    max_rate = _parse_decimal(f.get("max_rate"))
    if max_rate is not None:
        qs = qs.filter(milling_rate__lte=max_rate)

    # ----------------- CSV Export -----------------
    if f.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="millings.csv"'
        writer = csv.writer(resp)
        writer.writerow([
            "Customer ID", "Customer Name", "Phone",
            "Initial (kg)", "Hulled (kg)",
            "Rate", "Milling Cost",
            "Status", "Created At", "Completed At",
            "Created By", "Notes",
        ])
        for m in qs:
            writer.writerow([
                m.customer.id,
                m.customer.name,
                m.customer.phone,
                m.initial_weight,
                m.hulled_weight,
                f"{m.milling_rate:.2f}" if m.milling_rate is not None else "",
                f"{(m.calc_cost or Decimal('0')):.2f}",
                m.get_status_display(),
                m.created_at.strftime("%Y-%m-%d %H:%M"),
                m.completed_at.strftime("%Y-%m-%d %H:%M") if m.completed_at else "",
                (m.created_by.get_full_name() if getattr(m.created_by, "get_full_name", None) else (m.created_by.username if m.created_by else "")),
                (m.notes or "").replace("\n", " ").strip(),
            ])
        return resp

    # ----------------- Aggregates & Counts -----------------
    aggregates = qs.aggregate(
        total_initial=Sum("initial_weight"),
        total_hulled=Sum("hulled_weight"),
        total_cost=Sum(milling_cost_expr),
        count_all=Count("id"),
    )

    # counts by status (for chips in UI)
    status_counts = qs.values("status").annotate(c=Count("id"))
    status_map = {row["status"]: row["c"] for row in status_counts}
    count_pending = status_map.get(MillingProcess.PENDING, 0)
    count_completed = status_map.get(MillingProcess.COMPLETED, 0)
    count_cancelled = status_map.get(MillingProcess.CANCELLED, 0)

    # ----------------- Pagination -----------------
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(f.get("page"))

    # For filter dropdown
    customer_options = (
        Customer.objects.order_by("name").values("id", "name", "phone")
    )

    context = {
        "form": form,
        "page_obj": page_obj,

        # Filters echo
        "filters": {
            "q": q,
            "status": status,
            "customer": customer_id,
            "date_from": f.get("date_from") or "",
            "date_to": f.get("date_to") or "",
            "min_initial": f.get("min_initial") or "",
            "max_initial": f.get("max_initial") or "",
            "min_hulled": f.get("min_hulled") or "",
            "max_hulled": f.get("max_hulled") or "",
            "min_rate": f.get("min_rate") or "",
            "max_rate": f.get("max_rate") or "",
        },

        # Choices for select fields in template
        "choices": {
            "statuses": MillingProcess.STATUS_CHOICES,
            "customers": customer_options,
        },

        # Totals
        "totals": {
            "count": aggregates["count_all"] or 0,
            "initial": aggregates["total_initial"] or 0,
            "hulled": aggregates["total_hulled"] or 0,
            "cost": aggregates["total_cost"] or Decimal("0.00"),
        },

        # Per-status counts
        "counts": {
            "pending": count_pending,
            "completed": count_completed,
            "cancelled": count_cancelled,
        },
    }
    return render(request, "milling_list.html", context)


@module_required("access_milling")
def milling_detail(request, pk):
    milling = get_object_or_404(MillingProcess, pk=pk)
    context = get_base_context(request, 'Milling Process Details')
    
    context.update({
        'milling': milling,
        'transactions': milling.transactions.all()
    })
    return render(request, 'milling_detail.html', context)


@module_required("access_milling")
def customer_search(request):
    search_term = request.GET.get('q', '').strip()
    if not search_term:
        return JsonResponse({'error': 'No search term provided'}, status=400)
    
    customers = Customer.objects.filter(
        Q(name__icontains=search_term) | Q(phone__icontains=search_term)
    ).order_by('name')[:10]
    
    results = [{
        'id': customer.id,
        'text': f"{customer.name} ({customer.phone})",
        'name': customer.name,
        'phone': customer.phone
    } for customer in customers]
    
    return JsonResponse({'results': results})


def _q2(x):
    if x is None or x == "":
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@module_required("access_milling")
@require_POST
def create_milling_payment(request, pk: int):
    """
    Record a CREDIT transaction (customer pays us) for a completed milling process.
    Body: amount, reference (optional), notes (optional)
    Returns JSON {ok, balance_html}
    """
    process = get_object_or_404(MillingProcess.objects.select_related("customer"), pk=pk)

    raw_amount = request.POST.get("amount") or request.POST.get("amount_ugx")
    reference = (request.POST.get("reference") or "").strip() or None
    notes = (request.POST.get("notes") or "").strip()

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

    # Fresh balance (signals already applied)
    fresh_balance = CustomerAccount.objects.get(pk=account.pk).balance
    return JsonResponse({
        "ok": True,
        "balance_html": f"UGX {intcomma(fresh_balance)}",
    })
