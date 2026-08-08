from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    # Template Auth URLs
    path('login/', views.login_view, name='login'),
    path('accounts/login/', views.login_view),
    path('register/', views.register_view, name='register'),
    path('accounts/register/', views.register_view),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),

    # REST API Auth URLs
    path('api/auth/register/', views.RegisterAPIView.as_view(), name='api_register'),
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/me/', views.UserProfileAPIView.as_view(), name='api_profile'),
]
