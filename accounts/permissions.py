from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin


def module_required(perm_codename: str):
    """
    Decorator to guard *whole views* by a single custom permission (e.g., 'access_finance').
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.has_perm(f"accounts.{perm_codename}"):
                raise PermissionDenied("You do not have access to this module.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


class ModuleRequiredMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """
    Use like:
    class FinanceDashboard(ModuleRequiredMixin, TemplateView):
        permission_required = "accounts.access_finance"
    """
    raise_exception = True  # raise 403 instead of redirect to login
