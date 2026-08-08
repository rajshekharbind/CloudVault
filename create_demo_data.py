import os
import django
from django.core.files.base import ContentFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloudvault.settings')
django.setup()

from django.contrib.auth import get_user_model
from storage.models import Folder, FileItem
from analytics.models import ActivityLog, Notification
from sharing.models import ShareLink

User = get_user_model()

def run():
    print("Creating Demo Superuser and Users...")
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={'email': 'admin@cloudvault.io', 'is_staff': True, 'is_superuser': True}
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        print("Superuser created: admin / admin123")

    demo_user, created = User.objects.get_or_create(
        username='demo',
        defaults={'email': 'demo@cloudvault.io', 'first_name': 'Demo', 'last_name': 'User'}
    )
    if created:
        demo_user.set_password('demo123')
        demo_user.save()
        print("Demo user created: demo / demo123")

    target_user = demo_user

    print("Creating Demo Folders...")
    f1, _ = Folder.objects.get_or_create(name='Projects & Code', owner=target_user, defaults={'color': '#6366F1'})
    f2, _ = Folder.objects.get_or_create(name='Design Assets', owner=target_user, defaults={'color': '#8B5CF6'})
    f3, _ = Folder.objects.get_or_create(name='Finance & Invoices', owner=target_user, defaults={'color': '#10B981'})

    print("Creating Sample Files...")
    sample_txt_content = b"CloudVault Enterprise Cloud Storage Platform\n==========================================\nSecure, scalable, and ultra-fast file storage."
    file1, _ = FileItem.objects.get_or_create(
        name="Platform_Overview.txt",
        owner=target_user,
        defaults={
            'original_name': "Platform_Overview.txt",
            'folder': f1,
            'file_type': 'text',
            'extension': 'txt',
            'file_size': len(sample_txt_content),
            'mime_type': 'text/plain',
            'file': ContentFile(sample_txt_content, name='Platform_Overview.txt')
        }
    )

    sample_json_content = b'{\n  "app": "CloudVault",\n  "version": "1.0.0",\n  "environment": "production",\n  "storage": "S3 / Local"\n}'
    file2, _ = FileItem.objects.get_or_create(
        name="config.json",
        owner=target_user,
        defaults={
            'original_name': "config.json",
            'folder': f1,
            'file_type': 'code',
            'extension': 'json',
            'file_size': len(sample_json_content),
            'mime_type': 'application/json',
            'file': ContentFile(sample_json_content, name='config.json')
        }
    )

    # Update storage usage
    target_user.storage_used = sum(f.file_size for f in FileItem.objects.filter(owner=target_user))
    target_user.save()

    print("Creating Sample Notifications & Logs...")
    Notification.create_notification(
        user=target_user,
        title="Welcome to CloudVault",
        message="Your 15 GB enterprise cloud storage vault has been provisioned successfully.",
        notification_type="success"
    )

    ActivityLog.log_activity(
        user=target_user,
        action="LOGIN",
        details={"ip": "127.0.0.1"},
        ip_address="127.0.0.1"
    )

    print("Demo Data Setup Completed Successfully!")

if __name__ == '__main__':
    run()
