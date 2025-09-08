from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Customer, MillingProcess, CustomerAccount, MillingTransaction

# Register your models here.

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """Admin configuration for Customer model"""
    list_display = ('id', 'name', 'phone', 'created_at', 'created_by')
    list_filter = ('created_at',)
    search_fields = ('id', 'name', 'phone')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        (None, {
            'fields': ('id', 'name', 'phone')
        }),
        ('Metadata', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        return super().get_queryset(request).select_related('created_by')

    def save_model(self, request, obj, form, change):
        """Automatically set created_by to current user when creating new customer"""
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class MillingProcessInline(admin.TabularInline):
    """Inline for MillingProcess in Customer admin"""
    model = MillingProcess
    extra = 0
    readonly_fields = ('milling_cost', 'created_at', 'completed_at')
    fields = ('initial_weight', 'hulled_weight', 'milling_rate', 'milling_cost', 'status', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MillingProcess)
class MillingProcessAdmin(admin.ModelAdmin):
    """Admin configuration for MillingProcess model"""
    list_display = ('customer', 'initial_weight', 'hulled_weight', 'milling_rate', 'milling_cost', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'completed_at')
    search_fields = ('customer__id', 'customer__name', 'customer__phone')
    readonly_fields = ('milling_cost', 'created_at', 'completed_at')
    fieldsets = (
        ('Process Details', {
            'fields': ('customer', 'initial_weight', 'hulled_weight', 'milling_rate', 'milling_cost')
        }),
        ('Status & Timing', {
            'fields': ('status', 'created_at', 'completed_at')
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('customer', 'created_by')

    def save_model(self, request, obj, form, change):
        """Automatically set created_by to current user when creating new process"""
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    """Admin configuration for CustomerAccount model"""
    list_display = ('customer', 'balance', 'last_updated')
    search_fields = ('customer__id', 'customer__name', 'customer__phone')
    readonly_fields = ('last_updated',)
    fields = ('customer', 'balance', 'last_updated')

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('customer')


class MillingTransactionInline(admin.TabularInline):
    """Inline for MillingTransaction in CustomerAccount admin"""
    model = MillingTransaction
    extra = 0
    readonly_fields = ('amount', 'transaction_type', 'reference', 'created_at', 'created_by')
    fields = ('transaction_type', 'amount', 'reference', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MillingTransaction)
class MillingTransactionAdmin(admin.ModelAdmin):
    """Admin configuration for MillingTransaction model"""
    list_display = ('account', 'transaction_type', 'amount', 'reference', 'created_at', 'created_by')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('account__customer__id', 'account__customer__name', 'reference')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Transaction Details', {
            'fields': ('account', 'amount', 'transaction_type', 'reference')
        }),
        ('Related Process', {
            'fields': ('milling_process',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('account__customer', 'created_by', 'milling_process')

    def save_model(self, request, obj, form, change):
        """Automatically set created_by to current user when creating new transaction"""
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# Optional: Customize the admin site appearance
admin.site.site_header = "GPC Milling System Administration"
admin.site.site_title = "GPC Milling System"
admin.site.index_title = "Welcome to GPC Milling System Admin"