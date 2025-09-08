from django import forms
from django_select2 import forms as s2forms
from .models import (
    Customer, MillingProcess, CustomerAccount, MillingTransaction
)
from assessment.models import Assessment
from django.core.exceptions import ValidationError

# ========== CUSTOM WIDGETS ==========
class BaseSelect2Widget(s2forms.ModelSelect2Widget):
    """Base Select2 widget with consistent styling"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs.update({
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 ease-in-out bg-white shadow-sm hover:shadow-md',
            'data-placeholder': self.get_placeholder(),
            'data-allow-clear': 'true'
        })

    def get_placeholder(self):
        return "Search or select..."

class CustomerWidget(BaseSelect2Widget):
    search_fields = ["name__icontains", "phone__icontains", "id__icontains"]
    def get_placeholder(self):
        return "Search customer by name, phone or ID..."

class SupplierWidget(BaseSelect2Widget):
    search_fields = ["name__icontains", "phone__icontains", "id__icontains"]
    def get_placeholder(self):
        return "Search supplier by name, phone or ID..."

class CustomerAccountWidget(BaseSelect2Widget):
    search_fields = ["customer__name__icontains", "customer__phone__icontains"]
    def get_placeholder(self):
        return "Search by customer name or phone..."

class MillingProcessWidget(BaseSelect2Widget):
    search_fields = ["customer__name__icontains", "id__icontains"]
    def get_placeholder(self):
        return "Search milling process by customer or ID..."

class CoffeeInventoryWidget(BaseSelect2Widget):
    search_fields = ["coffee_type__icontains", "coffee_category__icontains"]
    def get_placeholder(self):
        return "Search inventory by coffee type or category..."

# ========== FORM MIXINS ==========
class EnhancedTailwindFormMixin:
    """Enhanced form mixin with modern Tailwind CSS styling"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styling()
        self.setup_fields()
    
    def apply_tailwind_styling(self):
        """Apply consistent Tailwind CSS styling to all form fields"""
        for field_name, field in self.fields.items():
            # Skip Select2 widgets as they have their own styling
            if isinstance(field.widget, (s2forms.Select2Widget, s2forms.Select2MultipleWidget)):
                continue
            
            # Base classes for all inputs
            base_classes = (
                'w-full px-4 py-3 border rounded-lg transition-all duration-200 ease-in-out '
                'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                'bg-white shadow-sm hover:shadow-md placeholder-gray-400'
            )
            
            # Error state styling
            if field_name in self.errors:
                base_classes += ' border-red-500 focus:ring-red-500 focus:border-red-500 bg-red-50'
            else:
                base_classes += ' border-gray-300'
            
            # Required field styling
            if field.required:
                base_classes += ' ring-1 ring-blue-100'
            
            # Widget-specific styling
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': (
                        'h-5 w-5 text-blue-600 bg-white border-gray-300 rounded '
                        'focus:ring-blue-500 focus:ring-2 transition-all duration-200 '
                        'hover:bg-blue-50 cursor-pointer'
                    )
                })
            elif isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs.update({
                    'class': 'text-blue-600 bg-white border-gray-300 focus:ring-blue-500'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': f'{base_classes} pr-10 cursor-pointer appearance-none'
                })
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    'class': f'{base_classes} resize-none min-h-[100px]',
                    'rows': field.widget.attrs.get('rows', 4)
                })
            elif isinstance(field.widget, (forms.DateInput, forms.DateTimeInput)):
                field.widget.attrs.update({
                    'class': f'{base_classes} cursor-pointer',
                    'autocomplete': 'off'
                })
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({
                    'class': f'{base_classes} text-right font-mono',
                    'autocomplete': 'off'
                })
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs.update({
                    'class': (
                        'w-full px-4 py-3 border border-gray-300 rounded-lg '
                        'file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 '
                        'file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 '
                        'hover:file:bg-blue-100 file:cursor-pointer cursor-pointer'
                    )
                })
            else:
                field.widget.attrs.update({
                    'class': f'{base_classes}',
                    'autocomplete': 'off'
                })
    
    def setup_fields(self):
        """Setup field-specific attributes and help texts"""
        pass

# ========== MODEL FORMS ==========
class CustomerForm(EnhancedTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Full legal name'}),
            'phone': forms.TextInput(attrs={'placeholder': '+256XXXXXXXXX'}),
        }
    
    def setup_fields(self):
        self.fields['name'].help_text = "Customer's full legal name"
        self.fields['phone'].help_text = "Unique phone number with country code"

class MillingProcessForm(EnhancedTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = MillingProcess
        fields = ['customer', 'hulled_weight', 'milling_rate', 'status', 'notes']
        widgets = {
            'customer': CustomerWidget,
            'hulled_weight': forms.NumberInput(attrs={'step': '0.01', 'min': '0.1'}),
            'milling_rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def setup_fields(self):
        self.fields['hulled_weight'].help_text = "Weight after milling (kg)"
        self.fields['milling_rate'].help_text = "Rate per kg (UGX)"
        self.fields['notes'].help_text = "Optional process notes"

class CustomerAccountForm(EnhancedTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerAccount
        fields = ['customer', 'balance']
        widgets = {
            'customer': CustomerWidget,
            'balance': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def setup_fields(self):
        self.fields['balance'].help_text = "Initial account balance in UGX"
