from django import forms
from django_select2 import forms as s2forms
from .models import *
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


class SupplierForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)

    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'email', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'maxlength': '255'}),
            'phone': forms.TextInput(attrs={'maxlength': '20'}),
            'email': forms.EmailInput(),
            'address': forms.Textarea(attrs={'rows': 3}),
        }
    
    def setup_fields(self):
        self.fields['name'].help_text = "Official supplier/company name"
        self.fields['phone'].help_text = "Primary contact number"
        self.fields['email'].help_text = "Business email address"
        self.fields['address'].help_text = "Physical address details"

class CoffeePurchaseForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)

        
    class Meta:
        model = CoffeePurchase
        fields = [
            'supplier', 'coffee_category', 'coffee_type', 'quantity', 'bags', 'notes', 'purchase_date', 'delivery_date'
        ]
        widgets = {
            'supplier': SupplierWidget,
            'notes': forms.Textarea(attrs={'rows': 3}),
            'delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def setup_fields(self):
        self.fields['quantity'].widget.attrs.update({
            'step': '1',
            'min': '1'
        })
        self.fields['bags'].widget.attrs.update({
            'min': '0'
        })
        
        self.fields['quantity'].help_text = "Weight in kilograms"
        self.fields['bags'].help_text = "Number of bags (if applicable)"
        self.fields['notes'].help_text = "Additional notes or remarks"
        self.fields['coffee_type'].initial = CoffeePurchase.ARABICA


class CoffeeSaleForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)

    class Meta:
        model = CoffeeSale
        fields = [
            'customer', 'customer_address', 'customer_contact',
            'coffee_category', 'coffee_type', 'quantity', 'unit_price',
            'sale_date', 'notes'
        ]
        widgets = {
            'customer': forms.TextInput(attrs={'maxlength': '255'}),
            'customer_address': forms.TextInput(attrs={'maxlength': '150'}),
            'customer_contact': forms.TextInput(attrs={'maxlength': '150'}),
            'quantity': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'sale_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def setup_fields(self):
        self.fields['quantity'].help_text = "Weight in kilograms (min: 0.01kg)"
        self.fields['unit_price'].help_text = "Price per kilogram in UGX"
        self.fields['customer_contact'].help_text = "Phone or email for follow-up"
        self.fields['coffee_type'].initial = CoffeeSale.ARABICA

