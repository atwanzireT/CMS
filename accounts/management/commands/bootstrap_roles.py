from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.apps import apps
from django.conf import settings

CUSTOM_PERMS = [
    "access_sales",
    "access_inventory",
    "access_reports",
    "access_assessment",
    "access_analysis",
    "access_accounts",
    "access_finance",
    "access_milling",
    "access_store",
    "access_expenses",
]

GROUP_MATRIX = {
    "Admin": CUSTOM_PERMS,  # all access
    "Finance": ["access_finance", "access_reports", "access_accounts", "access_expenses"],
    "Quality": ["access_assessment", "access_milling", "access_reports"],
    "Store": ["access_store", "access_inventory", "access_reports"],
    "Sales": ["access_sales", "access_reports"],
}

class Command(BaseCommand):
    help = "Create default groups and attach module permissions"

    def handle(self, *args, **options):
        # permissions live on your CustomUser's Meta
        # We fetch them directly by codename:
        perm_qs = Permission.objects.filter(codename__in=CUSTOM_PERMS)
        perm_map = {p.codename: p for p in perm_qs}

        # sanity check
        missing = set(CUSTOM_PERMS) - set(perm_map.keys())
        if missing:
            self.stdout.write(self.style.ERROR(f"Missing permissions: {missing}. "
                                               f"Run migrations and ensure CustomUser is loaded."))
            return

        for group_name, codenames in GROUP_MATRIX.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.clear()
            group.permissions.add(*[perm_map[c] for c in codenames])
            self.stdout.write(self.style.SUCCESS(f"Configured group: {group_name}"))

        self.stdout.write(self.style.SUCCESS("Done."))
