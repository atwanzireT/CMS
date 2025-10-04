from __future__ import annotations

import csv
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.contrib import messages
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db.models import Q
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from accounts.permissions import module_required
from .forms import CustomerForm
from .models import Customer, CustomerAccount, MillingProcess, MillingTransaction




# ========== UTILITY FUNCTIONS ==========
def get_base_context(request, page_title='Default Page Title'):
    return {
        'page_title': page_title,
        'user': request.user
    }


# ========== CUSTOMER VIEWS ==========
from decimal import Decimal
from django.db.models import Q, Count, Max, F
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.http import HttpResponse
import csv

@module_required("access_milling")
def customer_list(request):
    """
    List + create/update Customers.
    Extras:
      - Filter: q (name/phone/id)
      - Pagination: ?per=20|50|100|200
      - CSV export: ?export=csv (respects filters)
    Also ensures each customer has a CustomerAccount.
    """
    # ----------------- Create/Update on POST -----------------
    if request.method == "POST":
        customer_id = (request.POST.get("customer_id") or "").strip()
        instance = None
        if customer_id:
            instance = get_object_or_404(Customer, id=customer_id)

        form = CustomerForm(request.POST, instance=instance)

        if form.is_valid():
            try:
                with transaction.atomic():
                    customer = form.save(commit=False)
                    # set created_by only on first creation
                    if instance is None:
                        customer.created_by = request.user
                    customer.save()

                    # ensure account exists
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

    # ----------------- Base queryset + annotations -----------------
    qs = (
        Customer.objects
        .select_related("created_by")
        .annotate(
            balance=Coalesce(F("account__balance"), Decimal("0.00")),
            milling_count=Count("milling_processes", distinct=True),
            last_milling=Max("milling_processes__created_at"),
        )
        .order_by("-created_at")
    )

    # ----------------- Filters -----------------
    f = request.GET
    q = (f.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(id__icontains=q) |
            Q(name__icontains=q) |
            Q(phone__icontains=q)
        )

    # ----------------- CSV Export -----------------
    if f.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="customers.csv"'
        writer = csv.writer(resp)
        writer.writerow([
            "Customer ID", "Name", "Phone",
            "Balance", "Milling Count", "Last Milling",
            "Created At", "Created By",
        ])
        for c in qs:
            writer.writerow([
                c.id,
                c.name,
                c.phone,
                f"{(c.balance or Decimal('0')):.2f}",
                c.milling_count or 0,
                (c.last_milling.strftime("%Y-%m-%d %H:%M") if c.last_milling else ""),
                c.created_at.strftime("%Y-%m-%d %H:%M"),
                (c.created_by.get_full_name() if getattr(c.created_by, "get_full_name", None) else (c.created_by.username if c.created_by else "")),
            ])
        return resp

    # ----------------- Pagination -----------------
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
        "filters": {
            "q": q,
            "per": str(per),
        },
        "per_options": allowed_per,
        # Optional: totals for header chips
        "totals": {
            "customers": paginator.count,
            "with_milling": qs.filter(milling_count__gt=0).count(),
        },
    }
    return render(request, "customer_list.html", context)


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

# ---------- helpers ----------
def _parse_decimal(val: str | None) -> Decimal | None:
    if not val:
        return None
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        return None


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
