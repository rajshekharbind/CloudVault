from rest_framework import serializers
from .models import Folder, FileItem, FileVersion

class FolderSerializer(serializers.ModelSerializer):
    formatted_size = serializers.ReadOnlyField()
    subfolders_count = serializers.SerializerMethodField()
    files_count = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = [
            'id', 'name', 'parent', 'color', 'is_favorite', 'is_trashed',
            'trashed_at', 'created_at', 'updated_at', 'formatted_size',
            'subfolders_count', 'files_count'
        ]
        read_only_fields = ['id', 'is_trashed', 'trashed_at', 'created_at', 'updated_at']

    def get_subfolders_count(self, obj):
        return obj.subfolders.filter(is_trashed=False).count()

    def get_files_count(self, obj):
        return obj.files.filter(is_trashed=False).count()


class FileVersionSerializer(serializers.ModelSerializer):
    formatted_size = serializers.ReadOnlyField()
    uploaded_by_username = serializers.ReadOnlyField(source='uploaded_by.username')

    class Meta:
        model = FileVersion
        fields = [
            'id', 'version_number', 'file', 'file_size', 'formatted_size',
            'checksum', 'uploaded_by_username', 'changelog', 'created_at'
        ]


class FileItemSerializer(serializers.ModelSerializer):
    formatted_size = serializers.ReadOnlyField()
    icon_class = serializers.ReadOnlyField()
    folder_name = serializers.ReadOnlyField(source='folder.name')
    versions = FileVersionSerializer(many=True, read_only=True)

    class Meta:
        model = FileItem
        fields = [
            'id', 'name', 'original_name', 'file', 'folder', 'folder_name',
            'file_type', 'extension', 'file_size', 'formatted_size',
            'mime_type', 'thumbnail', 'checksum', 'is_favorite', 'is_trashed',
            'trashed_at', 'tags', 'current_version', 'icon_class', 'versions',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'original_name', 'file_type', 'extension', 'file_size',
            'mime_type', 'thumbnail', 'checksum', 'is_trashed', 'trashed_at',
            'current_version', 'created_at', 'updated_at'
        ]
