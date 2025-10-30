# store/forms.py
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django_select2 import forms as s2forms

from .models import (
    Supplier,
    CoffeePurchase,
    SupplierAccount,
    SupplierTransaction,
    EUDRDocumentation,
)

# Optional: you mentioned you import Assessment elsewhere
# from assessment.models import Assessment


# =========================
# Select2 base + widgets
# =========================

class BaseSelect2Widget(s2forms.ModelSelect2Widget):
    """
    Select2 with Tailwind-friendly classes and dark-mode support.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base = (
            "w-full px-4 py-2 border rounded-lg transition focus:outline-none "
            "bg-white text-gray-900 placeholder-gray-400 "
            "border-gray-300 hover:shadow-sm "
            "focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 "
            "dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-400 "
            "dark:border-gray-700"
        )

        self.attrs.update({
            "class": base,
            "data-placeholder": self.get_placeholder(),
            "data-allow-clear": "true",

            # let Select2 containers inherit these classes
            "data-container-css-class": "tw-s2-container dark:tw-s2-container-dark",
            "data-dropdown-css-class": "tw-s2-dropdown dark:tw-s2-dropdown-dark",

            # ergonomics
            "data-minimum-results-for-search": "10",
            "data-width": "100%",
        })

    def get_placeholder(self):
        return "Search or select..."


class SupplierWidget(BaseSelect2Widget):
    model = Supplier
    search_fields = ["name__icontains", "phone__icontains", "id__icontains"]

    def get_placeholder(self):
        return "Search supplier by name, phone or ID..."


class SupplierAccountWidget(BaseSelect2Widget):
    model = SupplierAccount
    search_fields = [
        "supplier__name__icontains",
        "supplier__phone__icontains",
        "supplier__id__icontains",
    ]

    def get_placeholder(self):
        return "Search supplier account by supplier..."


class PurchaseWidget(BaseSelect2Widget):
    model = CoffeePurchase
    search_fields = [
        "supplier__name__icontains",
        "supplier__id__icontains",
        "notes__icontains",
    ]

    def get_placeholder(self):
        return "Search purchase by supplier or note..."


# =========================
# Tailwind mixin
# =========================

class EnhancedTailwindFormMixin:
    """
    Adds modern Tailwind styling with explicit dark-mode variants.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_styling()
        self.setup_fields()

    def base_classes(self, field_name: str) -> str:
        base = (
            "w-full px-4 py-2 border rounded-lg transition "
            "focus:outline-none "
            "bg-white text-gray-900 placeholder-gray-400 "
            "border-gray-300 hover:shadow-sm "
            "focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 "
            "dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-400 "
            "dark:border-gray-700"
        )
        if field_name in self.errors:
            base += (
                " border-rose-400 focus:ring-rose-500 focus:border-rose-500 "
                "bg-rose-50 dark:bg-rose-950/40"
            )
        return base

    def apply_tailwind_styling(self):
        for name, field in self.fields.items():
            # Skip Select2 — it's styled via BaseSelect2Widget
            if isinstance(field.widget, (s2forms.Select2Widget, s2forms.Select2MultipleWidget)):
                continue

            base = self.base_classes(name)

            if field.required:
                base += " ring-1 ring-emerald-50 dark:ring-emerald-900/20"

            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    "class": (
                        "h-5 w-5 rounded border-gray-300 text-emerald-600 "
                        "focus:ring-2 focus:ring-emerald-500 "
                        "dark:bg-gray-900 dark:border-gray-700"
                    )
                })
                continue

            if isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs.update({
                    "class": (
                        "text-emerald-600 bg-white border-gray-300 "
                        "focus:ring-emerald-500 dark:bg-gray-900 dark:border-gray-700"
                    )
                })
                continue

            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    "class": f"{base} pr-10 cursor-pointer appearance-none",
                })
                continue

            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    "class": f"{base} min-h-[100px] resize-y",
                    "rows": field.widget.attrs.get("rows", 4),
                })
                continue

            if isinstance(field.widget, (forms.DateInput, forms.DateTimeInput)):
                field.widget.attrs.update({
                    "class": f"{base} cursor-pointer",
                    "autocomplete": "off",
                })
                continue

            if isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({
                    "class": f"{base} text-right font-mono",
                    "autocomplete": "off",
                    "inputmode": "decimal",
                })
                continue

            if isinstance(field.widget, forms.FileInput):
                field.widget.attrs.update({
                    "class": (
                        "w-full px-4 py-2 border rounded-lg "
                        "border-gray-300 bg-white text-gray-900 "
                        "dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 "
                        "file:text-sm file:font-medium file:bg-emerald-50 file:text-emerald-700 "
                        "hover:file:bg-emerald-100 file:cursor-pointer"
                    )
                })
                continue

            # Default text-like inputs
            field.widget.attrs.update({
                "class": base,
                "autocomplete": "off",
            })

    def setup_fields(self):
        """Hook for child forms."""
        pass


# =========================
# SupplierForm
# =========================

class SupplierForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Supplier
        fields = ["name", "phone", "email", "address"]
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": "255", "placeholder": "Acme Coffee Ltd"}),
            "phone": forms.TextInput(attrs={"maxlength": "20", "placeholder": "+256 7XX XXX XXX"}),
            "email": forms.EmailInput(attrs={"placeholder": "contact@acmecoffee.com"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Street • City • Country"}),
        }

    def setup_fields(self):
        self.fields["name"].help_text = "Official supplier/company name"
        self.fields["phone"].help_text = "Primary contact number"
        self.fields["email"].help_text = "Business email address"
        self.fields["address"].help_text = "Physical address details"

    def save(self, commit=True):
        obj = super().save(commit=False)
        # If you want to stamp created_by on create from forms/views (admin already handles):
        if not self.instance.pk and self.user and hasattr(obj, "created_by") and obj.created_by_id is None:
            obj.created_by = self.user
        if commit:
            obj.save()
        return obj


# =========================
# CoffeePurchaseForm
# =========================

class CoffeePurchaseForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Set step/min dynamically from field type (int vs decimal)
        q_field = self._meta.model._meta.get_field("quantity")
        step = "0.01" if getattr(q_field, "decimal_places", 0) else "1"
        min_value = "0.01" if step == "0.01" else "1"

        self.fields["quantity"].widget.attrs.update({
            "step": step,
            "min": min_value,
            "placeholder": "e.g. 500",
        })
        self.fields["bags"].widget.attrs.update({
            "min": "0",
            "step": "1",
            "placeholder": "e.g. 10",
        })

        # nice defaults/help
        self.fields["quantity"].help_text = "Weight in kilograms"
        self.fields["bags"].help_text = "Number of bags (if applicable)"
        self.fields["notes"].help_text = "Additional notes or remarks"

        # Prefer Arabica initially (matches your model default)
        if not self.instance.pk:
            self.fields["coffee_type"].initial = self._meta.model.ARABICA

    class Meta:
        model = CoffeePurchase
        fields = [
            "supplier",
            "coffee_category",
            "coffee_type",
            "quantity",
            "bags",
            "assessment_needed",
            "notes",
            "purchase_date",
            "delivery_date",
        ]
        widgets = {
            # IMPORTANT: widget instances, not classes
            "supplier": SupplierWidget(),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Any special notes/remarks…"}),
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        purchase_date = cleaned.get("purchase_date")
        delivery_date = cleaned.get("delivery_date")
        quantity = cleaned.get("quantity")
        bags = cleaned.get("bags")

        # Dates sanity
        if purchase_date and delivery_date and delivery_date < purchase_date:
            raise ValidationError("Delivery date cannot be before the purchase date.")

        # Quantity/Bags sanity (form-level, model validation also runs)
        if quantity is not None:
            if isinstance(quantity, (int, float, Decimal)):
                if quantity <= 0:
                    raise ValidationError("Quantity must be greater than zero.")
        if bags is not None and bags < 0:
            raise ValidationError("Bags cannot be negative.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        # Stamp recorded_by when saving from a normal view
        if not self.instance.pk and self.user and hasattr(obj, "recorded_by") and obj.recorded_by_id is None:
            obj.recorded_by = self.user
        if commit:
            obj.save()
        return obj


# =========================
# SupplierTransactionForm
# =========================

class SupplierTransactionForm(EnhancedTailwindFormMixin, forms.ModelForm):
    """
    For creating a debit (we owe more) or credit (payment made to supplier).
    """
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Number input ergonomics
        self.fields["amount"].widget = forms.NumberInput()
        self.fields["amount"].widget.attrs.update({
            "step": "0.01",
            "min": "0.01",
            "placeholder": "e.g. 150000.00",
            "class": self.base_classes("amount") + " text-right font-mono",
        })

        # Optional reference placeholder
        self.fields["reference"].widget.attrs.update({
            "placeholder": "Optional external ref (e.g., MM/INV/1234)"
        })

    class Meta:
        model = SupplierTransaction
        fields = [
            "account",
            "transaction_type",
            "amount",
            "reference",
            "purchase",
            "notes",
        ]
        widgets = {
            "account": SupplierAccountWidget(),
            "purchase": PurchaseWidget(),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional note…"}),
        }

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        if amount is not None and amount <= 0:
            raise ValidationError("Amount must be greater than zero.")

        # Optional: enforce that credit transactions should usually have a reference
        # if cleaned.get("transaction_type") == SupplierTransaction.CREDIT and not cleaned.get("reference"):
        #     raise ValidationError("Please provide a payment reference for credit transactions.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not self.instance.pk and self.user and hasattr(obj, "created_by") and obj.created_by_id is None:
            obj.created_by = self.user
        if commit:
            obj.save()
        return obj


# =========================
# EUDRDocumentationForm
# =========================

class EUDRDocumentationForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Number input ergonomics
        self.fields["total_kilograms"].widget = forms.NumberInput()
        self.fields["total_kilograms"].widget.attrs.update({
            "step": "0.01",
            "min": "0.00",
            "placeholder": "e.g. 1250.50",
            "class": self.base_classes("total_kilograms") + " text-right font-mono",
        })

        # Make batch_number clearly read-only in the form (it's auto-set in model)
        if "batch_number" in self.fields:
            self.fields["batch_number"].disabled = True

        # Helpful placeholders
        self.fields["supplier_name"].widget.attrs.update({
            "placeholder": "e.g. John Bosco / GPC-SUP0001"
        })
        self.fields["documentation_notes"].widget.attrs.update({
            "placeholder": "Any remarks (traceability, geo-refs, etc.)"
        })

    class Meta:
        model = EUDRDocumentation
        fields = [
            "coffee_type",
            "total_kilograms",
            "supplier_name",
            "batch_number", 
            "documentation_receipts",
            "documentation_notes",
        ]
        widgets = {
            # ArrayField will render as a comma-separated input by default in admin;
            # in custom templates you can provide add/remove JS. Keeping default here.
            "documentation_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_total_kilograms(self):
        kg = self.cleaned_data.get("total_kilograms")
        if kg is not None and kg < 0:
            raise ValidationError("Total kilograms cannot be negative.")
        return kg
