from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import Supplier, SupplierAccount, SupplierTransaction
from assessment.models import Assessment  # if you keep the assessment logic


# ------------ utils ------------
def _q2(x: Decimal | None) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.1"))

def _signed_amount(tx: SupplierTransaction) -> Decimal:
    """
    Debit increases payables (positive), Credit decreases payables (negative).
    """
    amt = _q2(tx.amount)
    if tx.transaction_type == SupplierTransaction.DEBIT:
        return amt
    elif tx.transaction_type == SupplierTransaction.CREDIT:
        return -amt
    # Be defensive; treat unknown as 0 effect
    return Decimal("0.00")


# ------------ Supplier creation -> ensure account ------------
@receiver(post_save, sender=Supplier)
def create_supplier_account_on_supplier_create(sender, instance: Supplier, created: bool, **kwargs):
    if not created:
        return
    with transaction.atomic():
        SupplierAccount.objects.get_or_create(
            supplier=instance,
            defaults={"balance": Decimal("0.00")},
        )

# ------------ Assessment -> update SupplierAccount ------------
def total_payable(assessment: Assessment) -> Decimal:
    price = assessment.analysis_price_ugx or Decimal("0")
    qty = assessment.coffee.quantity or Decimal("0")
    return _q2(price * qty)

@receiver(pre_save, sender=Assessment)
def cache_previous_payable(sender, instance: Assessment, **kwargs):
    if instance.pk:
        try:
            prev = Assessment.objects.select_related("coffee").get(pk=instance.pk)
            instance._prev_payable = total_payable(prev)
        except Assessment.DoesNotExist:
            instance._prev_payable = Decimal("0.0")
    else:
        instance._prev_payable = Decimal("0.0")

@receiver(post_save, sender=Assessment)
def post_assessment_to_account(sender, instance: Assessment, created: bool, **kwargs):
    new_payable = total_payable(instance)
    prev_payable = getattr(instance, "_prev_payable", Decimal("0.0"))
    delta = _q2(new_payable - prev_payable)
    if delta == 0:
        return

    def _apply():
        supplier = instance.coffee.supplier
        account, _ = SupplierAccount.objects.get_or_create(supplier=supplier)
        SupplierAccount.objects.filter(pk=account.pk).update(balance=F("balance") + delta)
    transaction.on_commit(_apply)


# ------------ SupplierTransaction -> update SupplierAccount ------------
@receiver(pre_save, sender=SupplierTransaction)
def cache_prev_signed_amount(sender, instance: SupplierTransaction, **kwargs):
    """
    Cache the previous signed amount and previous account id before update,
    so post_save can compute the delta.
    """
    if not instance.pk:
        instance._prev_signed_amount = Decimal("0.00")
        instance._prev_account_id = instance.account_id  # for completeness
        return

    try:
        prev = SupplierTransaction.objects.select_related("account").get(pk=instance.pk)
    except SupplierTransaction.DoesNotExist:
        instance._prev_signed_amount = Decimal("0.00")
        instance._prev_account_id = instance.account_id
        return

    # compute previously applied signed amount
    instance._prev_signed_amount = _signed_amount(prev)
    instance._prev_account_id = prev.account_id



@receiver(post_save, sender=SupplierTransaction)
def apply_transaction_delta(sender, instance: SupplierTransaction, created: bool, **kwargs):
    """
    Apply the delta to the SupplierAccount:
      - On create: delta = new_signed
      - On update: delta = new_signed - prev_signed
      - If the account changed, remove from old account and add to new.
    """
    new_signed = _signed_amount(instance)
    prev_signed = getattr(instance, "_prev_signed_amount", Decimal("0.00"))
    prev_account_id = getattr(instance, "_prev_account_id", instance.account_id)

    # If account changed, we need two updates:
    if prev_account_id and prev_account_id != instance.account_id:
        # Remove old effect from the old account
        delta_old = -prev_signed
        # Apply new effect to the new account
        delta_new = new_signed

        def _apply_account_change():
            SupplierAccount.objects.filter(supplier_id__isnull=False, pk=prev_account_id).update(
                balance=F("balance") + delta_old
            )
            SupplierAccount.objects.filter(pk=instance.account_id).update(
                balance=F("balance") + delta_new
            )
        transaction.on_commit(_apply_account_change)
        return

    # Same account: just apply the delta
    delta = new_signed - prev_signed
    if delta == 0:
        return

    def _apply():
        SupplierAccount.objects.filter(pk=instance.account_id).update(
            balance=F("balance") + delta
        )
    transaction.on_commit(_apply)


@receiver(post_delete, sender=SupplierTransaction)
def reverse_on_delete(sender, instance: SupplierTransaction, **kwargs):
    """
    When a transaction is deleted, reverse its previously applied effect.
    """
    signed = _signed_amount(instance)
    if signed == 0:
        return

    def _apply():
        SupplierAccount.objects.filter(pk=instance.account_id).update(
            balance=F("balance") - signed
        )
    transaction.on_commit(_apply)
