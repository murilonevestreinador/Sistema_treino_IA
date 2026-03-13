import hashlib
import json
import secrets

import streamlit as st
import streamlit.components.v1 as components

from core.banco import conectar
from core.usuarios import buscar_usuario_por_id


QUERY_PARAM_BROWSER_KEY = "bk"
QUERY_PARAM_BROWSER_SYNC = "bk_sync"
SESSION_KEY_BROWSER = "browser_key"
SESSION_KEY_RESET_NONCE = "browser_key_reset_nonce"
LOCAL_STORAGE_BROWSER_KEY = "trilab_browser_key"
SESSION_STORAGE_BROWSER_SYNC = "trilab_browser_key_synced"
SESSION_STORAGE_RESET_NONCE = "trilab_browser_key_reset_nonce"


def _hash_browser_key(browser_key):
    return hashlib.sha256((browser_key or "").encode("utf-8")).hexdigest()


def _browser_key_atual():
    return (st.session_state.get(SESSION_KEY_BROWSER) or "").strip()


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

        if (!browserKeyUrl && browserSincronizado !== browserKey) {{
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


def registrar_sessao_persistente(usuario_id):
    browser_key = _browser_key_atual()
    if not browser_key or not usuario_id:
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
    return True


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


def preparar_rotacao_browser_key():
    st.session_state[SESSION_KEY_RESET_NONCE] = secrets.token_urlsafe(12)
