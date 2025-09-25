from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper, Q, Avg
from django.db.models.functions import Coalesce as _Coalesce
from django.shortcuts import render
from django.utils import timezone

from sales.models import CoffeeSale, SaleCustomer
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


# ---- Enhanced Data Providers ----
def sales_cards(user) -> Dict[str, Any]:
    """Sales/purchases data with role-based filtering."""
    today = date.today()
    base_qs = CoffeePurchase.objects.all()

    # Role-based filtering
    if not (user.is_superuser or in_any_group(user, ["Management", "Finance", "Sales"])):
        # Regular users only see today's data
        base_qs = base_qs.filter(purchase_date=today)

    qs_today = base_qs.filter(purchase_date=today)
    pending_qs = base_qs.filter(payment_status=CoffeePurchase.PAYMENT_PENDING)
    partial_qs = base_qs.filter(payment_status=CoffeePurchase.PAYMENT_PARTIAL)

    # Total value for management/finance
    total_value = None
    if user.is_superuser or in_any_group(user, ["Management", "Finance"]):
        total_value = (
            base_qs.aggregate(total=Sum(F("quantity") * F("unit_price"), output_field=DecimalField()))["total"]
            or Decimal("0.00")
        )

    return {
        "purchases_today": qs_today.count(),
        "pending_count": pending_qs.count(),
        "partial_count": partial_qs.count(),
        "total_value": total_value,
        "show_detailed": user.is_superuser or in_any_group(user, ["Management", "Finance", "Sales"]),
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
        F("hulled_weight") * _Coalesce(F("milling_rate"), Decimal("0.00")),
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
    """Quality assessment data."""
    today = timezone.localdate()
    base_qs = Assessment.objects.all()

    if not (user.is_superuser or in_any_group(user, ["Management", "Quality"])):
        base_qs = base_qs.filter(created_at__date=today)

    today_qs = base_qs.filter(created_at__date=today)

    # Quality metrics for management/quality team
    quality_metrics = None
    if user.is_superuser or in_any_group(user, ["Management", "Quality"]):
        total = base_qs.count()
        accepted = base_qs.filter(decision="Accepted").count()
        avg_clean_outturn = base_qs.aggregate(v=Avg("clean_outturn"))["v"]
        quality_metrics = {
            "avg_clean_outturn": avg_clean_outturn,
            "acceptance_rate": (accepted * 100.0 / total) if total > 0 else 0.0,
        }

    return {
        "assessed_today": today_qs.count(),
        "accepted_today": today_qs.filter(decision="Accepted").count(),
        "rejected_today": today_qs.filter(decision="Rejected").count(),
        "quality_metrics": quality_metrics,
        "show_detailed": user.is_superuser or in_any_group(user, ["Management", "Quality"]),
    }


# Recent activity → icon mapping (optional but improves UI)
ICON_MAP = {
    "login": "sign-in-alt",
    "logout": "sign-out-alt",
    "create": "plus-circle",
    "update": "edit",
    "delete": "trash",
    # add more if your actions differ
}


def get_recent_activities(user, limit=5):
    """Get recent user activities based on role and attach a 'icon' attr for the template."""
    activities = UserActivity.objects.all()

    # Regular users only see their own activities
    if not (user.is_superuser or in_any_group(user, ["Management"])):
        activities = activities.filter(user=user)

    qs = activities.select_related("user").order_by("-timestamp")[:limit]

    # Attach a non-model attribute for icon (safe for template)
    for a in qs:
        # handle both .action (raw) and get_action_display() if available
        action_key = getattr(a, "action", None)
        if action_key is None and hasattr(a, "get_action_display"):
            try:
                action_key = a.get_action_display().lower()
            except Exception:
                action_key = "update"
        a.icon = ICON_MAP.get(str(action_key).lower(), "circle")
    return qs


# ---- Enhanced Module Registry ----
MODULES = [
    {
        "key": "sales",
        "title": "Sales / Purchases",
        "icon": "shopping-bag",
        "url_name": "store:purchase_list",   # was purchases:list
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
        "url_name": "finance:finance_dashboard",  # was finance:dashboard
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
        "url_name": "assessment:assessment_list",  # was assessment:list
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
        "url_name": None,  # set to your milling list when you have it, e.g., "milling:process_list"
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
        "url_name": "analysis:analysis_view",  # was reports:home
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
        "url_name": "inventory:inventory_home",  # was inventory:dashboard
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

    # Sort by priority
    visible_modules.sort(key=lambda x: x["priority"])

    return visible_modules


# ---- Enhanced Dashboard View ----
@login_required
def dashboard(request):
    user = request.user
    user_role = get_user_role(user)
    modules = get_role_based_modules(user)

    # Compute per-module stats
    tiles = []
    for mod in modules:
        data = {}
        if callable(mod.get("cards_fn")):
            try:
                data = mod["cards_fn"](user)  # Pass user for role-based filtering
            except Exception as e:
                # Log and expose a template-safe error key
                print(f"Error loading {mod['key']} cards: {e}")
                data = {"error": "Failed to load"}  # <-- no leading underscore

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

    # Get recent activities (with icon attr)
    recent_activities = get_recent_activities(user)

    # Role-based welcome message
    welcome_messages = {
        "superuser": "System Administrator Dashboard",
        "management": "Executive Overview Dashboard",
        "finance": "Financial Management Dashboard",
        "quality": "Quality Control Dashboard",
        "sales": "Sales Operations Dashboard",
        "milling": "Milling Operations Dashboard",
        "operations": "Operations Dashboard",
        "user": "Welcome to Your Dashboard",   # added explicit fallback
        "default": "Welcome to Your Dashboard",
    }
    welcome_title = welcome_messages.get(user_role, welcome_messages["default"])

    # Weather config (optional)
    api_key = getattr(settings, "WEATHER_API_KEY", "")
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
