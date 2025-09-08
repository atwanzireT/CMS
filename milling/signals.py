from decimal import Decimal
from django.db import transaction as db_transaction
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import MillingProcess, CustomerAccount, MillingTransaction, Customer


@receiver(post_save, sender=Customer)
def create_customer_account(sender, instance: Customer, created, **kwargs):
    """
    When a Customer is created, ensure they have a CustomerAccount.
    Safe to call repeatedly due to get_or_create.
    """
    if created:
        CustomerAccount.objects.get_or_create(customer=instance)


@receiver(post_save, sender=MillingProcess)
def handle_completed_milling(sender, instance: MillingProcess, created, **kwargs):
    """
    When a MillingProcess is completed, increment the customer's balance
    by creating a MillingTransaction and updating the CustomerAccount.
    """
    # Only act if process is completed and has a hulled_weight
    if instance.status == MillingProcess.COMPLETED and instance.hulled_weight:
        account = CustomerAccount.objects.get(customer=instance.customer)

        # Calculate milling cost
        amount = instance.milling_cost

        # Prevent duplicate transaction on updates
        exists = MillingTransaction.objects.filter(
            milling_process=instance,
            account=account,
            amount=amount,
            transaction_type=MillingTransaction.DEBIT
        ).exists()
        if exists:
            return

        # Create a transaction record (audit trail)
        tx = MillingTransaction.objects.create(
            account=account,
            amount=amount,
            transaction_type=MillingTransaction.DEBIT,
            reference=f"MILL-{instance.pk}",
            created_by=instance.created_by,
            milling_process=instance
        )

        # Increment balance (debit)
        account.balance += amount
        account.save(update_fields=['balance', 'last_updated'])


def tx_effect(amount: Decimal, tx_type: str) -> Decimal:
    """
    Business rule:
      - DEBIT (D) increases balance (customer owes more)
      - CREDIT (C) decreases balance (customer owes less)
    """
    if tx_type == MillingTransaction.DEBIT:
        return Decimal(amount)
    elif tx_type == MillingTransaction.CREDIT:
        return Decimal(amount) * Decimal('-1')
    return Decimal('0')


# --- Handle create & update ---
@receiver(pre_save, sender=MillingTransaction)
def cache_old_values(sender, instance, **kwargs):
    """
    Before saving, cache the old values to adjust balance if this is an update.
    """
    if instance.pk:
        try:
            old = MillingTransaction.objects.get(pk=instance.pk)
            instance._old_account_id = old.account_id
            instance._old_effect = tx_effect(old.amount, old.transaction_type)
        except MillingTransaction.DoesNotExist:
            instance._old_account_id = None
            instance._old_effect = Decimal('0')
    else:
        instance._old_account_id = None
        instance._old_effect = Decimal('0')


@receiver(post_save, sender=MillingTransaction)
def update_balance_on_save(sender, instance, created, **kwargs):
    """
    After save, apply the net effect to the account.
    Handles both create and update.
    """
    new_effect = tx_effect(instance.amount, instance.transaction_type)
    old_effect = getattr(instance, '_old_effect', Decimal('0'))
    old_account_id = getattr(instance, '_old_account_id', None)

    with db_transaction.atomic():
        # If account changed, reverse on old account
        if old_account_id and old_account_id != instance.account_id:
            try:
                old_acc = CustomerAccount.objects.select_for_update().get(pk=old_account_id)
                old_acc.balance -= old_effect
                old_acc.save(update_fields=['balance', 'last_updated'])
            except CustomerAccount.DoesNotExist:
                pass

        # Apply delta on new account
        delta = new_effect - old_effect if old_account_id == instance.account_id else new_effect
        if delta:
            acc = CustomerAccount.objects.select_for_update().get(pk=instance.account_id)
            acc.balance += delta
            acc.save(update_fields=['balance', 'last_updated'])


# --- Handle delete ---
@receiver(post_delete, sender=MillingTransaction)
def update_balance_on_delete(sender, instance, **kwargs):
    """
    Reverse the effect of the deleted transaction.
    """
    effect = tx_effect(instance.amount, instance.transaction_type)
    with db_transaction.atomic():
        try:
            acc = CustomerAccount.objects.select_for_update().get(pk=instance.account_id)
            acc.balance -= effect
            acc.save(update_fields=['balance', 'last_updated'])
        except CustomerAccount.DoesNotExist:
            pass
