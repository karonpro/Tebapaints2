# core/emails.py
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def send_password_reset_email(user, reset_url):
    """Send password reset email"""
    context = {
        'user': user,
        'password_reset_url': reset_url,
        'site_name': settings.SITE_NAME,
    }
    
    # Render HTML content
    html_content = render_to_string('account/email/password_reset_key.html', context)
    text_content = strip_tags(html_content)
    
    subject = f"Password Reset Request for {settings.SITE_NAME}"
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()
    
    return True

def send_welcome_email(user):
    """Send welcome email to new users"""
    subject = f"Welcome to {settings.SITE_NAME}"
    message = f"""
    Hello {user.get_full_name() or user.email},
    
    Welcome to {settings.SITE_NAME}! Your account has been successfully created.
    
    You can now log in and start using our system.
    
    Best regards,
    The {settings.SITE_NAME} Team
    """
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

def send_notification_email(subject, message, recipient_list):
    """Send general notification email"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )

def send_html_email(subject, template_name, context, recipient_list):
    """Send HTML email with template"""
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

# =======================
# EMAIL VERIFICATION FUNCTIONS - ADD THESE
# =======================

def send_verification_code_email(user, verification_code):
    """Send verification code email"""
    context = {
        'user': user,
        'verification_code': verification_code,
        'site_name': settings.SITE_NAME,
    }
    
    # Render HTML content
    html_content = render_to_string('emails/verification_code.html', context)
    text_content = render_to_string('emails/verification_code.txt', context)
    
    subject = f"Verify Your Email - {settings.SITE_NAME}"
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
        reply_to=['support@teba.com'],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()
    
    return True

def send_email_change_verification(user, new_email, verification_code):
    """Send verification for email change"""
    context = {
        'user': user,
        'new_email': new_email,
        'verification_code': verification_code,
        'site_name': settings.SITE_NAME,
    }
    
    html_content = render_to_string('emails/email_change_verification.html', context)
    text_content = render_to_string('emails/email_change_verification.txt', context)
    
    subject = f"Confirm Your Email Change - {settings.SITE_NAME}"
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[new_email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_login_verification_email(user, verification_code):
    """Send verification code for login"""
    context = {
        'user': user,
        'verification_code': verification_code,
        'site_name': settings.SITE_NAME,
    }
    
    html_content = render_to_string('emails/login_verification.html', context)
    text_content = render_to_string('emails/login_verification.txt', context)
    
    subject = f"Login Verification Code - {settings.SITE_NAME}"
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()
    
    return True

def send_test_email(recipient=None):
    """Test email with noreply@teba.com sender"""
    recipient = recipient or settings.ADMINS[0][1]
    
    send_mail(
        subject=f'Test Email from {settings.SITE_NAME}',
        message='This is a test email to verify the noreply@teba.com sender is working correctly.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )
    return True