# teba/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.shortcuts import redirect
from core.views import CustomLoginView  # ADD THIS IMPORT
from django.conf import settings  # ADD THIS IMPORT

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Apps
    path('', include('transactions.urls', namespace='transactions')),
    path('core/', include('core.urls', namespace='core')),
    path('inventory/', include('inventory.urls', namespace='inventory')),
    
    # Override Allauth login with our custom view
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    
    # Allauth other URLs (keep the rest)
    path('accounts/', include('allauth.urls')),
    
    # Home page
    path('home/', TemplateView.as_view(template_name='home.html'), name='home'),
   
    # Redirect root to transactions home
    path('', lambda request: redirect('transactions:home')),
]

