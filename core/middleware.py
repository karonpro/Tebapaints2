import time
import logging
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.conf import settings
from django.contrib.sessions.exceptions import SessionInterrupted
from .utils import get_user_locations

logger = logging.getLogger(__name__)

class SessionErrorMiddleware:
    """Middleware to handle session interruptions gracefully"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # Ensure session exists before processing
            if not request.session.session_key:
                request.session.create()
                
            response = self.get_response(request)
            return response
            
        except SessionInterrupted:
            logger.warning("Session interrupted - redirecting to login")
            # Clear problematic session and redirect
            if hasattr(request, 'session'):
                request.session.flush()
            messages.error(request, 'Your session was interrupted. Please log in again.')
            return redirect('account_login')
        except Exception as e:
            logger.error(f"Unexpected error in SessionErrorMiddleware: {e}")
            # Continue with request even if there's an error
            return self.get_response(request)


class LocationAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for admin URLs, static files, and common endpoints
        excluded_paths = [
            '/admin/', '/static/', '/media/', '/accounts/login/', 
            '/accounts/logout/', '/api/', '/health/',
            '/accounts/password/', '/accounts/signup/',
            '/core/profile/', '/core/verify-email-signup/',
            '/core/verify-login/', '/core/session-test/',
            '/inventory/'  # ADD inventory to excluded paths
        ]
        
        if any(request.path.startswith(path) for path in excluded_paths):
            return self.get_response(request)
        
        # Check if user is authenticated and has location access
        if request.user.is_authenticated:
            try:
                from core.models import UserProfile
                from core.utils import get_user_locations
                from django.utils import timezone
                from datetime import timedelta
                
                # Check if profile exists
                profile_exists = UserProfile.objects.filter(user=request.user).exists()
                
                if not profile_exists:
                    # Create profile if it doesn't exist with admin privileges
                    profile = UserProfile.objects.create(user=request.user)
                    
                    # GIVE NEW USERS FULL CONTROL - Set as admin with all permissions
                    profile.role = 'admin'
                    profile.can_manage_inventory = True
                    profile.can_manage_sales = True
                    profile.can_manage_purchases = True
                    profile.can_manage_customers = True
                    profile.can_view_reports = True
                    profile.can_manage_users = True
                    profile.save()
                    
                    logger.info(f"Created admin profile for new user: {request.user.username}")
                    return self.get_response(request)  # Allow immediate access
                
                # Get user profile
                profile = UserProfile.objects.get(user=request.user)
                
                # CHECK IF USER IS NEW (created within last 24 hours)
                is_new_user = (timezone.now() - request.user.date_joined) < timedelta(hours=24)
                
                # If user is new (less than 24 hours old), give full access
                if is_new_user:
                    logger.info(f"New user {request.user.username} has full access (created within 24 hours)")
                    return self.get_response(request)
                
                # For existing users, check location access as before
                user_locations = get_user_locations(request.user)
                can_access_all = profile.can_access_all_locations
                
                if not user_locations.exists() and not can_access_all:
                    # Only redirect if not already going to profile
                    if not request.path.startswith('/core/profile/'):
                        messages.error(
                            request, 
                            "Your account is not assigned to any location. Please update your profile."
                        )
                        return redirect('core:profile')
                            
            except Exception as e:
                logger.error(f"Error in LocationAccessMiddleware for user {request.user.username}: {str(e)}")
                # Don't block access if there's an error - continue normally
                
        return self.get_response(request)


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # Skip for static files and non-authenticated users
            if not request.user.is_authenticated:
                return self.get_response(request)

            # Skip session timeout check for verification URLs
            if request.path.startswith('/core/verify-login/') or request.path.startswith('/core/verify-email-signup/'):
                return self.get_response(request)

            # Ensure session exists before accessing it
            if not request.session.session_key:
                request.session.create()
                request.session['last_activity'] = time.time()
                return self.get_response(request)

            # Check session expiry
            current_time = time.time()
            last_activity = request.session.get('last_activity', current_time)
            
            # Calculate time since last activity
            time_since_last_activity = current_time - last_activity
            
            # If session has expired, log user out
            if time_since_last_activity > settings.SESSION_COOKIE_AGE:
                logger.info(f"Session expired for user {request.user.username}")
                # Save user info before logout
                username = request.user.username
                logout(request)
                request.session.flush()
                messages.warning(request, 'Your session has expired. Please log in again.')
                return redirect('account_login')
            
            # Update last activity time (only if changed significantly)
            if current_time - last_activity > 60:  # Only update every minute to reduce writes
                request.session['last_activity'] = current_time
            
            return self.get_response(request)
            
        except SessionInterrupted:
            logger.warning("Session interrupted in SessionTimeoutMiddleware")
            # Let SessionErrorMiddleware handle this
            raise
        except Exception as e:
            logger.error(f"SessionTimeoutMiddleware error: {e}")
            # If there's an error, just continue with the request
            return self.get_response(request)


class AllauthRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # If user is being redirected to Allauth confirmation page, redirect to our page
        if (request.path == '/accounts/confirm-email/' and 
            request.session.get('email_confirmation_sent')):
            from django.urls import reverse
            from django.shortcuts import redirect
            return redirect('core:verify_email_signup')
            
        return response


class LoginVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check for verification redirect at the VERY BEGINNING
        if (request.session.get('pending_verification_redirect') and 
            not request.user.is_authenticated and
            request.session.get('needs_verification')):
            
            print("DEBUG: Middleware - Redirecting to verification page immediately")
            
            # Clear the flag
            request.session.pop('pending_verification_redirect', None)
            
            # Redirect to verification page
            from django.shortcuts import redirect
            return redirect('core:verify_login')
        
        response = self.get_response(request)
        
        # Also check after processing the response
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Check before each view if we need to redirect to verification
        """
        # If user is trying to access any page but needs verification, redirect
        if (not request.user.is_authenticated and
            request.session.get('needs_verification') and
            not request.path.startswith('/core/verify-login') and
            not request.path.startswith('/static/') and
            not request.path.startswith('/accounts/login/')):
            
            print(f"DEBUG: process_view - Redirecting from {request.path} to verification")
            from django.shortcuts import redirect
            return redirect('core:verify_login')
        
        return None

    def process_response(self, request, response):
        """
        Catch redirects that might be missed
        """
        # If this is a redirect to login but we have verification data
        if (response.status_code == 302 and 
            hasattr(response, 'url') and
            '/accounts/login/' in response.url and
            not request.user.is_authenticated and
            request.session.get('needs_verification')):
            
            print("DEBUG: process_response - Intercepted login redirect")
            from django.shortcuts import redirect
            return redirect('core:verify_login')
        
        return response