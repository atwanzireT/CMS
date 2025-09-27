# forms.py
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Optional
from django import forms
from .models import ExpenseRequest

# ---------------- UI helpers (dark-mode aware Tailwind) ----------------

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

UG_COUNTRY_CODE = "+256"

def normalize_msisdn(raw: str) -> str:
    s = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == "+").strip()
    if not s:
        return s
    if s.startswith("+"):
        return s
    if s.startswith("0") and len(s) >= 10:
        return UG_COUNTRY_CODE + s[1:]
    if s.startswith("256"):
        return "+" + s
    if s.isdigit() and 9 <= len(s) <= 15:
        return "+" + s
    return raw


class ExpenseRequestForm(forms.ModelForm):
    class Meta:
        model = ExpenseRequest
        fields = [
            "expense_type",
            "amount",
            "phone_msisdn",
            "business_reason",
            "priority",
            "payment_method",
        ]
        widgets = {
            "expense_type": forms.Select(),
            "amount": forms.NumberInput(attrs={"min": "2000", "step": "1", "inputmode": "decimal"}),
            "phone_msisdn": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel-national"}),
            "business_reason": forms.Textarea(attrs={"rows": 3}),
            "priority": forms.Select(),
            "payment_method": forms.Select(),
        }
        labels = {
            "expense_type": "Expense Type *",
            "amount": "Amount (UGX) *",
            "phone_msisdn": "Phone Number for Payment *",
            "business_reason": "Business Reason *",
            "priority": "Priority",
            "payment_method": "Payment Method",
        }
        help_texts = {
            "amount": "Minimum 2,000 UGX. Enter digits only (decimals allowed).",
            "phone_msisdn": "Enter a local number (e.g., 0700123456) or E.164 (e.g., +256700123456).",
            "business_reason": "Explain why this expense is necessary for work.",
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Optional in UI
        self.fields["priority"].required = False
        self.fields["payment_method"].required = False

        # ----- “Select …” prompts for <select> fields (visible first option) -----
        # Insert an empty choice at the top so the UI shows a prompt-like option.
        for name, prompt in (
            ("expense_type", "— Select expense type —"),
            ("priority", "— Priority (default: Normal) —"),
            ("payment_method", "— Payment method (default: Cash) —"),
        ):
            field = self.fields[name]
            choices = list(field.choices)
            if choices and choices[0][0] != "":
                field.choices = [("", prompt)] + choices


        # Sensible defaults on empty forms
        if not self.initial.get("priority"):
            self.initial["priority"] = ExpenseRequest.Priority.NORMAL
        if not self.initial.get("payment_method"):
            self.initial["payment_method"] = ExpenseRequest.PaymentMethod.CASH

        # Apply Tailwind classes (with dark variants)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("aria-describedby", f"{name}-help")
            field.widget.attrs.setdefault("id", f"id_{name}")

            if isinstance(field.widget, (forms.TextInput, forms.NumberInput)):
                _merge_class(field.widget, BASE_INPUT)
            elif isinstance(field.widget, forms.Textarea):
                _merge_class(field.widget, BASE_INPUT + " resize-y")
            elif isinstance(field.widget, forms.Select):
                _merge_class(field.widget, BASE_INPUT + " pr-10 appearance-none bg-no-repeat")

            # Store label/help classes for templates (if you read them)
            field.widget.attrs["data-label-class"] = LABEL
            field.widget.attrs["data-help-class"] = HELP
            field.widget.attrs["data-error-class"] = ERROR_TXT

        # Autofocus the first field for faster entry
        self.fields["expense_type"].widget.attrs.setdefault("autofocus", "autofocus")

        # If re-rendering with errors, swap error styles for invalid fields
        for name in self.errors:
            w = self.fields[name].widget
            w.attrs["class"] = w.attrs["class"].replace(BASE_INPUT, ERROR_INPUT)

    # ---------------- Cleaners ----------------

    def clean_amount(self) -> Decimal:
        raw = self.cleaned_data.get("amount")
        if raw is None:
            raise forms.ValidationError("Amount is required.")
        try:
            amt = Decimal(raw)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError("Enter a valid number for amount.")
        if amt < Decimal("2000"):
            raise forms.ValidationError("Minimum amount is UGX 2,000.")
        if amt.as_tuple().exponent < -2:
            raise forms.ValidationError("Use at most 2 decimal places.")
        return amt

    def clean_phone_msisdn(self) -> str:
        raw = self.cleaned_data.get("phone_msisdn", "")
        norm = normalize_msisdn(raw)
        digits = "".join(ch for ch in norm if ch.isdigit())
        if len(digits) < 9 or len(digits) > 15:
            raise forms.ValidationError("Enter a valid phone number (9–15 digits).")
        return norm

    def clean_business_reason(self) -> str:
        txt = (self.cleaned_data.get("business_reason") or "").strip()
        if len(txt) < 5:
            raise forms.ValidationError("Please provide a short explanation.")
        return txt

    def as_tailwind(self):
        return super().as_p
