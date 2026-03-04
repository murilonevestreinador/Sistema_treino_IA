from datetime import datetime, timedelta

from core.banco import conectar
from core.pagamentos_gateway import cancelar_assinatura_gateway, criar_assinatura_gateway


TRIAL_DIAS = 7
STATUS_COM_ACESSO = {"ativa", "trial"}


def _agora_iso():
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso(data_texto):
    if not data_texto:
        return None
    try:
        return datetime.fromisoformat(str(data_texto))
    except ValueError:
        return None


def _linha_para_dict(linha):
    return dict(linha) if linha else None


def status_para_exibicao(status):
    if status == "trial":
        return "teste"
    return status or "desconhecido"


def listar_planos_ativos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM planos
        WHERE ativo = 1
        ORDER BY tipo, preco_mensal
        """
    )
    planos = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return planos


def buscar_plano_por_codigo(codigo):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM planos WHERE codigo = ?", (codigo,))
    plano = _linha_para_dict(cursor.fetchone())
    conn.close()
    return plano


def buscar_plano_por_id(plano_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM planos WHERE id = ?", (plano_id,))
    plano = _linha_para_dict(cursor.fetchone())
    conn.close()
    return plano


def buscar_plano_padrao_por_tipo(tipo_usuario):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM planos
        WHERE tipo = ?
          AND ativo = 1
        ORDER BY preco_mensal ASC
        LIMIT 1
        """,
        ((tipo_usuario or "atleta").strip().lower(),),
    )
    plano = _linha_para_dict(cursor.fetchone())
    conn.close()
    return plano


def _encerrar_assinaturas_abertas(cursor, usuario_id):
    agora = _agora_iso()
    cursor.execute(
        """
        UPDATE assinaturas
        SET status = CASE
                WHEN status = 'trial' THEN 'inativa'
                WHEN status = 'ativa' THEN 'cancelada'
                ELSE status
            END,
            data_fim = COALESCE(data_fim, ?)
        WHERE usuario_id = ?
          AND status IN ('trial', 'ativa')
        """,
        (agora, usuario_id),
    )


def criar_trial_assinatura(usuario_id, tipo_usuario):
    plano = buscar_plano_padrao_por_tipo(tipo_usuario)
    if not plano:
        raise ValueError("Nenhum plano ativo encontrado para este perfil.")

    inicio = datetime.now()
    data_inicio = inicio.isoformat(timespec="seconds")
    data_fim = (inicio + timedelta(days=TRIAL_DIAS)).isoformat(timespec="seconds")

    conn = conectar()
    cursor = conn.cursor()
    _encerrar_assinaturas_abertas(cursor, usuario_id)
    cursor.execute(
        """
        INSERT INTO assinaturas (
            usuario_id, plano_id, status, data_inicio, data_fim,
            renovacao_automatica, gateway, gateway_reference, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usuario_id,
            plano["id"],
            "trial",
            data_inicio,
            data_fim,
            0,
            "manual",
            f"trial-{usuario_id}-{inicio.strftime('%Y%m%d%H%M%S')}",
            _agora_iso(),
        ),
    )
    assinatura_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura_id)


def buscar_assinatura_por_id(assinatura_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.*, p.codigo AS plano_codigo, p.nome AS plano_nome, p.tipo AS plano_tipo,
               p.preco_mensal, p.limite_atletas
        FROM assinaturas a
        INNER JOIN planos p ON p.id = a.plano_id
        WHERE a.id = ?
        """,
        (assinatura_id,),
    )
    assinatura = _linha_para_dict(cursor.fetchone())
    conn.close()
    return assinatura


def listar_assinaturas_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.*, p.codigo AS plano_codigo, p.nome AS plano_nome, p.tipo AS plano_tipo,
               p.preco_mensal, p.limite_atletas
        FROM assinaturas a
        INNER JOIN planos p ON p.id = a.plano_id
        WHERE a.usuario_id = ?
        ORDER BY a.criado_em DESC, a.id DESC
        """,
        (usuario_id,),
    )
    assinaturas = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return assinaturas


def _normalizar_assinatura(cursor, assinatura):
    if not assinatura:
        return None

    agora = datetime.now()
    data_fim = _parse_iso(assinatura.get("data_fim"))
    novo_status = None

    if assinatura["status"] == "trial" and data_fim and data_fim < agora:
        novo_status = "inativa"
    elif assinatura["status"] == "ativa" and data_fim and data_fim < agora:
        novo_status = "inadimplente"

    if not novo_status:
        return assinatura

    cursor.execute(
        """
        UPDATE assinaturas
        SET status = ?, data_fim = COALESCE(data_fim, ?)
        WHERE id = ?
        """,
        (novo_status, _agora_iso(), assinatura["id"]),
    )
    assinatura["status"] = novo_status
    return assinatura


def buscar_assinatura_atual(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.*, p.codigo AS plano_codigo, p.nome AS plano_nome, p.tipo AS plano_tipo,
               p.preco_mensal, p.limite_atletas
        FROM assinaturas a
        INNER JOIN planos p ON p.id = a.plano_id
        WHERE a.usuario_id = ?
        ORDER BY CASE a.status
            WHEN 'ativa' THEN 0
            WHEN 'trial' THEN 1
            WHEN 'inadimplente' THEN 2
            WHEN 'inativa' THEN 3
            WHEN 'cancelada' THEN 4
            ELSE 5
        END,
        a.criado_em DESC,
        a.id DESC
        LIMIT 1
        """,
        (usuario_id,),
    )
    assinatura = _linha_para_dict(cursor.fetchone())
    assinatura = _normalizar_assinatura(cursor, assinatura)
    conn.commit()
    conn.close()
    return assinatura


def garantir_assinatura_inicial(usuario):
    assinatura = buscar_assinatura_atual(usuario["id"])
    if assinatura:
        return assinatura
    return criar_trial_assinatura(usuario["id"], usuario.get("tipo_usuario"))


def usuario_tem_acesso(usuario):
    assinatura = garantir_assinatura_inicial(usuario)
    tem_acesso = bool(assinatura and assinatura.get("status") in STATUS_COM_ACESSO)
    return tem_acesso, assinatura


def criar_assinatura_manual(usuario, plano):
    retorno_gateway = criar_assinatura_gateway(usuario, plano)
    inicio = datetime.now()
    data_inicio = inicio.isoformat(timespec="seconds")
    data_fim = (inicio + timedelta(days=30)).isoformat(timespec="seconds")

    conn = conectar()
    cursor = conn.cursor()
    _encerrar_assinaturas_abertas(cursor, usuario["id"])
    cursor.execute(
        """
        INSERT INTO assinaturas (
            usuario_id, plano_id, status, data_inicio, data_fim,
            renovacao_automatica, gateway, gateway_reference, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usuario["id"],
            plano["id"],
            retorno_gateway["status"],
            data_inicio,
            data_fim,
            1,
            retorno_gateway.get("gateway", "manual"),
            retorno_gateway.get("gateway_reference"),
            _agora_iso(),
        ),
    )
    assinatura_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura_id)


def assinar_plano_manual(usuario, plano_codigo):
    plano = buscar_plano_por_codigo(plano_codigo)
    if not plano or not int(plano.get("ativo", 0)):
        return None, "Plano indisponivel."

    if plano["tipo"] != usuario.get("tipo_usuario"):
        return None, "Este plano nao corresponde ao perfil da sua conta."

    assinatura = criar_assinatura_manual(usuario, plano)
    return assinatura, "Assinatura ativada manualmente para testes."


def cancelar_renovacao_automatica(usuario_id):
    assinatura = buscar_assinatura_atual(usuario_id)
    if not assinatura:
        return None, "Nenhuma assinatura encontrada."

    if assinatura.get("gateway_reference"):
        cancelar_assinatura_gateway(assinatura["gateway_reference"])

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE assinaturas
        SET renovacao_automatica = 0
        WHERE id = ?
        """,
        (assinatura["id"],),
    )
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura["id"]), "Renovacao automatica desativada."


def expirar_assinatura_atual_para_teste(usuario_id):
    assinatura = buscar_assinatura_atual(usuario_id)
    if not assinatura:
        return None, "Nenhuma assinatura encontrada."

    novo_status = "inativa" if assinatura.get("status") == "trial" else "inadimplente"
    agora = _agora_iso()

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE assinaturas
        SET status = ?, data_fim = ?
        WHERE id = ?
        """,
        (novo_status, agora, assinatura["id"]),
    )
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura["id"]), "Assinatura expirada para teste."


def resumo_status_assinatura(assinatura):
    if not assinatura:
        return {
            "titulo": "Sem assinatura",
            "descricao": "Nenhuma assinatura encontrada para esta conta.",
        }

    status = assinatura.get("status")
    if status == "ativa":
        titulo = "Assinatura ativa"
    elif status == "trial":
        titulo = "Periodo de teste"
    elif status == "inadimplente":
        titulo = "Pagamento pendente"
    elif status == "cancelada":
        titulo = "Assinatura cancelada"
    else:
        titulo = "Assinatura inativa"

    data_fim = assinatura.get("data_fim") or "sem data definida"
    descricao = (
        f"Plano: {assinatura.get('plano_nome', 'N/A')} | "
        f"Status: {status_para_exibicao(status)} | Vigencia ate: {data_fim}"
    )
    return {
        "titulo": titulo,
        "descricao": descricao,
    }
