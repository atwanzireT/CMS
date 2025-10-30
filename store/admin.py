# store/admin.py
from decimal import Decimal
from django.contrib import admin, messages
from django.db.models import Sum
from .models import (
    Supplier,
    CoffeePurchase,
    SupplierAccount,
    SupplierTransaction,
    EUDRDocumentation,
)

# -------------------------
# Inlines
# -------------------------

class SupplierAccountInline(admin.StackedInline):
    model = SupplierAccount
    can_delete = False
    extra = 0
    readonly_fields = ("balance", "last_updated")


class SupplierPurchaseInline(admin.TabularInline):
    model = CoffeePurchase
    extra = 0
    show_change_link = True
    fields = ("purchase_date", "coffee_category", "coffee_type", "quantity", "bags", "payment_status")
    readonly_fields = ()
    ordering = ("-purchase_date",)


class SupplierTransactionInline(admin.TabularInline):
    model = SupplierTransaction
    extra = 0
    show_change_link = True
    fields = ("created_at", "transaction_type", "amount", "reference", "purchase", "created_by")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


# -------------------------
# Suppliers
# -------------------------

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "email", "created_at", "created_by")
    list_filter = ("created_at",)
    search_fields = ("id", "name", "phone", "email")
    ordering = ("name",)
    inlines = (SupplierAccountInline, SupplierPurchaseInline)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# -------------------------
# Coffee Purchases
# -------------------------

@admin.register(CoffeePurchase)
class CoffeePurchaseAdmin(admin.ModelAdmin):
    date_hierarchy = "purchase_date"
    list_display = (
        "purchase_date",
        "supplier",
        "coffee_category",
        "coffee_type",
        "quantity",
        "bags",
        "payment_status",
        "assessment_needed",
        "recorded_by",
    )
    list_filter = (
        "purchase_date",
        "payment_status",
        "assessment_needed",
        "coffee_category",
        "coffee_type",
        "supplier",
    )
    search_fields = (
        "supplier__name",
        "supplier__phone",
        "supplier__id",
        "notes",
    )
    autocomplete_fields = ("supplier", "recorded_by")
    ordering = ("-purchase_date",)
    readonly_fields = ()
    actions = ("mark_as_paid", "mark_as_partial", "mark_as_pending")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("supplier", "recorded_by")

    def save_model(self, request, obj, form, change):
        # NOTE: CoffeePurchase.save_model in models won't be called; this is the right place.
        if not change and not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)

    # --- Actions
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(payment_status=CoffeePurchase.PAYMENT_PAID)
        self.message_user(request, f"{updated} purchase(s) marked as Paid.", level=messages.SUCCESS)
    mark_as_paid.short_description = "Mark selected purchases as Paid"

    def mark_as_partial(self, request, queryset):
        updated = queryset.update(payment_status=CoffeePurchase.PAYMENT_PARTIAL)
        self.message_user(request, f"{updated} purchase(s) marked as Partial.", level=messages.SUCCESS)
    mark_as_partial.short_description = "Mark selected purchases as Partial"

    def mark_as_pending(self, request, queryset):
        updated = queryset.update(payment_status=CoffeePurchase.PAYMENT_PENDING)
        self.message_user(request, f"{updated} purchase(s) marked as Pending.", level=messages.SUCCESS)
    mark_as_pending.short_description = "Mark selected purchases as Pending"


# -------------------------
# Supplier Accounts & Transactions
# -------------------------

@admin.register(SupplierAccount)
class SupplierAccountAdmin(admin.ModelAdmin):
    list_display = ("supplier", "balance", "last_updated", "total_debits", "total_credits")
    search_fields = ("supplier__name", "supplier__phone", "supplier__id")
    ordering = ("supplier__name",)
    inlines = (SupplierTransactionInline,)
    readonly_fields = ("balance", "last_updated")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("supplier")

    def total_debits(self, obj):
        agg = obj.transactions.filter(transaction_type=SupplierTransaction.DEBIT).aggregate(s=Sum("amount"))["s"]
        return agg or Decimal("0.00")

    def total_credits(self, obj):
        agg = obj.transactions.filter(transaction_type=SupplierTransaction.CREDIT).aggregate(s=Sum("amount"))["s"]
        return agg or Decimal("0.00")


@admin.register(SupplierTransaction)
class SupplierTransactionAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("created_at", "account", "supplier_name", "transaction_type", "amount", "reference", "purchase", "created_by")
    list_filter = ("created_at", "transaction_type")
    search_fields = ("account__supplier__name", "account__supplier__phone", "reference", "notes")
    autocomplete_fields = ("account", "purchase", "created_by")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("account__supplier", "purchase", "created_by")

    def supplier_name(self, obj):
        return obj.account.supplier.name
    supplier_name.admin_order_field = "account__supplier__name"
    supplier_name.short_description = "Supplier"


# -------------------------
# EUDR Documentation
# -------------------------
@admin.register(EUDRDocumentation)
class EUDRDocumentationAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("created_at", "batch_number", "coffee_type", "supplier_name", "total_kilograms", "receipts_count")
    list_filter = ("created_at", "coffee_type")
    search_fields = ("batch_number", "supplier_name", "documentation_notes")
    readonly_fields = ("batch_number", "created_at")
    ordering = ("-created_at",)

    def receipts_count(self, obj):
        return len(obj.documentation_receipts or [])
    receipts_count.short_description = "Receipts"

