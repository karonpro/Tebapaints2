# core/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

urlpatterns = [
    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/', views.user_detail, name='user_detail'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    
    # Profile & Email Verification
    path('profile/', views.profile_view, name='profile'),
    path('verify-email/', views.verify_email, name='verify_email'),
    path('force-verification/', views.force_verification_test, name='force_verification_test'),
    # SIGNUP VERIFICATION URLS - MAKE SURE THESE EXIST
    path('verify-email-signup/', views.verify_email_signup, name='verify_email_signup'),
    path('resend-signup-verification/', views.resend_signup_verification, name='resend_signup_verification'),
    path('cleanup-verification/', views.cleanup_verification, name='cleanup_verification'),
    # Change Password
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

    # Location Management
    path('locations/', views.location_list, name='location_list'),
    path('locations/add/', views.location_add, name='location_add'),
    path('locations/create/', views.location_create_api, name='location_create_api'),
    path('session-test/', views.session_test, name='session_test'),
    # Authentication & Sessions
    path('google-login/', views.google_login, name='google_login'),
    path('verify-login/', views.verify_login, name='verify_login'),
    path('resend-login-code/', views.resend_login_code, name='resend_login_code'),

]