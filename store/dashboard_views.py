from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Sum, Count, F, DecimalField, ExpressionWrapper, Q, Avg
)
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from sales.models import CoffeeSale, SaleCustomer  # (kept; optional)
from store.models import CoffeePurchase, SupplierAccount, SupplierTransaction
from assessment.models import Assessment
from milling.models import MillingProcess, Customer
from accounts.models import UserActivity

# ---- Resolve app label of your CustomUser dynamically ----
APP_LABEL = apps.get_model(settings.AUTH_USER_MODEL)._meta.app_label


# ---- Enhanced Permission & Role checks ----
def has_perm(user, codename: str) -> bool:
    """Check a custom permission codename declared on CustomUser.Meta.permissions."""
    return bool(user.is_superuser or user.has_perm(f"{APP_LABEL}.{codename}"))


def in_any_group(user, names: List[str]) -> bool:
    """Check if user is in any of the specified groups."""
    if user.is_superuser:
        return True
    user_groups = set(user.groups.values_list("name", flat=True))
    return any(name in user_groups for name in names)


def get_user_role(user) -> str:
    """Get the primary role of the user for dashboard customization."""
    if user.is_superuser:
        return "superuser"

    groups = user.groups.values_list("name", flat=True)
    role_priority = ["Management", "Finance", "Quality", "Sales", "Operations", "Milling", "Accounts"]

    for role in role_priority:
        if role in groups:
            return role.lower()

    return "user"


# ---- Data Providers ----
def sales_cards(user) -> Dict[str, Any]:
    """
    Purchases snapshot with role-based filtering.
    Uses Assessment.final_price (per-kg) to compute total value safely.
    """
    today = timezone.localdate()
    base_qs = CoffeePurchase.objects.select_related("assessment")

    # Role scoping: regular users see only today's rows
    if not (user.is_superuser or in_any_group(user, ["Management", "Finance", "Sales"])):
        base_qs = base_qs.filter(purchase_date=today)

    qs_today   = base_qs.filter(purchase_date=today)
    pending_qs = base_qs.filter(payment_status=CoffeePurchase.PAYMENT_PENDING)
    partial_qs = base_qs.filter(payment_status=CoffeePurchase.PAYMENT_PARTIAL)

    # Decimal-safe total value: quantity (int) * COALESCE(assessment.final_price, 0)
    price_expr = ExpressionWrapper(
        F("quantity") * Coalesce(F("assessment__final_price"), Decimal("0.00")),
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )

    total_value = None
    if user.is_superuser or in_any_group(user, ["Management", "Finance"]):
        total_value = base_qs.aggregate(
            total=Sum(price_expr, output_field=DecimalField(max_digits=20, decimal_places=2))
        )["total"] or Decimal("0.00")

    return {
        "purchases_today": qs_today.count(),
        "pending_count":   pending_qs.count(),
        "partial_count":   partial_qs.count(),
        "total_value":     total_value,
        "show_detailed":   user.is_superuser or in_any_group(user, ["Management", "Finance", "Sales"]),
    }


def finance_cards(user) -> Dict[str, Any]:
    """Finance overview with role-based access."""
    if not (user.is_superuser or in_any_group(user, ["Management", "Finance", "Accounts"])):
        return {"restricted": True}

    totals = SupplierAccount.objects.aggregate(total_payable=Sum("balance"))
    recent_payments = SupplierTransaction.objects.filter(transaction_type="C").order_by("-created_at")[:5]

    return {
        "supplier_accounts": SupplierAccount.objects.count(),
        "total_payable": totals.get("total_payable") or Decimal("0.00"),
        "recent_payments": recent_payments,
        "show_detailed": user.is_superuser or in_any_group(user, ["Management", "Finance"]),
    }


def milling_cards(user) -> Dict[str, Any]:
    """Milling data with role-based filtering."""
    today = timezone.localdate()
    base_qs = MillingProcess.objects.all()

    if not (user.is_superuser or in_any_group(user, ["Management", "Milling", "Operations"])):
        base_qs = base_qs.filter(created_at__date=today)

    today_qs = base_qs.filter(created_at__date=today)

    revenue_expr = ExpressionWrapper(
        F("hulled_weight") * Coalesce(F("milling_rate"), Decimal("0.00")),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    agg = today_qs.aggregate(
        processes=Count("id"),
        hulled_total=Sum("hulled_weight"),
        revenue_today=Sum(revenue_expr),
    )

    monthly_revenue = None
    if user.is_superuser or in_any_group(user, ["Management", "Finance"]):
        monthly_qs = base_qs.filter(created_at__month=today.month)
        monthly_revenue = monthly_qs.aggregate(revenue=Sum(revenue_expr))["revenue"] or Decimal("0.00")

    return {
        "processes_today": agg.get("processes") or 0,
        "hulled_today_kg": agg.get("hulled_total") or 0,
        "revenue_today": agg.get("revenue_today") or Decimal("0.00"),
        "monthly_revenue": monthly_revenue,
        "show_detailed": user.is_superuser or in_any_group(user, ["Management", "Milling"]),
    }


def quality_cards(user) -> Dict[str, Any]:
    """
    Quality assessment counters:
    - Main counters reflect the role-scoped base queryset (NOT only 'today').
    - Extra keys provide 'today-only' numbers if needed in the UI.
    """
    today = timezone.localdate()
    base_qs = Assessment.objects.all()

    if not (user.is_superuser or in_any_group(user, ["Management", "Quality"])):
        base_qs = base_qs.filter(created_at__date=today)

    # Role-scoped totals (what most users expect to see)
    total_count    = base_qs.count()
    accepted_count = base_qs.filter(decision="Accepted").count()
    rejected_count = base_qs.filter(decision="Rejected").count()

    # Today-only (optional)
    today_qs            = base_qs.filter(created_at__date=today)
    accepted_today_only = today_qs.filter(decision="Accepted").count()
    rejected_today_only = today_qs.filter(decision="Rejected").count()

    quality_metrics = None
    if user.is_superuser or in_any_group(user, ["Management", "Quality"]):
        avg_clean_outturn = base_qs.aggregate(v=Avg("clean_outturn"))["v"]
        acceptance_rate   = (accepted_count * 100.0 / total_count) if total_count else 0.0
        quality_metrics = {
            "avg_clean_outturn": avg_clean_outturn,
            "acceptance_rate":   acceptance_rate,
        }

    # Keep original keys your template reads, but map them to role-scoped totals
    return {
        "assessed_today": today_qs.count(),      # unchanged key
        "accepted_today": accepted_count,        # was "today-only"; now role-scoped total so it won't show 0 incorrectly
        "rejected_today": rejected_count,        # same idea

        # Optional extras if you want to show both:
        "accepted_today_only": accepted_today_only,
        "rejected_today_only": rejected_today_only,

        "quality_metrics": quality_metrics,
        "show_detailed": user.is_superuser or in_any_group(user, ["Management", "Quality"]),
    }


# Recent activity → icon mapping
ICON_MAP = {
    "login": "sign-in-alt",
    "logout": "sign-out-alt",
    "create": "plus-circle",
    "update": "edit",
    "delete": "trash",
}


def get_recent_activities(user, limit=5):
    """Get recent user activities based on role and attach an 'icon' attr for the template."""
    activities = UserActivity.objects.all()

    if not (user.is_superuser or in_any_group(user, ["Management"])):
        activities = activities.filter(user=user)

    qs = activities.select_related("user").order_by("-timestamp")[:limit]

    for a in qs:
        action_key = getattr(a, "action", None)
        if action_key is None and hasattr(a, "get_action_display"):
            try:
                action_key = a.get_action_display().lower()
            except Exception:
                action_key = "update"
        a.icon = ICON_MAP.get(str(action_key).lower(), "circle")
    return qs


# ---- Module Registry ----
MODULES = [
    {
        "key": "sales",
        "title": "Sales / Purchases",
        "icon": "shopping-bag",
        "url_name": "store:purchase_list",
        "perm": "access_sales",
        "groups": ["Sales", "Operations", "Management"],
        "cards_fn": sales_cards,
        "priority": 1,
        "description": "Manage coffee purchases and sales",
    },
    {
        "key": "finance",
        "title": "Finance",
        "icon": "banknote",
        "url_name": "finance:finance_dashboard",
        "perm": "access_finance",
        "groups": ["Finance", "Accounts", "Management"],
        "cards_fn": finance_cards,
        "priority": 2,
        "description": "Financial management and reporting",
    },
    {
        "key": "quality",
        "title": "Quality / Assessment",
        "icon": "check-badge",
        "url_name": "assessment:assessment_list",
        "perm": "access_assessment",
        "groups": ["Quality", "Operations", "Management"],
        "cards_fn": quality_cards,
        "priority": 3,
        "description": "Quality control and assessment",
    },
    {
        "key": "milling",
        "title": "Milling",
        "icon": "cog",
        "url_name": None,  # e.g., "milling:process_list" when ready
        "perm": "access_milling",
        "groups": ["Milling", "Factory", "Management"],
        "cards_fn": milling_cards,
        "priority": 4,
        "description": "Coffee milling operations",
    },
    {
        "key": "reports",
        "title": "Reports",
        "icon": "chart-bar",
        "url_name": "analysis:analysis_view",
        "perm": "access_reports",
        "groups": ["Management", "Finance", "Quality"],
        "cards_fn": None,
        "priority": 5,
        "description": "Analytics and reporting",
    },
    {
        "key": "inventory",
        "title": "Inventory",
        "icon": "archive-box",
        "url_name": "inventory:inventory_home",
        "perm": "access_inventory",
        "groups": ["Operations", "Management"],
        "cards_fn": None,
        "priority": 6,
        "description": "Stock and inventory management",
    },
]


def get_role_based_modules(user) -> List[Dict[str, Any]]:
    """Get modules filtered and prioritized by user role."""
    visible_modules = []

    for mod in MODULES:
        if user.is_superuser or has_perm(user, mod["perm"]) or in_any_group(user, mod["groups"]):
            visible_modules.append(mod)

    visible_modules.sort(key=lambda x: x["priority"])
    return visible_modules


# ---- Dashboard View ----
@login_required
def dashboard(request):
    user = request.user
    user_role = get_user_role(user)
    modules = get_role_based_modules(user)

    tiles = []
    for mod in modules:
        data = {}
        if callable(mod.get("cards_fn")):
            try:
                data = mod["cards_fn"](user)
            except Exception as e:
                # Log in real code; keep template-safe value here
                print(f"Error loading {mod['key']} cards: {e}")
                data = {"error": "Failed to load"}

        tiles.append(
            {
                "key": mod["key"],
                "title": mod["title"],
                "icon": mod["icon"],
                "url_name": mod["url_name"],
                "description": mod.get("description", ""),
                "data": data,
                "role": user_role,
            }
        )

    recent_activities = get_recent_activities(user)

    welcome_messages = {
        "superuser": "System Administrator Dashboard",
        "management": "Executive Overview Dashboard",
        "finance": "Financial Management Dashboard",
        "quality": "Quality Control Dashboard",
        "sales": "Sales Operations Dashboard",
        "milling": "Milling Operations Dashboard",
        "operations": "Operations Dashboard",
        "user": "Welcome to Your Dashboard",
        "default": "Welcome to Your Dashboard",
    }
    welcome_title = welcome_messages.get(user_role, welcome_messages["default"])

    api_key = getattr(settings, "WEATHER_API_KEY", "41e63358947f461f94485541252309")
    weather_location = getattr(settings, "WEATHER_LOCATION", "Kasese,Uganda")

    context = {
        "tiles": tiles,
        "recent_activities": recent_activities,
        "user_role": user_role,
        "welcome_title": welcome_title,
        "is_superuser": user.is_superuser,
        "groups": list(user.groups.values_list("name", flat=True)),
        "user_permissions": user.get_all_permissions(),
        "api_key": api_key,
        "weather_location": weather_location,
    }
    return render(request, "index.html", context)
