from django import forms
from .models import Assessment


class TailwindFormMixin:
    """
    Tailwind styling with explicit dark-mode variants.
    Does NOT call self.errors (to avoid triggering full_clean during __init__).
    Subclasses should call self._apply_tailwind() after finishing their own init.
    """

    BASE = (
        "block w-full px-3 py-2 rounded-lg border transition "
        "bg-white text-gray-900 placeholder-gray-400 border-gray-300 "
        "focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 "
        "dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-400 dark:border-gray-700"
    )
    ERROR = (
        " border-rose-400 focus:ring-rose-500 focus:border-rose-500 "
        "bg-rose-50 dark:bg-rose-950/40"
    )

    def __init__(self, *args, **kwargs):
        # Important: DO NOT style here (subclass will do it after it’s done).
        super().__init__(*args, **kwargs)

    def _strip_placeholder(self, widget: forms.Widget):
        if hasattr(widget, "attrs"):
            widget.attrs.pop("placeholder", None)

    def _apply_tailwind(self):
        # Use internal _errors if already computed; never touch self.errors here.
        current_errors = getattr(self, "_errors", {}) or {}

        for name, field in self.fields.items():
            widget = field.widget

            # Base classes
            classes = self.BASE

            # Add error classes ONLY if errors were already computed elsewhere
            if name in current_errors:
                classes += self.ERROR

            # Required hint ring
            if field.required:
                classes += " ring-1 ring-emerald-50 dark:ring-emerald-900/20"

            # Remove placeholders globally as requested
            self._strip_placeholder(widget)

            # Widget-specific styling
            if isinstance(widget, forms.NumberInput):
                widget.attrs.setdefault("class", f"{classes} text-right font-mono")
                widget.attrs.setdefault("inputmode", "decimal")
                widget.attrs.setdefault("autocomplete", "off")
                continue

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", f"{classes} min-h-[100px] resize-y")
                widget.attrs.setdefault("rows", 4)
                widget.attrs.setdefault("autocomplete", "off")
                continue

            if isinstance(widget, (forms.DateInput, forms.DateTimeInput)):
                widget.attrs.setdefault("class", f"{classes} cursor-pointer")
                widget.attrs.setdefault("autocomplete", "off")
                continue

            if isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", f"{classes} pr-10 cursor-pointer appearance-none")
                continue

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault(
                    "class",
                    "h-5 w-5 rounded border-gray-300 text-emerald-600 "
                    "focus:ring-2 focus:ring-emerald-500 dark:bg-gray-900 dark:border-gray-700"
                )
                continue

            # Default inputs
            widget.attrs.setdefault("class", classes)
            widget.attrs.setdefault("autocomplete", "off")


class AssessmentForm(TailwindFormMixin, forms.ModelForm):
    """
    - Sets instance.coffee safely before any validation is attempted
    - Calls _apply_tailwind AFTER binding coffee to avoid early full_clean
    - Adds numeric steps/min/max as before
    """

    def __init__(self, *args, **kwargs):
        self.coffee_purchase = kwargs.pop("coffee_purchase", None)
        super().__init__(*args, **kwargs)

        # Bind the coffee BEFORE any validation ever runs
        if self.coffee_purchase and not self.instance.pk:
            self.instance.coffee = self.coffee_purchase

        # Configure numeric widgets (no placeholders)
        percent_fields = [
            "moisture_content", "group1_defects", "group2_defects",
            "below_screen_12", "pods", "husks", "stones", "fm",
        ]
        money_fields = ["ref_price", "offered_price"]

        for name, field in self.fields.items():
            widget = field.widget
            if hasattr(widget, "attrs"):
                widget.attrs.pop("placeholder", None)

            if isinstance(widget, forms.NumberInput):
                widget.attrs.update({"step": "50" if name == "ref_price" else "0.1"})
                if name in percent_fields:
                    widget.attrs.setdefault("min", "0")
                    widget.attrs.setdefault("max", "100")
                if name in money_fields:
                    widget.attrs.setdefault("min", "0")

        # Help text only (kept minimal)
        self.fields["ref_price"].help_text = "Reference price per kg (UGX)."
        self.fields["offered_price"].help_text = "Optional: offered price per kg (UGX)."
        self.fields["discretion"].help_text = "Manual adjustment (can be negative)."
        self.fields["moisture_content"].help_text = "Percentage of moisture (0–100%)."
        self.fields["group1_defects"].help_text = "Group 1 defect % (0–100%)."
        self.fields["group2_defects"].help_text = "Group 2 defect % (0–100%)."
        self.fields["below_screen_12"].help_text = "Beans below screen 12 % (0–100%)."
        self.fields["pods"].help_text = "Pods % (0–100%)."
        self.fields["husks"].help_text = "Husks % (0–100%)."
        self.fields["stones"].help_text = "Stones % (0–100%)."
        self.fields["fm"].help_text = "Foreign matter % (auto from pods+husks+stones)."

        # Now it's safe to style
        self._apply_tailwind()

    class Meta:
        model = Assessment
        fields = [
            "moisture_content", "group1_defects", "group2_defects",
            "below_screen_12", "pods", "husks", "stones", "fm",
            "discretion", "ref_price", "offered_price",
        ]
        widgets = {
            "ref_price": forms.NumberInput(),
            "offered_price": forms.NumberInput(),
            "discretion": forms.NumberInput(),
            "moisture_content": forms.NumberInput(),
            "group1_defects": forms.NumberInput(),
            "group2_defects": forms.NumberInput(),
            "below_screen_12": forms.NumberInput(),
            "pods": forms.NumberInput(),
            "husks": forms.NumberInput(),
            "stones": forms.NumberInput(),
            "fm": forms.NumberInput(),
        }
