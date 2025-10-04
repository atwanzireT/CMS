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
from django.db.models.functions import Coalesce
from django.http import (
    HttpResponse, JsonResponse, HttpResponseBadRequest
)
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.permissions import module_required
from .models import Customer, MillingProcess, MillingTransaction, CustomerAccount
from .forms import CustomerForm, MillingProcessForm




@login_required
@module_required("access_milling")
def milling_list(request):
    """
    Milling processes list with filters, per-row balances, totals and CSV export.
    Also supports creating/updating a MillingProcess and (optionally) recording
    linked CustomerAccount transactions in the same atomic operation.

    POST extras:
      - auto_debit_cost: '1'/'true'/'on' (optional) -> DEBIT hulled_weight * milling_rate
      - paid_amount: numeric UGX (optional, defaults to 0) -> CREDIT of that amount
    """
    # ----------------- Create/Update on POST -----------------
    if request.method == "POST":
        milling_id = request.POST.get("milling_id")
        instance = get_object_or_404(MillingProcess, id=milling_id) if milling_id else None
        form = MillingProcessForm(request.POST, instance=instance)

        # Parse simplified extra fields
        auto_debit_cost = (request.POST.get("auto_debit_cost") or "").strip().lower() in {"1", "true", "on", "yes"}
        raw_paid_amount = (request.POST.get("paid_amount") or "0").strip()

        # Local precise 2dp rounder
        def _q2(x):
            if x in (None, ""):
                return None
            if not isinstance(x, Decimal):
                try:
                    x = Decimal(str(x))
                except (InvalidOperation, TypeError, ValueError):
                    return None
            return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        paid_amount = _q2(raw_paid_amount)
        if paid_amount is None:
            messages.error(request, "Invalid paid amount.")
            return redirect("milling:milling_list")
        if paid_amount < 0:
            messages.error(request, "Paid amount cannot be negative.")
            return redirect("milling:milling_list")

        if form.is_valid():
            try:
                with transaction.atomic():
                    milling = form.save(commit=False)
                    if not instance:
                        milling.created_by = request.user
                    milling.save()

                    # Ensure account exists
                    account, _ = CustomerAccount.objects.get_or_create(customer=milling.customer)

                    did_debit = False
                    did_credit = False

                    # 1) Auto-debit milling cost (hulled_weight * rate)
                    if auto_debit_cost:
                        cost = _q2(
                            (Decimal(str(milling.hulled_weight or 0))) *
                            (Decimal(str(milling.milling_rate or 0)))
                        )
                        if cost and cost > 0:
                            MillingTransaction.objects.create(
                                account=account,
                                amount=cost,
                                transaction_type=MillingTransaction.DEBIT,
                                reference=f"MILL-{milling.pk}",
                                created_by=request.user,
                                milling_process=milling,
                            )
                            # DEBIT increases what the customer owes
                            account.update_balance(cost)
                            did_debit = True

                    # 2) Paid amount (if provided) -> CREDIT
                    if paid_amount > 0:
                        MillingTransaction.objects.create(
                            account=account,
                            amount=paid_amount,
                            transaction_type=MillingTransaction.CREDIT,
                            reference=None,
                            created_by=request.user,
                            milling_process=milling,
                        )
                        # CREDIT reduces what the customer owes
                        account.update_balance(Decimal("0.00") - paid_amount)
                        did_credit = True

                # Success messages based on what happened
                if did_debit and did_credit:
                    messages.success(request, "Milling saved, cost debited, and payment recorded.")
                elif did_debit:
                    messages.success(request, "Milling saved and milling cost debited to the account.")
                elif did_credit:
                    messages.success(request, "Milling saved and payment recorded.")
                else:
                    messages.success(request, "Milling process saved successfully.")
                return redirect("milling:milling_list")

            except Exception as e:
                messages.error(request, f"Error saving process/transactions: {e}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = MillingProcessForm()

    # ----------------- Base annotations -----------------
    milling_cost_expr = ExpressionWrapper(
        F("hulled_weight") * F("milling_rate"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    # Sum of credits applied to this specific milling process
    credits_sum_expr = Coalesce(
        Sum(
            "transactions__amount",
            filter=Q(transactions__transaction_type=MillingTransaction.CREDIT),
        ),
        Decimal("0.00"),
    )

    # milling_due = cost - credits
    milling_due_expr = ExpressionWrapper(
        Coalesce(milling_cost_expr, Decimal("0.00")) - credits_sum_expr,
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    # ----------------- Queryset -----------------
    qs = (
        MillingProcess.objects
        .select_related("customer", "created_by", "customer__account")
        .annotate(
            calc_cost=milling_cost_expr,
            milling_due=milling_due_expr,
            account_balance=Coalesce(F("customer__account__balance"), Decimal("0.00")),
        )
        .order_by("-created_at")
    )

    # ----------------- Filters -----------------
    f = request.GET

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

    # Helper to safely parse decimals from filter input
    def _parse_decimal(val):
        try:
            if val is None or val == "":
                return None
            return Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return None

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
            "Milling Due", "Customer Balance",
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
                f"{(m.milling_due or Decimal('0')):.2f}",
                f"{(m.account_balance or Decimal('0')):.2f}",
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
        total_cost=Sum("calc_cost"),
        total_due=Sum("milling_due"),
        count_all=Count("id"),
    )

    status_counts = qs.values("status").annotate(c=Count("id"))
    status_map = {row["status"]: row["c"] for row in status_counts}
    count_pending = status_map.get(MillingProcess.PENDING, 0)
    count_completed = status_map.get(MillingProcess.COMPLETED, 0)
    count_cancelled = status_map.get(MillingProcess.CANCELLED, 0)

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

    # For filter dropdown
    customer_options = Customer.objects.order_by("name").values("id", "name", "phone")

    context = {
        "form": form,
        "page_obj": page_obj,
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
            "per": str(per),
        },
        "choices": {
            "statuses": MillingProcess.STATUS_CHOICES,
            "customers": customer_options,
            "per_options": allowed_per,
        },
        "totals": {
            "count": aggregates["count_all"] or 0,
            "initial": aggregates["total_initial"] or 0,
            "hulled": aggregates["total_hulled"] or 0,
            "cost": aggregates["total_cost"] or Decimal("0.00"),
            "due": aggregates["total_due"] or Decimal("0.00"),
        },
        "counts": {
            "pending": count_pending,
            "completed": count_completed,
            "cancelled": count_cancelled,
        },
    }
    return render(request, "milling_list.html", context)

