from django.urls import path
from . import views
app_name='reports'
urlpatterns=[path('daily/', views.daily_report, name='daily'), path('daily/export/', views.daily_export, name='daily_export')]
