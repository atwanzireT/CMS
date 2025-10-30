# accounts/forms.py
from __future__ import annotations

from django import forms
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

# ========= helpers =========

def _perm_codename(gate: str) -> str:
    return f"access_{gate}"

def _user_content_type() -> ContentType:
    # Attach access_* permissions to your CustomUser content type
    return ContentType.objects.get_for_model(User)

def _perm_full_name(codename: str) -> str:
    # Permissions live under the app_label of the User model's ContentType
    ct = _user_content_type()
    return f"{ct.app_label}.{codename}"

def _ensure_access_permission(gate: str) -> Permission:
    """
    Ensure the 'access_<gate>' permission exists on the CustomUser ContentType.
    Safe to call multiple times.
    """
    ct = _user_content_type()
    codename = _perm_codename(gate)
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=ct,
        defaults={"name": f"Can access {gate} app"},
    )
    return perm

def _list_access_gates() -> list[str]:
    """
    Discover available access gates.

    Primary source: existing permissions with codename starting 'access_' on the User ContentType.
    Fallback: infer gates from installed non-Django apps (no APP_GATES needed).
    """
    ct = _user_content_type()
    existing = Permission.objects.filter(
        content_type=ct, codename__startswith="access_"
    ).values_list("codename", flat=True)

    if existing:
        gates = {c.split("access_", 1)[1] for c in existing if c.startswith("access_")}
        return sorted(gates)

    # Fallback — infer from installed apps (exclude core Django apps)
    EXCLUDE = {"admin", "auth", "contenttypes", "sessions", "messages", "staticfiles"}
    gates = []
    for cfg in django_apps.get_app_configs():
        if cfg.label in EXCLUDE or cfg.name.startswith("django."):
            continue
        # Optionally exclude 'accounts' itself:
        # if cfg.label == "accounts": continue
        gates.append(cfg.label)
    return sorted(set(gates))

# ========= Tailwind utility presets =========

BASE_INPUT = (
    "block w-full rounded-xl border border-gray-300 bg-white "
    "px-4 py-2.5 text-gray-900 placeholder-gray-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
    "disabled:opacity-60 dark:bg-dark-800 dark:text-gray-100 dark:border-dark-700"
)
ERROR_INPUT = (
    "block w-full rounded-xl border border-rose-400 bg-white "
    "px-4 py-2.5 text-gray-900 placeholder-gray-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-rose-500 "
    "dark:bg-dark-800 dark:text-gray-100 dark:border-rose-500"
)
SELECT_INPUT = (
    "block w-full rounded-xl border border-gray-300 bg-white "
    "px-4 py-2.5 text-gray-900 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
    "disabled:opacity-60 dark:bg-dark-800 dark:text-gray-100 dark:border-dark-700"
)
TEXTAREA_INPUT = BASE_INPUT + " min-h-[120px]"
CHECKBOX_INPUT = (
    "h-5 w-5 rounded-md border-gray-300 text-primary-600 "
    "focus:ring-2 focus:ring-primary-500 dark:border-dark-600"
)
FILE_INPUT = (
    "block w-full text-sm text-gray-900 dark:text-gray-100 "
    "file:mr-4 file:rounded-lg file:border-0 file:bg-primary-50 file:px-4 file:py-2 file:text-primary-700 "
    "hover:file:bg-primary-100 dark:file:bg-dark-700 dark:file:text-gray-200"
)

class TailwindWidgetMixin:
    def _tw_style_fields(self):
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                cls = CHECKBOX_INPUT
            elif isinstance(w, forms.Textarea):
                cls = TEXTAREA_INPUT
            elif isinstance(w, forms.Select):
                cls = SELECT_INPUT
            elif isinstance(w, forms.ClearableFileInput):
                cls = FILE_INPUT
            else:
                cls = BASE_INPUT

            if getattr(self, "is_bound", False) and self.errors.get(name):
                if isinstance(w, forms.Textarea):
                    cls = (
                        TEXTAREA_INPUT
                        .replace("border-gray-300", "border-rose-400")
                        .replace("focus:ring-primary-500", "focus:ring-rose-500")
                        .replace("focus:border-primary-500", "focus:border-rose-500")
                    )
                elif not isinstance(w, (forms.CheckboxInput, forms.ClearableFileInput)):
                    cls = ERROR_INPUT
                w.attrs["aria-invalid"] = "true"
                w.attrs["aria-describedby"] = f"id_{name}_error"

            placeholder = f"{field.label}{'' if field.required else ' (optional)'}"
            existing = w.attrs.get("class", "")
            w.attrs["class"] = (existing + " " + cls).strip()
            w.attrs.setdefault("placeholder", placeholder)
            w.attrs.setdefault("aria-label", field.label)

# ========= Auth form =========

class TailwindAuthenticationForm(TailwindWidgetMixin, AuthenticationForm):
    """
    Login form with Tailwind classes applied.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sensible defaults
        self.fields["username"].widget.attrs.setdefault("autofocus", True)
        self.fields["username"].widget.attrs.setdefault("autocomplete", "username")
        self.fields["password"].widget.attrs.setdefault("autocomplete", "current-password")
        self._tw_style_fields()

# ========= User create / change =========

class CustomUserCreationForm(TailwindWidgetMixin, UserCreationForm):
    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "phone_number",
            "address",
            "profile_picture",
            "password1",
            "password2",
        ]
        labels = {
            "username": "Username",
            "email": "Email Address",
            "phone_number": "Phone Number",
            "address": "Address",
            "profile_picture": "Profile Picture",
            "password1": "Password",
            "password2": "Confirm Password",
        }
        help_texts = {"username": None, "password1": None, "password2": None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "username" in self.fields:
            self.fields["username"].widget.attrs.setdefault("autofocus", True)
            self.fields["username"].widget.attrs.setdefault("autocomplete", "username")
        if "email" in self.fields:
            self.fields["email"].widget.attrs.setdefault("autocomplete", "email")
            self.fields["email"].widget.attrs.setdefault("inputmode", "email")
        if "phone_number" in self.fields:
            self.fields["phone_number"].widget.attrs.setdefault("inputmode", "tel")
            self.fields["phone_number"].widget.attrs.setdefault("pattern", r"[0-9+\-\s()]*")
        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.setdefault("autocomplete", "new-password")
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.setdefault("autocomplete", "new-password")
        self._tw_style_fields()

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower()
            if User.objects.filter(email=email).exists():
                raise forms.ValidationError("This email address is already in use.")
        return email

class CustomUserChangeForm(TailwindWidgetMixin, UserChangeForm):
    password = None  # hide raw password hash field

    class Meta:
        model = User
        fields = ["username", "email", "phone_number", "address", "profile_picture"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "email" in self.fields:
            self.fields["email"].widget.attrs.setdefault("autocomplete", "email")
        if "phone_number" in self.fields:
            self.fields["phone_number"].widget.attrs.setdefault("inputmode", "tel")
        self._tw_style_fields()

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower()
            qs = User.objects.filter(email=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This email address is already in use.")
        return email

# ========= permission forms (auto-discovered gates) =========

class UserAccessForm(TailwindWidgetMixin, forms.Form):
    """
    Toggle per-user 'access_<gate>' permissions with simple checkboxes.
    Gates are discovered automatically.
    """
    def __init__(self, *args, user_instance: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_instance = user_instance

        for gate in _list_access_gates():
            codename = _perm_codename(gate)
            self.fields[f"allow_{gate}"] = forms.BooleanField(
                label=gate.title(),
                required=False,
                initial=user_instance.has_perm(_perm_full_name(codename)),
                widget=forms.CheckboxInput(),
            )

        self._tw_style_fields()

    def save(self):
        user = self.user_instance
        for field_name, wanted in self.cleaned_data.items():
            if not field_name.startswith("allow_"):
                continue
            gate = field_name.replace("allow_", "", 1)
            codename = _perm_codename(gate)
            perm = _ensure_access_permission(gate)

            has_before = user.user_permissions.filter(codename=codename).exists()
            if wanted and not has_before:
                user.user_permissions.add(perm)
            elif not wanted and has_before:
                user.user_permissions.remove(perm)
        user.save()
        return user

class GroupAccessForm(TailwindWidgetMixin, forms.Form):
    """
    Toggle 'access_<gate>' permissions at the Group level (role-like).
    """
    def __init__(self, *args, group_instance: Group, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_instance = group_instance

        group_perms = set(group_instance.permissions.values_list("codename", flat=True))
        for gate in _list_access_gates():
            codename = _perm_codename(gate)
            self.fields[f"allow_{gate}"] = forms.BooleanField(
                label=gate.title(),
                required=False,
                initial=(codename in group_perms),
                widget=forms.CheckboxInput(),
            )

        self._tw_style_fields()

    def save(self):
        group = self.group_instance
        for field_name, wanted in self.cleaned_data.items():
            if not field_name.startswith("allow_"):
                continue
            gate = field_name.replace("allow_", "", 1)
            codename = _perm_codename(gate)
            perm = _ensure_access_permission(gate)

            has_before = group.permissions.filter(codename=codename).exists()
            if wanted and not has_before:
                group.permissions.add(perm)
            elif not wanted and has_before:
                group.permissions.remove(perm)
        group.save()
        return group

class GroupCreateForm(TailwindWidgetMixin, forms.Form):
    name = forms.CharField(
        label="Group Name",
        max_length=150,
        help_text=None,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for gate in _list_access_gates():
            self.fields[f"allow_{gate}"] = forms.BooleanField(
                label=gate.title(),
                required=False,
                widget=forms.CheckboxInput(),
            )
        self._tw_style_fields()

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Please provide a group name.")
        if Group.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("A group with this name already exists.")
        return name

    def save(self):
        group = Group.objects.create(name=self.cleaned_data["name"].strip())
        for field, value in self.cleaned_data.items():
            if not (field.startswith("allow_") and value):
                continue
            gate = field.replace("allow_", "", 1)
            perm = _ensure_access_permission(gate)
            group.permissions.add(perm)
        return group
