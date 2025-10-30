# expenses/views.py
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Tuple

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, F, Value, CharField, BooleanField, QuerySet
from django.db.models.functions import Concat, Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import module_required
from .forms import ExpenseRequestForm, SalaryRequestForm, RequisitionForm
from .models import ExpenseRequest, Requisition, SalaryRequest

User = get_user_model()

# =============================================================================
# Small helpers
# =============================================================================

def _parse_filters(request: HttpRequest) -> dict:
    f = request.GET
    try:
        per = int(f.get("per_page") or 20)
    except ValueError:
        per = 20
    if per not in (10, 20, 50, 100):
        per = 20
    return {
        "q": (f.get("q") or "").strip(),
        "page": f.get("page", "1"),
        "per_page": per,
        "order": (f.get("order") or "-created_at").strip(),  # applied after union
    }


def _text_search(qs: QuerySet, q: str, fields: Iterable[str]) -> QuerySet:
    if not q:
        return qs
    cond = Q()
    for f in fields:
        cond |= Q(**{f"{f}__icontains": q})
    return qs.filter(cond)


# =============================================================================
# Aligned base querysets for UNION (export the same keys)
# NOTE:
# - Use `requester_pk` (NOT requester_id) to avoid clashing with model field.
# - Normalize field names: category/title/description/requester_* across all.
# =============================================================================

def _base_exp_queryset(search: str) -> QuerySet:
    qs = ExpenseRequest.objects.select_related("requester")
    qs = _text_search(
        qs,
        search,
        ("reference", "description",
         "requester__username", "requester__first_name", "requester__last_name"),
    )
    return qs.annotate(
        title=Value("", output_field=CharField()),
        requester_pk=F("requester_id"),
        requester_username=F("requester__username"),
        requester_name=Concat(
            Coalesce(F("requester__first_name"), Value("", output_field=CharField())),
            Value(" "),
            Coalesce(F("requester__last_name"), Value("", output_field=CharField())),
            output_field=CharField(),
        ),
        kind=Value("expense", output_field=CharField()),
        url_name=Value("expenses:expense_detail", output_field=CharField()),
    ).values(
        "id", "created_at", "amount", "reference", "category",
        "title", "description", "finance_status", "admin_status", "is_paid",
        "requester_pk", "requester_username", "requester_name", "kind", "url_name",
    )


def _base_req_queryset(search: str) -> QuerySet:
    qs = Requisition.objects.select_related("requester")
    qs = _text_search(
        qs,
        search,
        ("reference", "title", "description",
         "requester__username", "requester__first_name", "requester__last_name"),
    )
    return qs.annotate(
        is_paid=Value(False, output_field=BooleanField()),  # normalize boolean column
        requester_pk=F("requester_id"),
        requester_username=F("requester__username"),
        requester_name=Concat(
            Coalesce(F("requester__first_name"), Value("", output_field=CharField())),
            Value(" "),
            Coalesce(F("requester__last_name"), Value("", output_field=CharField())),
            output_field=CharField(),
        ),
        kind=Value("requisition", output_field=CharField()),
        url_name=Value("expenses:requisition_detail", output_field=CharField()),
    ).values(
        "id", "created_at", "amount", "reference", "category",
        "title", "description", "finance_status", "admin_status", "is_paid",
        "requester_pk", "requester_username", "requester_name", "kind", "url_name",
    )


def _base_sal_queryset(search: str) -> QuerySet:
    qs = SalaryRequest.objects.select_related("employee")
    qs = _text_search(
        qs,
        search,
        ("reference", "reason",
         "employee__username", "employee__first_name", "employee__last_name"),
    )
    return qs.annotate(
        category=F("payment_type"),        # normalize to 'category'
        title=Value("", output_field=CharField()),
        description=F("reason"),           # normalize to 'description'
        requester_pk=F("employee_id"),
        requester_username=F("employee__username"),
        requester_name=Concat(
            Coalesce(F("employee__first_name"), Value("", output_field=CharField())),
            Value(" "),
            Coalesce(F("employee__last_name"), Value("", output_field=CharField())),
            output_field=CharField(),
        ),
        kind=Value("salary", output_field=CharField()),
        url_name=Value("expenses:salary_detail", output_field=CharField()),
    ).values(
        "id", "created_at", "amount", "reference", "category",
        "title", "description", "finance_status", "admin_status", "is_paid",
        "requester_pk", "requester_username", "requester_name", "kind", "url_name",
    )


def _build_union(request: HttpRequest, *, approved_only: bool = False) -> Tuple[QuerySet, dict]:
    """
    Returns (union_qs, filters_dict) built from three aligned value querysets.
    If approved_only=True, each base queryset is restricted to fully approved rows.
    """
    f = _parse_filters(request)

    exp = ExpenseRequest.objects.all()
    req = Requisition.objects.all()
    sal = SalaryRequest.objects.all()

    if approved_only:
        exp = exp.filter(finance_status="APPROVED", admin_status="APPROVED")
        req = req.filter(finance_status="APPROVED", admin_status="APPROVED")
        sal = sal.filter(finance_status="APPROVED", admin_status="APPROVED")

    exp_v = _base_exp_queryset(f["q"]).filter(id__in=exp.values("id"))
    req_v = _base_req_queryset(f["q"]).filter(id__in=req.values("id"))
    sal_v = _base_sal_queryset(f["q"]).filter(id__in=sal.values("id"))

    union_qs = exp_v.union(req_v, sal_v, all=True)

    allowed_order = {
        "created_at", "-created_at",
        "amount", "-amount",
        "requester_name", "-requester_name",
        "kind", "-kind",
        "finance_status", "-finance_status",
        "admin_status", "-admin_status",
    }
    order_by = f["order"] if f["order"] in allowed_order else "-created_at"
    union_qs = union_qs.order_by(order_by)
    return union_qs, f


# =============================================================================
# Unified inbox
# =============================================================================

@login_required
def requests_all(request: HttpRequest) -> HttpResponse:
    union_qs, f = _build_union(request, approved_only=False)
    paginator = Paginator(union_qs, f["per_page"])
    page_obj = paginator.get_page(f["page"])
    return render(request, "expenses/requests_all.html", {
        "page_obj": page_obj,
        "filters": f,
        "total": paginator.count,
    })


@login_required
@module_required("access_expenses")
def requests_approved(request: HttpRequest) -> HttpResponse:
    union_qs, f = _build_union(request, approved_only=True)
    paginator = Paginator(union_qs, f["per_page"])
    page_obj = paginator.get_page(f["page"])
    return render(request, "expenses/requests_all.html", {
        "page_obj": page_obj,
        "filters": f | {"approved_only": True},
        "total": paginator.count,
    })


# =============================================================================
# Unified actions (Finance/Admin decide + mark paid)
# =============================================================================

def _get_kind_model(kind: str):
    k = (kind or "").lower()
    if k == "expense":
        return "expense", ExpenseRequest
    if k == "salary":
        return "salary", SalaryRequest
    if k == "requisition":
        return "requisition", Requisition
    raise ValueError("Unknown kind")


@login_required
@module_required("access_finance")
@require_POST
def request_finance_decide(request: HttpRequest, kind: str, pk: int) -> HttpResponse:
    """Approve/Reject at Finance for any kind."""
    _, Model = _get_kind_model(kind)
    obj = get_object_or_404(Model, pk=pk)
    status = (request.POST.get("status") or "").upper()
    try:
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("Invalid status.")
        if hasattr(obj, "approve_finance") and hasattr(obj, "reject_finance"):
            obj.approve_finance() if status == "APPROVED" else obj.reject_finance()
        else:
            obj.finance_status = status
            obj.save(update_fields=["finance_status"])
        messages.success(request, f"Finance {status.lower()} recorded for {getattr(obj, 'reference', pk)}.")
    except Exception as e:
        messages.error(request, f"Could not record finance decision: {e}")
    return redirect(request.POST.get("next") or "expenses:requests_all")


@login_required
@user_passes_test(lambda u: u.is_superuser)  # only superusers
@require_POST
def request_admin_decide(request: HttpRequest, kind: str, pk: int) -> HttpResponse:
    """Approve/Reject at Admin for any kind."""
    _, Model = _get_kind_model(kind)
    obj = get_object_or_404(Model, pk=pk)
    status = (request.POST.get("status") or "").upper()
    try:
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("Invalid status.")
        if hasattr(obj, "approve_admin") and hasattr(obj, "reject_admin"):
            obj.approve_admin() if status == "APPROVED" else obj.reject_admin()
        else:
            obj.admin_status = status
            obj.save(update_fields=["admin_status"])
        messages.success(request, f"Admin {status.lower()} recorded for {getattr(obj, 'reference', pk)}.")
    except Exception as e:
        messages.error(request, f"Could not record admin decision: {e}")
    return redirect(request.POST.get("next") or "expenses:requests_all")


@login_required
@module_required("access_finance")
@require_POST
def request_mark_paid(request: HttpRequest, kind: str, pk: int) -> HttpResponse:
    """Mark as paid for expense/salary. (For requisitions, marks ordered.)"""
    k, Model = _get_kind_model(kind)
    obj = get_object_or_404(Model, pk=pk)
    try:
        if k == "requisition":
            if hasattr(obj, "mark_ordered"):
                obj.mark_ordered()
                messages.success(request, f"{getattr(obj, 'reference', pk)} marked as ordered.")
            else:
                raise ValueError("Requisitions do not support 'paid' state.")
        else:
            if hasattr(obj, "mark_as_paid"):
                obj.mark_as_paid()
            elif hasattr(obj, "is_paid"):
                obj.is_paid = True
                obj.save(update_fields=["is_paid"])
            messages.success(request, f"{getattr(obj, 'reference', pk)} marked as paid.")
    except Exception as e:
        messages.error(request, f"Could not mark as paid: {e}")
    return redirect(request.POST.get("next") or "expenses:requests_all")


# =============================================================================
# User-facing: create/list & detail
# =============================================================================
# --- Expenses ---

@login_required
@module_required("access_expenses")
def expense_list(request: HttpRequest) -> HttpResponse:
    """Submit and see MY expenses."""
    if request.method == "POST":
        form = ExpenseRequestForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.requester = request.user  # set FK correctly
            obj.save()
            messages.success(request, f"Expense request {obj.reference} submitted.")
            return redirect("expenses:expense_list")
        messages.error(request, "Please correct the errors and try again.")
    else:
        form = ExpenseRequestForm(user=request.user)

    qs = (ExpenseRequest.objects
          .select_related("requester")
          .filter(requester=request.user)
          .order_by("-created_at"))

    search = (request.GET.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(category__icontains=search.replace(" ", "_")) |
            Q(description__icontains=search)
        )

    page_obj = Paginator(qs, 10).get_page(request.GET.get("page"))

    # quick stats
    fully_approved = qs.filter(finance_status="APPROVED", admin_status="APPROVED").count()
    rejected = qs.filter(Q(finance_status="REJECTED") | Q(admin_status="REJECTED")).count()
    pending = qs.count() - fully_approved - rejected

    return render(request, "expenses/expense_list.html", {
        "form": form,
        "page_obj": page_obj,
        "total": qs.count(),
        "approved": fully_approved,
        "pending": pending,
        "today": timezone.now().date(),
        "search": search,
    })


@login_required
@module_required("access_expenses")
def expense_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(ExpenseRequest.objects.select_related("requester"), pk=pk)
    if obj.requester != request.user and not (
        request.user.is_superuser or request.user.has_perm("accounts.access_finance")
    ):
        messages.error(request, "You do not have permission to view this expense.")
        return redirect("expenses:expense_list")
    return render(request, "expenses/expense_detail.html", {"expense": obj})


# --- Salaries ---

@login_required
@module_required("access_expenses")
def salary_list(request: HttpRequest) -> HttpResponse:
    """Submit and see MY salary requests."""
    if request.method == "POST":
        form = SalaryRequestForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.employee = request.user
            obj.save()
            messages.success(request, f"Salary request {obj.reference} submitted.")
            return redirect("expenses:salary_list")
        messages.error(request, "Please correct the errors and try again.")
    else:
        form = SalaryRequestForm(user=request.user)

    qs = (SalaryRequest.objects
          .select_related("employee")
          .filter(employee=request.user)
          .order_by("-month", "-created_at"))

    search = (request.GET.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(payment_type__icontains=search.replace(" ", "_")) |
            Q(reason__icontains=search)
        )

    page_obj = Paginator(qs, 10).get_page(request.GET.get("page"))
    return render(request, "expenses/salary_list.html", {
        "form": form,
        "page_obj": page_obj,
        "total": qs.count(),
    })


@login_required
@module_required("access_expenses")
def salary_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(SalaryRequest.objects.select_related("employee"), pk=pk)
    if obj.employee != request.user and not (
        request.user.is_superuser or request.user.has_perm("accounts.access_finance")
    ):
        messages.error(request, "You do not have permission to view this salary request.")
        return redirect("expenses:salary_list")
    return render(request, "expenses/salary_detail.html", {"salary": obj})


# --- Requisitions ---

@login_required
@module_required("access_expenses")
def requisition_list(request: HttpRequest) -> HttpResponse:
    """Submit and see MY requisitions."""
    if request.method == "POST":
        form = RequisitionForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.requester = request.user  # set FK correctly
            obj.save()
            messages.success(request, f"Requisition {obj.reference} submitted.")
            return redirect("expenses:requisition_list")
        messages.error(request, "Please correct the errors and try again.")
    else:
        form = RequisitionForm(user=request.user)

    qs = (Requisition.objects
          .select_related("requester")
          .filter(requester=request.user)
          .order_by("-created_at"))

    search = (request.GET.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(title__icontains=search) |
            Q(category__icontains=search.replace(" ", "_")) |
            Q(description__icontains=search)
        )

    page_obj = Paginator(qs, 10).get_page(request.GET.get("page"))
    return render(request, "expenses/requisition_list.html", {
        "form": form,
        "page_obj": page_obj,
        "total": qs.count(),
        "search": search,
    })


@login_required
@module_required("access_expenses")
def requisition_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Requisition.objects.select_related("requester"), pk=pk)
    if obj.requester != request.user and not (
        request.user.is_superuser or request.user.has_perm("accounts.access_finance")
    ):
        messages.error(request, "You do not have permission to view this requisition.")
        return redirect("expenses:requisition_list")
    return render(request, "expenses/requisition_detail.html", {"requisition": obj})
