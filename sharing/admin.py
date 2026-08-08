from django.contrib import admin
from .models import ShareLink

@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ['token', 'file_item', 'folder', 'created_by', 'access_type', 'permission', 'download_count', 'expires_at', 'created_at']
    list_filter = ['access_type', 'permission', 'created_at']
    search_fields = ['token', 'created_by__username', 'file_item__name']
