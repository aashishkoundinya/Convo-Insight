from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter

from apps.call_analyzer.views import CallRecordingViewSet, CallAnalyticsView
from apps.email_generator.views import (
    EmailTemplateViewSet, 
    GeneratedEmailViewSet, 
    ABTestViewSet
)
from apps.core.views import dashboard, profile

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'call-recordings', CallRecordingViewSet, basename='call-recording')
router.register(r'call-analytics', CallAnalyticsView, basename='call-analytics')
router.register(r'email-templates', EmailTemplateViewSet, basename='email-template')
router.register(r'emails', GeneratedEmailViewSet, basename='email')
router.register(r'ab-tests', ABTestViewSet, basename='ab-test')

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API endpoints
    path('api/', include(router.urls)),
    path('api-auth/', include('rest_framework.urls')),
    
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Dashboard views
    path('', dashboard, name='dashboard'),
    path('profile/', profile, name='profile'),
    
    # Call analyzer views
    path('calls/', include('apps.call_analyzer.urls')),
    
    # Email generator views
    path('emails/', include('apps.email_generator.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)