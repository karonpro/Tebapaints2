# core/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class CustomAccountAdapter(DefaultAccountAdapter):
    
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """
        Send verification code for signup
        """
        try:
            user = emailconfirmation.email_address.user
            
            # Ensure profile exists
            if not hasattr(user, 'profile'):
                from core.models import UserProfile
                UserProfile.objects.create(user=user)
            
            # Generate verification code
            verification_code = user.profile.generate_verification_code()
            logger.info(f"📧 Signup verification code for {user.email}: {verification_code}")
            
            # Store session data
            request.session.update({
                'pending_email_confirmation_key': emailconfirmation.key,
                'pending_email': emailconfirmation.email_address.email,
                'email_confirmation_sent': True,
            })
            
            # Send email using Django's send_mail
            self._send_verification_email(user, verification_code, 'signup')
            return True
            
        except Exception as e:
            logger.error(f"❌ Error in email confirmation: {e}")
            return super().send_confirmation_mail(request, emailconfirmation, signup)

    def send_login_verification_email(self, request, user, verification_code):
        """
        Send verification code for login
        """
        logger.info(f"📧 Login verification code for {user.email}: {verification_code}")
        self._send_verification_email(user, verification_code, 'login')

    def _send_verification_email(self, user, verification_code, purpose='signup'):
        """
        Simple email sending using Django's send_mail
        """
        try:
            site_name = getattr(settings, 'SITE_NAME', 'Teba System')
            
            if purpose == 'login':
                subject = f"Login Verification Code - {site_name}"
                message = f"""Hello,

Your login verification code is: {verification_code}

This code will expire in 10 minutes.

If you didn't request this login, please ignore this email.

Best regards,
The {site_name} Team"""
            else:
                subject = f"Verify Your Email - {site_name}"
                message = f"""Hello,

Welcome to {site_name}! Your verification code is: {verification_code}

This code will expire in 10 minutes.

If you didn't create an account with {site_name}, please ignore this email.

Best regards,
The {site_name} Team"""

            # Use Django's simple send_mail function
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            
            logger.info(f"✅ Email sent successfully to {user.email}")
            
        except Exception as e:
            logger.error(f"❌ Email sending failed: {e}")
            # Manual code is already logged above

    def get_email_verification_redirect_url(self, email_address):
        return reverse('core:verify_email_signup')

    def respond_email_verification_sent(self, request, user):
        return HttpResponseRedirect(reverse('core:verify_email_signup'))
