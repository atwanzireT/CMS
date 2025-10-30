# accounts/context_processors.py
def module_access(request):
    user = request.user

    def can(codename: str) -> bool:
        return user.is_authenticated and user.has_perm(f"accounts.{codename}")

    return {
        "can_access": {
            "sales":      can("access_sales"),
            "inventory":  can("access_inventory"),
            "reports":    can("access_reports"),
            "assessment": can("access_assessment"),
            "analysis":   can("access_analysis"),
            "accounts":   can("access_accounts"),
            "finance":    can("access_finance"),
            "milling":    can("access_milling"),
            "store":      can("access_store"),
            "expenses":   can("access_expenses"),
        }
    }
