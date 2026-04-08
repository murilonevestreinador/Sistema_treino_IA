import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.banco import conectar  # noqa: E402
from core.permissoes import normalizar_status_conta, normalizar_tipo_usuario  # noqa: E402


ADMIN_EMAIL_PADRAO = "murilo_nevescontato@hotmail.com"


def _serializar(valor):
    return json.dumps(valor, ensure_ascii=True, indent=2, sort_keys=True, default=str)


def _buscar_usuario(cursor, email):
    cursor.execute(
        """
        SELECT
            id,
            nome,
            email,
            tipo_usuario,
            is_admin,
            status_conta,
            email_verificado,
            email_verificado_em,
            onboarding_completo,
            data_criacao
        FROM usuarios
        WHERE LOWER(COALESCE(email, '')) = %s
        ORDER BY id ASC
        """,
        (email,),
    )
    return cursor.fetchall()


def _contar_admins(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM usuarios
        WHERE COALESCE(is_admin, 0) = 1
           OR LOWER(COALESCE(tipo_usuario, '')) = 'admin'
        """
    )
    return int((cursor.fetchone() or {}).get("total") or 0)


def _buscar_config_bootstrap(cursor):
    cursor.execute(
        """
        SELECT chave, valor, updated_at
        FROM configuracoes_sistema
        WHERE chave = 'admin_bootstrap_consumed'
        """
    )
    return cursor.fetchone()


def _buscar_sessoes(cursor, usuario_id):
    cursor.execute(
        """
        SELECT
            id,
            usuario_id,
            LEFT(browser_key_hash, 12) AS browser_key_hash_prefix,
            CASE WHEN revogado_em IS NULL THEN 'ativa' ELSE 'revogada' END AS status_sessao,
            ultimo_acesso,
            revogado_em,
            created_at,
            LEFT(COALESCE(user_agent, ''), 120) AS user_agent_prefix
        FROM sessoes_persistentes
        WHERE usuario_id = %s
        ORDER BY ultimo_acesso DESC NULLS LAST, id DESC
        LIMIT 10
        """,
        (usuario_id,),
    )
    return cursor.fetchall()


def _buscar_tokens_email(cursor, usuario_id):
    cursor.execute(
        """
        SELECT
            tipo,
            email_destino,
            expira_em,
            usado_em,
            revogado_em,
            criado_em
        FROM email_auth_tokens
        WHERE usuario_id = %s
        ORDER BY criado_em DESC
        LIMIT 10
        """,
        (usuario_id,),
    )
    return cursor.fetchall()


def gerar_diagnostico(email):
    conn = conectar()
    try:
        cursor = conn.cursor()
        usuarios = _buscar_usuario(cursor, email)
        diagnostico = {
            "email_consultado": email,
            "contas_encontradas": len(usuarios),
            "total_admins_sistema": _contar_admins(cursor),
            "admin_bootstrap": _buscar_config_bootstrap(cursor),
            "usuarios": [],
        }

        for usuario in usuarios:
            usuario_info = dict(usuario)
            usuario_info["tipo_usuario_normalizado"] = normalizar_tipo_usuario(
                usuario.get("tipo_usuario"),
                usuario.get("is_admin"),
            )
            usuario_info["status_conta_normalizado"] = normalizar_status_conta(usuario.get("status_conta"))
            usuario_info["sessoes_persistentes"] = _buscar_sessoes(cursor, usuario["id"])
            usuario_info["tokens_email_recentes"] = _buscar_tokens_email(cursor, usuario["id"])
            diagnostico["usuarios"].append(usuario_info)

        return diagnostico
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostico somente-leitura da conta admin e das sessoes persistentes."
    )
    parser.add_argument("--email", default=ADMIN_EMAIL_PADRAO, help="E-mail da conta admin a diagnosticar.")
    args = parser.parse_args()

    email = (args.email or "").strip().lower()
    if not email:
        raise SystemExit("Informe um e-mail.")

    print(_serializar(gerar_diagnostico(email)))


if __name__ == "__main__":
    main()
