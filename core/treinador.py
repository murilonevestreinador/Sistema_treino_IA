import secrets

from core.banco import conectar
from core.usuarios import buscar_usuario_por_email, buscar_usuario_por_id


def gerar_link_convite(treinador_id, base_url=None):
    token = secrets.token_urlsafe(24)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO convites_treinador_link (treinador_id, token, ativo)
        VALUES (?, ?, 1)
        """,
        (treinador_id, token),
    )
    conn.commit()
    conn.close()

    url_base = (base_url or "http://localhost:8501").strip().rstrip("/")
    return f"{url_base}?convite={token}"


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
        WHERE ctl.token = ?
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
        WHERE treinador_id = ? AND atleta_id = ?
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
            SET status = ?
            WHERE id = ?
            """,
            (status, vinculo["id"]),
        )
    else:
        cursor.execute(
            """
            INSERT INTO treinador_atleta (treinador_id, atleta_id, status)
            VALUES (?, ?, ?)
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
        WHERE ta.treinador_id = ?
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
        WHERE ta.atleta_id = ?
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
        WHERE atleta_id = ?
          AND status = 'ativo'
          AND treinador_id <> ?
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
        WHERE ta.atleta_id = ?
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
