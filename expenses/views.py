from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from typing import Optional
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.permissions import module_required
from .forms import ExpenseRequestForm
from .models import ExpenseRequest

User = get_user_model()


def _parse_decimal(val: Optional[str]) -> Optional[Decimal]:
    if not val:
        return None
    try:
        return Decimal(val)
    except (InvalidOperation, TypeError):
        return None


@login_required
@module_required("access_expenses")  # tighten if only Finance/Admin should access
def expenses_all(request):
    """
    Global expense listing (Finance/Admin).
    GET filters:
      q, category, priority,
      finance_status, admin_status,
      payment_status, payment_method,
      requester (user id),
      date_from (YYYY-MM-DD), date_to (YYYY-MM-DD),
      min_amount, max_amount,
      requires_admin (true/false),
      export=csv (download filtered set)
    """
    qs = (
        ExpenseRequest.objects
        .select_related("requested_by", "finance_reviewer", "admin_reviewer")
        .order_by("-created_at")
    )

    # ---------- Filters ----------
    f = request.GET  # shorthand

    q = (f.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(expense_type__icontains=q.replace(" ", "_"))
            | Q(business_reason__icontains=q)
            | Q(requested_by__username__icontains=q)
            | Q(requested_by__first_name__icontains=q)
            | Q(requested_by__last_name__icontains=q)
        )

    category = f.get("category") or ""
    if category:
        qs = qs.filter(expense_type=category)

    priority = f.get("priority") or ""
    if priority:
        qs = qs.filter(priority=priority)

    finance_status = f.get("finance_status") or ""
    if finance_status:
        qs = qs.filter(finance_status=finance_status)

    admin_status = f.get("admin_status") or ""
    if admin_status:
        qs = qs.filter(admin_status=admin_status)

    payment_status = f.get("payment_status") or ""
    if payment_status:
        qs = qs.filter(payment_status=payment_status)

    payment_method = f.get("payment_method") or ""
    if payment_method:
        qs = qs.filter(payment_method=payment_method)

    requester = f.get("requester") or ""
    if requester:
        qs = qs.filter(requested_by_id=requester)

    requires_admin = f.get("requires_admin")
    if requires_admin in {"true", "false"}:
        qs = qs.filter(requires_admin_approval=(requires_admin == "true"))

    date_from = parse_date(f.get("date_from") or "")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = parse_date(f.get("date_to") or "")
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    min_amount = _parse_decimal(f.get("min_amount"))
    if min_amount is not None:
        qs = qs.filter(amount__gte=min_amount)

    max_amount = _parse_decimal(f.get("max_amount"))
    if max_amount is not None:
        qs = qs.filter(amount__lte=max_amount)

    # ---------- CSV export ----------
    if f.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="expenses.csv"'
        writer = csv.writer(resp)
        writer.writerow([
            "Reference", "Type", "Amount(UGX)", "Priority",
            "Finance Status", "Admin Status",
            "Payment Status", "Payment Method",
            "Requester", "Created At", "Business Reason"
        ])
        for e in qs:
            requester_name = (
                getattr(e.requested_by, "get_full_name", lambda: "")() or e.requested_by.username
            )
            writer.writerow([
                e.reference,
                e.get_expense_type_display(),
                f"{e.amount:.0f}",
                e.get_priority_display(),
                e.get_finance_status_display(),
                e.get_admin_status_display(),
                e.get_payment_status_display(),
                e.get_payment_method_display(),
                requester_name,
                e.created_at.strftime("%Y-%m-%d %H:%M"),
                (e.business_reason or "").replace("\n", " ").strip(),
            ])
        return resp

    # ---------- Pagination ----------
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(f.get("page"))

    requester_options = (
        User.objects.filter(expense_requests__isnull=False)
        .distinct()
        .order_by("first_name", "last_name", "username")
    )

    context = {
        "page_obj": page_obj,
        "total": qs.count(),
        "requester_options": requester_options,
        "filters": {
            "q": q,
            "category": category,
            "priority": priority,
            "finance_status": finance_status,
            "admin_status": admin_status,
            "payment_status": payment_status,
            "payment_method": payment_method,
            "requester": requester,
            "date_from": f.get("date_from") or "",
            "date_to": f.get("date_to") or "",
            "min_amount": f.get("min_amount") or "",
            "max_amount": f.get("max_amount") or "",
            "requires_admin": requires_admin or "",
        },
        "choices": {
            "categories": ExpenseRequest.ExpenseCategory.choices,
            "priorities": ExpenseRequest.Priority.choices,
            "approval": ExpenseRequest.ApprovalStatus.choices,
            "payment_statuses": ExpenseRequest.PaymentStatus.choices,
            "payment_methods": ExpenseRequest.PaymentMethod.choices,
        },
    }
    return render(request, "expenses_all.html", context)


@login_required
@module_required("access_expenses")
def expense_list(request):
    """
    - GET  : list current user's expense requests (with search + pagination)
    - POST : create a new expense request for current user
    """
    if request.method == "POST":
        form = ExpenseRequestForm(request.POST, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.requested_by = request.user
            expense.save()
            messages.success(request, f"Expense request {expense.reference} submitted.")
            return redirect("expense_list")
        messages.error(request, "Please correct the errors and try again.")
    else:
        form = ExpenseRequestForm(user=request.user)

    qs = (
        ExpenseRequest.objects
        .select_related("requested_by", "finance_reviewer", "admin_reviewer")
        .for_user(request.user)
        .order_by("-created_at")
    )

    # Simple search on reference, category code, and business_reason
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(expense_type__icontains=search.replace(" ", "_")) |
            Q(business_reason__icontains=search)
        )

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "form": form,
        "page_obj": page_obj,
        "total": qs.count(),
        "approved": qs.fully_approved().count(),
        "pending": qs.pending().count(),
        "today": timezone.now().date(),
        "search": search,
    }
    return render(request, "expense_list.html", context)


@login_required
@module_required("access_expenses")
def expense_detail(request, pk: int):
    expense = get_object_or_404(
        ExpenseRequest.objects.select_related("requested_by", "finance_reviewer", "admin_reviewer"),
        pk=pk
    )
    # Optional: ensure only owner or privileged users can view
    if expense.requested_by != request.user and not (
        request.user.is_superuser
        or request.user.has_perm("accounts.access_finance")
        or request.user.has_perm("accounts.access_expenses")
    ):
        messages.error(request, "You do not have permission to view this expense.")
        return redirect("expense_list")

    return render(request, "expense_detail.html", {"expense": expense})


# ---- Reviewer inboxes --------------------------------------------------------

@login_required
@module_required("access_finance")
def finance_inbox(request):
    qs = (
        ExpenseRequest.objects
        .select_related("requested_by")
        .finance_inbox()
        .order_by("-created_at")
    )
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "finance_inbox.html", {"page_obj": page_obj})


@login_required
@module_required("access_expenses")  # treat as your “admin” permission
def admin_inbox(request):
    qs = (
        ExpenseRequest.objects
        .select_related("requested_by")
        .admin_inbox()
        .order_by("-created_at")
    )
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "admin_inbox.html", {"page_obj": page_obj})


# ---- Actions: approvals & payments ------------------------------------------

@login_required
@module_required("access_finance")
@require_POST
def finance_decide(request, pk: int):
    expense = get_object_or_404(ExpenseRequest, pk=pk)
    status = request.POST.get("status")  # "APPROVED" or "REJECTED"
    note = request.POST.get("note", "").strip()

    try:
        expense.mark_finance_decision(request.user, status=status, note=note)
        messages.success(request, f"Finance {status.lower()} recorded for {expense.reference}.")
    except Exception as e:
        messages.error(request, f"Could not record finance decision: {e}")
    return redirect(request.POST.get("next") or "finance_inbox")


@login_required
@module_required("access_expenses")  # treat as your “admin” permission
@require_POST
def admin_decide(request, pk: int):
    expense = get_object_or_404(ExpenseRequest, pk=pk)
    status = request.POST.get("status")  # "APPROVED" or "REJECTED"
    note = request.POST.get("note", "").strip()

    try:
        expense.mark_admin_decision(request.user, status=status, note=note)
        messages.success(request, f"Admin {status.lower()} recorded for {expense.reference}.")
    except Exception as e:
        messages.error(request, f"Could not record admin decision: {e}")
    return redirect(request.POST.get("next") or "admin_inbox")


@login_required
@module_required("access_finance")
@require_POST
def expense_pay(request, pk: int):
    expense = get_object_or_404(ExpenseRequest, pk=pk)
    try:
        amount = Decimal(request.POST.get("amount", "0").strip())
        method = request.POST.get("method") or ExpenseRequest.PaymentMethod.CASH
        receipt_number = request.POST.get("receipt_number", "").strip() or None

        expense.register_payment(amount=amount, method=method, receipt_number=receipt_number)
        messages.success(request, f"Payment of UGX {amount:,.0f} recorded for {expense.reference}.")
    except Exception as e:
        messages.error(request, f"Could not record payment: {e}")
    return redirect(request.POST.get("next") or "expense_detail", pk=expense.pk)

