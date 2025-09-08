from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal


# Create your models here.
class Customer(models.Model):
    """Customer model with auto-generated ID"""
    id = models.CharField(primary_key=True, max_length=50, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.id})"

    def save(self, *args, **kwargs):
        if not self.id:
            prefix = 'GPC-CUS'
            last = Customer.objects.filter(id__startswith=prefix).order_by('id').last()
            if last:
                new_num = int(last.id[len(prefix):]) + 1
            else:
                new_num = 1
            self.id = f"{prefix}{new_num:03d}"
        super().save(*args, **kwargs)


class MillingProcess(models.Model):
    """Tracks coffee milling processes"""
    PENDING = 'P'
    COMPLETED = 'C'
    CANCELLED = 'X'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='milling_processes')
    initial_weight = models.DecimalField(max_digits=6, blank=True, null=True, decimal_places=2, validators=[MinValueValidator(0.1)])
    hulled_weight = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0.1)], null=True, blank=True)
    milling_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null = True, default=150.00)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, blank=True, null = True, default=COMPLETED)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True
    )
    notes = models.TextField(blank=True)

    @property
    def milling_cost(self):
        if self.hulled_weight is None or self.milling_rate is None:
            return Decimal('0.00')
        return Decimal(str(self.hulled_weight)) * Decimal(str(self.milling_rate))

    def save(self, *args, **kwargs):
        if self.status == self.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer.id} {self.customer.name} - Ugx {self.milling_cost}"

class CustomerAccount(models.Model):
    """Tracks customer balances"""
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='account')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def update_balance(self, amount):
        """Update account balance"""
        self.balance += amount
        self.save()

    def __str__(self):
        return f"Account for {self.customer.name} (Balance: {self.balance})"


class MillingTransaction(models.Model):
    """Records all financial transactions"""
    DEBIT = 'D'
    CREDIT = 'C'
    TYPE_CHOICES = [
        (DEBIT, 'Debit'),
        (CREDIT, 'Credit'),
    ]

    account = models.ForeignKey(CustomerAccount, on_delete=models.PROTECT, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=1, choices=TYPE_CHOICES)
    reference = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )
    milling_process = models.ForeignKey(
        MillingProcess, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='transactions'
    )

    def __str__(self):
        return f"{self.get_transaction_type_display()} of {self.amount}"

