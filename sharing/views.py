import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import ShareLink
from .models import ShareLink, Collaborator
from .serializers import ShareLinkSerializer, CollaboratorSerializer
from storage.models import FileItem, Folder
from analytics.models import ActivityLog
from django.contrib.auth import get_user_model

User = get_user_model()

def helper_get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR', '127.0.0.1')

# Template Views
def public_share_view(request, token):
    share_link = get_object_or_404(ShareLink, token=token)

    if not share_link.is_valid():
        return render(request, 'sharing/expired.html', {'share_link': share_link})

    # Password validation
    if share_link.password_hash:
        session_key = f'unlocked_share_{token}'
        if not request.session.get(session_key):
            if request.method == 'POST':
                password = request.POST.get('password', '')
                if share_link.verify_password(password):
                    request.session[session_key] = True
                    return redirect('public_share', token=token)
                else:
                    messages.error(request, 'Incorrect password. Access denied.')
            return render(request, 'sharing/password_prompt.html', {'share_link': share_link})

    return render(request, 'sharing/public_view.html', {'share_link': share_link})

def download_shared_file(request, token):
    share_link = get_object_or_404(ShareLink, token=token)

    if not share_link.is_valid():
        raise Http404("This share link has expired or reached its download limit.")

    if share_link.password_hash:
        session_key = f'unlocked_share_{token}'
        if not request.session.get(session_key):
            return redirect('public_share', token=token)

    file_item = share_link.file_item
    if not file_item or file_item.is_trashed or not os.path.exists(file_item.file.path):
        raise Http404("File no longer exists.")

    share_link.download_count += 1
    share_link.save()

    ActivityLog.log_activity(
        user=share_link.created_by,
        action='DOWNLOAD',
        details={'file_name': file_item.name, 'share_token': str(token)},
        ip_address=helper_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    response = FileResponse(open(file_item.file.path, 'rb'), as_attachment=True, filename=file_item.original_name)
    return response

# REST API Views
class ShareLinkListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        links = ShareLink.objects.filter(created_by=request.user)
        serializer = ShareLinkSerializer(links, many=True)
        return Response(serializer.data)

    def post(self, request):
        file_id = request.data.get('file_id')
        folder_id = request.data.get('folder_id')
        access_type = request.data.get('access_type', 'public')
        permission = request.data.get('permission', 'view')
        password = request.data.get('password', None)
        expires_in_days = request.data.get('expires_in_days', None)
        max_downloads = request.data.get('max_downloads', None)

        file_item = None
        folder = None

        if file_id:
            file_item = get_object_or_404(FileItem, id=file_id, owner=request.user)
        elif folder_id:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
        else:
            return Response({'error': 'Either file_id or folder_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        expires_at = None
        if expires_in_days:
            try:
                expires_at = timezone.now() + timezone.timedelta(days=int(expires_in_days))
            except ValueError:
                pass

        share_link = ShareLink(
            file_item=file_item,
            folder=folder,
            created_by=request.user,
            access_type=access_type,
            permission=permission,
            expires_at=expires_at,
            max_downloads=int(max_downloads) if max_downloads else None
        )
        if password:
            share_link.set_password(password)
        share_link.save()

        ActivityLog.log_activity(
            user=request.user,
            action='SHARE',
            details={'target': file_item.name if file_item else folder.name, 'link': str(share_link.token)},
            ip_address=helper_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        serializer = ShareLinkSerializer(share_link)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ShareLinkDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        share_link = get_object_or_404(ShareLink, id=pk, created_by=request.user)
        share_link.delete()
        return Response({'message': 'Share link revoked successfully.'}, status=status.HTTP_200_OK)


class CollaboratorListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # filter by file_id or folder_id
        file_id = request.query_params.get('file_id')
        folder_id = request.query_params.get('folder_id')
        if file_id:
            collabs = Collaborator.objects.filter(file_item_id=file_id)
        elif folder_id:
            collabs = Collaborator.objects.filter(folder_id=folder_id)
        else:
            collabs = Collaborator.objects.filter(user=request.user)
        serializer = CollaboratorSerializer(collabs, many=True)
        return Response(serializer.data)

    def post(self, request):
        target_file = request.data.get('file_id')
        target_folder = request.data.get('folder_id')
        user_id = request.data.get('user_id')
        permission = request.data.get('permission', 'view')

        if not user_id:
            return Response({'error': 'user_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        target = None
        if target_file:
            target = get_object_or_404(FileItem, id=target_file, owner=request.user)
        elif target_folder:
            target = get_object_or_404(Folder, id=target_folder, owner=request.user)
        else:
            return Response({'error': 'Either file_id or folder_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        target_user = get_object_or_404(User, id=user_id)

        collab = Collaborator.objects.create(
            user=target_user,
            file_item=target if isinstance(target, FileItem) else None,
            folder=target if isinstance(target, Folder) else None,
            permission=permission
        )

        ActivityLog.log_activity(user=request.user, action='COLLAB_ADD', details={'target': str(target), 'user': target_user.username, 'permission': permission})

        serializer = CollaboratorSerializer(collab)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CollaboratorDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        collab = get_object_or_404(Collaborator, id=pk)
        # Only owner of target may remove collaborator
        if collab.file_item and collab.file_item.owner != request.user:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        if collab.folder and collab.folder.owner != request.user:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        collab.delete()
        ActivityLog.log_activity(user=request.user, action='COLLAB_REMOVE', details={'id': pk})
        return Response({'message': 'Collaborator removed.'}, status=status.HTTP_200_OK)
