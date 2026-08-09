import json
from django.db import models
from django.conf import settings
from django.utils import timezone

class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ('UPLOAD', 'File Uploaded'),
        ('DOWNLOAD', 'File Downloaded'),
        ('DELETE', 'File Trashed'),
        ('RESTORE', 'File Restored'),
        ('PERMANENT_DELETE', 'Permanently Deleted'),
        ('MOVE', 'Item Moved'),
        ('RENAME', 'Item Renamed'),
        ('SHARE', 'Link Shared'),
        ('FAVORITE', 'Toggled Favorite'),
        ('LOGIN', 'User Login'),
        ('REGISTER', 'User Register'),
        ('LOGOUT', 'User Logout'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_logs',
        null=True,
        blank=True
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    details = models.TextField(blank=True, default='{}')
    ip_address = models.CharField(max_length=45, blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    @classmethod
    def log_activity(cls, user, action, details=None, ip_address=None, user_agent=None):
        if details is None:
            details = {}
        if isinstance(details, dict):
            details_str = json.dumps(details)
        else:
            details_str = str(details)
        
        obj = cls.objects.create(
            user=user,
            action=action,
            details=details_str,
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Publish activity over channels group for the user (if channels are available)
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer and user:
                data = {
                    'id': obj.id,
                    'action': obj.get_action_display(),
                    'details': obj.get_details_dict(),
                    'ip_address': obj.ip_address,
                    'timestamp': timezone.localtime(obj.timestamp).strftime('%b %d, %Y %H:%M')
                }
                async_to_sync(channel_layer.group_send)(f'user_{user.id}', {
                    'type': 'activity',
                    'data': data
                })
        except Exception:
            pass

        return obj

    def get_details_dict(self):
        try:
            return json.loads(self.details)
        except Exception:
            return {}

    def __str__(self):
        username = self.user.username if self.user else 'Anonymous'
        return f"{username} - {self.get_action_display()} at {timezone.localtime(self.timestamp).strftime('%Y-%m-%d %H:%M')}"


class Notification(models.Model):
    TYPE_CHOICES = (
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=150)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def create_notification(cls, user, title, message, notification_type='info'):
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type
        )

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"
