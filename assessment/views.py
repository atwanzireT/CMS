from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from .forms import AssessmentForm
from .models import Assessment, CoffeePurchase

# ========== ASSESSMENT VIEWS ==========
@login_required
def assessment_list(request):
    """
    Dashboard-style list page:
    - totals: completed, pending (purchases awaiting assessment), rejected, etc.
    - lists: assessed purchases and unassessed purchases
    """
    # Pull assessments with their purchase & assessor for efficient templates
    assessments_qs = Assessment.objects.select_related(
        "coffee",           # OneToOne to CoffeePurchase
        "coffee__supplier", # supplier for display columns
        "assessed_by"
    )

    total_assessments = assessments_qs.count()
    rejected_count = assessments_qs.filter(decision="Rejected").count()

    rejection_rate = (Decimal(rejected_count) / total_assessments * 100) if total_assessments else Decimal("0")

    # Pending = purchases that still need assessment and have none attached
    pending_count = CoffeePurchase.objects.filter(
        assessment_needed=True,
        assessment__isnull=True,   # reverse side of Assessment.coffee OneToOne
    ).count()

    completed_count = total_assessments

    totals = {
        "total_assessments": total_assessments,
        "completed_count": completed_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "rejection_rate": rejection_rate,  # Decimal percentage
    }

    assessed_purchases = (
        CoffeePurchase.objects
        .filter(assessment__isnull=False)
        .select_related("supplier", "assessment")
        .order_by("-purchase_date")
    )

    unassessed_purchases = (
        CoffeePurchase.objects
        .filter(assessment_needed=True, assessment__isnull=True)
        .select_related("supplier")
        .order_by("-purchase_date")
    )

    context = {
        "totals": totals,
        "assessed_purchases": assessed_purchases,
        "unassessed_purchases": unassessed_purchases,
        "assessments": assessments_qs,
    }
    return render(request, "assessment_list.html", context)


@login_required
def assessment_create(request, pk):
    """
    Create or update an assessment tied to a CoffeePurchase (one-per-purchase).
    """
    coffee_purchase = get_object_or_404(
        CoffeePurchase.objects.select_related('supplier'),
        pk=pk
    )

    # Try to get existing assessment
    try:
        assessment = Assessment.objects.get(coffee=coffee_purchase)
        created = False
    except Assessment.DoesNotExist:
        assessment = Assessment(assessed_by=request.user)  # Empty instance
        created = True

    if request.method == 'POST':
        form = AssessmentForm(
            request.POST,
            instance=assessment,
            coffee_purchase=coffee_purchase  # Pass it here
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    assessment = form.save(commit=False)
                    assessment.assessed_by = request.user
                    # coffee already set in form
                    assessment.save()

                    if coffee_purchase.assessment_needed:
                        coffee_purchase.assessment_needed = False
                        coffee_purchase.save(update_fields=['assessment_needed'])

                messages.success(request, 'Quality assessment saved successfully!')
                return redirect('assessment_list')

            except Exception as e:
                messages.error(request, f'Error saving assessment: {str(e)}')
    else:
        form = AssessmentForm(instance=assessment, coffee_purchase=coffee_purchase)

    context = {
        'form': form,
        'coffee_purchase': coffee_purchase,
        'page_title': f'Quality Assessment - {coffee_purchase}',
        'form_title': 'Create Assessment' if created else 'Update Assessment',
    }
    return render(request, 'assessment_form.html', context)



@login_required
def assessment_detail(request, pk):
    """
    Detailed view of a single assessment.
    Uses model-computed fields: final_price, decision, decision_reasons.
    """
    assessment = get_object_or_404(
        Assessment.objects.select_related('coffee', 'coffee__supplier', 'assessed_by'),
        pk=pk
    )

    is_rejected = (assessment.decision == "Rejected")
    rejection_reason = assessment.decision_reasons or None

    final_price = assessment.final_price or Decimal("0")
    ref_price = assessment.ref_price or Decimal("0")
    diff = (final_price - ref_price) if ref_price else Decimal("0")
    pct = (diff / ref_price * 100) if ref_price else Decimal("0")

    context = {
        'assessment': assessment,
        'is_rejected': is_rejected,
        'rejection_reason': rejection_reason,
        'price_analysis': {
            'final_price': final_price,
            'reference_price': ref_price,
            'difference': diff,
            'percentage': pct,
        },
        'page_title': f'Assessment - {assessment.coffee}',
    }
    return render(request, 'assessment_detail.html', context)
