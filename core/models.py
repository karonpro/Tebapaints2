from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.functional import classproperty
from django.utils import timezone
from datetime import timedelta
import random
import string


class Location(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('staff', 'Staff'),
        ('cashier', 'Cashier'),
    ]
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff')
    assigned_location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # Email Verification Fields
    email_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    verification_sent_at = models.DateTimeField(blank=True, null=True)
    
    # Permissions
    can_manage_inventory = models.BooleanField(default=False)
    can_manage_sales = models.BooleanField(default=True)
    can_manage_purchases = models.BooleanField(default=False)
    can_manage_customers = models.BooleanField(default=True)
    can_view_reports = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    @property
    def can_access_all_locations(self):
        return self.role == 'admin'

    @classproperty
    def USER_ROLES(cls):
        return cls.ROLE_CHOICES
    
    # Email Verification Methods
    def generate_verification_code(self):
        """Generate a 6-digit verification code"""
        self.verification_code = ''.join(random.choices(string.digits, k=6))
        self.verification_sent_at = timezone.now()
        self.save()
        return self.verification_code
    
    def is_verification_expired(self):
        """Check if verification code is expired (15 minutes)"""
        if not self.verification_sent_at:
            return True
        return timezone.now() > self.verification_sent_at + timedelta(minutes=15)
    
    def verify_email(self, code):
        """Verify email with code"""
        if (self.verification_code == code and 
            not self.is_verification_expired()):
            self.email_verified = True
            self.verification_code = None
            self.verification_sent_at = None
            self.save()
            return True
        return False
    
    def resend_verification_code(self):
        """Generate and return a new verification code"""
        return self.generate_verification_code()


# Signal to create user profile automatically
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class LoginVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    verification_code = models.CharField(max_length=6)
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=15)
    
    class Meta:
        verbose_name = "Login Verification"
        verbose_name_plural = "Login Verifications" 