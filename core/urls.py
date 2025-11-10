# core/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import CustomLoginView

app_name = 'core'

urlpatterns = [
    # Authentication URLs
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    
    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/', views.user_detail, name='user_detail'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('user-permissions/', views.user_permissions, name='user_permissions'),
    path('user-permissions/<int:user_id>/edit/', views.edit_user_permissions, name='edit_user_permissions'),
   
    # Profile & Email Verification
    path('profile/', views.profile_view, name='profile'),
    path('verify-email/', views.verify_email, name='verify_email'),
    
    # Signup Verification URLs
    path('verify-email-signup/', views.verify_email_signup, name='verify_email_signup'),
    path('resend-signup-verification/', views.resend_signup_verification, name='resend_signup_verification'),
    
    # Login Verification URLs
    path('verify-login/', views.verify_login, name='verify_login'),
    path('resend-login-code/', views.resend_login_code, name='resend_login_code'),
    
    # Location Management
    path('locations/', views.location_list, name='location_list'),
    path('locations/add/', views.location_add, name='location_add'),
    path('locations/create/', views.location_create_api, name='location_create_api'),
    
    # Session Management
    path('session-test/', views.session_test, name='session_test'),
    path('session-keepalive/', views.session_keepalive, name='session_keepalive'),
    path('cleanup-verification/', views.cleanup_verification, name='cleanup_verification'),
    path('force-verification-test/', views.force_verification_test, name='force_verification_test'),
    
    # Password Change
    path('change-password/', 
         auth_views.PasswordChangeView.as_view(
             template_name='core/change_password.html',
             success_url='/core/change-password/done/'
         ), 
         name='change_password'),
    path('change-password/done/', 
         auth_views.PasswordChangeDoneView.as_view(
             template_name='core/change_password_done.html'
         ), 
         name='password_change_done'),
    
    # OAuth
    path('google-login/', views.google_login, name='google_login'),
    
    # Test URLs
    path('test-email/', views.test_email_setup, name='test_email'),
    path('test-verification-email/', views.test_verification_email, name='test_verification_email'),
    path('test-environment/', views.test_environment, name='test_environment'),
    
    # Force Verification Redirect
    path('force-verification-redirect/', views.force_verification_redirect, name='force_verification_redirect'),
]
