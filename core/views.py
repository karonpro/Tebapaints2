from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse, HttpResponse
from django import forms
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import logout
import threading
from django.core.mail import send_mail

from .models import Location, UserProfile, LoginVerification
from .forms import CustomUserCreationForm, CustomUserChangeForm, UserProfileForm
from .utils import get_user_locations, can_user_access_location

from allauth.account.views import LoginView as AllauthLoginView

# Async Email Sending Function
def send_verification_email_async(user_email, verification_code, email_type='login'):
    """Send verification email in background thread to prevent timeouts"""
    def _send_email():
        try:
            subject = 'Your Verification Code'
            if email_type == 'signup':
                subject = 'Welcome to Teba System - Verify Your Email'
            
            message = f'''
Your verification code is: {verification_code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.
'''
            
            send_mail(
                subject,
                message,
                'noreply@tebasystem.com',
                [user_email],
                fail_silently=False,
            )
            print(f"✅ Email sent successfully to {user_email}")
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
    
    # Start email sending in background thread
    email_thread = threading.Thread(target=_send_email)
    email_thread.daemon = True
    email_thread.start()

# Location Management Views
class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'address']

def location_list(request):
    return render(request, 'core/location_list.html', {'locations': Location.objects.all()})

def location_add(request):
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('core:location_list')
    else:
        form = LocationForm()
    return render(request, 'core/location_form.html', {'form': form})

@require_POST
def location_create_api(request):
    name = request.POST.get('name')
    address = request.POST.get('address', '')
    if not name:
        return JsonResponse({'ok': False, 'error': 'name required'}, status=400)
    loc = Location.objects.create(name=name, address=address)
    return JsonResponse({'ok': True, 'id': loc.id, 'name': loc.name})

# User Management Views
def is_admin_user(user):
    """Check if user is admin"""
    return hasattr(user, 'profile') and user.profile.role == 'admin'

@login_required
@user_passes_test(is_admin_user)
def user_list(request):
    """List all users with their roles and locations"""
    users = User.objects.all().select_related('profile').order_by('username')
    
    # Filter by role if specified
    role_filter = request.GET.get('role', '')
    location_filter = request.GET.get('location', '')
    
    if role_filter:
        users = users.filter(profile__role=role_filter)
    
    if location_filter:
        users = users.filter(profile__assigned_location_id=location_filter)
    
    context = {
        'users': users,
        'roles': UserProfile.USER_ROLES,
        'locations': Location.objects.filter(is_active=True),
        'role_filter': role_filter,
        'location_filter': location_filter,
    }
    return render(request, 'core/user_list.html', context)

@login_required
@user_passes_test(is_admin_user)
def user_create(request):
    """Create new user with profile"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created successfully!')
            return redirect('core:user_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    
    context = {
        'form': form,
        'title': 'Create New User',
    }
    return render(request, 'core/user_form.html', context)

@login_required
@user_passes_test(is_admin_user)
def user_edit(request, user_id):
    """Edit user and profile"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} updated successfully!')
            return redirect('core:user_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserChangeForm(instance=user)
    
    context = {
        'form': form,
        'title': f'Edit User: {user.username}',
        'user': user,
    }
    return render(request, 'core/user_form.html', context)

@login_required
@user_passes_test(is_admin_user)
def user_toggle_active(request, user_id):
    """Toggle user active status"""
    user = get_object_or_404(User, id=user_id)
    
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account!')
    else:
        user.is_active = not user.is_active
        user.save()
        status = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'User {user.username} {status} successfully!')
    
    return redirect('core:user_list')

@login_required
@user_passes_test(is_admin_user)
def user_detail(request, user_id):
    """View user details"""
    user = get_object_or_404(User.objects.select_related('profile'), id=user_id)
    
    context = {
        'user_obj': user,
        'title': f'User Details: {user.username}',
    }
    return render(request, 'core/user_detail.html', context)

@login_required
def user_permissions(request):
    if not request.user.profile.role == 'admin':
        messages.error(request, "You don't have permission to manage user permissions.")
        return redirect('core:profile')
    
    users = User.objects.select_related('profile').all().order_by('username')
    
    context = {
        'users': users,
    }
    return render(request, 'core/user_permissions.html', context)

@login_required
def edit_user_permissions(request, user_id):
    if not request.user.profile.role == 'admin':
        messages.error(request, "You don't have permission to edit user permissions.")
        return redirect('core:profile')
    
    user = get_object_or_404(User, id=user_id)
    profile = user.profile
    
    if request.method == 'POST':
        # Update role and permissions
        profile.role = request.POST.get('role', 'staff')
        profile.assigned_location_id = request.POST.get('assigned_location') or None
        
        # Update permissions
        profile.can_manage_inventory = 'can_manage_inventory' in request.POST
        profile.can_manage_sales = 'can_manage_sales' in request.POST
        profile.can_manage_purchases = 'can_manage_purchases' in request.POST
        profile.can_manage_customers = 'can_manage_customers' in request.POST
        profile.can_view_reports = 'can_view_reports' in request.POST
        profile.can_manage_users = 'can_manage_users' in request.POST
        
        profile.save()
        messages.success(request, f"Permissions updated for {user.username}")
        return redirect('core:user_permissions')
    
    locations = Location.objects.all()
    
    context = {
        'edit_user': user,
        'profile': profile,
        'locations': locations,
    }
    return render(request, 'core/edit_user_permissions.html', context)

# Profile & Email Verification Views
@login_required
def profile_view(request):
    """User profile page that automatically sends verification code"""
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # If email is not verified, send verification code automatically (async)
    if not profile.email_verified:
        try:
            verification_code = profile.generate_verification_code()
            send_verification_email_async(request.user.email, verification_code, 'verification')
            messages.info(request, f'Verification code sent to {request.user.email}')
        except Exception as e:
            messages.error(request, f'Error sending verification code: {str(e)}')
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('core:profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileForm(instance=profile)
    
    context = {
        'form': form,
        'user': user,
        'profile': profile,
        'title': 'My Profile',
    }
    return render(request, 'core/profile.html', context)

@login_required
def verify_email(request):
    """Single page for sending and verifying email code"""
    profile = request.user.profile
    
    if request.method == 'POST':
        # Check if user is requesting to resend code
        if 'resend_code' in request.POST:
            try:
                verification_code = profile.generate_verification_code()
                send_verification_email_async(request.user.email, verification_code, 'verification')
                messages.success(request, 'New verification code sent to your email!')
            except Exception as e:
                messages.error(request, f'Error sending verification code: {str(e)}')
            return redirect('core:verify_email')
        
        # Check if user is submitting verification code
        elif 'verify_code' in request.POST:
            entered_code = request.POST.get('verification_code', '').strip()
            
            try:
                # Check if code is expired
                if profile.is_verification_expired():
                    messages.error(request, 'Verification code has expired. Please request a new one.')
                    return redirect('core:verify_email')
                
                # Verify the code
                if profile.verify_email(entered_code):
                    messages.success(request, 'Email verified successfully!')
                    return redirect('core:profile')
                else:
                    messages.error(request, 'Invalid verification code. Please try again.')
                    
            except Exception as e:
                messages.error(request, f'Error verifying code: {str(e)}')
    
    # If GET request or after resend, show verification page
    context = {
        'profile': profile,
        'email': request.user.email,
    }
    return render(request, 'core/verify_email.html', context)

# Authentication Views
def google_login(request):
    """Redirect to Google OAuth"""
    from django.conf import settings
    if not settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {}).get('client_id'):
        messages.error(request, 'Google authentication is not configured. Please contact administrator.')
        return redirect('account_login')
    
    # This will be handled by allauth
    return redirect('socialaccount_login', 'google')

@login_required
def session_timeout_test(request):
    """Test view to check session timeout - used for keep-alive"""
    return JsonResponse({'status': 'ok'})

# Email Verification for Signup
def verify_email_signup(request):
    """
    Verify email during signup with code instead of link
    """
    pending_email = request.session.get('pending_email')
    pending_key = request.session.get('pending_email_confirmation_key')
    
    print(f"DEBUG: verify_email_signup - pending_email={pending_email}, pending_key={pending_key}")
    
    if not pending_email or not pending_key:
        messages.error(request, 'Session expired. Please sign up again.')
        return redirect('account_signup')
    
    # Check if user is already verified via allauth AND profile
    try:
        from allauth.account.models import EmailAddress
        email_addr = EmailAddress.objects.get(email=pending_email, verified=True)
        
        # Also check if user has verified profile
        user = email_addr.user
        if hasattr(user, 'profile') and user.profile.email_verified:
            # User is fully verified - log them in and redirect
            user.backend = 'allauth.account.auth_backends.AuthenticationBackend'
            login(request, user)
            
            # Clean up session
            request.session.pop('pending_email', None)
            request.session.pop('pending_email_confirmation_key', None)
            request.session.pop('email_confirmation_sent', None)
            
            messages.success(request, 'Email already verified! Welcome to Teba System.')
            return redirect('inventory:index')
        else:
            # Allauth says verified but profile doesn't - fix the profile
            if hasattr(user, 'profile'):
                user.profile.email_verified = True
                user.profile.save()
                print(f"DEBUG: Fixed profile verification for {user.username}")
                
            # Log them in and redirect
            user.backend = 'allauth.account.auth_backends.AuthenticationBackend'
            login(request, user)
            
            # Clean up session
            request.session.pop('pending_email', None)
            request.session.pop('pending_email_confirmation_key', None)
            request.session.pop('email_confirmation_sent', None)
            
            messages.success(request, 'Email verified! Welcome to Teba System.')
            return redirect('inventory:index')
            
    except EmailAddress.DoesNotExist:
        pass  # Continue with verification
    
    if request.method == 'POST':
        entered_code = request.POST.get('verification_code', '').strip()
        print(f"DEBUG: Entered code: {entered_code}")
        
        try:
            # Get the email confirmation
            from allauth.account.models import EmailConfirmation
            email_confirmation = EmailConfirmation.objects.get(key=pending_key)
            user = email_confirmation.email_address.user
            print(f"DEBUG: Found user: {user.username}")
            print(f"DEBUG: User profile exists: {hasattr(user, 'profile')}")
            
            # Check if user has profile
            if not hasattr(user, 'profile'):
                messages.error(request, 'User profile not found. Please contact support.')
                print(f"DEBUG: No profile found for user {user.username}")
                return redirect('account_signup')
            
            profile = user.profile
            print(f"DEBUG: Profile verification_code: {profile.verification_code}")
            print(f"DEBUG: Profile email_verified: {profile.email_verified}")
            print(f"DEBUG: Verification expired: {profile.is_verification_expired()}")
            
            # Check if verification code exists and is not expired
            if not profile.verification_code:
                messages.error(request, 'No verification code found. Please request a new code.')
                print(f"DEBUG: No verification code in profile")
                
            elif profile.is_verification_expired():
                messages.error(request, 'Verification code has expired. Please request a new code.')
                print(f"DEBUG: Verification code expired")
                
            # Verify the code using user profile
            elif profile.verify_email(entered_code):
                print(f"DEBUG: Verification successful!")
                
                # Confirm the email address in allauth
                email_confirmation.confirm(request)
                
                # Log the user in
                user.backend = 'allauth.account.auth_backends.AuthenticationBackend'
                login(request, user)
                
                # Clean up session
                request.session.pop('pending_email', None)
                request.session.pop('pending_email_confirmation_key', None)
                request.session.pop('email_confirmation_sent', None)
                
                messages.success(request, 'Email verified successfully! Welcome to Teba System.')
                return redirect('inventory:index')
            else:
                print(f"DEBUG: Verification failed - code mismatch or other issue")
                messages.error(request, 'Invalid verification code. Please try again.')
                
        except EmailConfirmation.DoesNotExist:
            messages.error(request, 'Verification session expired. Please sign up again.')
            print(f"DEBUG: EmailConfirmation with key {pending_key} not found")
            return redirect('account_signup')
        except Exception as e:
            messages.error(request, f'Error verifying email: {str(e)}')
            print(f"DEBUG: Exception: {e}")
    
    context = {
        'pending_email': pending_email,
    }
    return render(request, 'core/verify_email_standalone.html', context)

def resend_signup_verification(request):
    """
    Resend verification code during signup
    """
    pending_email = request.session.get('pending_email')
    pending_key = request.session.get('pending_email_confirmation_key')
    
    if not pending_email or not pending_key:
        messages.error(request, 'Session expired. Please sign up again.')
        return redirect('account_signup')
    
    try:
        from allauth.account.models import EmailConfirmation
        email_confirmation = EmailConfirmation.objects.get(key=pending_key)
        user = email_confirmation.email_address.user
        
        if hasattr(user, 'profile'):
            verification_code = user.profile.generate_verification_code()
            
            # Send async email
            send_verification_email_async(user.email, verification_code, 'signup')
            
            messages.success(request, 'New verification code sent to your email!')
        else:
            messages.error(request, 'Error resending verification code.')
            
    except Exception as e:
        messages.error(request, f'Error resending verification code: {str(e)}')
    
    return redirect('core:verify_email_signup')

def force_verification_redirect(request):
    """
    Manual redirect from Allauth confirmation page to our code verification
    """
    if request.session.get('email_confirmation_sent'):
        return redirect('core:verify_email_signup')
    else:
        # If no code was sent, redirect to signup
        messages.info(request, 'Please sign up first to receive a verification code.')
        return redirect('account_signup')

# Login Verification Views
class CustomLoginView(AllauthLoginView):
    def form_valid(self, form):
        print("DEBUG: CustomLoginView - Processing login")
        
        # Call parent to handle authentication
        response = super().form_valid(form)
        
        # If login successful and verification needed
        if (self.request.user.is_authenticated and 
            not self.request.session.get('login_verified')):
            
            user = self.request.user
            print(f"DEBUG: CustomLoginView - {user.username} needs verification")
            
            if hasattr(user, 'profile'):
                # Generate verification code
                verification_code = user.profile.generate_verification_code()
                print(f"✅ Verification code: {verification_code}")
                
                # Store verification in database
                verification = LoginVerification.objects.create(
                    user=user,
                    verification_code=verification_code,
                    session_key=self.request.session.session_key
                )
                print(f"✅ Verification stored in database with ID: {verification.id}")
                
                # Send email ASYNC to prevent timeout
                try:
                    send_verification_email_async(user.email, verification_code, 'login')
                    print(f"✅ Email sending initiated for {user.email}")
                except Exception as e:
                    print(f"❌ Email failed: {e}")
                    # Still continue with manual code display
                    print(f"MANUAL CODE: {verification_code}")
                
                # Store minimal session data before logout
                verification_id = verification.id
                
                # Logout and redirect with verification ID
                logout(self.request)
                
                # Preserve the verification ID in session
                self.request.session['pending_verification_id'] = verification_id
                self.request.session.save()
                
                # Redirect to verification page
                from django.urls import reverse
                verification_url = reverse('core:verify_login') + f'?vid={verification_id}'
                return redirect(verification_url)
        
        return response

def verify_login(request):
    """
    Verify login with code sent to email - IMPROVED VERSION
    """
    print(f"DEBUG: verify_login called - User authenticated: {request.user.is_authenticated}")
    
    # Handle POST request - code verification
    if request.method == 'POST':
        verification_id = request.POST.get('verification_id') or request.session.get('pending_verification_id')
        entered_code = request.POST.get('verification_code', '').strip()
        
        print(f"DEBUG: Verification attempt - ID: {verification_id}, Code: {entered_code}")
        
        if verification_id and entered_code:
            try:
                verification = LoginVerification.objects.get(
                    id=verification_id, 
                    is_used=False
                )
                
                # Check if expired
                if verification.is_expired():
                    verification.delete()
                    request.session.pop('pending_verification_id', None)
                    messages.error(request, 'Verification code has expired. Please login again.')
                    return redirect('account_login')
                
                # Verify the code
                if verification.verification_code == entered_code:
                    print("DEBUG: Database verification successful")
                    # Mark as used
                    verification.is_used = True
                    verification.save()
                    
                    # Log the user in
                    from django.contrib.auth import login
                    user = verification.user
                    
                    # Set the backend explicitly
                    user.backend = 'allauth.account.auth_backends.AuthenticationBackend'
                    login(request, user)
                    
                    # Clean up session
                    request.session.pop('pending_verification_id', None)
                    request.session['login_verified'] = True
                    
                    messages.success(request, 'Login verified successfully!')
                    return redirect('/inventory/')
                else:
                    messages.error(request, 'Invalid verification code. Please try again.')
                    
            except LoginVerification.DoesNotExist:
                messages.error(request, 'Invalid verification session. Please login again.')
                request.session.pop('pending_verification_id', None)
                return redirect('account_login')
        else:
            messages.error(request, 'Please enter the verification code.')
    
    # Handle GET request - show verification form
    verification_id = request.GET.get('vid') or request.session.get('pending_verification_id')
    verification = None
    user = None
    pending_email = None
    
    if verification_id:
        try:
            verification = LoginVerification.objects.get(
                id=verification_id, 
                is_used=False
            )
            print(f"DEBUG: Found verification record: {verification.id}")
            
            # Check if expired
            if verification.is_expired():
                verification.delete()
                request.session.pop('pending_verification_id', None)
                messages.error(request, 'Verification code has expired. Please login again.')
                return redirect('account_login')
                
            user = verification.user
            pending_email = user.email
            # Store in session for POST requests
            request.session['pending_verification_id'] = verification_id
                
        except LoginVerification.DoesNotExist:
            print("DEBUG: No verification record found")
            messages.error(request, 'Invalid verification session. Please login again.')
            request.session.pop('pending_verification_id', None)
            return redirect('account_login')
    
    # If user is already logged in and verified, redirect them
    if request.user.is_authenticated and request.session.get('login_verified'):
        return redirect('/inventory/')
    
    # Check if we have a valid verification
    if not verification:
        messages.error(request, 'Please login first.')
        return redirect('account_login')
    
    # SHOW THE VERIFICATION FORM
    print("DEBUG: Showing verification form")
    context = {
        'pending_email': pending_email,
        'verification_id': verification_id,
        'manual_code': verification.verification_code,  # For testing
    }
    return render(request, 'core/verify_login.html', context)

def resend_login_code(request):
    """
    Resend login verification code - ASYNC VERSION
    """
    verification_id = request.session.get('pending_verification_id')
    
    if verification_id:
        try:
            verification = LoginVerification.objects.get(id=verification_id)
            user = verification.user
            
            # Generate new code
            new_code = user.profile.generate_verification_code()
            
            # Update verification record
            verification.verification_code = new_code
            verification.created_at = timezone.now()
            verification.is_used = False
            verification.save()
            
            # Send email ASYNC
            send_verification_email_async(user.email, new_code, 'login')
            
            messages.info(request, 'New verification code sent to your email.')
            print(f"✅ New code sent: {new_code}")
            
        except (LoginVerification.DoesNotExist, User.DoesNotExist):
            messages.error(request, 'Session expired. Please login again.')
            request.session.pop('pending_verification_id', None)
            return redirect('account_login')
    
    return redirect('core:verify_login')

# Testing and Utility Views
def force_verification_test(request):
    """
    Force the verification flow for testing
    """
    if request.user.is_authenticated:
        user = request.user
        print(f"DEBUG: User {user.username} is authenticated, forcing verification")
        
        if hasattr(user, 'profile'):
            verification_code = user.profile.generate_verification_code()
            
            # Store verification session data
            request.session['needs_verification'] = True
            request.session['verification_user_id'] = user.id
            request.session['pending_email'] = user.email
            request.session['verification_sent'] = True
            request.session['next_url'] = '/inventory/'
            request.session['manual_verification_code'] = verification_code
            
            print(f"TEST: Verification code: {verification_code}")
            
            # Log user out and redirect to verification
            logout(request)
            return redirect('core:verify_login')
        else:
            return HttpResponse("User has no profile")
    else:
        return HttpResponse("Please login first at /accounts/login/ then visit this page")

def cleanup_verification(request):
    """
    Clean up any stuck verification sessions
    """
    request.session.pop('pending_verification_id', None)
    request.session.pop('verification_temp_data', None)
    request.session.pop('needs_verification', None)
    request.session.pop('verification_user_id', None)
    request.session.pop('pending_email', None)
    messages.info(request, 'Verification session cleared. Please login again.')
    return redirect('account_login')

@require_http_methods(["GET"])
def session_test(request):
    """Simple endpoint to test session and keep it alive"""
    return JsonResponse({
        'status': 'success', 
        'user': request.user.username if request.user.is_authenticated else 'anonymous',
        'session_active': True
    })

@require_http_methods(["POST"])
@csrf_exempt
def session_keepalive(request):
    """Endpoint to keep session alive - exempt from CSRF for simplicity"""
    return JsonResponse({
        'status': 'success', 
        'message': 'Session kept alive',
        'timestamp': timezone.now().isoformat()
    })

from django.core.mail import EmailMessage
from django.http import JsonResponse, HttpResponse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def test_email_setup(request):
    """Test basic email functionality"""
    try:
        email = EmailMessage(
            subject='🧪 Teba System - Email Test',
            body='If you receive this, SendGrid is working correctly!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.ADMIN_EMAIL],
        )
        email.send(fail_silently=False)
        
        return JsonResponse({
            'status': 'success', 
            'message': '✅ Test email sent successfully!',
            'from_email': settings.DEFAULT_FROM_EMAIL,
            'to_email': settings.ADMIN_EMAIL,
            'sendgrid_key': '✅ Set' if settings.SENDGRID_API_KEY else '❌ Missing'
        })
    except Exception as e:
        logger.error(f"Test email failed: {e}")
        return JsonResponse({
            'status': 'error', 
            'message': str(e),
            'from_email': settings.DEFAULT_FROM_EMAIL,
            'sendgrid_key': '✅ Set' if settings.SENDGRID_API_KEY else '❌ Missing'
        })

def test_verification_email(request):
    """Test verification email (like what users receive)"""
    try:
        from core.adapters import CustomAccountAdapter
        
        # Create a test user or use current user
        from django.contrib.auth.models import User
        test_user = User.objects.filter(email=settings.ADMIN_EMAIL).first()
        if not test_user:
            test_user = User.objects.first()
        
        if not test_user:
            return JsonResponse({'status': 'error', 'message': 'No users found to test with'})
        
        verification_code = "123456"  # Test code
        adapter = CustomAccountAdapter()
        adapter._send_verification_email(test_user, verification_code, 'login')
        
        return JsonResponse({
            'status': 'success', 
            'message': '✅ Verification email test sent!',
            'to_user': test_user.email,
            'verification_code': verification_code
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def test_environment(request):
    """Check environment variables"""
    return JsonResponse({
        'sendgrid_api_key_set': bool(settings.SENDGRID_API_KEY),
        'from_email': settings.DEFAULT_FROM_EMAIL,
        'admin_email': settings.ADMIN_EMAIL,
        'email_backend': settings.EMAIL_BACKEND,
        'debug_mode': settings.DEBUG
    })

# core/views.py
from django.core.mail import send_mail
from django.http import HttpResponse
from django.conf import settings

def test_email(request):
    try:
        send_mail(
            'Test Email from Teba',
            'This is a test email from your Teba application.',
            settings.DEFAULT_FROM_EMAIL,
            ['kaggaronald1@gmail.com'],  # Your email
            fail_silently=False,
        )
        return HttpResponse("Test email sent successfully!")
    except Exception as e:
        return HttpResponse(f"Email failed: {str(e)}")
