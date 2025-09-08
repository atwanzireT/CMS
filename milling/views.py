from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Count, Avg, Q, Case, When, Value, IntegerField
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
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



# ========== DASHBOARD ==========
def milling_dashboard(request):
    return render(request, 'milling_dashboard.html', {})

# ========== CUSTOMER VIEWS ==========
@login_required
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


@login_required
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
@login_required
def milling_list(request):
    milling_processes = MillingProcess.objects.select_related('customer').order_by('-created_at')
    form = MillingProcessForm()

    if request.method == 'POST':
        milling_id = request.POST.get('milling_id')
        instance = get_object_or_404(MillingProcess, id=milling_id) if milling_id else None
        
        form = MillingProcessForm(request.POST, instance=instance)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    milling = form.save(commit=False)
                    if not instance:  # Only set created_by for new records
                        milling.created_by = request.user
                    milling.save()
                    messages.success(request, 'Milling process saved successfully!')
                    return redirect('milling_list')
            except Exception as e:
                messages.error(request, f'Error saving process: {str(e)}')
        else:
            print("Form errors:", form.errors)
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    return render(request, 'milling_list.html', {
        'form': form,
        'milling_processes': milling_processes
    })

@login_required
def milling_detail(request, pk):
    milling = get_object_or_404(MillingProcess, pk=pk)
    context = get_base_context(request, 'Milling Process Details')
    
    context.update({
        'milling': milling,
        'transactions': milling.transactions.all()
    })
    return render(request, 'milling_detail.html', context)


@login_required
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

@login_required
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
