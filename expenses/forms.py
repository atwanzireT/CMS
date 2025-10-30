# expenses/forms.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Tuple, Optional

from django import forms
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import ExpenseRequest, SalaryRequest, Requisition

# ---------------- UI helpers (dark-mode aware Tailwind) ----------------

BASE_INPUT = (
    "block w-full rounded-xl border border-gray-300 dark:border-gray-700 "
    "bg-white dark:bg-gray-950 px-4 py-2.5 "
    "text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 "
    "focus:border-indigo-500 dark:focus:border-indigo-400 "
    "focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900 "
    "disabled:opacity-60"
)
ERROR_INPUT = (
    "block w-full rounded-xl border border-rose-400 dark:border-rose-500 "
    "bg-white dark:bg-gray-950 px-4 py-2.5 "
    "text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-rose-500 dark:focus:ring-rose-400 "
    "focus:border-rose-500 dark:focus:border-rose-400 "
    "focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900"
)
LABEL = "mb-1.5 block text-sm font-medium text-gray-800 dark:text-gray-200"
HELP = "mt-1 text-xs text-gray-500 dark:text-gray-400"
ERROR_TXT = "mt-1 text-xs text-rose-600 dark:text-rose-400"

UG_COUNTRY_CODE = "+256"


def _merge_class(widget: forms.Widget, cls: str):
    widget.attrs["class"] = (widget.attrs.get("class", "") + " " + cls).strip()
    return widget


def normalize_msisdn(raw: str) -> str:
    """
    Normalize phone numbers to E.164 where possible (defaulting to UG).
    - Allow '+' if already present.
    - '0xxxxxxxxx' -> '+256xxxxxxxxx'
    - '256xxxxxxxxx' -> '+256xxxxxxxxx'
    - Raw digits (9–15) -> '+<digits>'
    Otherwise, return raw.
    """
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


def quantize_money(val: Decimal, places: int = 2) -> Decimal:
    q = Decimal(10) ** -places
    return val.quantize(q, rounding=ROUND_HALF_UP)


class TailwindFormMixin:
    """
    - Applies Tailwind classes consistently
    - Provides select prompts via `_add_prompt(field, label)`
    - Swaps error styles on invalid fields
    - `as_tailwind()` renders simple <p>-wrapped fields with labels/help/errors and returns SafeString
    """
    first_autofocus: Optional[str] = None

    def _add_prompt(self, field: forms.Field, label: str):
        """
        Ensure select fields show a friendly first placeholder option.
        If the first choice is an empty option (e.g. '---------'), replace its label.
        Otherwise, prepend a new empty option.
        """
        if not hasattr(field, "choices"):
            return
        choices: Iterable[Tuple[str, str]] = list(getattr(field, "choices", []))
        if not choices:
            return
        if choices[0][0] == "":
            choices[0] = ("", label)
            field.choices = choices
        else:
            field.choices = [("", label)] + choices

    def _apply_tailwind(self):
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("aria-describedby", f"{name}-help")
            field.widget.attrs.setdefault("id", f"id_{name}")

            if isinstance(field.widget, (forms.TextInput, forms.NumberInput)):
                _merge_class(field.widget, BASE_INPUT)
            elif isinstance(field.widget, forms.Textarea):
                _merge_class(field.widget, BASE_INPUT + " resize-y")
            elif isinstance(field.widget, forms.Select):
                _merge_class(field.widget, BASE_INPUT + " pr-10 appearance-none bg-no-repeat")

            field.widget.attrs["data-label-class"] = LABEL
            field.widget.attrs["data-help-class"] = HELP
            field.widget.attrs["data-error-class"] = ERROR_TXT

        # Autofocus convenience
        if self.first_autofocus and self.first_autofocus in self.fields:
            self.fields[self.first_autofocus].widget.attrs.setdefault("autofocus", "autofocus")

        # Swap error classes for invalid fields
        for name in self.errors:
            w = self.fields[name].widget
            w.attrs["class"] = w.attrs.get("class", "").replace(BASE_INPUT, ERROR_INPUT)

    def as_tailwind(self) -> str:
        html = []
        for name, field in self.fields.items():
            bf = self[name]
            label_cls = field.widget.attrs.get("data-label-class", LABEL)
            help_cls = field.widget.attrs.get("data-help-class", HELP)
            err_cls = field.widget.attrs.get("data-error-class", ERROR_TXT)
            label = bf.label_tag(attrs={"class": label_cls})
            help_id = field.widget.attrs.get("aria-describedby")
            help_txt = getattr(field, "help_text", "")
            err_html = ""
            if bf.errors:
                err_html = "".join(f'<div class="{err_cls}">{e}</div>' for e in bf.errors)
            html.append(
                f'<p class="mb-4">{label}{bf}<span id="{help_id}" class="{help_cls}">{help_txt}</span>{err_html}</p>'
            )
        # Return a safe string so templates don't render the raw HTML
        return mark_safe("".join(html))


# -------------------------------------------------------------------
# ExpenseRequest form
# -------------------------------------------------------------------
class ExpenseRequestForm(TailwindFormMixin, forms.ModelForm):
    first_autofocus = "category"

    class Meta:
        model = ExpenseRequest
        fields = ["category", "amount", "phone_number", "description"]
        widgets = {
            "category": forms.Select(),
            "amount": forms.NumberInput(attrs={"min": "2000", "step": "0.01", "inputmode": "decimal"}),
            "phone_number": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel-national", "maxlength": "15"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "category": "Expense Category *",
            "amount": "Amount (UGX) *",
            "phone_number": "Phone Number for Payment *",
            "description": "Description / Business Reason *",
        }
        help_texts = {
            "amount": "Minimum 2,000 UGX. Use at most 2 decimal places.",
            "phone_number": "Local (0700xxxxxx) or E.164 (+2567xxxxxxxx).",
            "description": "Why is this expense necessary?",
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self._add_prompt(self.fields["category"], "— Select category —")
        self._apply_tailwind()

    # ---- Cleaners ----
    def clean_amount(self) -> Decimal:
        raw = self.cleaned_data.get("amount")
        if raw in (None, ""):
            raise forms.ValidationError("Amount is required.")
        try:
            amt = Decimal(raw)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError("Enter a valid number.")
        if amt < Decimal("2000"):
            raise forms.ValidationError("Minimum amount is UGX 2,000.")
        return quantize_money(amt)

    def clean_phone_number(self) -> str:
        raw = self.cleaned_data.get("phone_number", "")
        norm = normalize_msisdn(raw)
        digits = "".join(ch for ch in norm if ch.isdigit())
        if not (9 <= len(digits) <= 15):
            raise forms.ValidationError("Enter a valid phone number (9–15 digits).")
        return norm

    def clean_description(self) -> str:
        txt = (self.cleaned_data.get("description") or "").strip()
        if len(txt) < 5:
            raise forms.ValidationError("Please provide a short explanation.")
        return txt


# -------------------------------------------------------------------
# SalaryRequest form
# -------------------------------------------------------------------
class SalaryRequestForm(TailwindFormMixin, forms.ModelForm):
    first_autofocus = "payment_type"

    class Meta:
        model = SalaryRequest
        fields = ["payment_type", "amount", "phone_number", "reason", "month"]
        widgets = {
            "payment_type": forms.Select(),
            "amount": forms.NumberInput(attrs={"min": "10000", "step": "0.01", "inputmode": "decimal"}),
            "phone_number": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel-national", "maxlength": "15"}),
            "reason": forms.Textarea(attrs={"rows": 3}),
            "month": forms.DateInput(attrs={"type": "month"}),  # we'll cap in __init__
        }
        labels = {
            "payment_type": "Payment Type *",
            "amount": "Amount (UGX) *",
            "phone_number": "Mobile Money Number *",
            "reason": "Reason *",
            "month": "Salary Month *",
        }
        help_texts = {
            "amount": "Minimum 10,000 UGX. Use at most 2 decimal places.",
            "phone_number": "Local (0700xxxxxx) or E.164 (+2567xxxxxxxx).",
            "month": "Stored as the 1st day of the chosen month.",
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Set a safe max on the month input (current month)
        self.fields["month"].widget.attrs.setdefault("max", timezone.now().strftime("%Y-%m"))
        self._add_prompt(self.fields["payment_type"], "— Select payment type —")
        self._apply_tailwind()

    def clean_amount(self) -> Decimal:
        raw = self.cleaned_data.get("amount")
        if raw in (None, ""):
            raise forms.ValidationError("Amount is required.")
        try:
            amt = Decimal(raw)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError("Enter a valid number.")
        if amt < Decimal("10000"):
            raise forms.ValidationError("Minimum amount is UGX 10,000.")
        return quantize_money(amt)

    def clean_phone_number(self) -> str:
        raw = self.cleaned_data.get("phone_number", "")
        norm = normalize_msisdn(raw)
        digits = "".join(ch for ch in norm if ch.isdigit())
        if not (9 <= len(digits) <= 15):
            raise forms.ValidationError("Enter a valid phone number (9–15 digits).")
        return norm

    def clean_reason(self) -> str:
        txt = (self.cleaned_data.get("reason") or "").strip()
        if len(txt) < 5:
            raise forms.ValidationError("Please provide a short explanation.")
        return txt

    def clean_month(self):
        value = self.cleaned_data.get("month")
        if value:
            # Normalize to first day of month
            return value.replace(day=1)
        return value


# -------------------------------------------------------------------
# Requisition form
# -------------------------------------------------------------------
class RequisitionForm(TailwindFormMixin, forms.ModelForm):
    first_autofocus = "title"

    class Meta:
        model = Requisition
        fields = ["title", "category", "amount", "description"]
        widgets = {
            "title": forms.TextInput(),
            "category": forms.Select(),
            "amount": forms.NumberInput(attrs={"min": "2000", "step": "0.01", "inputmode": "decimal"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "title": "Title *",
            "category": "Category *",
            "amount": "Estimated Amount (UGX) *",
            "description": "Description / Specification *",
        }
        help_texts = {
            "amount": "Minimum 2,000 UGX. Use at most 2 decimal places.",
            "description": "What is needed, why, and any specs or vendor hints.",
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self._add_prompt(self.fields["category"], "— Select category —")
        self._apply_tailwind()

    def clean_amount(self) -> Decimal:
        raw = self.cleaned_data.get("amount")
        if raw in (None, ""):
            raise forms.ValidationError("Amount is required.")
        try:
            amt = Decimal(raw)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError("Enter a valid number.")
        if amt < Decimal("2000"):
            raise forms.ValidationError("Minimum amount is UGX 2,000.")
        return quantize_money(amt)

    def clean_title(self) -> str:
        t = (self.cleaned_data.get("title") or "").strip()
        if len(t) < 3:
            raise forms.ValidationError("Please provide a short title.")
        return t

    def clean_description(self) -> str:
        txt = (self.cleaned_data.get("description") or "").strip()
        if len(txt) < 5:
            raise forms.ValidationError("Please provide a short description.")
        return txt


__all__ = [
    "ExpenseRequestForm",
    "SalaryRequestForm",
    "RequisitionForm",
    "normalize_msisdn",
    "quantize_money",
    "TailwindFormMixin",
]
