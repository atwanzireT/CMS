from django import forms
from django_select2 import forms as s2forms
from .models import Supplier, CoffeePurchase
from assessment.models import Assessment  # (kept because you import it elsewhere)
from django.core.exceptions import ValidationError


# ========== CUSTOM WIDGETS ==========

class BaseSelect2Widget(s2forms.ModelSelect2Widget):
    """
    Select2 with Tailwind-friendly classes and dark-mode support.
    NOTE: Select2 renders its own DOM, so we pass container/dropdown classes
    that you can style via Tailwind utility classes (see notes below).
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

        # Tailwind-like styling on the underlying <select> that Select2 attaches to
        self.attrs.update({
            "class": base,
            "data-placeholder": self.get_placeholder(),
            "data-allow-clear": "true",

            # Select2-specific hooks so the floating container & dropdown can be themed
            # (these go onto the original element and Select2 will copy them)
            "data-container-css-class": "tw-s2-container dark:tw-s2-container-dark",
            "data-dropdown-css-class": "tw-s2-dropdown dark:tw-s2-dropdown-dark",
            # Optional ergonomics:
            "data-minimum-results-for-search": "10",
            "data-width": "100%",
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


# ========== FORM MIXIN WITH DARK/LIGHT SUPPORT ==========

class EnhancedTailwindFormMixin:
    """
    Adds modern Tailwind styling with **explicit dark-mode variants**.
    Works for standard inputs, textareas, selects, dates, numbers, files, etc.
    Select2 widgets skip here (they’re themed via BaseSelect2Widget above).
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
            # Skip Select2 — already styled in BaseSelect2Widget
            if isinstance(field.widget, (s2forms.Select2Widget, s2forms.Select2MultipleWidget)):
                continue

            base = self.base_classes(name)

            # Required: add subtle ring
            if field.required:
                base += " ring-1 ring-emerald-50 dark:ring-emerald-900/20"

            # Widget-specific tweaks
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
        """Override in child form to add help_text, placeholders, etc."""
        pass


# ========== FORMS ==========

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


class CoffeePurchaseForm(EnhancedTailwindFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = CoffeePurchase
        fields = [
            "supplier", "coffee_category", "coffee_type",
            "quantity", "bags", "notes", "purchase_date", "delivery_date",
        ]
        widgets = {
            "supplier": SupplierWidget,
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Any special notes/remarks…"}),
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
        }

    def setup_fields(self):
        self.fields["quantity"].widget.attrs.update({
            "step": "1",
            "min": "1",
            "placeholder": "e.g. 500",
        })
        self.fields["bags"].widget.attrs.update({
            "min": "0",
            "placeholder": "e.g. 10",
        })

        self.fields["quantity"].help_text = "Weight in kilograms"
        self.fields["bags"].help_text = "Number of bags (if applicable)"
        self.fields["notes"].help_text = "Additional notes or remarks"
        self.fields["coffee_type"].initial = CoffeePurchase.ARABICA
