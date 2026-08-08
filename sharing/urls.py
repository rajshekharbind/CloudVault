from django.urls import path
from . import views

urlpatterns = [
    # Public share URLs
    path('s/<uuid:token>/', views.public_share_view, name='public_share'),
    path('s/<uuid:token>/download/', views.download_shared_file, name='download_shared'),

    # REST API Share URLs
    path('api/shares/', views.ShareLinkListCreateAPIView.as_view(), name='api_shares'),
    path('api/shares/<int:pk>/', views.ShareLinkDetailAPIView.as_view(), name='api_share_detail'),
    path('api/collaborators/', views.CollaboratorListCreateAPIView.as_view(), name='api_collaborators'),
    path('api/collaborators/<int:pk>/', views.CollaboratorDetailAPIView.as_view(), name='api_collaborator_detail'),
]
