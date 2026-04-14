import logging

from core.email_service import email_envio_habilitado
from core.env import get_env_bool, get_env_datetime, parse_datetime
from core.permissoes import eh_admin, eh_atleta, email_verificado


LOGGER = logging.getLogger("trilab.email.verification")
ENV_ENFORCEMENT_START_AT = "EMAIL_VERIFICATION_ENFORCEMENT_START_AT"


def _mask_email(valor):
    texto = str(valor or "").strip()
    if "@" not in texto:
        return texto
    local, dominio = texto.split("@", 1)
    if len(local) <= 2:
        local_mask = "*" * len(local)
    else:
        local_mask = f"{local[:2]}***"
    return f"{local_mask}@{dominio}"


def obter_email_verificacao_enforcement_start_at(contexto=None):
    return get_env_datetime(
        ENV_ENFORCEMENT_START_AT,
        None,
        logger=LOGGER,
        contexto=contexto or "email_verification_enforcement_start_at",
    )


def avaliar_email_verificacao_obrigatoria(usuario, contexto=None):
    contexto_log = contexto or "default"
    envio_habilitado = email_envio_habilitado()
    obrigatoria_configurada = get_env_bool(
        "EMAIL_VERIFICATION_REQUIRED",
        False,
        logger=LOGGER,
        contexto=f"{contexto_log}:required",
    )
    enforcement_start_at = obter_email_verificacao_enforcement_start_at(
        contexto=f"{contexto_log}:enforcement_start_at"
    )

    usuario = usuario or {}
    tipo_usuario = (usuario.get("tipo_usuario") or "").strip().lower() or "desconhecido"
    usuario_id = usuario.get("id")
    email_usuario = usuario.get("email")
    email_confirmado = email_verificado(usuario)
    admin = eh_admin(usuario)
    atleta = eh_atleta(usuario)
    data_criacao = parse_datetime(usuario.get("data_criacao"))
    conta_legada = None
    obrigatoria = False
    motivo = "usuario_ausente"

    if not usuario_id:
        motivo = "usuario_ausente"
    elif not envio_habilitado:
        motivo = "email_disabled"
    elif not obrigatoria_configurada:
        motivo = "flag_desligada"
    elif email_confirmado:
        motivo = "email_ja_verificado"
    elif admin:
        motivo = "admin_isento"
    elif not atleta:
        motivo = f"tipo_usuario_isento:{tipo_usuario}"
    elif not (email_usuario or "").strip():
        motivo = "email_ausente"
    elif enforcement_start_at is None:
        motivo = "data_corte_ausente_ou_invalida"
    elif data_criacao is None:
        motivo = "data_criacao_ausente_ou_invalida"
    else:
        conta_legada = data_criacao < enforcement_start_at
        if conta_legada:
            motivo = "conta_legada"
        else:
            obrigatoria = True
            motivo = "conta_nova_na_data_de_corte"

    LOGGER.info(
        "[EMAIL_VERIFY_ENFORCEMENT] Decisao contexto=%s usuario_id=%s email=%s obrigatoria=%s motivo=%s email_enabled=%s verification_required=%s enforcement_start_at=%s data_criacao=%s conta_legada=%s is_admin=%s tipo_usuario=%s email_verificado=%s",
        contexto_log,
        usuario_id,
        _mask_email(email_usuario),
        obrigatoria,
        motivo,
        envio_habilitado,
        obrigatoria_configurada,
        enforcement_start_at.isoformat() if enforcement_start_at else None,
        data_criacao.isoformat() if data_criacao else None,
        conta_legada,
        admin,
        tipo_usuario,
        email_confirmado,
    )
    return {
        "obrigatoria": obrigatoria,
        "motivo": motivo,
        "email_enabled": envio_habilitado,
        "verification_required": obrigatoria_configurada,
        "enforcement_start_at": enforcement_start_at,
        "data_criacao": data_criacao,
        "conta_legada": conta_legada,
        "is_admin": admin,
        "is_atleta": atleta,
        "email_verificado": email_confirmado,
        "usuario_id": usuario_id,
        "tipo_usuario": tipo_usuario,
    }


def email_verificacao_obrigatoria(usuario, contexto=None):
    return bool(avaliar_email_verificacao_obrigatoria(usuario, contexto=contexto).get("obrigatoria"))
