import re
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.contrib.postgres.fields import ArrayField


# Create your models here.
class Supplier(models.Model):
    """Track coffee suppliers/vendors"""
    id = models.CharField(primary_key=True, max_length=50, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Coffee Supplier"
        verbose_name_plural = "Coffee Suppliers"

    def __str__(self):
        return f"{self.name} ({self.id})"

  
    def save(self, *args, **kwargs):
        if not self.id:
            prefix = 'GPC-SUP'
            last = Supplier.objects.filter(id__startswith=prefix).order_by('id').last()
            if last:
                # Extract the numeric part after the prefix
                match = re.search(rf'^{prefix}(\d+)$', last.id)
                if match:
                    new_num = int(match.group(1)) + 1
                else:
                    new_num = 1
            else:
                new_num = 1
            self.id = f"{prefix}{new_num:04d}"
        super().save(*args, **kwargs)


class CoffeePurchase(models.Model):
    """Records coffee purchases from suppliers with detailed classification"""
    # Coffee Categories
    GREEN = 'GR'
    PARCHMENT = 'PA'
    KIBOKO = 'KB'
    COFFEE_CATEGORIES = [
        (GREEN, 'Green Coffee'),
        (PARCHMENT, 'Parchment Coffee'),
        (KIBOKO, 'Kiboko Coffee'),
    ]
    
    # Coffee Types
    ARABICA = 'AR'
    ROBUSTA = 'RB'
    COFFEE_TYPES = [
        (ARABICA, 'Arabica'),
        (ROBUSTA, 'Robusta'),
    ]

    PAYMENT_PENDING = 'P'
    PAYMENT_PAID = 'D'
    PAYMENT_PARTIAL = 'T'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, 'Pending'),
        (PAYMENT_PAID, 'Paid'),
        (PAYMENT_PARTIAL, 'Partial'),
    ]


    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchases')
    coffee_category = models.CharField(
        max_length=2, choices=COFFEE_CATEGORIES, verbose_name="Coffee Form", blank=True
    )
    coffee_type = models.CharField(max_length=2, choices=COFFEE_TYPES, default="AR")
    quantity = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)], help_text="Coffee quantity in kilograms"
    )
    bags = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)], help_text="Number of bags (if applicable)"
    )
    payment_status = models.CharField(
        max_length=1, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_PENDING, verbose_name="Payment Status"
    )
    assessment_needed = models.BooleanField(default=True, verbose_name="Quality Assessment")
    purchase_date = models.DateField(default=timezone.now)
    delivery_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        editable=False, null=True, blank=True
    )

    class Meta:
        ordering = ['-purchase_date']
        verbose_name = "Coffee Purchase"
        verbose_name_plural = "Coffee Purchases"
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gte=0.01),
                name="quantity_gte_001"
            ),
        ]

    def save_model(self, request, obj, form, change):
        if not obj.pk:  # Only for new objects
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)

    def __str__(self):
        return f"{self.get_coffee_category_display()} {self.get_coffee_type_display()} - {self.quantity}kg"
    

class SupplierAccount(models.Model):
    """Tracks how much we owe each supplier (payables)."""
    supplier = models.OneToOneField('Supplier', on_delete=models.CASCADE, related_name='account')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # amount payable
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Account for {self.supplier.name} (Balance: {self.balance})"


class SupplierTransaction(models.Model):
    """Records debits/credits against a supplier's account (payables & payments)."""
    DEBIT = 'D'
    CREDIT = 'C'
    TYPE_CHOICES = [
        (DEBIT, 'Debit'),
        (CREDIT, 'Credit'),
    ]

    account = models.ForeignKey(SupplierAccount, on_delete=models.PROTECT, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    transaction_type = models.CharField(max_length=1, choices=TYPE_CHOICES)
    reference = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    purchase = models.ForeignKey('CoffeePurchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_transactions')
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount} for {self.account.supplier.name}"


class CoffeeType(models.TextChoices):
    ARABICA = 'Arabica', 'Arabica'
    ROBUSTA = 'Robusta', 'Robusta'
    BLEND = 'Blend', 'Blend'

class EUDRDocumentation(models.Model):
    coffee_type = models.CharField(
        max_length=20,
        choices=CoffeeType.choices,
        default=CoffeeType.ARABICA
    )
    total_kilograms = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00
    )
    supplier_name = models.CharField(max_length=255)
    batch_number = models.CharField(
        max_length=100,
        unique=True,
        blank=True
    )
    documentation_receipts = ArrayField(
        models.CharField(max_length=255),
        blank=True,
        default=list,
        help_text="List of receipt references"
    )
    documentation_notes = models.TextField(
        blank=True,
        help_text="Additional notes or remarks"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.batch_number:
            self.batch_number = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.coffee_type} - {self.batch_number}"