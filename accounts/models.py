from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    # Default 15 GB storage quota
    storage_quota = models.BigIntegerField(default=15 * 1024 * 1024 * 1024)
    storage_used = models.BigIntegerField(default=0)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    is_email_verified = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_used_percentage(self):
        if not self.storage_quota or self.storage_quota == 0:
            return 0
        return min(100, round((self.storage_used / self.storage_quota) * 100, 1))

    @property
    def free_storage(self):
        return max(0, self.storage_quota - self.storage_used)

    @staticmethod
    def format_bytes(size):
        if not size:
            return "0 B"
        size = float(size)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def formatted_used(self):
        return self.format_bytes(self.storage_used)

    def formatted_quota(self):
        return self.format_bytes(self.storage_quota)

    def formatted_free(self):
        return self.format_bytes(self.free_storage)

    def __str__(self):
        return self.username
