from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import *

admin.site.register(SupplierAccount)
admin.site.register(SupplierTransaction)
admin.site.register(CoffeePurchase)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'email_display', 'created_at')
    search_fields = ('id', 'name', 'phone', 'email')
    list_filter = ('created_at',)
    readonly_fields = ('id', 'created_at', 'created_by')
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'phone', 'email', 'address')
        }),
        ('Metadata', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def email_display(self, obj):
        return obj.email if obj.email else "-"
    email_display.short_description = 'Email'
    
    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CoffeeSale)
class CoffeeSaleAdmin(admin.ModelAdmin):
    list_display = (
        'sale_display',
        'customer_info',
        'coffee_type_display',
        'quantity_price_display',
        'total_amount_display',
        'sale_date',
        'recorded_by_display'
    )
    list_filter = (
        'sale_date',
        'coffee_category',
        'coffee_type',
    )
    search_fields = (
        'customer',
        'customer_contact',
        'notes'
    )
    readonly_fields = ('recorded_by', 'sale_date', 'total_amount_display')
    fieldsets = (
        ('Sale Information', {
            'fields': (
                'customer',
                'customer_address',
                'customer_contact',
                'coffee_category',
                'coffee_type',
                'quantity',
                'unit_price',
            )
        }),
        ('Dates & Metadata', {
            'fields': (
                'sale_date',
                'notes',
                'recorded_by',
            ),
            'classes': ('collapse',)
        }),
    )
    date_hierarchy = 'sale_date'
    
    def sale_display(self, obj):
        return f"Sale #{obj.id}"
    sale_display.short_description = 'Sale'
    
    def customer_info(self, obj):
        return format_html("{}<br><small>{}</small>", obj.customer or "Unknown", obj.customer_contact or "")
    customer_info.short_description = 'Customer'
    
    def coffee_type_display(self, obj):
        return f"{obj.get_coffee_category_display()} {obj.get_coffee_type_display()}"
    coffee_type_display.short_description = 'Coffee Type'
    
    def quantity_price_display(self, obj):
        return f"{obj.quantity}kg @ UGX {obj.unit_price:,.2f}"
    quantity_price_display.short_description = 'Qty/Price'
    
    def total_amount_display(self, obj):
        return f"UGX {obj.total_amount:,.2f}"
    total_amount_display.short_description = 'Total'
    
    def recorded_by_display(self, obj):
        return obj.recorded_by.get_full_name() or obj.recorded_by.username
    recorded_by_display.short_description = 'Recorded By'
    
    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.recorded_by:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(CoffeeInventory)
class CoffeeInventoryAdmin(admin.ModelAdmin):
    list_display = (
        'inventory_display',
        'current_stock',
        'average_cost',
        'current_value_display',
        'last_updated'
    )
    list_filter = (
        'coffee_category',
        'coffee_type',
    )
    search_fields = (
        'coffee_category',
        'coffee_type',
    )
    readonly_fields = ('last_updated', 'current_value', 'average_unit_cost')
    fieldsets = (
        ('Inventory Information', {
            'fields': (
                'coffee_category',
                'coffee_type',
                'quantity',
                'unit',
            )
        }),
        ('Financial Information', {
            'fields': (
                'average_unit_cost',
                'current_value',
                'last_updated',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def inventory_display(self, obj):
        return f"{obj.get_coffee_category_display()} {obj.get_coffee_type_display()}"
    inventory_display.short_description = 'Inventory Item'
    
    def current_stock(self, obj):
        return f"{obj.quantity}{obj.unit}"
    current_stock.short_description = 'Current Stock'
    
    def average_cost(self, obj):
        return f"UGX {obj.average_unit_cost:,.2f}/{obj.unit}"
    average_cost.short_description = 'Avg. Cost'
    
    def current_value_display(self, obj):
        return f"UGX {obj.current_value:,.2f}"
    current_value_display.short_description = 'Total Value'


@admin.register(EUDRDocumentation)
class EUDRDocumentationAdmin(admin.ModelAdmin):
    list_display = (
        'coffee_type',
        'supplier_name',
        'batch_number',
        'total_kilograms',
        'created_at'
    )
    list_filter = ('coffee_type', 'created_at')
    search_fields = ('supplier_name', 'batch_number')
    readonly_fields = ('batch_number', 'created_at')

    fieldsets = (
        (None, {
            'fields': (
                'coffee_type',
                'total_kilograms',
                'supplier_name',
                'batch_number',
                'documentation_receipts',
                'documentation_notes',
            )
        }),
    )