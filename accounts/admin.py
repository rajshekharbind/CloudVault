from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'first_name', 'last_name', 'storage_quota', 'storage_used', 'is_blocked', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ('CloudVault Info', {'fields': ('storage_quota', 'storage_used', 'profile_picture', 'phone_number', 'bio', 'is_email_verified', 'is_blocked')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('CloudVault Info', {'fields': ('storage_quota', 'storage_used', 'profile_picture', 'phone_number', 'bio', 'is_email_verified', 'is_blocked')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)
