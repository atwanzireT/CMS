from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from .forms import ExpenseRequestForm
from .models import ExpenseRequest


@login_required
def expense_list(request):
    # Create
    if request.method == "POST":
        form = ExpenseRequestForm(request.POST, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.requested_by = request.user
            expense.save()
            messages.success(request, "Expense request submitted successfully.")
            return redirect("expense_list")
        messages.error(request, "Please correct the errors and try again.")
    else:
        form = ExpenseRequestForm(user=request.user)

    # List for current user
    qs = (
        ExpenseRequest.objects
        .select_related("requested_by")
        .for_user(request.user)
        .order_by("-created_at")
    )

    # Simple search (reference/description/category code)
    search = request.GET.get("q")
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(description__icontains=search) |
            Q(expense_type__icontains=search.replace(" ", "_"))
        )

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Stats
    total = qs.count()
    approved = qs.fully_approved().count()
    pending = qs.pending().count()

    context = {
        "form": form,
        "page_obj": page_obj,
        "total": total,
        "approved": approved,
        "pending": pending,
        "today": timezone.now().date(),
    }
    return render(request, "expense_list.html", context)
