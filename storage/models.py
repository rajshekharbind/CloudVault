import os
from django.db import models
from django.conf import settings
from django.utils import timezone
from .utils import detect_file_category, get_file_icon_class, format_bytes, calculate_checksum, generate_image_thumbnail

class Folder(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='folders'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subfolders'
    )
    color = models.CharField(max_length=20, default='#6366F1')  # Indigo default
    is_favorite = models.BooleanField(default=False)
    is_trashed = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('name', 'owner', 'parent', 'is_trashed')

    def get_ancestors(self):
        ancestors = []
        curr = self.parent
        while curr:
            ancestors.insert(0, curr)
            curr = curr.parent
        return ancestors

    def get_total_size(self):
        file_size = sum(f.file_size for f in self.files.filter(is_trashed=False))
        subfolder_size = sum(sub.get_total_size() for sub in self.subfolders.filter(is_trashed=False))
        return file_size + subfolder_size

    def formatted_size(self):
        return format_bytes(self.get_total_size())

    def soft_delete(self):
        now = timezone.now()
        self.is_trashed = True
        self.trashed_at = now
        self.save()
        # Soft delete subfolders and files
        for sub in self.subfolders.filter(is_trashed=False):
            sub.soft_delete()
        for f in self.files.filter(is_trashed=False):
            f.soft_delete()

    def restore(self):
        self.is_trashed = False
        self.trashed_at = None
        self.save()
        for sub in self.subfolders.filter(is_trashed=True):
            sub.restore()
        for f in self.files.filter(is_trashed=True):
            f.restore()

    def __str__(self):
        return self.name


class FileItem(models.Model):
    FILE_TYPES = (
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('pdf', 'PDF Document'),
        ('document', 'Word Document'),
        ('spreadsheet', 'Spreadsheet'),
        ('presentation', 'Presentation'),
        ('archive', 'Archive (ZIP/RAR)'),
        ('code', 'Source Code'),
        ('text', 'Text File'),
        ('other', 'Other File'),
    )

    name = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='files'
    )
    folder = models.ForeignKey(
        Folder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='files'
    )
    file_type = models.CharField(max_length=30, choices=FILE_TYPES, default='other')
    extension = models.CharField(max_length=20, blank=True)
    file_size = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    thumbnail = models.ImageField(upload_to='thumbnails/%Y/%m/%d/', null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    is_favorite = models.BooleanField(default=False)
    is_trashed = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True, blank=True)
    tags = models.CharField(max_length=255, blank=True, help_text="Comma separated tags")
    current_version = models.IntegerField(default=1)
    security_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('manual_review', 'Manual Review'),
            ('blocked', 'Blocked'),
        ],
        default='pending',
    )
    risk_score = models.PositiveSmallIntegerField(default=0)
    is_quarantined = models.BooleanField(default=False)
    quarantine_reason = models.TextField(blank=True)
    security_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def formatted_size(self):
        return format_bytes(self.file_size)

    def icon_class(self):
        return get_file_icon_class(self.file_type, self.extension)

    def soft_delete(self):
        self.is_trashed = True
        self.trashed_at = timezone.now()
        self.save()
        # Update user used storage
        if self.owner and self.owner.storage_used >= self.file_size:
            self.owner.storage_used -= self.file_size
            self.owner.save()

    def restore(self):
        self.is_trashed = False
        self.trashed_at = None
        self.save()
        if self.owner:
            self.owner.storage_used += self.file_size
            self.owner.save()

    def create_version(self, new_file, uploader, changelog="Uploaded new version"):
        # Save current state as FileVersion
        FileVersion.objects.create(
            file_item=self,
            version_number=self.current_version,
            file=self.file,
            file_size=self.file_size,
            checksum=self.checksum,
            uploaded_by=uploader,
            changelog=changelog
        )
        # Update to new file
        old_size = self.file_size
        self.file = new_file
        self.file_size = new_file.size
        self.checksum = calculate_checksum(new_file)
        self.current_version += 1
        self.save()

        # Update owner storage delta
        size_delta = self.file_size - old_size
        self.owner.storage_used += size_delta
        self.owner.save()

    def __str__(self):
        return self.name


class FileVersion(models.Model):
    file_item = models.ForeignKey(
        FileItem,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.IntegerField()
    file = models.FileField(upload_to='versions/%Y/%m/%d/')
    file_size = models.BigIntegerField()
    checksum = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    changelog = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def formatted_size(self):
        return format_bytes(self.file_size)

    def __str__(self):
        return f"{self.file_item.name} (v{self.version_number})"


class SentinelScan(models.Model):
    file_item = models.ForeignKey(
        FileItem,
        on_delete=models.CASCADE,
        related_name='sentinel_scans'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('manual_review', 'Manual Review'),
            ('blocked', 'Blocked'),
        ],
        default='pending'
    )
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_level = models.CharField(max_length=20, default='low')
    summary = models.TextField(blank=True)
    findings = models.JSONField(default=dict, blank=True)
    recommendations = models.TextField(blank=True)
    quarantine_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.file_item.name} ({self.status})"


class ExternalUrlScan(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='url_scans'
    )
    url = models.URLField(max_length=2000)
    final_url = models.URLField(max_length=2000, blank=True)
    http_status = models.PositiveIntegerField(default=0)
    redirect_chain = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('approved', 'Approved'),
            ('manual_review', 'Manual Review'),
            ('blocked', 'Blocked'),
        ],
        default='manual_review'
    )
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_level = models.CharField(max_length=20, default='low')
    summary = models.TextField(blank=True)
    findings = models.JSONField(default=dict, blank=True)
    quarantined_file = models.FileField(upload_to='quarantine/%Y/%m/%d/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.url} ({self.status})"
