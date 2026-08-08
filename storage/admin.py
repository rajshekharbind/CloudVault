from django.contrib import admin
from .models import Folder, FileItem, FileVersion

@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'parent', 'color', 'is_favorite', 'is_trashed', 'created_at']
    list_filter = ['is_trashed', 'is_favorite', 'created_at']
    search_fields = ['name', 'owner__username']

@admin.register(FileItem)
class FileItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'folder', 'file_type', 'extension', 'file_size', 'current_version', 'is_favorite', 'is_trashed', 'created_at']
    list_filter = ['file_type', 'is_trashed', 'is_favorite', 'created_at']
    search_fields = ['name', 'original_name', 'tags', 'owner__username']

@admin.register(FileVersion)
class FileVersionAdmin(admin.ModelAdmin):
    list_display = ['file_item', 'version_number', 'file_size', 'uploaded_by', 'created_at']
    search_fields = ['file_item__name', 'uploaded_by__username']
