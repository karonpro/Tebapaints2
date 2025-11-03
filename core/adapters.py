# core/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account import app_settings
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class CustomAccountAdapter(DefaultAccountAdapter):
    
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """
        Override to send verification code instead of confirmation link for SIGNUP
        """
        try:
            user = emailconfirmation.email_address.user
            logger.info(f"🔄 Custom adapter called for user signup: {user.email}")
            
            # Generate verification code using user profile
            if hasattr(user, 'profile'):
                verification_code = user.profile.generate_verification_code()
                logger.info(f"✅ Generated verification code for signup: {verification_code}")
                
                # Send verification code email
                self._send_verification_code_email(user, verification_code, 'signup')
                
                # Store email confirmation key in session for verification
                request.session['pending_email_confirmation_key'] = emailconfirmation.key
                request.session['pending_email'] = emailconfirmation.email_address.email
                request.session['email_confirmation_sent'] = True
                request.session.modified = True
                
                logger.info(f"✅ Verification code sent to {user.email} for signup")
                return True  # Return True to prevent Allauth from sending its own email
                
        except Exception as e:
            logger.error(f"❌ Error in custom email confirmation for signup: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # If anything fails, let Allauth handle it
        logger.info("🔄 Falling back to default email confirmation for signup")
        return super().send_confirmation_mail(request, emailconfirmation, signup)

    def send_verification_email(self, request, user, verification_code):
        """
        Send verification code email for LOGIN verification
        """
        logger.info(f"🔄 Sending login verification code to {user.email}")
        self._send_verification_code_email(user, verification_code, 'login')

    def _send_verification_code_email(self, user, verification_code, purpose='signup'):
        """Send verification code email for both login and signup"""
        context = {
            'user': user,
            'verification_code': verification_code,
            'site_name': settings.SITE_NAME,
            'purpose': purpose
        }
        
        # Set subject based on purpose
        if purpose == 'login':
            subject = f"Login Verification Code - {settings.SITE_NAME}"
            action_url = f"{settings.SITE_DOMAIN}/core/verify-login/"
        else:  # signup
            subject = f"Verify Your Email - {settings.SITE_NAME}"
            action_url = f"{settings.SITE_DOMAIN}/core/verify-email-signup/"
        
        try:
            # Try to render templates
            html_content = render_to_string('emails/verification_code.html', context)
            text_content = render_to_string('emails/verification_code.txt', context)
        except Exception as e:
            # Fallback to simple text email
            logger.warning(f"Template error, using fallback email: {e}")
            
            if purpose == 'login':
                text_content = f"""
                Login Verification Code

                Hello {user.get_full_name() or user.username},

                Your login verification code is: {verification_code}

                Go to: {action_url}
                Enter the code above to complete your login.

                This code will expire in 15 minutes.

                If you didn't request this login, please ignore this email.

                Best regards,
                The {settings.SITE_NAME} Team
                """
            else:  # signup
                text_content = f"""
                Verify Your Email Address

                Hello {user.get_full_name() or user.email},

                Please use the following verification code to confirm your email address for {settings.SITE_NAME}:

                Verification Code: {verification_code}

                Go to: {action_url}
                Enter the code above to verify your email.

                This code will expire in 15 minutes.

                Best regards,
                The {settings.SITE_NAME} Team
                """
            html_content = None
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            reply_to=['support@teba.com'],
        )
        
        if html_content:
            email.attach_alternative(html_content, "text/html")
        
        email.send()
        logger.info(f"✅ {purpose.capitalize()} verification email sent to {user.email}")

    def get_email_confirmation_redirect_url(self, request):
        """
        Redirect to our code verification page after signup
        """
        logger.info("🔄 Redirecting to custom verification page after signup")
        return reverse('core:verify_email_signup')

    def respond_email_verification_sent(self, request, user):
        """
        Respond after email verification is sent - redirect to our code verification page
        """
        logger.info("🔄 Responding to email verification sent for signup")
        return HttpResponseRedirect(reverse('core:verify_email_signup'))

    def is_open_for_signup(self, request):
        return True

    def save_user(self, request, user, form, commit=True):
        """
        Override user saving to ensure profile is created
        """
        user = super().save_user(request, user, form, commit=False)
        if commit:
            user.save()
        return user