from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models

class CustomUser(AbstractUser):
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    # Avoid related_name clashes with AbstractUser defaults
    groups = models.ManyToManyField(Group, related_name="customer_users", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="customer_user_permissions", blank=True)

    class Meta(AbstractUser.Meta):
        permissions = [
            ("access_sales", "Can access sales app"),
            ("access_inventory", "Can access inventory app"),
            ("access_reports", "Can access reports app"),
            ("access_assessment", "Can access assessment app"),
            ("access_analysis", "Can access analysis app"),
            ("access_accounts", "Can access accounts app"),
            ("access_finance", "Can access finance app"),
            ("access_milling", "Can access milling app"),
            ("access_store", "Can access store app"),
            ("access_expenses", "Can access expenses app"),
        ]

class UserActivity(models.Model):
    ACTION_CHOICES = [
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('create', 'Create Record'),
        ('update', 'Update Record'),
        ('delete', 'Delete Record'),
        ('view', 'View Record'),
    ]
    
    user = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50, blank=True, null=True)
    object_id = models.CharField(max_length=50, blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'User Activities'

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.model_name or ''}"