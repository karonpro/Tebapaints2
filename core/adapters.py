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
import threading
from django.utils import timezone

logger = logging.getLogger(__name__)

class CustomAccountAdapter(DefaultAccountAdapter):
    
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """
        Override to send verification code instead of confirmation link for SIGNUP
        Uses async email sending to prevent worker timeouts
        """
        try:
            user = emailconfirmation.email_address.user
            logger.info(f"🔄 Custom adapter called for user signup: {user.email}")
            
            # Ensure user has a profile
            if not hasattr(user, 'profile'):
                from core.models import UserProfile
                UserProfile.objects.create(user=user)
                logger.info(f"✅ Created profile for user: {user.username}")
            
            # Generate verification code using user profile
            verification_code = user.profile.generate_verification_code()
            logger.info(f"✅ Generated verification code for signup: {verification_code}")
            
            # Store email confirmation data in session
            request.session['pending_email_confirmation_key'] = emailconfirmation.key
            request.session['pending_email'] = emailconfirmation.email_address.email
            request.session['email_confirmation_sent'] = True
            request.session['verification_code'] = verification_code  # For debugging
            request.session.modified = True
            
            # Send verification code email ASYNC
            self._send_verification_code_email_async(user, verification_code, 'signup')
            
            logger.info(f"✅ Verification process initiated for {user.email}")
            return True  # Return True to prevent Allauth from sending its own email
            
        except Exception as e:
            logger.error(f"❌ Error in custom email confirmation for signup: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Fallback to default behavior but still store session data
            try:
                request.session['pending_email_confirmation_key'] = emailconfirmation.key
                request.session['pending_email'] = emailconfirmation.email_address.email
                request.session['email_confirmation_sent'] = True
                request.session.modified = True
            except:
                pass
            
            return super().send_confirmation_mail(request, emailconfirmation, signup)

    def send_login_verification_email(self, request, user, verification_code):
        """
        Send verification code email for LOGIN verification - ASYNC
        """
        logger.info(f"🔄 Sending login verification code to {user.email}")
        self._send_verification_code_email_async(user, verification_code, 'login')

    def _send_verification_code_email_async(self, user, verification_code, purpose='signup'):
        """
        Send verification code email asynchronously to prevent timeouts
        """
        def send_email():
            try:
                context = {
                    'user': user,
                    'verification_code': verification_code,
                    'site_name': getattr(settings, 'SITE_NAME', 'Teba System'),
                    'site_domain': getattr(settings, 'SITE_DOMAIN', 'http://localhost:8000'),
                    'purpose': purpose,
                    'timestamp': timezone.now()
                }
                
                # Set subject based on purpose
                if purpose == 'login':
                    subject = f"Login Verification Code - {context['site_name']}"
                    action_url = f"{context['site_domain']}/core/verify-login/"
                else:  # signup
                    subject = f"Verify Your Email - {context['site_name']}"
                    action_url = f"{context['site_domain']}/core/verify-email-signup/"
                
                # Create email content
                text_content = self._create_email_content(context, purpose, action_url)
                
                # Send email
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@tebasystem.com'),
                    to=[user.email],
                    reply_to=[getattr(settings, 'SUPPORT_EMAIL', 'support@teba.com')],
                )
                
                # Try to add HTML content if template exists
                try:
                    html_content = render_to_string('emails/verification_code.html', context)
                    email.attach_alternative(html_content, "text/html")
                except:
                    pass  # Continue without HTML content
                
                email.send(fail_silently=False)
                logger.info(f"✅ {purpose.capitalize()} verification email sent to {user.email}")
                
            except Exception as e:
                logger.error(f"❌ Failed to send {purpose} verification email to {user.email}: {e}")
                # Still log the code for manual use
                logger.info(f"🔑 MANUAL VERIFICATION CODE for {user.email}: {verification_code}")
        
        # Start email sending in background thread
        email_thread = threading.Thread(target=send_email)
        email_thread.daemon = True
        email_thread.start()

    def _create_email_content(self, context, purpose, action_url):
        """Create email text content"""
        user = context['user']
        verification_code = context['verification_code']
        site_name = context['site_name']
        
        if purpose == 'login':
            return f"""
Login Verification Code - {site_name}

Hello {user.get_full_name() or user.username or user.email},

Your login verification code is: 

{verification_code}

Go to: {action_url}
Enter the code above to complete your login.

This code will expire in 10 minutes.

If you didn't request this login, please ignore this email.

Best regards,
The {site_name} Team
"""
        else:  # signup
            return f"""
Verify Your Email Address - {site_name}

Hello {user.get_full_name() or user.email},

Welcome to {site_name}! Please use the following verification code to confirm your email address:

Verification Code: {verification_code}

Go to: {action_url}
Enter the code above to verify your email and activate your account.

This code will expire in 10 minutes.

If you didn't create an account with {site_name}, please ignore this email.

Best regards,
The {site_name} Team
"""

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
        logger.info(f"🔄 Responding to email verification sent for {user.email}")
        
        # Ensure session data is set
        if not request.session.get('email_confirmation_sent'):
            request.session['email_confirmation_sent'] = True
            request.session.modified = True
            
        return HttpResponseRedirect(reverse('core:verify_email_signup'))

    def is_open_for_signup(self, request):
        """Control whether signup is open"""
        return True

    def save_user(self, request, user, form, commit=True):
        """
        Override user saving to ensure profile is created and initial data is set
        """
        user = super().save_user(request, user, form, commit=False)
        
        # Set additional user data if needed
        if not user.first_name and form.cleaned_data.get('email'):
            # Extract name from email as fallback
            email_name = form.cleaned_data['email'].split('@')[0]
            user.username = email_name  # Ensure username is set
        
        if commit:
            user.save()
            
            # Ensure profile exists
            if not hasattr(user, 'profile'):
                from core.models import UserProfile
                UserProfile.objects.create(user=user)
                logger.info(f"✅ Created user profile for {user.username}")
        
        return user

    def get_login_redirect_url(self, request):
        """Override login redirect to go to inventory after verification"""
        return settings.LOGIN_REDIRECT_URL

    def get_logout_redirect_url(self, request):
        """Override logout redirect"""
        return settings.LOGOUT_REDIRECT_URL

    def clean_email(self, email):
        """
        Add custom email validation if needed
        """
        # You can add custom email validation logic here
        # For example, domain restrictions, etc.
        return super().clean_email(email)

    def validate_unique_email(self, email):
        """
        Validate unique email with custom logic if needed
        """
        return super().validate_unique_email(email)
