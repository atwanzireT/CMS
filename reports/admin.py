# app/admin.py
from django.contrib import admin
from .models import DailyStoreReport


@admin.register(DailyStoreReport)
class DailyStoreReportAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "coffee_type",
        "kilograms_bought",
        "kilograms_sold",
        "number_of_bags_sold",
        "bags_left_in_store",
        "kilograms_left_in_store",
        "average_buying_price_ugx_per_kg",
        "advances_given_ugx",
        "sold_to",
        "input_by",
        "created_at",
    )
    list_filter = (
        "coffee_type",
        "date",
        "input_by",
    )
    search_fields = (
        "sold_to",
        "comments",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "date"
    ordering = ("-date", "-created_at")

    fieldsets = (
        ("Report Info", {
            "fields": ("date", "coffee_type", "input_by")
        }),
        ("Transactions", {
            "fields": (
                "average_buying_price_ugx_per_kg",
                "kilograms_bought",
                "kilograms_sold",
                "number_of_bags_sold",
                "sold_to",
                "advances_given_ugx",
            )
        }),
        ("Inventory Snapshot", {
            "fields": (
                "bags_left_in_store",
                "kilograms_left_in_store",
                "kilograms_unbought_in_store",
            )
        }),
        ("Attachments & Comments", {
            "fields": ("attachment", "comments")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )
