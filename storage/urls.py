from django.urls import path
from . import views

urlpatterns = [
    # Page Navigation URLs
    path('', views.dashboard_view, name='dashboard'),
    path('files/', views.files_view, name='files'),
    path('favorites/', views.favorites_view, name='favorites'),
    path('shared/', views.shared_view, name='shared'),
    path('trash/', views.trash_view, name='trash'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('sentinel/', views.sentinel_dashboard_view, name='sentinel'),
    path('security/', views.sentinel_dashboard_view, name='security_dashboard'),
    path('admin-panel/', views.admin_panel_view, name='admin_panel'),

    # File Download & Preview URLs
    path('files/<int:file_id>/download/', views.download_file_view, name='download_file'),
    path('files/<int:file_id>/preview/', views.preview_file_content_view, name='preview_file_content'),

    # REST APIs
    path('api/files/upload/', views.UploadFileAPIView.as_view(), name='api_file_upload'),
    path('api/folders/', views.FolderListCreateAPIView.as_view(), name='api_folders'),
    path('api/files/<int:pk>/', views.FileItemDetailAPIView.as_view(), name='api_file_detail'),
    path('api/items/<int:pk>/restore/', views.RestoreItemAPIView.as_view(), name='api_restore_item'),
    path('api/files/compress/', views.CompressZipAPIView.as_view(), name='api_compress_zip'),
    path('api/scan-url/', views.scan_url_api, name='api_scan_url'),
]
