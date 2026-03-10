import secrets
import os
from pathlib import Path

from core.banco import conectar
from core.usuarios import buscar_usuario_por_email, buscar_usuario_por_id

DEFAULT_PUBLIC_APP_URL = "https://trilab-treinamento.onrender.com"
DEFAULT_TEMA_TREINADOR = {
    "cor_primaria": "#1b6f5c",
    "cor_secundaria": "#2f8f7a",
    "logo_url": None,
}


def _resolver_url_base_publica():
    candidatos = [
        os.getenv("APP_BASE_URL", ""),
        os.getenv("RENDER_EXTERNAL_URL", ""),
        os.getenv("PUBLIC_APP_URL", ""),
        DEFAULT_PUBLIC_APP_URL,
    ]

    for url in candidatos:
        url_limpa = (url or "").strip().rstrip("/")
        if url_limpa:
            return url_limpa

    hostname_render = (os.getenv("RENDER_EXTERNAL_HOSTNAME", "") or "").strip()
    if hostname_render:
        return f"https://{hostname_render.strip('/')}"

    return DEFAULT_PUBLIC_APP_URL


def gerar_link_convite(treinador_id, base_url=None):
    token = secrets.token_urlsafe(24)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO convites_treinador_link (treinador_id, token, ativo)
        VALUES (%s, %s, 1)
        """,
        (treinador_id, token),
    )
    conn.commit()
    conn.close()

    url_base = (base_url or _resolver_url_base_publica()).strip().rstrip("/")
    return f"{url_base}?convite={token}"


def _normalizar_cor(valor, fallback):
    cor = (valor or "").strip()
    if cor.startswith("#") and len(cor) in {4, 7}:
        return cor
    return fallback


def tema_padrao_treinador():
    return dict(DEFAULT_TEMA_TREINADOR)


def salvar_tema_treinador(treinador_id, cor_primaria, cor_secundaria, logo_url):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO treinador_tema (treinador_id, cor_primaria, cor_secundaria, logo_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (treinador_id)
        DO UPDATE SET
            cor_primaria = EXCLUDED.cor_primaria,
            cor_secundaria = EXCLUDED.cor_secundaria,
            logo_url = EXCLUDED.logo_url
        """,
        (
            treinador_id,
            _normalizar_cor(cor_primaria, DEFAULT_TEMA_TREINADOR["cor_primaria"]),
            _normalizar_cor(cor_secundaria, DEFAULT_TEMA_TREINADOR["cor_secundaria"]),
            (logo_url or "").strip() or None,
        ),
    )
    conn.commit()
    conn.close()


def buscar_tema_treinador(treinador_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, treinador_id, cor_primaria, cor_secundaria, logo_url, created_at
        FROM treinador_tema
        WHERE treinador_id = %s
        LIMIT 1
        """,
        (treinador_id,),
    )
    tema = cursor.fetchone()
    conn.close()

    if not tema:
        return tema_padrao_treinador()

    return {
        "id": tema["id"],
        "treinador_id": tema["treinador_id"],
        "cor_primaria": _normalizar_cor(tema.get("cor_primaria"), DEFAULT_TEMA_TREINADOR["cor_primaria"]),
        "cor_secundaria": _normalizar_cor(tema.get("cor_secundaria"), DEFAULT_TEMA_TREINADOR["cor_secundaria"]),
        "logo_url": tema.get("logo_url"),
        "created_at": tema.get("created_at"),
    }


def buscar_tema_por_atleta(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT treinador_id
        FROM treinador_atleta
        WHERE atleta_id = %s
          AND status = 'ativo'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (atleta_id,),
    )
    vinculo = cursor.fetchone()
    conn.close()

    if not vinculo:
        return tema_padrao_treinador()

    tema = buscar_tema_treinador(vinculo["treinador_id"])
    tema["treinador_id"] = vinculo["treinador_id"]
    return tema


def resolver_logo_treinador(logo_url):
    caminho = (logo_url or "").strip()
    if not caminho:
        return None
    if caminho.startswith(("http://", "https://", "data:")):
        return caminho
    if caminho.startswith("/"):
        caminho = caminho.lstrip("/").replace("/", os.sep)
    arquivo = Path(caminho)
    if not arquivo.is_absolute():
        arquivo = Path.cwd() / arquivo
    return str(arquivo) if arquivo.exists() else None


def buscar_convite_por_token(token):
    token_normalizado = (token or "").strip()
    if not token_normalizado:
        return None

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ctl.id,
               ctl.treinador_id,
               ctl.token,
               ctl.ativo,
               ctl.created_at,
               u.nome AS treinador_nome,
               u.email AS treinador_email
        FROM convites_treinador_link ctl
        JOIN usuarios u ON u.id = ctl.treinador_id
        WHERE ctl.token = %s
          AND ctl.ativo = 1
        LIMIT 1
        """,
        (token_normalizado,),
    )
    convite = cursor.fetchone()
    conn.close()
    return dict(convite) if convite else None


def buscar_status_vinculo(treinador_id, atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, status
        FROM treinador_atleta
        WHERE treinador_id = %s AND atleta_id = %s
        LIMIT 1
        """,
        (treinador_id, atleta_id),
    )
    vinculo = cursor.fetchone()
    conn.close()
    return dict(vinculo) if vinculo else None


def definir_vinculo_treinador_atleta(treinador_id, atleta_id, status="ativo"):
    vinculo = buscar_status_vinculo(treinador_id, atleta_id)
    conn = conectar()
    cursor = conn.cursor()

    if vinculo:
        cursor.execute(
            """
            UPDATE treinador_atleta
            SET status = %s
            WHERE id = %s
            """,
            (status, vinculo["id"]),
        )
    else:
        cursor.execute(
            """
            INSERT INTO treinador_atleta (treinador_id, atleta_id, status)
            VALUES (%s, %s, %s)
            """,
            (treinador_id, atleta_id, status),
        )

    conn.commit()
    conn.close()


def remover_vinculo_treinador_atleta(treinador_id, atleta_id):
    vinculo = buscar_status_vinculo(treinador_id, atleta_id)
    if not vinculo:
        return False
    definir_vinculo_treinador_atleta(treinador_id, atleta_id, status="encerrado")
    return True


def convidar_atleta(treinador_id, email_atleta):
    atleta = buscar_usuario_por_email(email_atleta)
    if not atleta:
        return False, "Atleta n\u00e3o encontrado."
    if atleta["id"] == treinador_id:
        return False, "Voc\u00ea n\u00e3o pode se convidar."
    if atleta.get("tipo_usuario") != "atleta":
        return False, "O e-mail informado n\u00e3o pertence a um atleta."

    vinculo = buscar_status_vinculo(treinador_id, atleta["id"])

    if vinculo:
        if vinculo["status"] in {"pendente", "ativo"}:
            return False, f"J\u00e1 existe um convite com status '{vinculo['status']}'."

    definir_vinculo_treinador_atleta(treinador_id, atleta["id"], status="pendente")
    return True, "Convite enviado."


def listar_vinculos(treinador_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ta.id,
               ta.treinador_id,
               ta.atleta_id,
               ta.status,
               ta.created_at,
               u.nome AS atleta_nome,
               u.apelido AS atleta_apelido,
               u.foto_perfil AS atleta_foto_perfil,
               u.email AS atleta_email
        FROM treinador_atleta ta
        JOIN usuarios u ON u.id = ta.atleta_id
        WHERE ta.treinador_id = %s
        ORDER BY ta.status, u.nome
        """,
        (treinador_id,),
    )
    vinculos = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return vinculos


def listar_atletas_do_treinador(treinador_id):
    return [vinculo for vinculo in listar_vinculos(treinador_id) if vinculo["status"] == "ativo"]


def listar_treinadores_do_atleta(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ta.id,
               ta.treinador_id,
               ta.atleta_id,
               ta.status,
               ta.created_at,
               u.nome AS treinador_nome,
               u.apelido AS treinador_apelido,
               u.email AS treinador_email
        FROM treinador_atleta ta
        JOIN usuarios u ON u.id = ta.treinador_id
        WHERE ta.atleta_id = %s
        ORDER BY
            CASE ta.status
                WHEN 'ativo' THEN 0
                WHEN 'pendente' THEN 1
                ELSE 2
            END,
            u.nome
        """,
        (atleta_id,),
    )
    vinculos = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return vinculos


def vincular_atleta_ao_treinador(atleta_id, treinador_id):
    treinador = buscar_usuario_por_id(treinador_id)
    if not treinador or treinador.get("tipo_usuario") != "treinador":
        return False, "Treinador nao encontrado."
    if treinador["id"] == atleta_id:
        return False, "Voce nao pode se vincular ao proprio usuario."

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE treinador_atleta
        SET status = 'encerrado'
        WHERE atleta_id = %s
          AND status = 'ativo'
          AND treinador_id <> %s
        """,
        (atleta_id, treinador_id),
    )
    conn.commit()
    conn.close()

    definir_vinculo_treinador_atleta(treinador_id, atleta_id, status="ativo")
    return True, "Vinculo com treinador atualizado."


def vincular_atleta_ao_treinador_por_email(atleta_id, email_treinador):
    treinador = buscar_usuario_por_email(email_treinador)
    if not treinador or treinador.get("tipo_usuario") != "treinador":
        return False, "Nenhum treinador encontrado com esse e-mail."
    return vincular_atleta_ao_treinador(atleta_id, treinador["id"])


def listar_convites_pendentes_do_atleta(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ta.id,
               ta.treinador_id,
               ta.atleta_id,
               ta.status,
               ta.created_at,
               u.nome AS treinador_nome,
               u.email AS treinador_email
        FROM treinador_atleta ta
        JOIN usuarios u ON u.id = ta.treinador_id
        WHERE ta.atleta_id = %s
          AND ta.status = 'pendente'
        ORDER BY ta.created_at DESC
        """,
        (atleta_id,),
    )
    convites = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return convites


def responder_convite(atleta_id, treinador_id, aceitar=True):
    novo_status = "ativo" if aceitar else "recusado"
    definir_vinculo_treinador_atleta(treinador_id, atleta_id, status=novo_status)


def buscar_atleta_vinculado(treinador_id, atleta_id):
    atletas = listar_atletas_do_treinador(treinador_id)
    for atleta in atletas:
        if atleta["atleta_id"] == atleta_id:
            return buscar_usuario_por_id(atleta_id)
    return None
