from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.contrib.auth.models import Group as AuthGroup
from .models import CustomUser, UserActivity

# Unregister the default Group admin if you want to customize it
admin.site.unregister(AuthGroup)

@admin.register(AuthGroup)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'user_count')
    search_fields = ('name',)
    filter_horizontal = ('permissions',)
    
    def user_count(self, obj):
        return obj.customuser_set.count()
    user_count.short_description = 'Users'

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'phone_number', 'is_staff', 'is_active', 'profile_picture_display')
    list_filter = ('is_staff', 'is_active', 'groups')
    search_fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
    ordering = ('username',)
    readonly_fields = ('last_login', 'date_joined')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'address', 'profile_picture')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    
    def profile_picture_display(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" width="50" height="50" style="border-radius: 50%;" />', obj.profile_picture.url)
        return "No Image"
    profile_picture_display.short_description = 'Profile Picture'

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_display', 'model_display', 'object_link', 'timestamp', 'ip_address')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__username', 'details', 'ip_address', 'user_agent')
    readonly_fields = ('timestamp', 'user', 'action', 'model_name', 'object_id', 'details', 'ip_address', 'user_agent')
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    fieldsets = (
        ('Activity Information', {
            'fields': ('user', 'action', 'timestamp')
        }),
        ('Object Information', {
            'fields': ('model_name', 'object_id', 'details')
        }),
        ('Technical Details', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    def action_display(self, obj):
        return obj.get_action_display()
    action_display.short_description = 'Action'
    
    def model_display(self, obj):
        return obj.model_name or 'System'
    model_display.short_description = 'Model'
    
    def object_link(self, obj):
        if obj.model_name and obj.object_id:
            try:
                model = apps.get_model('your_app', obj.model_name)
                item = model.objects.get(pk=obj.object_id)
                url = reverse(f'admin:your_app_{obj.model_name.lower()}_change', args=[obj.object_id])
                return format_html('<a href="{}">{}</a>', url, str(item))
            except:
                return f"{obj.model_name} #{obj.object_id}"
        return "-"
    object_link.short_description = 'Object'
    object_link.admin_order_field = 'object_id'

# Admin site customization
admin.site.site_header = 'Administration Dashboard'
admin.site.site_title = 'Admin Portal'
admin.site.index_title = 'System Administration'