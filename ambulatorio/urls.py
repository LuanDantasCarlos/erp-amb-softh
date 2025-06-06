"""
URL configuration for ambulatorio project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Import site URLs from core.urls
from core.urls import site_urlpatterns

# Swagger/OpenAPI Schema configuration
schema_view = get_schema_view(
    openapi.Info(
        title="Sistema de Gerenciamento Ambulatorial API",
        default_version='v1',
        description="API para gerenciamento de pacientes e documentos médicos",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="contato@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    
    # Documentation URLs
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Redirect /accounts/login/ to /login/
    path('accounts/login/', include('django.contrib.auth.urls')),
]

# Add site URLs
urlpatterns += site_urlpatterns

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns.append(path('__debug__/', include('debug_toolbar.urls')))
