# teba/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.core.mail import send_mail
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt



app_name = 'core'  # ADD THIS LINE for namespace support

@csrf_exempt
def test_email(request):
    """Test email functionality"""
    try:
        result = send_mail(
            'Test Email from Teba Paint Center',
            'This is a test email from your Teba application. If you receive this, email configuration is working!',
            settings.DEFAULT_FROM_EMAIL,
            ['kaggaronald1@gmail.com'],
            fail_silently=False,
        )
        return HttpResponse(f"✅ Test email sent successfully! Result: {result}")
    except Exception as e:
        return HttpResponse(f"❌ Email failed: {str(e)}")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('inventory/', include('inventory.urls')),
    path('transactions/', include('transactions.urls')),
    path('test-email/', views.test_email, name='test_email'),  # If you added it heath('core/', include('core.urls')),
    
    # Test email endpoint
    path('test-email/', test_email, name='test_email'),
    
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
]
