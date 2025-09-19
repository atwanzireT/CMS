from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Optional
from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from assessment.models import Assessment 
from .models import CoffeeInventory
from sales.models import CoffeeSale


# ----------------- small helpers -----------------
def q2(x) -> Decimal:
    if isinstance(x, Decimal):
        d = x
    else:
        d = Decimal(str(x))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# Map CoffeeSale.coffee_type -> CoffeeInventory.coffee_type choices
SALE_TO_INV_TYPE = {
    "AR": "ARABICA",
    "RB": "ROBUSTA",
}
DEFAULT_SALES_CATEGORY = "GR"   # assume sales are Green coffee; change to "PA"/"KB" if needed
DEFAULT_UNIT = "kg"


def extract_purchase_values(purchase) -> Tuple[Decimal, Decimal, str, str, str]:
    """
    From CoffeePurchase: return (quantity_kg, total_cost, category_code, type_code, unit)
    Tries common field names so you don't have to edit this unless your schema is unusual.
    """
    # quantity
    qty = (
        getattr(purchase, "quantity", None)
        or getattr(purchase, "quantity_kg", None)
        or getattr(purchase, "net_weight_kg", None)
        or getattr(purchase, "weight_kg", None)
    )
    if qty is None:
        raise ValueError("Purchase missing quantity field (quantity/quantity_kg/net_weight_kg/weight_kg)")
    qty = q2(qty)

    # total cost (or derive from unit price)
    total_cost = getattr(purchase, "total_cost", None) or getattr(purchase, "total_price", None)
    if total_cost is None:
        unit_price = getattr(purchase, "unit_price", None) or getattr(purchase, "price_per_kg", None)
        if unit_price is None:
            raise ValueError("Purchase missing price fields (total_cost/total_price or unit_price)")
        total_cost = q2(unit_price) * qty
    else:
        total_cost = q2(total_cost)

    # classification
    category = getattr(purchase, "coffee_category", None)
    ctype = getattr(purchase, "coffee_type", None)
    if not category or not ctype:
        raise ValueError("Purchase missing classification (coffee_category/coffee_type)")
    return qty, total_cost, category, ctype, DEFAULT_UNIT


def extract_sale_key_qty(sale: CoffeeSale) -> Tuple[str, str, Decimal, str]:
    """
    From CoffeeSale: return (category_code, type_code_for_inventory, quantity_kg, unit)
    Assumes all sales are Green coffee unless you change DEFAULT_SALES_CATEGORY.
    """
    category = DEFAULT_SALES_CATEGORY
    inv_type = SALE_TO_INV_TYPE.get(sale.coffee_type, "ARABICA")
    qty = q2(sale.quantity_kg or 0)
    return category, inv_type, qty, DEFAULT_UNIT


# ----------------- Assessment -> add purchases -----------------
@receiver(post_save, sender=Assessment)
def _apply_inventory_on_assessment_accept(sender, instance: Assessment, created: bool, **kwargs):
    """
    When an Assessment saves and is Accepted (and has a linked purchase),
    add that purchase's quantity to inventory and update weighted-average cost.

    This applies on first save *when* it's Accepted. If you need reversals or
    idempotency tracking, we can extend this later.
    """
    if instance.decision != "Accepted":
        return
    if not instance.coffee_id:
        return

    try:
        qty, total_cost, category, ctype, unit = extract_purchase_values(instance.coffee)
    except Exception:
        return  # quietly skip if purchase fields are incomplete

    inv, _ = CoffeeInventory.objects.get_or_create(
        coffee_category=category,
        coffee_type=ctype,
        defaults={"unit": unit},
    )
    try:
        inv.update_inventory(quantity_change=qty, cost_change=total_cost)
    except Exception:
        # e.g., invalid values; skip to avoid crashing the save
        pass


# ----------------- CoffeeSale -> deduct/restore stock -----------------
@receiver(pre_save, sender=CoffeeSale)
def _sales_pre_save_diff(sender, instance: CoffeeSale, **kwargs):
    """
    Compute how inventory should change for this save and stash it on the instance.
    We'll apply it in post_save to ensure the sale itself saved successfully.

    If new: delta = -new_qty @ (new category/type)
    If update:
      - if type/category same: delta = -(new - old)
      - if changed type/category: +old back to old bucket, -new from new bucket
    """
    # default: no adjustments
    instance._inv_adjustments = []  # list of tuples: (category, inv_type, delta_qty, unit)

    # Calculate new key
    new_cat, new_type, new_qty, unit = extract_sale_key_qty(instance)

    if instance.pk is None:
        # create: just deduct new qty
        if new_qty > 0:
            instance._inv_adjustments.append((new_cat, new_type, -new_qty, unit))
        return

    # Fetch previous persisted values
    try:
        prev = sender.objects.only("coffee_type", "quantity_kg").get(pk=instance.pk)
    except sender.DoesNotExist:
        prev = None

    if not prev:
        if new_qty > 0:
            instance._inv_adjustments.append((new_cat, new_type, -new_qty, unit))
        return

    old_cat, old_type, old_qty, _unit = extract_sale_key_qty(prev)

    if (old_cat, old_type) == (new_cat, new_type):
        delta = q2(new_qty - old_qty)
        if delta != 0:
            instance._inv_adjustments.append((new_cat, new_type, -delta, unit))
    else:
        # move stock between buckets
        if old_qty > 0:
            instance._inv_adjustments.append((old_cat, old_type, +old_qty, unit))  # give back old
        if new_qty > 0:
            instance._inv_adjustments.append((new_cat, new_type, -new_qty, unit))  # deduct new


@receiver(post_save, sender=CoffeeSale)
def _sales_post_save_apply(sender, instance: CoffeeSale, created: bool, **kwargs):
    """
    Apply inventory adjustments computed in pre_save.
    For sales, we don't touch costs; avg cost is unchanged on issues.
    """
    adjustments = getattr(instance, "_inv_adjustments", [])
    if not adjustments:
        return

    for category, inv_type, delta_qty, unit in adjustments:
        inv, _ = CoffeeInventory.objects.get_or_create(
            coffee_category=category,
            coffee_type=inv_type,
            defaults={"unit": unit},
        )
        try:
            inv.update_inventory(quantity_change=delta_qty)
        except Exception:
            # If insufficient stock or other errors, skip silently (or log if you prefer).
            pass

    # cleanup
    instance._inv_adjustments = []


@receiver(post_delete, sender=CoffeeSale)
def _sales_post_delete_restore(sender, instance: CoffeeSale, **kwargs):
    """
    On delete, restore the previously deducted quantity back to inventory.
    """
    category, inv_type, qty, unit = extract_sale_key_qty(instance)
    if qty <= 0:
        return
    inv, _ = CoffeeInventory.objects.get_or_create(
        coffee_category=category,
        coffee_type=inv_type,
        defaults={"unit": unit},
    )
    try:
        inv.update_inventory(quantity_change=+qty)
    except Exception:
        pass
