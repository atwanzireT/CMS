# forms.py
from django import forms
from django_select2 import forms as s2forms
from .models import Customer, MillingProcess, CustomerAccount
# from assessment.models import Assessment  # (keep if you need it)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _merge_class(widget, extra):
    base = widget.attrs.get("class", "").strip()
    widget.attrs["class"] = (base + " " + extra).strip()

def _set(widget, **attrs):
    for k, v in attrs.items():
        widget.attrs[k] = v

# ──────────────────────────────────────────────────────────────────────────────
# Select2 widgets (styled for light/dark)
# ──────────────────────────────────────────────────────────────────────────────
class BaseSelect2Widget(s2forms.ModelSelect2Widget):
    """Select2 with Tailwind-friendly classes and dark-mode support."""
    search_fields: list[str] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _set(
            self,
            **{
                # Select2 picks width from style unless configured.
                "style": "width:100%;",
                "data-placeholder": self.get_placeholder(),
                "data-allow-clear": "true",
                "data-width": "style",
            }
        )
        # Base input look – rely on Select2’s generated container; this still
        # improves the underlying <select> so SSR looks fine before JS loads.
        _merge_class(
            self,
            "w-full px-3 py-2 rounded-lg border transition "
            "bg-white text-slate-900 border-slate-300 "
            "hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
            "dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700 "
            "dark:focus:ring-primary-400 dark:focus:border-primary-400"
        )

    def get_placeholder(self):
        return "Search or select..."

class CustomerWidget(BaseSelect2Widget):
    search_fields = ["name__icontains", "phone__icontains", "id__icontains"]
    def get_placeholder(self): return "Search customer by name, phone, or ID…"

class SupplierWidget(BaseSelect2Widget):
    search_fields = ["name__icontains", "phone__icontains", "id__icontains"]
    def get_placeholder(self): return "Search supplier by name, phone, or ID…"

class CustomerAccountWidget(BaseSelect2Widget):
    search_fields = ["customer__name__icontains", "customer__phone__icontains"]
    def get_placeholder(self): return "Search by customer name or phone…"

class MillingProcessWidget(BaseSelect2Widget):
    search_fields = ["customer__name__icontains", "id__icontains"]
    def get_placeholder(self): return "Search milling process…"

class CoffeeInventoryWidget(BaseSelect2Widget):
    search_fields = ["coffee_type__icontains", "coffee_category__icontains"]
    def get_placeholder(self): return "Search inventory by type or category…"

# ──────────────────────────────────────────────────────────────────────────────
# Tailwind form mixin (dark/light aware)
# ──────────────────────────────────────────────────────────────────────────────
class EnhancedTailwindFormMixin:
    """
    Adds consistent Tailwind styling (light + dark) to all widgets,
    with accessible error states and better focus/hovers.
    """

    base_input = (
        "w-full px-3 py-2 rounded-lg border transition "
        "bg-white text-slate-900 placeholder-slate-400 border-slate-300 "
        "hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
        "disabled:opacity-60 disabled:cursor-not-allowed "
        "dark:bg-slate-900 dark:text-slate-100 dark:placeholder-slate-500 dark:border-slate-700 "
        "dark:focus:ring-primary-400 dark:focus:border-primary-400"
    )

    base_file = (
        "block w-full text-sm text-slate-900 dark:text-slate-100 "
        "file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 "
        "file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100 "
        "dark:file:bg-slate-800 dark:file:text-slate-200 dark:hover:file:bg-slate-700 "
        "border rounded-lg border-slate-300 dark:border-slate-700 "
        "focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
        "dark:focus:ring-primary-400 dark:focus:border-primary-400"
    )

    base_checkbox = (
        "h-5 w-5 rounded border-slate-300 text-primary-600 "
        "focus:ring-2 focus:ring-primary-500 focus:ring-offset-0 "
        "dark:border-slate-600 dark:bg-slate-900"
    )

    base_radio = (
        "text-primary-600 focus:ring-2 focus:ring-primary-500 "
        "dark:bg-slate-900 dark:border-slate-600"
    )

    base_select = (
        "appearance-none pr-10 cursor-pointer "  # space for chevron
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional nicer label suffix
        if hasattr(self, "label_suffix"):
            self.label_suffix = ""
        self._apply_tailwind()
        self.setup_fields()

    def _apply_tailwind(self):
        for name, field in self.fields.items():
            widget = field.widget

            # Skip Select2 — already styled above.
            if isinstance(widget, (s2forms.Select2Widget, s2forms.Select2MultipleWidget, BaseSelect2Widget)):
                continue

            # Input field classes
            if isinstance(widget, forms.FileInput):
                _merge_class(widget, self.base_file)
            elif isinstance(widget, forms.CheckboxInput):
                _merge_class(widget, self.base_checkbox)
            elif isinstance(widget, forms.RadioSelect):
                _merge_class(widget, self.base_radio)
            else:
                # Inputs / Textareas / Date/Time / Number / Select
                classes = self.base_input
                if isinstance(widget, forms.Select):
                    classes = f"{classes} {self.base_select}"
                if isinstance(widget, forms.NumberInput):
                    _set(widget, inputmode="decimal")
                    classes = f"{classes} text-right font-mono"
                if isinstance(widget, (forms.DateInput, forms.DateTimeInput)):
                    _set(widget, autocomplete="off")
                    classes = f"{classes} cursor-pointer"

                # Error state (aria + red styles)
                if name in self.errors:
                    classes += (
                        " border-rose-500 focus:ring-rose-500 focus:border-rose-500 "
                        "dark:border-rose-500 dark:focus:ring-rose-400 dark:focus:border-rose-400"
                    )
                    _set(widget, **{"aria-invalid": "true"})

                # Required hint (subtle)
                if field.required:
                    classes += " ring-1 ring-primary-100 dark:ring-primary-900/30"

                _merge_class(widget, classes)

            # Common accessibility niceties
            _set(widget, **{"aria-required": "true" if field.required else "false"})

    def setup_fields(self):
        """Hook for per-form tweaks (placeholders/help_text)."""
        pass

# ──────────────────────────────────────────────────────────────────────────────
# Model forms
# ──────────────────────────────────────────────────────────────────────────────
class CustomerForm(EnhancedTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Full legal name"}),
            "phone": forms.TextInput(attrs={"placeholder": "+256XXXXXXXXX"}),
        }

    def setup_fields(self):
        self.fields["name"].help_text = "Customer’s full legal name."
        self.fields["phone"].help_text = "Unique phone number (with country code)."

class MillingProcessForm(EnhancedTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = MillingProcess
        fields = ["customer", "hulled_weight", "milling_rate", "status", "notes"]
        widgets = {
            "customer": CustomerWidget,
            "hulled_weight": forms.NumberInput(attrs={"step": "1", "min": "1", "placeholder": "e.g. 800"}),
            "milling_rate": forms.NumberInput(attrs={"step": "1", "min": "0", "placeholder": "UGX/kg"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes…"}),
        }

    def setup_fields(self):
        self.fields["hulled_weight"].help_text = "Weight after milling (kg)."
        self.fields["milling_rate"].help_text = "Rate per kg (UGX)."
        self.fields["notes"].help_text = "Optional process notes."

class CustomerAccountForm(EnhancedTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerAccount
        fields = ["customer", "balance"]
        widgets = {
            "customer": CustomerWidget,
            "balance": forms.NumberInput(attrs={"step": "0.01", "placeholder": "0.00"}),
        }

    def setup_fields(self):
        self.fields["balance"].help_text = "Initial account balance (UGX)."
