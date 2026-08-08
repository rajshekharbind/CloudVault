import os
import io
import zipfile
from PIL import Image
from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Folder, FileItem, FileVersion
from sharing.models import Collaborator
from .serializers import FolderSerializer, FileItemSerializer, FileVersionSerializer
from .utils import (
    detect_file_category,
    calculate_checksum,
    generate_image_thumbnail,
    format_bytes
)
from analytics.models import ActivityLog, Notification
from sharing.models import ShareLink
from django.contrib.auth import get_user_model

User = get_user_model()

def helper_get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


# Page Template Views
@login_required
def dashboard_view(request):
    user = request.user
    recent_files = FileItem.objects.filter(owner=user, is_trashed=False).order_by('-created_at')[:8]
    recent_activities = ActivityLog.objects.filter(user=user)[:6]

    # File types storage stats
    stats_qs = FileItem.objects.filter(owner=user, is_trashed=False).values('file_type').annotate(
        total_bytes=Sum('file_size'),
        count=Count('id')
    )

    stats_by_type = {
        'image': 0, 'video': 0, 'audio': 0, 'pdf': 0,
        'document': 0, 'spreadsheet': 0, 'archive': 0, 'other': 0
    }
    for item in stats_qs:
        ftype = item['file_type']
        if ftype in stats_by_type:
            stats_by_type[ftype] += item['total_bytes'] or 0
        else:
            stats_by_type['other'] += item['total_bytes'] or 0

    total_files_count = FileItem.objects.filter(owner=user, is_trashed=False).count()
    total_folders_count = Folder.objects.filter(owner=user, is_trashed=False).count()
    notifications = Notification.objects.filter(user=user, is_read=False)[:5]

    context = {
        'recent_files': recent_files,
        'recent_activities': recent_activities,
        'stats_by_type': stats_by_type,
        'total_files_count': total_files_count,
        'total_folders_count': total_folders_count,
        'notifications': notifications,
    }
    return render(request, 'dashboard.html', context)


@login_required
def files_view(request):
    user = request.user
    folder_id = request.GET.get('folder')
    search_query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('type', '')
    sort_by = request.GET.get('sort', '-updated_at')

    current_folder = None
    if folder_id:
        current_folder = get_object_or_404(Folder, id=folder_id, owner=user, is_trashed=False)

    folders_qs = Folder.objects.filter(owner=user, is_trashed=False)
    files_qs = FileItem.objects.filter(owner=user, is_trashed=False)

    if current_folder:
        folders_qs = folders_qs.filter(parent=current_folder)
        files_qs = files_qs.filter(folder=current_folder)
    elif not search_query and not filter_type:
        folders_qs = folders_qs.filter(parent=None)
        files_qs = files_qs.filter(folder=None)

    if search_query:
        folders_qs = folders_qs.filter(name__icontains=search_query)
        files_qs = files_qs.filter(Q(name__icontains=search_query) | Q(tags__icontains=search_query))

    if filter_type:
        files_qs = files_qs.filter(file_type=filter_type)

    if sort_by in ['name', '-name', 'created_at', '-created_at', 'file_size', '-file_size', 'updated_at', '-updated_at']:
        files_qs = files_qs.order_by(sort_by)

    ancestors = current_folder.get_ancestors() if current_folder else []

    filter_choices = [
        ('', 'All'),
        ('image', 'Images'),
        ('video', 'Videos'),
        ('audio', 'Audio'),
        ('pdf', 'PDF'),
        ('document', 'Documents'),
        ('spreadsheet', 'Spreadsheets'),
        ('presentation', 'Presentations'),
        ('archive', 'Archives'),
        ('code', 'Code'),
    ]

    context = {
        'current_folder': current_folder,
        'folders': folders_qs,
        'files': files_qs,
        'ancestors': ancestors,
        'search_query': search_query,
        'filter_type': filter_type,
        'sort_by': sort_by,
        'filter_choices': filter_choices,
    }
    return render(request, 'files.html', context)



@login_required
def favorites_view(request):
    user = request.user
    folders = Folder.objects.filter(owner=user, is_favorite=True, is_trashed=False)
    files = FileItem.objects.filter(owner=user, is_favorite=True, is_trashed=False)
    context = {'folders': folders, 'files': files}
    return render(request, 'favorites.html', context)


@login_required
def shared_view(request):
    user = request.user
    my_shares = ShareLink.objects.filter(created_by=user)
    context = {'my_shares': my_shares}
    return render(request, 'shared.html', context)


@login_required
def trash_view(request):
    user = request.user
    trashed_folders = Folder.objects.filter(owner=user, is_trashed=True).order_by('-trashed_at')
    trashed_files = FileItem.objects.filter(owner=user, is_trashed=True).order_by('-trashed_at')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'empty_trash':
            # Permanently delete all trashed files & folders for user
            for f in trashed_files:
                if f.file and os.path.exists(f.file.path):
                    try:
                        os.remove(f.file.path)
                    except Exception:
                        pass
                f.delete()
            for fold in trashed_folders:
                fold.delete()
            messages.success(request, 'Trash emptied permanently.')
            ActivityLog.log_activity(
                user=user,
                action='PERMANENT_DELETE',
                details={'scope': 'empty_trash'},
                ip_address=helper_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return redirect('trash')

    context = {
        'trashed_folders': trashed_folders,
        'trashed_files': trashed_files
    }
    return render(request, 'trash.html', context)


@login_required
def analytics_view(request):
    user = request.user
    # Storage usage breakdown
    files_by_type = FileItem.objects.filter(owner=user, is_trashed=False).values('file_type').annotate(
        size=Sum('file_size'), count=Count('id')
    )
    largest_files = FileItem.objects.filter(owner=user, is_trashed=False).order_by('-file_size')[:5]
    activities = ActivityLog.objects.filter(user=user)[:15]

    context = {
        'files_by_type': list(files_by_type),
        'largest_files': largest_files,
        'activities': activities,
    }
    return render(request, 'analytics.html', context)


@login_required
def admin_panel_view(request):
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, 'Access restricted to administrators.')
        return redirect('dashboard')

    users = User.objects.all().order_by('-date_joined')
    total_users = users.count()
    total_files = FileItem.objects.filter(is_trashed=False).count()
    total_storage = FileItem.objects.filter(is_trashed=False).aggregate(total=Sum('file_size'))['total'] or 0

    if request.method == 'POST':
        action = request.POST.get('action')
        target_user_id = request.POST.get('user_id')
        if action == 'toggle_block' and target_user_id:
            target_user = get_object_or_404(User, id=target_user_id)
            target_user.is_blocked = not target_user.is_blocked
            target_user.save()
            messages.success(request, f"User {target_user.username} {'blocked' if target_user.is_blocked else 'unblocked'}.")
            return redirect('admin_panel')

    context = {
        'users': users,
        'total_users': total_users,
        'total_files': total_files,
        'total_storage_fmt': format_bytes(total_storage),
    }
    return render(request, 'admin_panel.html', context)


# File Streaming & Preview Views
@login_required
def download_file_view(request, file_id):
    file_item = get_object_or_404(FileItem, id=file_id, owner=request.user, is_trashed=False)
    if not file_item.file or not os.path.exists(file_item.file.path):
        raise Http404("File does not exist.")

    ActivityLog.log_activity(
        user=request.user,
        action='DOWNLOAD',
        details={'file_name': file_item.name, 'file_id': file_item.id},
        ip_address=helper_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return FileResponse(open(file_item.file.path, 'rb'), as_attachment=True, filename=file_item.original_name)


@login_required
def preview_file_content_view(request, file_id):
    file_item = get_object_or_404(FileItem, id=file_id, owner=request.user, is_trashed=False)
    if not file_item.file or not os.path.exists(file_item.file.path):
        return JsonResponse({'error': 'File not found'}, status=404)

    if file_item.file_type in ['code', 'text']:
        try:
            with open(file_item.file.path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(50000)  # Read max 50KB
            return JsonResponse({'type': 'text', 'content': content})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'type': file_item.file_type,
        'url': file_item.file.url,
        'name': file_item.name,
        'size': file_item.formatted_size()
    })


# REST APIs & File Operations
class UploadFileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        uploaded_files = request.FILES.getlist('files') or ([request.FILES.get('file')] if request.FILES.get('file') else [])
        folder_id = request.data.get('folder_id')

        if not uploaded_files:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        folder = None
        if folder_id:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_trashed=False)

        created_file_items = []
        user = request.user

        for uploaded_file in uploaded_files:
            # Check user storage quota
            if user.storage_used + uploaded_file.size > user.storage_quota:
                return Response({'error': f'Storage quota exceeded for file {uploaded_file.name}.'}, status=status.HTTP_400_BAD_REQUEST)

            ext = os.path.splitext(uploaded_file.name)[1].lower()
            category = detect_file_category(ext, uploaded_file.content_type)
            checksum = calculate_checksum(uploaded_file)

            # Check if version update requested or identical file upload
            existing_file = FileItem.objects.filter(
                owner=user, folder=folder, name=uploaded_file.name, is_trashed=False
            ).first()

            if existing_file:
                existing_file.create_version(uploaded_file, user, changelog="Uploaded duplicate name file version")
                created_file_items.append(existing_file)
                ActivityLog.log_activity(
                    user=user,
                    action='UPLOAD',
                    details={'file_name': existing_file.name, 'version': existing_file.current_version},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            else:
                file_item = FileItem(
                    name=uploaded_file.name,
                    original_name=uploaded_file.name,
                    file=uploaded_file,
                    owner=user,
                    folder=folder,
                    file_type=category,
                    extension=ext.strip('.'),
                    file_size=uploaded_file.size,
                    mime_type=uploaded_file.content_type or '',
                    checksum=checksum
                )
                file_item.save()

                # Generate thumbnail if image
                if category == 'image':
                    thumb = generate_image_thumbnail(file_item.file)
                    if thumb:
                        file_item.thumbnail.save(f"thumb_{file_item.id}.jpg", thumb, save=True)

                # Update user storage
                user.storage_used += uploaded_file.size
                user.save()

                created_file_items.append(file_item)

                ActivityLog.log_activity(
                    user=user,
                    action='UPLOAD',
                    details={'file_name': file_item.name, 'file_size': file_item.file_size},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

        serializer = FileItemSerializer(created_file_items, many=True)
        return Response({'message': 'Files uploaded successfully.', 'files': serializer.data}, status=status.HTTP_201_CREATED)


class FolderListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        name = request.data.get('name', '').strip()
        parent_id = request.data.get('parent_id')
        color = request.data.get('color', '#6366F1')

        if not name:
            return Response({'error': 'Folder name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        parent = None
        if parent_id:
            parent = get_object_or_404(Folder, id=parent_id, owner=request.user, is_trashed=False)

        folder = Folder.objects.create(
            name=name,
            owner=request.user,
            parent=parent,
            color=color
        )
        serializer = FolderSerializer(folder)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FileItemDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        file_item = get_object_or_404(FileItem, id=pk, owner=request.user)
        # capture previous favorite state to detect changes
        previous_is_favorite = file_item.is_favorite

        name = request.data.get('name')
        folder_id = request.data.get('folder_id')
        is_favorite = request.data.get('is_favorite')
        tags = request.data.get('tags')

        if name:
            file_item.name = name.strip()
        if folder_id is not None:
            if folder_id == "":
                file_item.folder = None
            else:
                target_folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_trashed=False)
                file_item.folder = target_folder
        if is_favorite is not None:
            file_item.is_favorite = bool(is_favorite)
        if tags is not None:
            file_item.tags = tags

        file_item.save()
        # If favorite state changed, publish over channels so other open sessions update
        try:
            if is_favorite is not None and (bool(previous_is_favorite) != bool(file_item.is_favorite)):
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(f'user_{request.user.id}', {
                        'type': 'activity',
                        'data': {
                            'event': 'favorite_update',
                            'file_id': file_item.id,
                            'is_favorite': bool(file_item.is_favorite)
                        }
                    })
        except Exception:
            pass
        serializer = FileItemSerializer(file_item)
        return Response(serializer.data)

    def delete(self, request, pk):
        item_type = request.query_params.get('type', 'file')
        permanent = request.query_params.get('permanent', 'false').lower() == 'true'

        if item_type == 'folder':
            folder = get_object_or_404(Folder, id=pk)
            # Owner always allowed
            if folder.owner == request.user:
                allowed = True
            else:
                # collaborator allowed to delete ONLY if folder is empty (no non-trashed files or subfolders)
                is_empty = (folder.files.filter(is_trashed=False).count() == 0) and (folder.subfolders.filter(is_trashed=False).count() == 0)
                allowed = is_empty and Collaborator.objects.filter(user=request.user, folder=folder, permission__in=['delete', 'edit']).exists()

            if not allowed:
                return Response({'error': 'Not authorized to delete this folder.'}, status=status.HTTP_403_FORBIDDEN)

            if permanent or folder.is_trashed:
                # permanently delete folder and files on disk
                for f in folder.files.all():
                    if f.file and os.path.exists(f.file.path):
                        try:
                            os.remove(f.file.path)
                        except Exception:
                            pass
                    f.delete()
                # delete subfolders
                for sub in folder.subfolders.all():
                    sub.delete()
                folder.delete()
                ActivityLog.log_activity(
                    user=request.user,
                    action='PERMANENT_DELETE',
                    details={'folder_name': folder.name},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                return Response({'message': 'Folder deleted permanently.'}, status=status.HTTP_200_OK)
            else:
                folder.soft_delete()
                ActivityLog.log_activity(
                    user=request.user,
                    action='DELETE',
                    details={'folder_name': folder.name},
                    ip_address=helper_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                return Response({'message': 'Folder moved to trash.'}, status=status.HTTP_200_OK)

        # default: handle file
        file_item = get_object_or_404(FileItem, id=pk)
        # Permit owner or collaborator with delete/edit permission
        has_permission = (file_item.owner == request.user) or Collaborator.objects.filter(
            user=request.user, file_item=file_item, permission__in=['delete', 'edit']
        ).exists()
        if not has_permission:
            return Response({'error': 'Not authorized to delete this file.'}, status=status.HTTP_403_FORBIDDEN)

        if permanent or file_item.is_trashed:
            if file_item.file and os.path.exists(file_item.file.path):
                try:
                    os.remove(file_item.file.path)
                except Exception:
                    pass
            file_item.delete()
            ActivityLog.log_activity(
                user=request.user,
                action='PERMANENT_DELETE',
                details={'file_name': file_item.name},
                ip_address=helper_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return Response({'message': 'File deleted permanently.'}, status=status.HTTP_200_OK)
        else:
            file_item.soft_delete()
            ActivityLog.log_activity(
                user=request.user,
                action='DELETE',
                details={'file_name': file_item.name},
                ip_address=helper_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return Response({'message': 'File moved to trash.'}, status=status.HTTP_200_OK)


class RestoreItemAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        item_type = request.data.get('type', 'file')
        if item_type == 'folder':
            folder = get_object_or_404(Folder, id=pk)
            # Permit owner or collaborator with delete/edit permission for folder restore
            has_permission = (folder.owner == request.user) or Collaborator.objects.filter(
                user=request.user, folder=folder, permission__in=['delete', 'edit']
            ).exists()
            if not has_permission:
                return Response({'error': 'Not authorized to restore this folder.'}, status=status.HTTP_403_FORBIDDEN)
            folder.restore()
            ActivityLog.log_activity(user=request.user, action='RESTORE', details={'folder': folder.name})
        else:
            file_item = get_object_or_404(FileItem, id=pk)
            has_permission = (file_item.owner == request.user) or Collaborator.objects.filter(
                user=request.user, file_item=file_item, permission__in=['delete', 'edit']
            ).exists()
            if not has_permission:
                return Response({'error': 'Not authorized to restore this file.'}, status=status.HTTP_403_FORBIDDEN)
            file_item.restore()
            ActivityLog.log_activity(user=request.user, action='RESTORE', details={'file': file_item.name})
        return Response({'message': 'Item restored successfully.'})


class CompressZipAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file_ids = request.data.get('file_ids', [])
        zip_name = request.data.get('zip_name', 'archive.zip')

        if not file_ids:
            return Response({'error': 'No files selected for compression.'}, status=status.HTTP_400_BAD_REQUEST)

        files = FileItem.objects.filter(id__in=file_ids, owner=request.user, is_trashed=False)
        zip_io = io.BytesIO()

        with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if f.file and os.path.exists(f.file.path):
                    zf.write(f.file.path, arcname=f.name)

        zip_io.seek(0)
        zip_file = ContentFile(zip_io.getvalue(), name=zip_name)
        
        new_file = FileItem.objects.create(
            name=zip_name,
            original_name=zip_name,
            file=zip_file,
            owner=request.user,
            file_type='archive',
            extension='zip',
            file_size=zip_file.size,
            mime_type='application/zip',
            checksum=calculate_checksum(zip_file)
        )
        request.user.storage_used += zip_file.size
        request.user.save()

        serializer = FileItemSerializer(new_file)
        return Response({'message': 'ZIP archive created successfully.', 'file': serializer.data})
