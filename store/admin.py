from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Supplier,
    SupplierAccount,
    SupplierTransaction,
    CoffeePurchase,
    EUDRDocumentation,
)

# ---------- Inlines ----------

class SupplierTransactionInline(admin.TabularInline):
    """
    Inline for transactions under SupplierAccount (read-only by default).
    """
    model = SupplierTransaction
    extra = 0
    readonly_fields = ("created_at", "created_by", "transaction_type", "amount", "reference", "purchase_link")
    fields = ("created_at", "transaction_type", "amount", "reference", "purchase_link", "created_by")
    can_delete = False
    show_change_link = True
    autocomplete_fields = ("purchase",)

    @admin.display(description="Purchase")
    def purchase_link(self, obj):
        if obj.purchase_id:
            url = reverse("admin:store_coffeepurchase_change", args=[obj.purchase_id])
            return format_html('<a href="{}">#{}</a>', url, obj.purchase_id)
        return "—"


class SupplierAccountInline(admin.StackedInline):
    """
    Read-only snapshot of the account inside Supplier admin.
    """
    model = SupplierAccount
    can_delete = False
    extra = 0
    readonly_fields = ("balance", "last_updated")
    fields = ("balance", "last_updated")


# ---------- Supplier ----------

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "phone",
        "email_display",
        "account_badge",
        "created_at",
    )
    search_fields = ("id", "name", "phone", "email")
    list_filter = ("created_at",)
    readonly_fields = ("id", "created_at", "created_by", "account_link")
    fieldsets = (
        ("Basic Information", {
            "fields": ("id", "name", "phone", "email", "address", "account_link")
        }),
        ("Metadata", {
            "fields": ("created_at", "created_by"),
            "classes": ("collapse",)
        }),
    )
    inlines = [SupplierAccountInline]
    actions = ["ensure_account"]

    @admin.display(description="Email")
    def email_display(self, obj):
        return obj.email or "—"

    @admin.display(description="Account")
    def account_badge(self, obj):
        account = getattr(obj, "account", None)
        if not account:
            return format_html('<span class="badge" style="background:#f59e0b;color:white;padding:2px 6px;border-radius:8px;">None</span>')
        url = reverse("admin:store_supplieraccount_change", args=[account.id])
        return format_html(
            '<a href="{}" style="text-decoration:none;"><span class="badge" style="background:#10b981;color:white;padding:2px 6px;border-radius:8px;">UGX {:,.2f}</span></a>',
            url, account.balance or 0
        )

    @admin.display(description="Account")
    def account_link(self, obj):
        account = getattr(obj, "account", None)
        if not account:
            return "This supplier has no account yet."
        url = reverse("admin:store_supplieraccount_change", args=[account.id])
        return format_html('<a href="{}">Open account (balance: UGX {:,.2f})</a>', url, account.balance or 0)

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Ensure a Supplier Account exists")
    def ensure_account(self, request, queryset):
        created = 0
        for supplier in queryset:
            _, was_created = SupplierAccount.objects.get_or_create(supplier=supplier)
            created += 1 if was_created else 0
        if created:
            self.message_user(request, f"Created {created} supplier account(s).", level=messages.SUCCESS)
        else:
            self.message_user(request, "All selected suppliers already have accounts.", level=messages.INFO)


# ---------- Supplier Account ----------

@admin.register(SupplierAccount)
class SupplierAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier_link", "balance_fmt", "last_updated")
    search_fields = ("supplier__id", "supplier__name", "supplier__phone")
    readonly_fields = ("last_updated",)
    autocomplete_fields = ("supplier",)
    inlines = [SupplierTransactionInline]

    @admin.display(description="Supplier")
    def supplier_link(self, obj):
        url = reverse("admin:store_supplier_change", args=[obj.supplier_id])
        return format_html('<a href="{}">{} ({})</a>', url, obj.supplier.name, obj.supplier_id)

    @admin.display(description="Balance")
    def balance_fmt(self, obj):
        return f"UGX {obj.balance:,.2f}"


# ---------- Supplier Transaction ----------

@admin.register(SupplierTransaction)
class SupplierTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "transaction_type",
        "amount_fmt",
        "account_link",
        "purchase_link",
        "created_by",
        "reference",
    )
    list_filter = ("transaction_type", "created_at")
    search_fields = ("reference", "account__supplier__name", "account__supplier__id")
    autocomplete_fields = ("account", "purchase", "created_by")
    readonly_fields = ("created_at",)

    @admin.display(description="Amount")
    def amount_fmt(self, obj):
        return f"UGX {obj.amount:,.2f}"

    @admin.display(description="Account")
    def account_link(self, obj):
        url = reverse("admin:store_supplieraccount_change", args=[obj.account_id])
        return format_html('<a href="{}">{} ({})</a>', url, obj.account.supplier.name, obj.account.supplier_id)

    @admin.display(description="Purchase")
    def purchase_link(self, obj):
        if not obj.purchase_id:
            return "—"
        url = reverse("admin:store_coffeepurchase_change", args=[obj.purchase_id])
        return format_html('<a href="{}">Purchase #{}</a>', url, obj.purchase_id)


# ---------- Coffee Purchase ----------

@admin.register(CoffeePurchase)
class CoffeePurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "supplier_link",
        "coffee_type",
        "coffee_category",
        "quantity",
        "bags",
        "payment_status_badge",
        "purchase_date",
        "delivery_date",
        "assessment_link",
    )
    list_filter = ("payment_status", "coffee_type", "coffee_category", "purchase_date", "delivery_date")
    search_fields = ("supplier__name", "supplier__id", "supplier__phone")
    date_hierarchy = "purchase_date"
    autocomplete_fields = ("supplier", "recorded_by")
    readonly_fields = ("recorded_by",)

    @admin.display(description="Supplier")
    def supplier_link(self, obj):
        url = reverse("admin:store_supplier_change", args=[obj.supplier_id])
        return format_html('<a href="{}">{} ({})</a>', url, obj.supplier.name, obj.supplier_id)

    @admin.display(description="Payment")
    def payment_status_badge(self, obj):
        label = obj.get_payment_status_display()
        color = {
            "D": "#10b981",  # Paid
            "T": "#3b82f6",  # Partial
            "P": "#f59e0b",  # Pending
        }.get(obj.payment_status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:9999px;font-size:12px;">{}</span>',
            color, label
        )

    @admin.display(description="Assessment")
    def assessment_link(self, obj):
        # If you also register Assessment in its own admin, this will link there.
        assessment = getattr(obj, "assessment", None)
        if not assessment:
            return mark_safe('<span style="color:#9ca3af;">—</span>')
        try:
            url = reverse("admin:assessment_assessment_change", args=[assessment.id])
            return format_html('<a href="{}">View</a>', url)
        except Exception:
            return "Yes"


# ---------- EUDR Documentation ----------

@admin.register(EUDRDocumentation)
class EUDRDocumentationAdmin(admin.ModelAdmin):
    list_display = (
        "coffee_type",
        "supplier_name",
        "batch_number",
        "total_kilograms",
        "created_at",
        "receipts_count",
    )
    list_filter = ("coffee_type", "created_at")
    search_fields = ("supplier_name", "batch_number", "documentation_receipts")
    readonly_fields = ("batch_number", "created_at", "receipts_preview")

    fieldsets = (
        (None, {
            "fields": (
                "coffee_type",
                "total_kilograms",
                "supplier_name",
                "batch_number",
                "documentation_receipts",
                "receipts_preview",
                "documentation_notes",
                "created_at",
            )
        }),
    )

    @admin.display(description="Receipts")
    def receipts_count(self, obj):
        return len(obj.documentation_receipts or [])

    @admin.display(description="Receipts Preview")
    def receipts_preview(self, obj):
        """
        Pretty list for ArrayField receipts.
        """
        items = obj.documentation_receipts or []
        if not items:
            return mark_safe('<em style="color:#9ca3af;">No receipts attached</em>')
        lis = "".join(f"<li>{admin.utils.escape(i)}</li>" for i in items)
        return mark_safe(f"<ul style='margin:0 0 0 1rem;padding:0;list-style:disc;'>{lis}</ul>")
