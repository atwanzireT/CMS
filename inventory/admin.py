# admin.py
from django.contrib import admin
from .models import CoffeeInventory


@admin.register(CoffeeInventory)
class CoffeeInventoryAdmin(admin.ModelAdmin):
    list_display = (
        "coffee_category",
        "coffee_type",
        "quantity",
        "unit",
        "average_unit_cost",
        "current_value",
        "last_updated",
    )
    list_filter = ("coffee_category", "coffee_type", "unit")
    search_fields = ("coffee_type",)
    ordering = ("coffee_category", "coffee_type")
    readonly_fields = ("current_value", "last_updated")
    list_per_page = 50

    fieldsets = (
        ("Classification", {"fields": ("coffee_category", "coffee_type", "unit")}),
        ("Stock & Cost", {"fields": ("quantity", "average_unit_cost", "current_value")}),
        ("Timestamps", {"fields": ("last_updated",)}),
    )
