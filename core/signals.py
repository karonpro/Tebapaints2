# core/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import logout
from .models import UserProfile

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

# COMMENTED OUT - Login verification is now handled by CustomLoginView
# @receiver(user_logged_in)
# def require_verification_on_login(sender, request, user, **kwargs):
#     """
#     Require email verification after every login
#     """
#     # Skip if already verified in this session
#     if request.session.get('login_verified'):
#         print("DEBUG: User already verified, skipping verification")
#         return
#     
#     print(f"DEBUG: Signal - Starting verification for user {user.username}")
#     
#     # Generate and send verification code
#     if hasattr(user, 'profile'):
#         verification_code = user.profile.generate_verification_code()
#         print(f"DEBUG: Signal - Generated code: {verification_code}")
#         
#         # Store verification session data
#         request.session['needs_verification'] = True
#         request.session['verification_user_id'] = user.id
#         request.session['pending_email'] = user.email
#         request.session['verification_sent'] = True
#         request.session['next_url'] = '/inventory/'
#         
#         try:
#             from core.adapters import CustomAccountAdapter
#             adapter = CustomAccountAdapter()
#             adapter.send_verification_email(request, user, verification_code)
#             print(f"✅ Signal - Code sent: {verification_code}")
#         except Exception as e:
#             request.session['manual_verification_code'] = verification_code
#             print(f"MANUAL: Signal - Code: {verification_code}")
#         
#         # Don't log out here - let the custom login view handle it
#         # Just set a flag that the custom view can check
#         request.session['pending_custom_verification'] = True
#         print("DEBUG: Signal - Verification flag set")