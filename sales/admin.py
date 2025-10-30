# admin.py
from __future__ import annotations

import csv
from decimal import Decimal
from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from .models import SaleCustomer, CoffeeSale


# ----- Small helpers ---------------------------------------------------------
def _dec(v) -> str:
    """Pretty decimal for CSV."""
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    try:
        return f"{Decimal(str(v)):.2f}"
    except Exception:
        return str(v)


def export_sales_csv(modeladmin, request, queryset):
    """Admin action: export selected CoffeeSales as CSV."""
    filename = f"coffee_sales_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fields = [
        "id",
        "sale_date",
        "customer__name",
        "coffee_type",
        "moisture_pct",
        "quantity_kg",
        "unit_price_ugx",
        "total_amount_ugx",
        "truck_details",
        "driver_details",
        "recorded_by__username",
        "created_at",
        "updated_at",
    ]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    # header
    writer.writerow(
        [
            "ID",
            "Sale Date",
            "Customer",
            "Coffee Type",
            "Moisture (%)",
            "Weight (kg)",
            "Unit Price (UGX/kg)",
            "Total Amount (UGX)",
            "Truck Details",
            "Driver Details",
            "Recorded By",
            "Created At",
            "Updated At",
        ]
    )

    # rows
    for obj in queryset.select_related("customer", "recorded_by"):
        writer.writerow(
            [
                obj.pk,
                obj.sale_date.isoformat(),
                obj.customer.name if obj.customer_id else "",
                obj.get_coffee_type_display(),
                _dec(obj.moisture_pct),
                _dec(obj.quantity_kg),
                _dec(obj.unit_price_ugx),
                _dec(obj.total_amount_ugx),
                obj.truck_details,
                obj.driver_details,
                getattr(obj.recorded_by, "username", ""),
                obj.created_at.isoformat() if obj.created_at else "",
                obj.updated_at.isoformat() if obj.updated_at else "",
            ]
        )
    return response


export_sales_csv.short_description = "Export selected sales to CSV"  # type: ignore[attr-defined]


# ----- Inlines ---------------------------------------------------------------
class CoffeeSaleInline(admin.TabularInline):
    model = CoffeeSale
    extra = 0
    can_delete = False
    fk_name = "customer"
    readonly_fields = (
        "sale_date",
        "coffee_type",
        "moisture_pct",
        "quantity_kg",
        "unit_price_ugx",
        "inline_total",
        "recorded_by",
        "created_at",
    )
    fields = (
        "sale_date",
        "coffee_type",
        "moisture_pct",
        "quantity_kg",
        "unit_price_ugx",
        "inline_total",
        "recorded_by",
        "created_at",
    )
    show_change_link = True

    def inline_total(self, obj: CoffeeSale) -> str:
        return _dec(obj.total_amount_ugx)
    inline_total.short_description = "Total (UGX)"  # type: ignore[attr-defined]


# ----- ModelAdmins -----------------------------------------------------------
@admin.register(SaleCustomer)
class SaleCustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "email", "address", "created_at")
    search_fields = ("name", "contact", "email", "address")
    list_per_page = 50
    ordering = ("name",)
    inlines = [CoffeeSaleInline]

    fieldsets = (
        (None, {"fields": ("name", "address", "contact", "email")}),
        ("Notes", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(CoffeeSale)
class CoffeeSaleAdmin(admin.ModelAdmin):
    # List page
    list_display = (
        "id",
        "sale_date",
        "customer",
        "coffee_type",
        "quantity_kg",
        "unit_price_ugx",
        "total_admin",
        "recorded_by",
        "created_at",
    )
    list_select_related = ("customer", "recorded_by")
    list_filter = ("coffee_type", "sale_date", "recorded_by")
    search_fields = (
        "customer__name",
        "customer__contact",
        "customer__email",
        "truck_details",
        "driver_details",
        "notes",
        "id",
    )
    date_hierarchy = "sale_date"
    list_per_page = 50
    ordering = ("-sale_date", "-created_at")

    # Form
    autocomplete_fields = ("customer",)
    readonly_fields = ("created_at", "updated_at", "recorded_by", "computed_total")
    fieldsets = (
        ("Sale Info", {
            "fields": (
                "customer",
                "sale_date",
                "coffee_type",
                "moisture_pct",
                ("quantity_kg", "unit_price_ugx", "computed_total"),
            )
        }),
        ("Logistics", {"fields": ("truck_details", "driver_details", "sales_grn")}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("recorded_by", "created_at", "updated_at")}),
    )

    actions = [export_sales_csv]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("customer", "recorded_by")

    # Display helpers
    def total_admin(self, obj: CoffeeSale) -> str:
        return _dec(obj.total_amount_ugx)
    total_admin.short_description = "Total (UGX)"  # type: ignore[attr-defined]
    total_admin.admin_order_field = "unit_price_ugx"  # closest sortable field

    def computed_total(self, obj: CoffeeSale) -> str:
        return _dec(obj.total_amount_ugx)
    computed_total.short_description = "Total (UGX)"  # type: ignore[attr-defined]

    # Auto-set recorded_by to current user on create
    def save_model(self, request, obj: CoffeeSale, form, change):
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)

    # Prevent edits to certain fields after creation (optional, keeps data clean)
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        # Example rule: lock customer after creation
        # if obj:
        #     ro.append("customer")
        return ro


# ----- Admin site branding (optional) ----------------------------------------
admin.site.site_header = "Great Pearl Coffee – Admin"
admin.site.site_title = "Great Pearl Coffee Admin"
admin.site.index_title = "Operations Dashboard"
