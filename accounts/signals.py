from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth import get_user_model
from django.utils import timezone
from app.models import MillingProcess, MillingTransaction, Customer, Supplier, CoffeePurchase, CoffeeSale
from .models import UserActivity



User = get_user_model()

# Track model changes
@receiver(post_save)
def track_create_update(sender, instance, created, **kwargs):
    if sender.__name__ in ['MillingProcess', 'Transaction', 'Customer', 'Supplier', 'CoffeePurchase', 'CoffeeSale']:
        action = 'create' if created else 'update'
        details = f"{sender.__name__} {instance.pk} was {action}d"
        
        UserActivity.objects.create(
            user=getattr(instance, 'created_by', None) or getattr(instance, 'user', None),
            action=action,
            model_name=sender.__name__,
            object_id=instance.pk,
            details=details
        )

@receiver(post_delete)
def track_delete(sender, instance, **kwargs):
    if sender.__name__ in ['MillingProcess', 'Transaction', 'Customer', 'Supplier', 'CoffeePurchase', 'CoffeeSale']:
        UserActivity.objects.create(
            user=getattr(instance, 'created_by', None) or getattr(instance, 'user', None),
            action='delete',
            model_name=sender.__name__,
            object_id=instance.pk,
            details=f"{sender.__name__} {instance.pk} was deleted"
        )

# Track user logins/logouts
@receiver(user_logged_in)
def track_user_login(sender, request, user, **kwargs):
    UserActivity.objects.create(
        user=user,
        action='login',
        details='User logged in',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

@receiver(user_logged_out)
def track_user_logout(sender, request, user, **kwargs):
    UserActivity.objects.create(
        user=user,
        action='logout',
        details='User logged out',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip