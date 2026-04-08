import hashlib
import json
import logging
import secrets

import streamlit as st
import streamlit.components.v1 as components

from core.banco import conectar
from core.usuarios import buscar_usuario_por_id


LOGGER = logging.getLogger("trilab.session")
QUERY_PARAM_BROWSER_KEY = "bk"
QUERY_PARAM_BROWSER_SYNC = "bk_sync"
SESSION_KEY_BROWSER = "browser_key"
SESSION_KEY_RESET_NONCE = "browser_key_reset_nonce"
LOCAL_STORAGE_BROWSER_KEY = "trilab_browser_key"
SESSION_STORAGE_BROWSER_SYNC = "trilab_browser_key_synced"
SESSION_STORAGE_RESET_NONCE = "trilab_browser_key_reset_nonce"
ADMIN_DIAGNOSTIC_EMAIL = "murilo_nevescontato@hotmail.com"


def _hash_browser_key(browser_key):
    return hashlib.sha256((browser_key or "").encode("utf-8")).hexdigest()


def _browser_key_atual():
    return (st.session_state.get(SESSION_KEY_BROWSER) or "").strip()


def browser_key_disponivel():
    return bool(_browser_key_atual())


def _email_admin_diagnostico(usuario=None, email=None):
    email_normalizado = (email or (usuario or {}).get("email") or "").strip().lower()
    return email_normalizado == ADMIN_DIAGNOSTIC_EMAIL


def _user_agent_atual():
    try:
        headers = getattr(st.context, "headers", {}) or {}
    except Exception:
        headers = {}

    for chave in ("user-agent", "User-Agent"):
        valor = headers.get(chave)
        if valor:
            return str(valor)[:500]
    return ""


def injetar_bridge_navegador():
    reset_nonce = (st.session_state.get(SESSION_KEY_RESET_NONCE) or "").strip()
    payload = {
        "query_param_key": QUERY_PARAM_BROWSER_KEY,
        "query_param_sync": QUERY_PARAM_BROWSER_SYNC,
        "local_storage_key": LOCAL_STORAGE_BROWSER_KEY,
        "session_storage_sync": SESSION_STORAGE_BROWSER_SYNC,
        "session_storage_reset": SESSION_STORAGE_RESET_NONCE,
        "reset_nonce": reset_nonce,
        "browser_key_presente": browser_key_disponivel(),
    }
    components.html(
        f"""
        <script>
        const cfg = {json.dumps(payload)};
        const parentWindow = window.parent;
        const localStorageRef = parentWindow.localStorage;
        const sessionStorageRef = parentWindow.sessionStorage;

        function gerarChave() {{
            if (parentWindow.crypto && parentWindow.crypto.randomUUID) {{
                return parentWindow.crypto.randomUUID();
            }}
            return `${{Date.now()}}-${{Math.random().toString(36).slice(2)}}-${{Math.random().toString(36).slice(2)}}`;
        }}

        function limparUrl(url) {{
            url.searchParams.delete(cfg.query_param_key);
            url.searchParams.delete(cfg.query_param_sync);
            return url;
        }}

        if (cfg.reset_nonce) {{
            const ultimoReset = sessionStorageRef.getItem(cfg.session_storage_reset) || "";
            if (ultimoReset !== cfg.reset_nonce) {{
                localStorageRef.removeItem(cfg.local_storage_key);
                sessionStorageRef.removeItem(cfg.session_storage_sync);
                sessionStorageRef.setItem(cfg.session_storage_reset, cfg.reset_nonce);
            }}
        }}

        let browserKey = localStorageRef.getItem(cfg.local_storage_key) || "";
        if (!browserKey) {{
            browserKey = gerarChave();
            localStorageRef.setItem(cfg.local_storage_key, browserKey);
            sessionStorageRef.removeItem(cfg.session_storage_sync);
        }}

        const url = new URL(parentWindow.location.href);
        const browserKeyUrl = url.searchParams.get(cfg.query_param_key) || "";
        const browserSyncUrl = url.searchParams.get(cfg.query_param_sync) || "";
        const browserSincronizado = sessionStorageRef.getItem(cfg.session_storage_sync) || "";
        const backendPrecisaSincronizar = !cfg.browser_key_presente;

        if (!browserKeyUrl && (backendPrecisaSincronizar || browserSincronizado !== browserKey)) {{
            url.searchParams.set(cfg.query_param_key, browserKey);
            url.searchParams.set(cfg.query_param_sync, "1");
            parentWindow.location.replace(url.toString());
        }} else if (browserKeyUrl === browserKey && browserSyncUrl === "1") {{
            sessionStorageRef.setItem(cfg.session_storage_sync, browserKey);
            parentWindow.history.replaceState({{}}, "", limparUrl(url).toString());
        }} else if (browserKeyUrl && browserKeyUrl !== browserKey) {{
            url.searchParams.set(cfg.query_param_key, browserKey);
            url.searchParams.set(cfg.query_param_sync, "1");
            parentWindow.location.replace(url.toString());
        }}
        </script>
        """,
        height=0,
    )


def capturar_browser_key_da_url():
    try:
        browser_key = (st.query_params.get(QUERY_PARAM_BROWSER_KEY) or "").strip()
    except Exception:
        browser_key = ""

    if browser_key:
        st.session_state[SESSION_KEY_BROWSER] = browser_key
        st.session_state.pop(SESSION_KEY_RESET_NONCE, None)
    return browser_key or _browser_key_atual()


def registrar_sessao_persistente(usuario_id, usuario=None, contexto=None):
    browser_key = _browser_key_atual()
    if not browser_key or not usuario_id:
        if _email_admin_diagnostico(usuario):
            LOGGER.warning(
                "[ADMIN_SESSION] Falha ao criar sessao persistente email=%s usuario_id=%s contexto=%s motivo=%s",
                usuario.get("email"),
                usuario_id,
                contexto or "-",
                "browser_key_ausente" if not browser_key else "usuario_id_ausente",
            )
        return False

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sessoes_persistentes (
            usuario_id,
            browser_key_hash,
            user_agent,
            ultimo_acesso,
            revogado_em
        )
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, NULL)
        ON CONFLICT (browser_key_hash) DO UPDATE
        SET usuario_id = EXCLUDED.usuario_id,
            user_agent = EXCLUDED.user_agent,
            ultimo_acesso = CURRENT_TIMESTAMP,
            revogado_em = NULL
        """,
        (usuario_id, _hash_browser_key(browser_key), _user_agent_atual()),
    )
    cursor.execute(
        """
        DELETE FROM sessoes_persistentes
        WHERE ultimo_acesso < CURRENT_TIMESTAMP - INTERVAL '180 days'
        """
    )
    conn.commit()
    conn.close()
    if _email_admin_diagnostico(usuario):
        LOGGER.warning(
            "[ADMIN_SESSION] Sessao persistente criada/atualizada email=%s usuario_id=%s contexto=%s",
            usuario.get("email"),
            usuario_id,
            contexto or "-",
        )
    return True


def diagnosticar_sessao_persistente_atual(usuario_id=None):
    browser_key = _browser_key_atual()
    diagnostico = {
        "browser_key_presente": bool(browser_key),
        "usuario_id_esperado": usuario_id,
        "status": "browser_key_ausente" if not browser_key else "desconhecido",
        "sessao_usuario_id": None,
        "revogada": None,
        "ultimo_acesso": None,
    }
    if not browser_key:
        return diagnostico

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT usuario_id, revogado_em, ultimo_acesso
        FROM sessoes_persistentes
        WHERE browser_key_hash = %s
        LIMIT 1
        """,
        (_hash_browser_key(browser_key),),
    )
    sessao = cursor.fetchone()
    conn.close()

    if not sessao:
        diagnostico["status"] = "sessao_nao_encontrada"
        diagnostico["revogada"] = False
        return diagnostico

    diagnostico["sessao_usuario_id"] = sessao.get("usuario_id")
    diagnostico["revogada"] = sessao.get("revogado_em") is not None
    diagnostico["ultimo_acesso"] = sessao.get("ultimo_acesso")
    if sessao.get("revogado_em"):
        diagnostico["status"] = "sessao_revogada"
        return diagnostico
    if usuario_id and int(sessao.get("usuario_id") or 0) != int(usuario_id or 0):
        diagnostico["status"] = "usuario_divergente"
        return diagnostico

    diagnostico["status"] = "valida"
    return diagnostico


def sessao_persistente_atual_valida(usuario_id=None):
    browser_key = _browser_key_atual()
    if not browser_key:
        return False

    conn = conectar()
    cursor = conn.cursor()
    if usuario_id:
        cursor.execute(
            """
            SELECT 1
            FROM sessoes_persistentes
            WHERE browser_key_hash = %s
              AND usuario_id = %s
              AND revogado_em IS NULL
            LIMIT 1
            """,
            (_hash_browser_key(browser_key), usuario_id),
        )
    else:
        cursor.execute(
            """
            SELECT 1
            FROM sessoes_persistentes
            WHERE browser_key_hash = %s
              AND revogado_em IS NULL
            LIMIT 1
            """,
            (_hash_browser_key(browser_key),),
        )
    valido = cursor.fetchone() is not None
    conn.close()
    return valido


def garantir_sessao_persistente_atual(usuario, contexto=None):
    usuario_id = (usuario or {}).get("id")
    if sessao_persistente_atual_valida(usuario_id):
        return True

    diagnostico = diagnosticar_sessao_persistente_atual(usuario_id)
    if diagnostico.get("status") == "sessao_nao_encontrada":
        criada = registrar_sessao_persistente(usuario_id, usuario=usuario, contexto=contexto)
        if criada and sessao_persistente_atual_valida(usuario_id):
            if _email_admin_diagnostico(usuario):
                LOGGER.warning(
                    "[ADMIN_SESSION] Sessao persistente recriada apos diagnostico email=%s usuario_id=%s contexto=%s",
                    usuario.get("email"),
                    usuario_id,
                    contexto or "-",
                )
            return True

    if _email_admin_diagnostico(usuario):
        LOGGER.warning(
            "[ADMIN_SESSION] Sessao persistente invalida email=%s usuario_id=%s contexto=%s diagnostico=%s",
            usuario.get("email"),
            usuario_id,
            contexto or "-",
            diagnostico,
        )
    return False


def tocar_sessao_persistente_atual(usuario_id=None):
    browser_key = _browser_key_atual()
    if not browser_key:
        return False

    conn = conectar()
    cursor = conn.cursor()
    if usuario_id:
        cursor.execute(
            """
            UPDATE sessoes_persistentes
            SET ultimo_acesso = CURRENT_TIMESTAMP,
                user_agent = %s
            WHERE browser_key_hash = %s
              AND usuario_id = %s
              AND revogado_em IS NULL
            """,
            (_user_agent_atual(), _hash_browser_key(browser_key), usuario_id),
        )
    else:
        cursor.execute(
            """
            UPDATE sessoes_persistentes
            SET ultimo_acesso = CURRENT_TIMESTAMP,
                user_agent = %s
            WHERE browser_key_hash = %s
              AND revogado_em IS NULL
            """,
            (_user_agent_atual(), _hash_browser_key(browser_key)),
        )
    atualizado = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return atualizado


def restaurar_usuario_persistente():
    browser_key = _browser_key_atual()
    if not browser_key:
        return None

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT usuario_id
        FROM sessoes_persistentes
        WHERE browser_key_hash = %s
          AND revogado_em IS NULL
        LIMIT 1
        """,
        (_hash_browser_key(browser_key),),
    )
    sessao = cursor.fetchone()
    if not sessao:
        conn.close()
        return None

    cursor.execute(
        """
        UPDATE sessoes_persistentes
        SET ultimo_acesso = CURRENT_TIMESTAMP,
            user_agent = %s
        WHERE browser_key_hash = %s
        """,
        (_user_agent_atual(), _hash_browser_key(browser_key)),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(sessao["usuario_id"])


def revogar_sessao_persistente_atual(usuario_id=None):
    browser_key = _browser_key_atual()
    if not browser_key:
        return

    conn = conectar()
    cursor = conn.cursor()
    if usuario_id:
        cursor.execute(
            """
            UPDATE sessoes_persistentes
            SET revogado_em = CURRENT_TIMESTAMP
            WHERE browser_key_hash = %s
              AND usuario_id = %s
              AND revogado_em IS NULL
            """,
            (_hash_browser_key(browser_key), usuario_id),
        )
    else:
        cursor.execute(
            """
            UPDATE sessoes_persistentes
            SET revogado_em = CURRENT_TIMESTAMP
            WHERE browser_key_hash = %s
              AND revogado_em IS NULL
            """,
            (_hash_browser_key(browser_key),),
    )
    conn.commit()
    conn.close()


def revogar_sessoes_persistentes_usuario(usuario_id):
    if not usuario_id:
        return 0

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE sessoes_persistentes
        SET revogado_em = CURRENT_TIMESTAMP
        WHERE usuario_id = %s
          AND revogado_em IS NULL
        """,
        (usuario_id,),
    )
    total = cursor.rowcount
    conn.commit()
    conn.close()
    return total


def preparar_rotacao_browser_key():
    st.session_state[SESSION_KEY_RESET_NONCE] = secrets.token_urlsafe(12)
