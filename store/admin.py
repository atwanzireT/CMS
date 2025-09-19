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