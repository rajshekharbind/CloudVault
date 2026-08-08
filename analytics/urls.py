from django.urls import path
from . import views

urlpatterns = [
    path('api/analytics/activities/', views.ActivityLogAPIView.as_view(), name='api_activities'),
    path('api/notifications/', views.NotificationAPIView.as_view(), name='api_notifications'),
]
