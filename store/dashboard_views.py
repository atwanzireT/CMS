from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from sales.models import CoffeeSale
from milling.models import MillingProcess, MillingTransaction, Customer


def get_base_context(request, page_title='Default Page Title'):
    return {
        'page_title': page_title,
        'user': request.user
    }


@login_required
def dashboard(request):
    today = timezone.now().date()
    last_week = today - timedelta(days=7)
    
    context = get_base_context(request, 'Dashboard')
    context.update({
        'total_customers': Customer.objects.count(),
        'new_customers_week': Customer.objects.filter(created_at__date__gte=last_week).count(),
        'pending_milling': MillingProcess.objects.filter(status='P').count(),
        'completed_milling': MillingProcess.objects.filter(status='C').count(),
        'total_hulled': MillingProcess.objects.filter(status='C').aggregate(Sum('hulled_weight'))['hulled_weight__sum'] or 0,
        'total_revenue': MillingTransaction.objects.filter(transaction_type='C').aggregate(Sum('amount'))['amount__sum'] or 0,
        'total_debits': MillingTransaction.objects.filter(transaction_type='D').aggregate(Sum('amount'))['amount__sum'] or 0,
        'top_customers': Customer.objects.annotate(
            milling_volume=Sum('milling_processes__hulled_weight')
        ).exclude(milling_volume=None).order_by('-milling_volume')[:5],
        'recent_transactions': MillingTransaction.objects.select_related('account__customer').order_by('-created_at')[:5],
        'recent_sales': CoffeeSale.objects.select_related('recorded_by').order_by('-sale_date')[:5],
    })
    return render(request, 'index.html', context)
