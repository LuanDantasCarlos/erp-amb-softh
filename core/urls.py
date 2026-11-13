from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views_integracao import ImportarSoulMVView
from .views import PacienteViewSet, TemplateDocumentoViewSet, DocumentoViewSet, CampoTemplateDocumentoViewSet
from .views_site import (
    home, 
    paciente_list, paciente_create, paciente_update, paciente_detail, paciente_documentos,
    template_list, template_create, template_update, template_detail,
    documento_list, documento_detail, documento_download, gerar_documento, campos_template_json, paciente_json,
    valores_automaticos,
)

router = DefaultRouter()
router.register(r'pacientes', PacienteViewSet)
router.register(r'templates', TemplateDocumentoViewSet)
router.register(r'documentos', DocumentoViewSet)
router.register(r'campos_template', CampoTemplateDocumentoViewSet)


api_urlpatterns = [
    path('', include(router.urls)),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('integracao/soulmv/importar/', ImportarSoulMVView.as_view(), name='soulmv_importar'),
]

site_urlpatterns = [
    path('', home, name='home'),

    # Auth
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

    path('campos_template_json/<int:template_id>/', campos_template_json, name='campos_template_json'),
    path('paciente_json/<int:paciente_id>/', paciente_json, name='paciente_json'),
    path('valores_automaticos/', valores_automaticos, name='valores_automaticos'),



    # Documentos
    path('documentos/', documento_list, name='documento_list'),
    path('documentos/<int:pk>/', documento_detail, name='documento_detail'),
    path('documentos/<int:pk>/download/', documento_download, name='documento_download'),
    path('gerar-documento/', gerar_documento, name='gerar_documento'),
]

urlpatterns = api_urlpatterns + site_urlpatterns
