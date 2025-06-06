"""
URLs for the core app
"""
from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import PacienteViewSet, TemplateDocumentoViewSet, DocumentoViewSet, GerarPrescricaoPDFView
from .views_site import (
    home, 
    paciente_list, paciente_create, paciente_update, paciente_detail, paciente_documentos,
    template_list, template_create, template_update, template_detail,
    documento_list, documento_detail, documento_download, gerar_documento
)

# Create a router and register our API viewsets with it
router = DefaultRouter()
router.register(r'pacientes', PacienteViewSet)
router.register(r'templates', TemplateDocumentoViewSet)
router.register(r'documentos', DocumentoViewSet)

# API URLs
api_urlpatterns = [
    # API endpoints
    path('', include(router.urls)),
    
    # Authentication endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

# Site URLs
site_urlpatterns = [
    # Home
    path('', home, name='home'),
    
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Pacientes
    path('pacientes/', paciente_list, name='paciente_list'),
    path('pacientes/novo/', paciente_create, name='paciente_create'),
    path('pacientes/<int:pk>/', paciente_detail, name='paciente_detail'),
    path('pacientes/<int:pk>/editar/', paciente_update, name='paciente_update'),
    path('pacientes/<int:pk>/documentos/', paciente_documentos, name='paciente_documentos'),
    
    # Templates
    path('templates/', template_list, name='template_list'),
    path('templates/novo/', template_create, name='template_create'),
    path('templates/<int:pk>/', template_detail, name='template_detail'),
    path('templates/<int:pk>/editar/', template_update, name='template_update'),
    
    # Documentos
    path('documentos/', documento_list, name='documento_list'),
    path('documentos/<int:pk>/', documento_detail, name='documento_detail'),
    path('documentos/<int:pk>/download/', documento_download, name='documento_download'),
    path('gerar-documento/', gerar_documento, name='gerar_documento'),
    path("gerar-prescricao/", GerarPrescricaoPDFView.as_view(), name="gerar_prescricao"),

]

# Combine API and Site URLs
urlpatterns = [
    path('api/', include(api_urlpatterns)),
] + site_urlpatterns
