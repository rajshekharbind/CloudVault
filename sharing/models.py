import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from storage.models import FileItem, Folder

class ShareLink(models.Model):
    ACCESS_TYPES = (
        ('public', 'Public (Anyone with link)'),
        ('private', 'Private (Specific link)'),
    )
    PERMISSIONS = (
        ('view', 'View Only'),
        ('edit', 'Edit Permission'),
        ('copy', 'Copy Permission'),
    )

    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    file_item = models.ForeignKey(
        FileItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='share_links'
    )
    folder = models.ForeignKey(
        Folder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='share_links'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_share_links'
    )
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPES, default='public')
    permission = models.CharField(max_length=20, choices=PERMISSIONS, default='view')
    password_hash = models.CharField(max_length=128, blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_downloads = models.IntegerField(null=True, blank=True)
    download_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        if raw_password:
            self.password_hash = make_password(raw_password)
        else:
            self.password_hash = None

    def verify_password(self, raw_password):
        if not self.password_hash:
            return True
        return check_password(raw_password, self.password_hash)

    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def is_download_limit_reached(self):
        if self.max_downloads and self.download_count >= self.max_downloads:
            return True
        return False

    def is_valid(self):
        return not self.is_expired() and not self.is_download_limit_reached()

    def __str__(self):
        target = self.file_item.name if self.file_item else (self.folder.name if self.folder else 'Unassigned')
        return f"ShareLink ({self.token}) for {target}"


class Collaborator(models.Model):
    PERMISSIONS = (
        ('view', 'View'),
        ('edit', 'Edit'),
        ('delete', 'Delete'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='collaborations'
    )
    file_item = models.ForeignKey(
        FileItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='collaborators'
    )
    folder = models.ForeignKey(
        Folder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='collaborators'
    )
    permission = models.CharField(max_length=20, choices=PERMISSIONS, default='view')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'file_item', 'folder')

    def __str__(self):
        target = self.file_item.name if self.file_item else (self.folder.name if self.folder else 'Unassigned')
        return f"Collaborator {self.user} -> {target} ({self.permission})"
