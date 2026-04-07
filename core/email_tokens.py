import json
import logging
import secrets
from datetime import datetime, timedelta

from core.banco import conectar
from core.email_service import (
    enviar_email_reset_senha,
    enviar_email_verificacao,
    montar_link_publico,
)
from core.sessao_persistente import revogar_sessoes_persistentes_usuario
from core.usuarios import buscar_usuario_por_id, hash_senha


TOKEN_TIPO_VERIFICACAO_EMAIL = "verificacao_email"
TOKEN_TIPO_RESET_SENHA = "reset_senha"
EXPIRACAO_VERIFICACAO_EMAIL = timedelta(hours=48)
EXPIRACAO_RESET_SENHA = timedelta(minutes=30)
RATE_LIMIT_EMAIL_SEGUNDOS = 60
LOGGER = logging.getLogger("trilab.email.token")


def _agora():
    return datetime.now()


def _normalizar_email(email):
    return (email or "").strip().lower()


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


def _token_hash(token):
    import hashlib

    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _json(valor):
    return json.dumps(valor or {}, ensure_ascii=True, sort_keys=True, default=str)


def _parse_datetime(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _segundos_restantes_limite(ultimo_envio, janela_segundos):
    instante = _parse_datetime(ultimo_envio)
    if not instante:
        return 0
    restante = int(janela_segundos - (_agora() - instante).total_seconds())
    return max(restante, 0)


def _ttl_por_tipo(tipo):
    if tipo == TOKEN_TIPO_RESET_SENHA:
        return EXPIRACAO_RESET_SENHA
    return EXPIRACAO_VERIFICACAO_EMAIL


def _mensagem_status_token(tipo, status):
    if tipo == TOKEN_TIPO_VERIFICACAO_EMAIL:
        return {
            "valid": "Link valido.",
            "invalid": "Esse link e invalido.",
            "used": "Esse link ja foi utilizado.",
            "revoked": "Esse link nao esta mais ativo.",
            "expired": "Esse link expirou.",
            "email_changed": "Esse link nao corresponde mais ao e-mail atual da conta.",
        }.get(status, "Esse link nao e valido.")
    return {
        "valid": "Link valido.",
        "invalid": "Esse link e invalido.",
        "used": "Esse link ja foi utilizado.",
        "revoked": "Esse link nao esta mais ativo.",
        "expired": "Esse link expirou.",
    }.get(status, "Esse link nao e valido.")


def _buscar_usuario_para_token(cursor, usuario_id, for_update=False):
    sql = """
        SELECT
            id,
            nome,
            email,
            COALESCE(email_verificado, 0) AS email_verificado,
            email_verificado_em,
            ultimo_envio_verificacao_em,
            ultimo_reset_senha_solicitado_em
        FROM usuarios
        WHERE id = %s
    """
    if for_update:
        sql += " FOR UPDATE"
    cursor.execute(sql, (usuario_id,))
    return cursor.fetchone()


def _buscar_token(cursor, token, tipo, for_update=False):
    token_hash = _token_hash(token)
    sql = """
        SELECT
            t.*,
            u.nome AS usuario_nome,
            u.email AS usuario_email_atual,
            COALESCE(u.email_verificado, 0) AS usuario_email_verificado
        FROM email_auth_tokens t
        JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.token_hash = %s
          AND t.tipo = %s
        ORDER BY t.criado_em DESC, t.id DESC
        LIMIT 1
    """
    if for_update:
        sql += " FOR UPDATE"
    cursor.execute(sql, (token_hash, tipo))
    return cursor.fetchone()


def _status_token(row, tipo):
    if not row:
        return "invalid"
    if row.get("usado_em"):
        return "used"
    if row.get("revogado_em"):
        return "revoked"
    expira_em = _parse_datetime(row.get("expira_em"))
    if expira_em and expira_em < _agora():
        return "expired"
    if tipo == TOKEN_TIPO_VERIFICACAO_EMAIL:
        email_destino = _normalizar_email(row.get("email_destino"))
        email_atual = _normalizar_email(row.get("usuario_email_atual"))
        if email_destino != email_atual:
            return "email_changed"
    return "valid"


def _revogar_tokens_pendentes(cursor, usuario_id, tipo, motivo="substituido"):
    cursor.execute(
        """
        UPDATE email_auth_tokens
        SET revogado_em = CURRENT_TIMESTAMP,
            metadados_json = COALESCE(metadados_json, '{}')
        WHERE usuario_id = %s
          AND tipo = %s
          AND usado_em IS NULL
          AND revogado_em IS NULL
        """,
        (usuario_id, tipo),
    )
    if cursor.rowcount:
        LOGGER.info(
            "[EMAIL_TOKEN] Tokens revogados usuario_id=%s tipo=%s quantidade=%s motivo=%s",
            usuario_id,
            tipo,
            cursor.rowcount,
            motivo,
        )


def _inserir_token(cursor, usuario_id, tipo, email_destino, criado_ip=None, criado_user_agent=None, metadados=None):
    token = secrets.token_urlsafe(32)
    expira_em = _agora() + _ttl_por_tipo(tipo)
    cursor.execute(
        """
        INSERT INTO email_auth_tokens (
            usuario_id,
            tipo,
            token_hash,
            email_destino,
            expira_em,
            criado_ip,
            criado_user_agent,
            metadados_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, expira_em
        """,
        (
            usuario_id,
            tipo,
            _token_hash(token),
            _normalizar_email(email_destino),
            expira_em,
            (criado_ip or "").strip()[:200] or None,
            (criado_user_agent or "").strip()[:500] or None,
            _json(metadados),
        ),
    )
    registro = cursor.fetchone() or {}
    LOGGER.info(
        "[EMAIL_TOKEN] Token gerado usuario_id=%s tipo=%s email=%s token_id=%s expira_em=%s",
        usuario_id,
        tipo,
        _mask_email(email_destino),
        registro.get("id"),
        registro.get("expira_em"),
    )
    return {
        "token": token,
        "expira_em": registro.get("expira_em") or expira_em,
    }


def solicitar_verificacao_email(
    usuario_id,
    base_url=None,
    force=False,
    criado_ip=None,
    criado_user_agent=None,
    origem="manual",
):
    conn = conectar()
    try:
        cursor = conn.cursor()
        usuario = _buscar_usuario_para_token(cursor, usuario_id, for_update=True)
        if not usuario:
            LOGGER.warning("[EMAIL_VERIFY] Usuario nao encontrado usuario_id=%s", usuario_id)
            conn.rollback()
            return {"ok": False, "status": "usuario_nao_encontrado", "mensagem": "Conta nao encontrada."}

        if int(usuario.get("email_verificado") or 0) == 1:
            conn.rollback()
            return {
                "ok": True,
                "status": "ja_verificado",
                "mensagem": "Este e-mail ja esta confirmado.",
                "usuario": buscar_usuario_por_id(usuario_id),
            }

        restante = _segundos_restantes_limite(usuario.get("ultimo_envio_verificacao_em"), RATE_LIMIT_EMAIL_SEGUNDOS)
        if restante > 0 and not force:
            conn.rollback()
            return {
                "ok": False,
                "status": "rate_limited",
                "mensagem": f"Aguarde {restante}s antes de reenviar um novo link.",
                "segundos_restantes": restante,
            }

        _revogar_tokens_pendentes(cursor, usuario_id, TOKEN_TIPO_VERIFICACAO_EMAIL, motivo="novo_link")
        novo_token = _inserir_token(
            cursor,
            usuario_id,
            TOKEN_TIPO_VERIFICACAO_EMAIL,
            usuario.get("email"),
            criado_ip=criado_ip,
            criado_user_agent=criado_user_agent,
            metadados={"origem": origem},
        )
        cursor.execute(
            """
            UPDATE usuarios
            SET ultimo_envio_verificacao_em = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (usuario_id,),
        )
        conn.commit()
    finally:
        conn.close()

    link = montar_link_publico(
        {
            "auth_action": "verify_email",
            "token": novo_token["token"],
        },
        base_url=base_url,
    )
    envio = enviar_email_verificacao(usuario.get("nome"), usuario.get("email"), link, novo_token["expira_em"])
    if not envio.get("ok"):
        LOGGER.warning(
            "[EMAIL_VERIFY] Falha no envio usuario_id=%s email=%s provider=%s",
            usuario_id,
            _mask_email(usuario.get("email")),
            envio.get("provider"),
        )
        return {
            "ok": False,
            "status": "envio_falhou",
            "mensagem": "Sua conta foi criada, mas nao conseguimos enviar o e-mail agora. Voce pode reenviar daqui a pouco.",
            "usuario": buscar_usuario_por_id(usuario_id),
        }

    LOGGER.info(
        "[EMAIL_VERIFY] E-mail de verificacao enviado usuario_id=%s email=%s provider=%s",
        usuario_id,
        _mask_email(usuario.get("email")),
        envio.get("provider"),
    )
    return {
        "ok": True,
        "status": "enviado",
        "mensagem": "Enviamos um link para confirmar seu e-mail.",
        "usuario": buscar_usuario_por_id(usuario_id),
        "expira_em": novo_token["expira_em"],
    }


def atualizar_email_pendente_verificacao(
    usuario_id,
    novo_email,
    base_url=None,
    criado_ip=None,
    criado_user_agent=None,
):
    email_normalizado = _normalizar_email(novo_email)
    if not email_normalizado or "@" not in email_normalizado:
        raise ValueError("Informe um e-mail valido.")

    conn = conectar()
    try:
        cursor = conn.cursor()
        usuario = _buscar_usuario_para_token(cursor, usuario_id, for_update=True)
        if not usuario:
            raise ValueError("Conta nao encontrada.")

        cursor.execute(
            "SELECT id FROM usuarios WHERE LOWER(COALESCE(email, '')) = %s AND id <> %s LIMIT 1",
            (email_normalizado, usuario_id),
        )
        if cursor.fetchone():
            raise ValueError("Ja existe uma conta com este e-mail.")

        cursor.execute(
            """
            UPDATE usuarios
            SET email = %s,
                email_verificado = 0,
                email_verificado_em = NULL,
                ultimo_envio_verificacao_em = NULL
            WHERE id = %s
            """,
            (email_normalizado, usuario_id),
        )
        conn.commit()
    finally:
        conn.close()

    LOGGER.info(
        "[EMAIL_VERIFY] E-mail atualizado antes da confirmacao usuario_id=%s email=%s",
        usuario_id,
        _mask_email(email_normalizado),
    )
    return solicitar_verificacao_email(
        usuario_id,
        base_url=base_url,
        force=True,
        criado_ip=criado_ip,
        criado_user_agent=criado_user_agent,
        origem="troca_email_pendente",
    )


def inspecionar_token_email(token, tipo):
    conn = conectar()
    try:
        cursor = conn.cursor()
        row = _buscar_token(cursor, token, tipo, for_update=False)
    finally:
        conn.close()

    status = _status_token(row, tipo)
    if status != "valid":
        LOGGER.warning(
            "[EMAIL_TOKEN] Inspecao rejeitada tipo=%s usuario_id=%s status=%s",
            tipo,
            row.get("usuario_id") if row else None,
            status,
        )
    return {
        "ok": status == "valid",
        "status": status,
        "mensagem": _mensagem_status_token(tipo, status),
        "usuario_id": row.get("usuario_id") if row else None,
        "email_destino": row.get("email_destino") if row else None,
    }


def confirmar_email_por_token(token):
    conn = conectar()
    try:
        cursor = conn.cursor()
        row = _buscar_token(cursor, token, TOKEN_TIPO_VERIFICACAO_EMAIL, for_update=True)
        status = _status_token(row, TOKEN_TIPO_VERIFICACAO_EMAIL)
        if status != "valid":
            if row and status == "expired" and not row.get("revogado_em"):
                cursor.execute(
                    "UPDATE email_auth_tokens SET revogado_em = CURRENT_TIMESTAMP WHERE id = %s AND revogado_em IS NULL",
                    (row["id"],),
                )
                conn.commit()
            else:
                conn.rollback()
            LOGGER.warning(
                "[EMAIL_VERIFY] Token de verificacao rejeitado usuario_id=%s status=%s",
                row.get("usuario_id") if row else None,
                status,
            )
            return {
                "ok": False,
                "status": status,
                "mensagem": _mensagem_status_token(TOKEN_TIPO_VERIFICACAO_EMAIL, status),
                "usuario": None,
            }

        cursor.execute(
            """
            UPDATE usuarios
            SET email_verificado = 1,
                email_verificado_em = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (row["usuario_id"],),
        )
        cursor.execute(
            "UPDATE email_auth_tokens SET usado_em = CURRENT_TIMESTAMP WHERE id = %s",
            (row["id"],),
        )
        _revogar_tokens_pendentes(cursor, row["usuario_id"], TOKEN_TIPO_VERIFICACAO_EMAIL, motivo="confirmado")
        conn.commit()
    finally:
        conn.close()

    usuario = buscar_usuario_por_id(row["usuario_id"])
    LOGGER.info(
        "[EMAIL_VERIFY] E-mail confirmado usuario_id=%s email=%s",
        row["usuario_id"],
        _mask_email(row.get("email_destino")),
    )
    return {
        "ok": True,
        "status": "confirmado",
        "mensagem": "E-mail confirmado com sucesso. Seu acesso foi liberado.",
        "usuario": usuario,
    }


def solicitar_reset_senha_por_email(
    email,
    base_url=None,
    force=False,
    criado_ip=None,
    criado_user_agent=None,
):
    mensagem_neutra = "Se existir uma conta com esse e-mail, enviaremos as instrucoes para redefinir a senha."
    email_normalizado = _normalizar_email(email)
    if not email_normalizado:
        return {"ok": True, "status": "ignorado", "mensagem": mensagem_neutra}

    conn = conectar()
    usuario = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                nome,
                email,
                COALESCE(email_verificado, 0) AS email_verificado,
                ultimo_reset_senha_solicitado_em
            FROM usuarios
            WHERE LOWER(COALESCE(email, '')) = %s
            FOR UPDATE
            """,
            (email_normalizado,),
        )
        usuario = cursor.fetchone()
        if not usuario:
            conn.rollback()
            LOGGER.info("[EMAIL_RESET] Solicitacao ignorada email=%s motivo=nao_encontrado", _mask_email(email_normalizado))
            return {"ok": True, "status": "ignorado", "mensagem": mensagem_neutra}

        if int(usuario.get("email_verificado") or 0) != 1:
            conn.rollback()
            LOGGER.info("[EMAIL_RESET] Solicitacao ignorada usuario_id=%s motivo=email_nao_verificado", usuario["id"])
            return {"ok": True, "status": "ignorado", "mensagem": mensagem_neutra}

        restante = _segundos_restantes_limite(usuario.get("ultimo_reset_senha_solicitado_em"), RATE_LIMIT_EMAIL_SEGUNDOS)
        if restante > 0 and not force:
            conn.rollback()
            LOGGER.info("[EMAIL_RESET] Solicitacao limitada usuario_id=%s restante=%s", usuario["id"], restante)
            return {"ok": True, "status": "rate_limited", "mensagem": mensagem_neutra}

        _revogar_tokens_pendentes(cursor, usuario["id"], TOKEN_TIPO_RESET_SENHA, motivo="novo_link")
        novo_token = _inserir_token(
            cursor,
            usuario["id"],
            TOKEN_TIPO_RESET_SENHA,
            usuario["email"],
            criado_ip=criado_ip,
            criado_user_agent=criado_user_agent,
            metadados={"origem": "esqueci_senha"},
        )
        cursor.execute(
            """
            UPDATE usuarios
            SET ultimo_reset_senha_solicitado_em = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (usuario["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    link = montar_link_publico(
        {
            "auth_action": "reset_password",
            "token": novo_token["token"],
        },
        base_url=base_url,
    )
    envio = enviar_email_reset_senha(usuario.get("nome"), usuario.get("email"), link, novo_token["expira_em"])
    if not envio.get("ok"):
        LOGGER.warning(
            "[EMAIL_RESET] Falha no envio usuario_id=%s email=%s provider=%s",
            usuario["id"],
            _mask_email(usuario.get("email")),
            envio.get("provider"),
        )
        return {"ok": True, "status": "envio_falhou", "mensagem": mensagem_neutra}

    LOGGER.info(
        "[EMAIL_RESET] E-mail de reset enviado usuario_id=%s email=%s provider=%s",
        usuario["id"],
        _mask_email(usuario.get("email")),
        envio.get("provider"),
    )
    return {"ok": True, "status": "enviado", "mensagem": mensagem_neutra}


def redefinir_senha_por_token(token, nova_senha):
    nova_senha = nova_senha or ""
    if len(nova_senha) < 8:
        return {
            "ok": False,
            "status": "senha_fraca",
            "mensagem": "A nova senha deve ter pelo menos 8 caracteres.",
        }

    conn = conectar()
    try:
        cursor = conn.cursor()
        row = _buscar_token(cursor, token, TOKEN_TIPO_RESET_SENHA, for_update=True)
        status = _status_token(row, TOKEN_TIPO_RESET_SENHA)
        if status != "valid":
            if row and status == "expired" and not row.get("revogado_em"):
                cursor.execute(
                    "UPDATE email_auth_tokens SET revogado_em = CURRENT_TIMESTAMP WHERE id = %s AND revogado_em IS NULL",
                    (row["id"],),
                )
                conn.commit()
            else:
                conn.rollback()
            LOGGER.warning(
                "[EMAIL_RESET] Token rejeitado usuario_id=%s status=%s",
                row.get("usuario_id") if row else None,
                status,
            )
            return {
                "ok": False,
                "status": status,
                "mensagem": _mensagem_status_token(TOKEN_TIPO_RESET_SENHA, status),
            }

        cursor.execute(
            """
            UPDATE usuarios
            SET senha = %s
            WHERE id = %s
            """,
            (hash_senha(nova_senha), row["usuario_id"]),
        )
        cursor.execute(
            "UPDATE email_auth_tokens SET usado_em = CURRENT_TIMESTAMP WHERE id = %s",
            (row["id"],),
        )
        _revogar_tokens_pendentes(cursor, row["usuario_id"], TOKEN_TIPO_RESET_SENHA, motivo="senha_redefinida")
        conn.commit()
    finally:
        conn.close()

    revogar_sessoes_persistentes_usuario(row["usuario_id"])
    LOGGER.info("[EMAIL_RESET] Senha redefinida usuario_id=%s", row["usuario_id"])
    return {
        "ok": True,
        "status": "senha_redefinida",
        "mensagem": "Senha atualizada com sucesso. Faca login com a nova senha.",
        "usuario_id": row["usuario_id"],
    }
