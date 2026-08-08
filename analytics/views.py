from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from django.db.models import Count, Sum
from .models import ActivityLog, Notification

class ActivityLogAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        logs = ActivityLog.objects.filter(user=request.user)[:20]
        data = [{
            'id': log.id,
            'action': log.get_action_display(),
            'details': log.get_details_dict(),
            'ip_address': log.ip_address,
            'timestamp': log.timestamp.strftime('%b %d, %Y %H:%M')
        } for log in logs]
        return Response(data)

class NotificationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)[:10]
        data = [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.notification_type,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%b %d, %H:%M')
        } for n in notifications]
        return Response(data)

    def post(self, request):
        # Mark all as read
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})
