from decimal import Decimal
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import DetailView
from .forms import GeneralReportFilterForm, DailyStoreReportForm
from .models import DailyStoreReport
from accounts.permissions import module_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

@module_required("access_reports")
def general_reports(request):
    """
    List + filter + summarize DailyStoreReport (General Reports).
    Supports: date range, coffee type, text search, pagination.
    Shows totals and a weighted average buying price.
    """
    qs = DailyStoreReport.objects.select_related("input_by").order_by("-date", "-created_at")

    # Filters
    fform = GeneralReportFilterForm(request.GET or None)
    if fform.is_valid():
        date_from = fform.cleaned_data.get("date_from")
        date_to   = fform.cleaned_data.get("date_to")
        coffee_type = fform.cleaned_data.get("coffee_type")
        q = fform.cleaned_data.get("q")

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if coffee_type:
            qs = qs.filter(coffee_type=coffee_type)
        if q:
            qs = qs.filter(sold_to__icontains=q) | qs.filter(comments__icontains=q)

    # Aggregates
    totals = qs.aggregate(
        total_kg_bought=Sum("kilograms_bought"),
        total_kg_sold=Sum("kilograms_sold"),
        total_kg_left=Sum("kilograms_left_in_store"),
        total_advances=Sum("advances_given_ugx"),
    )

    # Weighted average buying price (by kg bought)
    weighted_price_expr = ExpressionWrapper(
        F("average_buying_price_ugx_per_kg") * F("kilograms_bought"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    weights = qs.aggregate(
        _sum_weight=Sum("kilograms_bought"),
        _sum_price_weighted=Sum(weighted_price_expr),
    )
    weighted_avg_price = None
    if (weights["_sum_weight"] or Decimal(0)) > 0:
        weighted_avg_price = (weights["_sum_price_weighted"] or Decimal(0)) / weights["_sum_weight"]

    # Pagination
    paginator = Paginator(qs, 25)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    context = {
        "filter_form": fform,
        "page_obj": page_obj,
        "reports": page_obj.object_list,
        "totals": totals,
        "weighted_avg_price": weighted_avg_price,
    }
    return render(request, "general_reports.html", context)


@module_required("access_reports")
def create_report(request):
    """
    Create a DailyStoreReport. Sets input_by to current user.
    """
    if request.method == "POST":
        form = DailyStoreReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.input_by = request.user
            report.save()
            messages.success(request, "Report saved.")
            return redirect(reverse("general_reports"))
    else:
        form = DailyStoreReportForm()

    return render(request, "report_form.html", {"form": form})



class ReportDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = DailyStoreReport
    template_name = "report_detail.html"
    context_object_name = "report"
    pk_url_kwarg = "pk"

    # permission lives on the "accounts" app (CustomUser.Meta.permissions)
    permission_required = "accounts.access_reports"
    raise_exception = True  # 403 instead of redirect if authenticated but unauthorized

    def get_queryset(self):
        return DailyStoreReport.objects.select_related("input_by")