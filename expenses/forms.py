from django import forms
from .models import ExpenseRequest

# Reusable helpers (now dark-mode aware)
BASE_INPUT = (
    "block w-full rounded-xl border border-gray-300 dark:border-gray-700 "
    "bg-white dark:bg-gray-950 "
    "px-4 py-2.5 text-gray-900 dark:text-gray-100 "
    "placeholder-gray-400 dark:placeholder-gray-500 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 "
    "focus:border-indigo-500 dark:focus:border-indigo-400 "
    "focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900 "
    "disabled:opacity-60"
)
ERROR_INPUT = (
    "block w-full rounded-xl border border-rose-400 dark:border-rose-500 "
    "bg-white dark:bg-gray-950 "
    "px-4 py-2.5 text-gray-900 dark:text-gray-100 "
    "placeholder-gray-400 dark:placeholder-gray-500 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-rose-500 dark:focus:ring-rose-400 "
    "focus:border-rose-500 dark:focus:border-rose-400 "
    "focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900"
)
LABEL = "mb-1.5 block text-sm font-medium text-gray-800 dark:text-gray-200"
HELP = "mt-1 text-xs text-gray-500 dark:text-gray-400"
ERROR_TXT = "mt-1 text-xs text-rose-600 dark:text-rose-400"

def _merge_class(widget: forms.Widget, cls: str):
    widget.attrs["class"] = (widget.attrs.get("class", "") + " " + cls).strip()
    return widget

class ExpenseRequestForm(forms.ModelForm):
    class Meta:
        model = ExpenseRequest
        fields = [
            "expense_type",
            "amount",
            "phone_msisdn",
            "description",
            "business_reason",
            "priority",
            "payment_method",
        ]
        widgets = {
            "expense_type": forms.Select(attrs={"placeholder": "Select expense type"}),
            "amount": forms.NumberInput(attrs={"min": "2000", "step": "1", "inputmode": "numeric"}),
            "phone_msisdn": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel-national"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "business_reason": forms.Textarea(attrs={"rows": 2}),
            "priority": forms.Select(),
            "payment_method": forms.Select(),
        }
        labels = {
            "expense_type": "Expense Type *",
            "amount": "Amount (UGX) * (Minimum: 2,000)",
            "phone_msisdn": "Phone Number for Payment *",
            "description": "Description *",
            "business_reason": "Business Reason *",
            "priority": "Priority",
            "payment_method": "Payment Method",
        }
        help_texts = {
            "phone_msisdn": "Enter the phone number where you want to receive the money via mobile money.",
            "business_reason": "Explain why this expense is necessary for work.",
        }

    def __init__(self, *args, **kwargs):
        kwargs_user = kwargs.pop("user", None)  # reserved for future use
        super().__init__(*args, **kwargs)

        # Optional in your UI
        self.fields["priority"].required = False
        self.fields["payment_method"].required = False

        # Placeholders
        self.fields["amount"].widget.attrs.setdefault("placeholder", "Enter amount (min. 2,000)")
        self.fields["phone_msisdn"].widget.attrs.setdefault("placeholder", "e.g., 0700123456")

        # Apply Tailwind classes (with dark variants)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("aria-describedby", f"{name}-help")
            field.widget.attrs.setdefault("id", f"id_{name}")

            # Base classes by widget type
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput)):
                _merge_class(field.widget, BASE_INPUT)
            elif isinstance(field.widget, forms.Textarea):
                _merge_class(field.widget, BASE_INPUT + " resize-y")
            elif isinstance(field.widget, forms.Select):
                # room for default chevron; add appearance-none for consistent look
                _merge_class(field.widget, BASE_INPUT + " pr-10 appearance-none bg-no-repeat")

            # Error style swap
            if self.errors.get(name):
                field.widget.attrs["class"] = field.widget.attrs["class"].replace(BASE_INPUT, ERROR_INPUT)

            # Store label/help classes for templates (if you read them)
            field.widget.attrs["data-label-class"] = LABEL
            field.widget.attrs["data-help-class"] = HELP
            field.widget.attrs["data-error-class"] = ERROR_TXT

    def as_tailwind(self):
        return super().as_p()
