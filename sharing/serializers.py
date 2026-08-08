from rest_framework import serializers
from .models import ShareLink, Collaborator
from storage.serializers import FileItemSerializer, FolderSerializer

class ShareLinkSerializer(serializers.ModelSerializer):
    file_item_detail = FileItemSerializer(source='file_item', read_only=True)
    folder_detail = FolderSerializer(source='folder', read_only=True)
    is_password_protected = serializers.SerializerMethodField()
    is_valid = serializers.ReadOnlyField()

    class Meta:
        model = ShareLink
        fields = [
            'id', 'token', 'file_item', 'file_item_detail', 'folder', 'folder_detail',
            'access_type', 'permission', 'is_password_protected', 'expires_at',
            'max_downloads', 'download_count', 'is_valid', 'created_at'
        ]
        read_only_fields = ['id', 'token', 'download_count', 'created_at']

    def get_is_password_protected(self, obj):
        return bool(obj.password_hash)


class CollaboratorSerializer(serializers.ModelSerializer):
    user_username = serializers.ReadOnlyField(source='user.username')
    file_item_detail = FileItemSerializer(source='file_item', read_only=True)
    folder_detail = FolderSerializer(source='folder', read_only=True)

    class Meta:
        model = Collaborator
        fields = ['id', 'user', 'user_username', 'file_item', 'file_item_detail', 'folder', 'folder_detail', 'permission', 'added_at']
        read_only_fields = ['id', 'added_at']
