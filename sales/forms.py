# forms.py
from __future__ import annotations

from django import forms
from django.forms.widgets import ClearableFileInput
from .models import SaleCustomer, CoffeeSale


# ---------- Minimal widgets ----------
class DateInput(forms.DateInput):
    input_type = "date"

class MoneyNumberInput(forms.NumberInput):
    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("step", "0.01")
        super().__init__(*args, **kwargs)


# ---------- One tiny mixin to style fields ----------
class SimpleStyleMixin:
    """
    Add a single, consistent class to all widgets; no widget-type branching.
    """
    INPUT_CLASS = "mt-1 block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-500"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            cls = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (cls + " " + self.INPUT_CLASS).strip()


# ---------- Optional request->save helper ----------
class RequestUserSaveMixin:
    def __init__(self, *args, request=None, **kwargs):
        self._request = request
        super().__init__(*args, **kwargs)


# ---------- Customer ----------
class SaleCustomerForm(SimpleStyleMixin, forms.ModelForm):
    class Meta:
        model = SaleCustomer
        fields = ["name", "address", "contact", "email", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Al Habibi Trading Co."}),
            "address": forms.TextInput(attrs={"placeholder": "City, Country"}),
            "contact": forms.TextInput(attrs={"placeholder": "+256 7XX XXX XXX"}),
            "email": forms.EmailInput(attrs={"placeholder": "buyer@example.com"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Customer name cannot be empty.")
        return name


# ---------- Coffee Sale ----------
class CoffeeSaleForm(SimpleStyleMixin, RequestUserSaveMixin, forms.ModelForm):
    class Meta:
        model = CoffeeSale
        fields = [
            "customer",
            "sale_date",
            "coffee_type",
            "moisture_pct",
            "quantity_kg",
            "unit_price_ugx",
            "truck_details",
            "driver_details",
            "sales_grn",
            "notes",
        ]
        widgets = {
            "customer": forms.Select(),
            "sale_date": DateInput(),
            "coffee_type": forms.Select(),
            "moisture_pct": MoneyNumberInput(attrs={"placeholder": "e.g. 12.50"}),
            "quantity_kg": MoneyNumberInput(attrs={"placeholder": "e.g. 18500.00"}),
            "unit_price_ugx": MoneyNumberInput(attrs={"placeholder": "e.g. 17500.00"}),
            "truck_details": forms.TextInput(attrs={"placeholder": "e.g. UAX 123A, 10T"}),
            "driver_details": forms.TextInput(attrs={"placeholder": "e.g. John Doe +256 7XX XXX XXX"}),
            "sales_grn": ClearableFileInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "sale_date": "Date of sale (local time).",
            "moisture_pct": "0–100%. Leave blank if unknown.",
        }
        labels = {
            "unit_price_ugx": "Unit Price (UGX/kg)",
            "quantity_kg": "Weight (kg)",
        }

    # Minimal validation (kept from your version)
    def clean_moisture_pct(self):
        v = self.cleaned_data.get("moisture_pct")
        if v is None:
            return v
        if v < 0 or v > 100:
            raise forms.ValidationError("Moisture must be between 0 and 100%.")
        return v

    def clean_quantity_kg(self):
        v = self.cleaned_data.get("quantity_kg")
        if v is None or v <= 0:
            raise forms.ValidationError("Weight (kg) must be greater than 0.")
        return v

    def clean_unit_price_ugx(self):
        v = self.cleaned_data.get("unit_price_ugx")
        if v is None or v <= 0:
            raise forms.ValidationError("Unit price must be greater than 0.")
        return v

    def save(self, commit=True):
        obj: CoffeeSale = super().save(commit=False)
        if obj.pk is None and self._request and self._request.user.is_authenticated:
            obj.recorded_by = self._request.user
        if commit:
            obj.save()
            self.save_m2m()
        return obj
