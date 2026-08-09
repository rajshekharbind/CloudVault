from django.urls import path
from . import views

urlpatterns = [
    path('api/analytics/activities/', views.ActivityLogAPIView.as_view(), name='api_activities'),
    path('analytics/activities/clear/', views.clear_recent_activity_view, name='clear_recent_activity'),
    path('api/notifications/', views.NotificationAPIView.as_view(), name='api_notifications'),
]
