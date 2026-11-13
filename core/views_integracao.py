"""Endpoint do Plano C: máquina externa envia o CSV do Soul MV para importação (spec §5)."""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import ContextManager, Optional

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.integracao.soulmv.importador import importar_conteudo
from core.integracao.soulmv.job import NOME_LOCK
from core.integracao.soulmv.lock import LockOcupado, lock_arquivo
from core.models import ExecucaoImportacao


def _caminho_lock() -> Optional[Path]:
    if settings.SOULMV_LOCK_FILE:
        return Path(settings.SOULMV_LOCK_FILE)
    if settings.SOULMV_INBOX_DIR:
        return Path(settings.SOULMV_INBOX_DIR) / NOME_LOCK
    return None


def _lock() -> ContextManager[object]:
    caminho = _caminho_lock()
    if caminho is None:
        return contextlib.nullcontext()
    return lock_arquivo(caminho, settings.SOULMV_LIMITE_EXECUCAO_MIN * 60)


class ImportarSoulMVView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser]

    def post(self, request):
        arquivo = request.FILES.get('arquivo')
        if arquivo is None:
            return Response({'error': "Envie o CSV no campo 'arquivo'."}, status=status.HTTP_400_BAD_REQUEST)
        limite = settings.SOULMV_UPLOAD_MAX_BYTES
        if arquivo.size > limite:
            return Response(
                {'error': f'Arquivo excede o limite de {limite // (1024 * 1024)} MB.'},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        try:
            with _lock():
                execucao = importar_conteudo(arquivo.read(), f'api:{arquivo.name}')
        except LockOcupado:
            return Response({'error': 'Importação já em execução.'}, status=status.HTTP_409_CONFLICT)

        corpo = {
            'execucao': execucao.pk,
            'status': execucao.status,
            'linhas_lidas': execucao.linhas_lidas,
            'pacientes_criados': execucao.pacientes_criados,
            'agendamentos_criados': execucao.agendamentos_criados,
            'linhas_rejeitadas': execucao.linhas_rejeitadas,
            'erro': execucao.erro,
        }
        http = status.HTTP_422_UNPROCESSABLE_ENTITY if execucao.status == ExecucaoImportacao.STATUS_ERRO else status.HTTP_200_OK
        return Response(corpo, status=http)
