from __future__ import annotations

import json
import logging
import traceback
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from core.banco import conectar
from core.pagamentos_gateway import (
    cancelar_assinatura_gateway,
    criar_assinatura_gateway,
    criar_cobranca_gateway,
)
from core.treinador import atleta_possui_vinculo_ativo
from core.usuarios import buscar_usuario_por_id, diagnosticar_dados_checkout


TRIAL_DIAS = 14
STATUS_COM_ACESSO = {"ativa", "trial"}
STATUS_FINANCEIROS_QUITADOS = {"pago", "bonificado"}
CENTAVOS = Decimal("0.01")
LOGGER = logging.getLogger("trilab.checkout")


def _agora():
    return datetime.now()


def _agora_iso():
    return _agora().isoformat(timespec="seconds")


def _hoje():
    return _agora().date()


def _date_to_iso(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def _parse_date(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto[:19], formato).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        return None


def _to_decimal(valor):
    if valor is None or valor == "":
        return Decimal("0")
    return Decimal(str(valor)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _decimal_para_float(valor):
    return float(_to_decimal(valor))


def _payload_log(payload):
    return json.dumps(payload or {}, ensure_ascii=True, sort_keys=True, default=str)


def _linha_para_dict(linha):
    return dict(linha) if linha else None


def _normalizar_plano(plano):
    if not plano:
        return None
    item = dict(plano)
    item["tipo_plano"] = item.get("tipo_plano") or item.get("tipo") or "atleta"
    item["tipo"] = item["tipo_plano"]
    item["periodicidade"] = item.get("periodicidade") or "mensal"
    item["valor_base"] = _decimal_para_float(item.get("valor_base") or item.get("preco_mensal") or 0)
    item["preco_mensal"] = item["valor_base"]
    item["taxa_por_aluno_ativo"] = _decimal_para_float(item.get("taxa_por_aluno_ativo") or 0)
    item["ativo"] = int(bool(item.get("ativo", 1)))
    item["descricao"] = item.get("descricao") or ""
    item["beneficios"] = item.get("beneficios") or ""
    item["ordem_exibicao"] = int(item.get("ordem_exibicao") or 0)
    return item


def _normalizar_assinatura(assinatura):
    if not assinatura:
        return None
    item = dict(assinatura)
    item["plano_tipo"] = item.get("plano_tipo") or item.get("tipo_plano") or item.get("tipo") or "atleta"
    item["tipo_plano"] = item.get("tipo_plano") or item["plano_tipo"]
    item["periodicidade"] = item.get("periodicidade") or "mensal"
    item["valor_base_cobrado"] = _decimal_para_float(item.get("valor_base_cobrado") or item.get("valor") or item.get("valor_base") or 0)
    item["valor_taxa_alunos"] = _decimal_para_float(item.get("valor_taxa_alunos") or 0)
    item["valor_total_cobrado"] = _decimal_para_float(
        item.get("valor_total_cobrado")
        or item.get("valor")
        or (item["valor_base_cobrado"] + item["valor_taxa_alunos"])
    )
    item["valor"] = item["valor_total_cobrado"]
    item["quantidade_alunos_ativos_fechamento"] = int(item.get("quantidade_alunos_ativos_fechamento") or 0)
    return item


def _normalizar_pagamento(pagamento):
    if not pagamento:
        return None
    item = dict(pagamento)
    item["valor_bruto"] = _decimal_para_float(item.get("valor_bruto") or item.get("valor") or 0)
    item["valor_desconto"] = _decimal_para_float(item.get("valor_desconto") or 0)
    item["valor_final"] = _decimal_para_float(item.get("valor_final") or item.get("valor") or item["valor_bruto"])
    item["valor"] = item["valor_final"]
    return item


def _periodo_para_fim(data_inicio, periodicidade):
    base = _parse_date(data_inicio) or _hoje()
    dias = 365 if (periodicidade or "mensal") == "anual" else 30
    return base + timedelta(days=dias)


def _status_pagamento_para_assinatura(status_pagamento):
    mapa = {
        "pago": "ativa",
        "bonificado": "ativa",
        "pendente": "pendente",
        "atrasado": "inadimplente",
        "cancelado": "cancelada",
        "estornado": "cancelada",
    }
    return mapa.get(status_pagamento, "inadimplente")


def status_para_exibicao(status):
    return {
        "trial": "teste",
        "pendente": "pendente",
        "ativa": "ativa",
        "inadimplente": "inadimplente",
        "cancelada": "cancelada",
        "expirada": "expirada",
        "bonificado": "bonificado",
    }.get(status, status or "desconhecido")


def _consulta_assinaturas_base():
    return """
        SELECT
            a.*,
            p.codigo AS plano_codigo,
            p.nome AS plano_nome,
            COALESCE(p.tipo_plano, p.tipo) AS plano_tipo,
            COALESCE(p.periodicidade, 'mensal') AS periodicidade,
            COALESCE(p.valor_base, p.preco_mensal) AS valor_base,
            COALESCE(p.taxa_por_aluno_ativo, 0) AS taxa_por_aluno_ativo,
            p.limite_atletas
        FROM assinaturas a
        INNER JOIN planos p ON p.id = a.plano_id
    """


def listar_planos_ativos(tipo_plano=None):
    conn = conectar()
    cursor = conn.cursor()
    filtros = ["COALESCE(ativo, 1) = 1"]
    params = []
    if tipo_plano:
        filtros.append("COALESCE(tipo_plano, tipo) = %s")
        params.append(tipo_plano)
    cursor.execute(
        f"""
        SELECT *
        FROM planos
        WHERE {' AND '.join(filtros)}
        ORDER BY COALESCE(ordem_exibicao, 0), COALESCE(tipo_plano, tipo), periodicidade, COALESCE(valor_base, preco_mensal)
        """,
        tuple(params),
    )
    planos = [_normalizar_plano(item) for item in cursor.fetchall()]
    conn.close()
    return planos


def buscar_plano_por_codigo(codigo):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM planos WHERE codigo = %s", (codigo,))
    plano = _normalizar_plano(cursor.fetchone())
    conn.close()
    return plano


def buscar_plano_por_id(plano_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM planos WHERE id = %s", (plano_id,))
    plano = _normalizar_plano(cursor.fetchone())
    conn.close()
    return plano


def listar_planos_admin(incluir_inativos=True):
    conn = conectar()
    cursor = conn.cursor()
    filtros = []
    params = []
    if not incluir_inativos:
        filtros.append("COALESCE(ativo, 1) = 1")
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    cursor.execute(
        f"""
        SELECT *
        FROM planos
        {where_sql}
        ORDER BY COALESCE(ordem_exibicao, 0), COALESCE(tipo_plano, tipo), periodicidade, id
        """,
        tuple(params),
    )
    itens = [_normalizar_plano(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def _validar_payload_plano_admin(dados):
    codigo = (dados.get("codigo") or "").strip().lower()
    nome = (dados.get("nome") or "").strip()
    tipo_plano = (dados.get("tipo_plano") or "").strip().lower()
    periodicidade = (dados.get("periodicidade") or "mensal").strip().lower()
    if not codigo or not nome or tipo_plano not in {"atleta", "treinador"}:
        raise ValueError("Codigo, nome e tipo do plano sao obrigatorios.")

    return {
        "codigo": codigo,
        "nome": nome,
        "tipo_plano": tipo_plano,
        "periodicidade": periodicidade,
        "valor_base": float(_to_decimal(dados.get("valor_base"))),
        "taxa_por_aluno_ativo": float(_to_decimal(dados.get("taxa_por_aluno_ativo"))),
        "descricao": (dados.get("descricao") or "").strip() or None,
        "beneficios": (dados.get("beneficios") or "").strip() or None,
        "ordem_exibicao": int(dados.get("ordem_exibicao") or 0),
        "limite_atletas": dados.get("limite_atletas"),
        "ativo": int(bool(dados.get("ativo", True))),
    }


def atualizar_plano_admin(plano_id, dados):
    plano_id = int(plano_id)
    payload = _validar_payload_plano_admin(dados)
    plano_atual = buscar_plano_por_id(plano_id)
    if not plano_atual:
        raise ValueError("Plano nao encontrado.")

    plano_com_mesmo_codigo = buscar_plano_por_codigo(payload["codigo"])
    if plano_com_mesmo_codigo and int(plano_com_mesmo_codigo["id"]) != int(plano_id):
        raise ValueError("Ja existe outro plano com este codigo.")

    conn = conectar()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE planos
            SET codigo = %s,
                nome = %s,
                tipo = %s,
                tipo_plano = %s,
                periodicidade = %s,
                preco_mensal = %s,
                valor_base = %s,
                taxa_por_aluno_ativo = %s,
                descricao = %s,
                beneficios = %s,
                ordem_exibicao = %s,
                limite_atletas = %s,
                ativo = %s
            WHERE id = %s
            """,
            (
                payload["codigo"],
                payload["nome"],
                payload["tipo_plano"],
                payload["tipo_plano"],
                payload["periodicidade"],
                payload["valor_base"],
                payload["valor_base"],
                payload["taxa_por_aluno_ativo"],
                payload["descricao"],
                payload["beneficios"],
                payload["ordem_exibicao"],
                payload["limite_atletas"],
                payload["ativo"],
                plano_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError("Nenhum plano foi atualizado.")
        conn.commit()
    finally:
        conn.close()
    return buscar_plano_por_id(plano_id)


def salvar_plano_admin(dados):
    payload = _validar_payload_plano_admin(dados)
    plano_com_mesmo_codigo = buscar_plano_por_codigo(payload["codigo"])
    if plano_com_mesmo_codigo:
        raise ValueError("Ja existe um plano com este codigo.")

    conn = conectar()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO planos (
                codigo, nome, tipo, tipo_plano, periodicidade, preco_mensal, valor_base,
                taxa_por_aluno_ativo, descricao, beneficios, ordem_exibicao, limite_atletas, ativo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload["codigo"],
                payload["nome"],
                payload["tipo_plano"],
                payload["tipo_plano"],
                payload["periodicidade"],
                payload["valor_base"],
                payload["valor_base"],
                payload["taxa_por_aluno_ativo"],
                payload["descricao"],
                payload["beneficios"],
                payload["ordem_exibicao"],
                payload["limite_atletas"],
                payload["ativo"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return buscar_plano_por_codigo(payload["codigo"])


def alterar_status_plano(plano_id, ativo):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE planos SET ativo = %s WHERE id = %s", (int(bool(ativo)), plano_id))
    conn.commit()
    conn.close()
    return buscar_plano_por_id(plano_id)


def duplicar_plano(plano_id):
    plano = buscar_plano_por_id(plano_id)
    if not plano:
        raise ValueError("Plano nao encontrado.")
    base_codigo = f"{plano['codigo']}_copy"
    codigo = base_codigo
    contador = 2
    while buscar_plano_por_codigo(codigo):
        codigo = f"{base_codigo}_{contador}"
        contador += 1
    return salvar_plano_admin({
        "codigo": codigo,
        "nome": f"{plano['nome']} (Copia)",
        "tipo_plano": plano["tipo_plano"],
        "periodicidade": plano["periodicidade"],
        "valor_base": plano["valor_base"],
        "taxa_por_aluno_ativo": plano["taxa_por_aluno_ativo"],
        "descricao": plano.get("descricao"),
        "beneficios": plano.get("beneficios"),
        "ordem_exibicao": plano.get("ordem_exibicao", 0) + 1,
        "limite_atletas": plano.get("limite_atletas"),
        "ativo": False,
    })


def buscar_plano_padrao_por_tipo(tipo_usuario, periodicidade="mensal"):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM planos
        WHERE COALESCE(tipo_plano, tipo) = %s
          AND COALESCE(periodicidade, 'mensal') = %s
          AND COALESCE(ativo, 1) = 1
        ORDER BY COALESCE(valor_base, preco_mensal) ASC
        LIMIT 1
        """,
        ((tipo_usuario or "atleta").strip().lower(), (periodicidade or "mensal").strip().lower()),
    )
    plano = _normalizar_plano(cursor.fetchone())
    conn.close()
    return plano


def contar_alunos_ativos_treinador(treinador_id, data_referencia):
    data_ref = _parse_date(data_referencia) or _hoje()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM treinador_atleta ta
        JOIN usuarios u ON u.id = ta.atleta_id
        WHERE ta.treinador_id = %s
          AND COALESCE(ta.status_vinculo, ta.status, 'pendente') = 'ativo'
          AND COALESCE(u.status_conta, 'ativo') = 'ativo'
          AND COALESCE(ta.data_inicio, DATE(ta.created_at)) <= %s
          AND (ta.data_fim IS NULL OR ta.data_fim >= %s)
        """,
        (treinador_id, data_ref, data_ref),
    )
    total = int(cursor.fetchone()["total"] or 0)
    conn.close()
    return total


def calcular_valor_assinatura_treinador(treinador_id, plano_id, data_referencia):
    plano = buscar_plano_por_id(plano_id)
    if not plano:
        raise ValueError("Plano nao encontrado.")
    quantidade = contar_alunos_ativos_treinador(treinador_id, data_referencia)
    valor_base = _to_decimal(plano.get("valor_base"))
    taxa = _to_decimal(plano.get("taxa_por_aluno_ativo"))
    valor_taxa = (taxa * quantidade).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    total = (valor_base + valor_taxa).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    return {
        "treinador_id": treinador_id,
        "plano_id": plano_id,
        "data_referencia": _date_to_iso(data_referencia),
        "valor_base": float(valor_base),
        "taxa_por_aluno_ativo": float(taxa),
        "quantidade_alunos_ativos_fechamento": quantidade,
        "valor_taxa_alunos": float(valor_taxa),
        "valor_total_cobrado": float(total),
    }


def aplicar_desconto(valor_bruto, cupom_ou_regra=None):
    bruto = _to_decimal(valor_bruto)
    regra = cupom_ou_regra or {}
    tipo = (regra.get("tipo_desconto") or regra.get("tipo") or "").strip().lower()
    desconto = Decimal("0")

    if tipo == "percentual":
        percentual = Decimal(str(regra.get("percentual_desconto") or regra.get("percentual") or 0))
        desconto = (bruto * percentual / Decimal("100")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    elif tipo == "valor_fixo":
        desconto = _to_decimal(regra.get("valor_desconto") or regra.get("valor") or 0)
    elif tipo == "gratuidade":
        desconto = bruto

    desconto = min(bruto, max(Decimal("0"), desconto)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    final = max(Decimal("0"), bruto - desconto).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    bonificado = final == 0 and desconto > 0
    return {
        "valor_bruto": float(bruto),
        "valor_desconto": float(desconto),
        "valor_final": float(final),
        "status_pagamento": "bonificado" if bonificado else "pendente",
        "bonificado": bonificado,
    }


def buscar_cupom_por_codigo(codigo):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cupons_desconto WHERE UPPER(codigo) = UPPER(%s)", (codigo,))
    item = _linha_para_dict(cursor.fetchone())
    conn.close()
    return item


def validar_cupom_para_plano(cupom, plano, data_referencia=None):
    if not cupom:
        return False, "Cupom nao encontrado."
    if not bool(cupom.get("ativo", True)):
        return False, "Cupom inativo."

    hoje = _parse_date(data_referencia) or _hoje()
    inicio = _parse_date(cupom.get("data_inicio"))
    fim = _parse_date(cupom.get("data_fim"))
    if inicio and hoje < inicio:
        return False, "Cupom ainda nao iniciou."
    if fim and hoje > fim:
        return False, "Cupom expirado."

    aplicavel_para = (cupom.get("aplicavel_para") or "todos").lower()
    periodicidade = (cupom.get("periodicidade_aplicavel") or "todos").lower()
    plano_tipo = (plano.get("tipo_plano") or plano.get("tipo") or "").lower()
    plano_periodicidade = (plano.get("periodicidade") or "mensal").lower()

    if aplicavel_para not in {"todos", plano_tipo}:
        return False, "Cupom nao se aplica a este perfil."
    if periodicidade not in {"todos", plano_periodicidade}:
        return False, "Cupom nao se aplica a esta periodicidade."

    limite = cupom.get("quantidade_max_uso")
    usados = int(cupom.get("quantidade_usada") or 0)
    if limite is not None and usados >= int(limite):
        return False, "Cupom sem usos disponiveis."
    return True, ""


def _aplicar_e_registrar_desconto(cursor, usuario_id, assinatura_id, pagamento_id, desconto_info, cupom_ou_regra=None, aplicado_por="usuario"):
    if not desconto_info or float(desconto_info.get("valor_desconto") or 0) <= 0:
        return
    cupom_id = cupom_ou_regra.get("id") if isinstance(cupom_ou_regra, dict) else None
    cursor.execute(
        """
        INSERT INTO descontos_aplicados (
            cupom_id, usuario_id, assinatura_id, pagamento_id, valor_bruto,
            valor_desconto, valor_final, aplicado_por
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            cupom_id,
            usuario_id,
            assinatura_id,
            pagamento_id,
            desconto_info["valor_bruto"],
            desconto_info["valor_desconto"],
            desconto_info["valor_final"],
            aplicado_por,
        ),
    )
    if cupom_id:
        cursor.execute(
            """
            UPDATE cupons_desconto
            SET quantidade_usada = COALESCE(quantidade_usada, 0) + 1
            WHERE id = %s
            """,
            (cupom_id,),
        )


def _encerrar_assinaturas_abertas(cursor, usuario_id):
    agora = _agora_iso()
    cursor.execute(
        """
        UPDATE assinaturas
        SET status = CASE
                WHEN status = 'trial' THEN 'expirada'
                WHEN status = 'ativa' THEN 'cancelada'
                ELSE status
            END,
            data_fim = COALESCE(data_fim, %s)
        WHERE usuario_id = %s
          AND status IN ('trial', 'ativa')
        """,
        (agora, usuario_id),
    )


def _payload_assinatura_normalizado(cursor, usuario_id, plano, status, data_inicio, data_fim, data_renovacao, calculo=None, gateway="manual", gateway_reference=None, renovacao_automatica=1):
    calculo = calculo or {}
    valor_base = _to_decimal(calculo.get("valor_base") or plano.get("valor_base") or 0)
    quantidade = int(calculo.get("quantidade_alunos_ativos_fechamento") or 0)
    valor_taxa = _to_decimal(calculo.get("valor_taxa_alunos") or 0)
    valor_total = _to_decimal(calculo.get("valor_total_cobrado") or (valor_base + valor_taxa))
    cursor.execute(
        """
        INSERT INTO assinaturas (
            usuario_id, plano_id, tipo_plano, status, valor, data_inicio, data_fim,
            data_renovacao, valor_base_cobrado, quantidade_alunos_ativos_fechamento,
            valor_taxa_alunos, valor_total_cobrado, renovacao_automatica, gateway,
            gateway_reference, criado_em, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
        )
        RETURNING id
        """,
        (
            usuario_id,
            plano["id"],
            plano.get("tipo_plano"),
            status,
            float(valor_total),
            _date_to_iso(data_inicio),
            _date_to_iso(data_fim),
            _date_to_iso(data_renovacao),
            float(valor_base),
            quantidade,
            float(valor_taxa),
            float(valor_total),
            renovacao_automatica,
            gateway,
            gateway_reference,
            _agora_iso(),
        ),
    )
    return int(cursor.fetchone()["id"])


def criar_trial_assinatura(usuario_id, tipo_usuario):
    plano = buscar_plano_padrao_por_tipo(tipo_usuario, "mensal")
    if not plano:
        raise ValueError("Nenhum plano ativo encontrado para este perfil.")

    inicio = _hoje()
    fim = inicio + timedelta(days=TRIAL_DIAS)
    conn = conectar()
    cursor = conn.cursor()
    _encerrar_assinaturas_abertas(cursor, usuario_id)
    assinatura_id = _payload_assinatura_normalizado(
        cursor,
        usuario_id,
        plano,
        "trial",
        inicio,
        fim,
        fim,
        gateway="manual",
        gateway_reference=f"trial-{usuario_id}-{inicio.strftime('%Y%m%d')}",
        renovacao_automatica=0,
    )
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura_id)


def buscar_assinatura_por_id(assinatura_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(_consulta_assinaturas_base() + " WHERE a.id = %s", (assinatura_id,))
    assinatura = _normalizar_assinatura(cursor.fetchone())
    conn.close()
    return assinatura


def listar_assinaturas_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        _consulta_assinaturas_base() + """
        WHERE a.usuario_id = %s
        ORDER BY COALESCE(a.created_at, CURRENT_TIMESTAMP) DESC, a.id DESC
        """,
        (usuario_id,),
    )
    itens = [_normalizar_assinatura(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def _normalizar_status_assinatura(cursor, assinatura):
    if not assinatura:
        return None
    hoje = _hoje()
    data_fim = _parse_date(assinatura.get("data_fim"))
    novo_status = None
    if assinatura["status"] == "trial" and data_fim and data_fim < hoje:
        novo_status = "expirada"
    elif assinatura["status"] == "ativa" and data_fim and data_fim < hoje:
        novo_status = "inadimplente"
    if not novo_status:
        return assinatura
    cursor.execute("UPDATE assinaturas SET status = %s WHERE id = %s", (novo_status, assinatura["id"]))
    assinatura["status"] = novo_status
    return assinatura


def buscar_assinatura_atual(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        _consulta_assinaturas_base() + """
        WHERE a.usuario_id = %s
        ORDER BY CASE a.status
            WHEN 'ativa' THEN 0
            WHEN 'trial' THEN 1
            WHEN 'pendente' THEN 2
            WHEN 'inadimplente' THEN 3
            WHEN 'expirada' THEN 4
            WHEN 'cancelada' THEN 5
            ELSE 6
        END,
        COALESCE(a.created_at, CURRENT_TIMESTAMP) DESC,
        a.id DESC
        LIMIT 1
        """,
        (usuario_id,),
    )
    assinatura = _normalizar_assinatura(cursor.fetchone())
    assinatura = _normalizar_status_assinatura(cursor, assinatura)
    conn.commit()
    conn.close()
    return assinatura


def garantir_assinatura_inicial(usuario):
    assinatura = buscar_assinatura_atual(usuario["id"])
    if assinatura:
        return assinatura
    return criar_trial_assinatura(usuario["id"], usuario.get("tipo_usuario"))


def atleta_tem_treinador_ativo(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM treinador_atleta ta
        JOIN usuarios u ON u.id = ta.treinador_id
        LEFT JOIN LATERAL (
            SELECT status
            FROM assinaturas a
            WHERE a.usuario_id = u.id
            ORDER BY CASE a.status
                WHEN 'ativa' THEN 0
                WHEN 'trial' THEN 1
                WHEN 'pendente' THEN 2
                WHEN 'inadimplente' THEN 3
                ELSE 4
            END,
            COALESCE(a.created_at, CURRENT_TIMESTAMP) DESC,
            a.id DESC
            LIMIT 1
        ) assinatura ON TRUE
        WHERE ta.atleta_id = %s
          AND COALESCE(ta.status_vinculo, ta.status, 'pendente') = 'ativo'
          AND COALESCE(u.status_conta, 'ativo') = 'ativo'
          AND COALESCE(assinatura.status, '') IN ('ativa', 'trial')
        LIMIT 1
        """,
        (atleta_id,),
    )
    ativo = cursor.fetchone() is not None
    conn.close()
    return ativo


def usuario_tem_acesso_atleta(usuario_id):
    assinatura = buscar_assinatura_atual(usuario_id)
    if not assinatura:
        assinatura = criar_trial_assinatura(usuario_id, "atleta")
    return bool((assinatura or {}).get("status") in STATUS_COM_ACESSO or atleta_tem_treinador_ativo(usuario_id))


def avaliar_acesso_atleta(usuario_id):
    assinatura = buscar_assinatura_atual(usuario_id)
    if not assinatura:
        assinatura = criar_trial_assinatura(usuario_id, "atleta")
    tem_assinatura_ativa = bool((assinatura or {}).get("status") in STATUS_COM_ACESSO)
    vinculo_ativo = atleta_possui_vinculo_ativo(usuario_id)
    tem_treinador_ativo = atleta_tem_treinador_ativo(usuario_id)
    tem_acesso = tem_assinatura_ativa or tem_treinador_ativo
    return {
        "tem_acesso": tem_acesso,
        "assinatura": assinatura,
        "motivo": None if tem_acesso else "atleta_trial_expirado",
        "tem_assinatura_ativa": tem_assinatura_ativa,
        "tem_treinador_ativo": tem_treinador_ativo,
        "vinculo_ativo": vinculo_ativo,
    }


def _buscar_vinculo_atleta_por_status(atleta_id, statuses):
    if not statuses:
        return None
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ta.id,
               ta.treinador_id,
               ta.atleta_id,
               COALESCE(ta.status_vinculo, ta.status, 'pendente') AS status,
               u.nome AS treinador_nome,
               u.apelido AS treinador_apelido,
               u.email AS treinador_email,
               ta.created_at,
               ta.data_inicio,
               ta.data_fim
        FROM treinador_atleta ta
        JOIN usuarios u ON u.id = ta.treinador_id
        WHERE ta.atleta_id = %s
          AND COALESCE(ta.status_vinculo, ta.status, 'pendente') = ANY(%s)
        ORDER BY COALESCE(ta.data_fim, DATE(ta.created_at), CURRENT_DATE) DESC,
                 COALESCE(ta.created_at, CURRENT_TIMESTAMP) DESC,
                 ta.id DESC
        LIMIT 1
        """,
        (atleta_id, list(statuses)),
    )
    vinculo = cursor.fetchone()
    conn.close()
    return dict(vinculo) if vinculo else None


def _nome_treinador_contexto(vinculo):
    if not vinculo:
        return None
    return vinculo.get("treinador_apelido") or vinculo.get("treinador_nome")


def _dias_restantes_trial(assinatura):
    if not assinatura or (assinatura.get("status") or "").strip().lower() != "trial":
        return None
    data_fim = _parse_date(assinatura.get("data_fim"))
    if not data_fim:
        return None
    return max((data_fim - _hoje()).days, 0)


def obter_status_interface_atleta(usuario_id):
    avaliacao = avaliar_acesso_atleta(usuario_id)
    assinatura = avaliacao.get("assinatura")
    vinculo_ativo = avaliacao.get("vinculo_ativo")
    vinculo_pendente = _buscar_vinculo_atleta_por_status(usuario_id, ["pendente"])
    vinculo_encerrado = _buscar_vinculo_atleta_por_status(usuario_id, ["removido", "cancelado", "encerrado"])
    nome_treinador_ativo = _nome_treinador_contexto(vinculo_ativo)
    nome_treinador_pendente = _nome_treinador_contexto(vinculo_pendente)
    nome_treinador_encerrado = _nome_treinador_contexto(vinculo_encerrado)
    dias_trial = _dias_restantes_trial(assinatura)
    status_assinatura = (assinatura or {}).get("status")

    contexto = {
        "status": "assinatura_ativa_propria",
        "variant": "success",
        "titulo": "",
        "texto": "",
        "detalhe": None,
        "cta_label": None,
        "cta_destino": None,
        "mostrar_no_dashboard": False,
        "mostrar_no_bloqueio": False,
        "tem_acesso": bool(avaliacao.get("tem_acesso")),
        "assinatura": assinatura,
        "dias_trial_restantes": dias_trial,
        "treinador_nome": nome_treinador_ativo or nome_treinador_pendente or nome_treinador_encerrado,
    }

    if avaliacao.get("tem_treinador_ativo") and vinculo_ativo:
        contexto.update(
            {
                "status": "vinculo_ativo",
                "variant": "success",
                "titulo": "Voce esta treinando com seu treinador",
                "texto": "Seu acesso esta vinculado ao acompanhamento do seu treinador. Seus treinos e evolucoes estao liberados normalmente na plataforma.",
                "detalhe": f"Treinador responsavel: {nome_treinador_ativo}" if nome_treinador_ativo else None,
                "mostrar_no_dashboard": True,
            }
        )
        return contexto

    if vinculo_pendente:
        contexto.update(
            {
                "status": "vinculo_pendente",
                "variant": "warning" if avaliacao.get("tem_acesso") else "danger",
                "titulo": "Seu vinculo com o treinador esta pendente",
                "texto": (
                    "Assim que o treinador aprovar seu vinculo, seu acesso sera liberado normalmente pela plataforma."
                    if not avaliacao.get("tem_acesso")
                    else "Assim que o treinador aprovar seu vinculo, seu acesso passara a ser coberto normalmente pela plataforma."
                ),
                "detalhe": (
                    f"Treinador aguardando aprovacao: {nome_treinador_pendente}"
                    if nome_treinador_pendente
                    else None
                ),
                "cta_label": "Ver planos" if not avaliacao.get("tem_acesso") else None,
                "cta_destino": "pages/planos.py" if not avaliacao.get("tem_acesso") else None,
                "mostrar_no_dashboard": True,
                "mostrar_no_bloqueio": not avaliacao.get("tem_acesso"),
            }
        )
        if status_assinatura == "trial" and dias_trial is not None:
            contexto["texto"] += f" Enquanto isso, seu acesso segue pelo teste gratis. Faltam {dias_trial} dias para o fim do seu teste."
        elif not avaliacao.get("tem_acesso"):
            contexto["texto"] += " Se preferir, voce tambem pode contratar um plano proprio para continuar."
        return contexto

    if status_assinatura == "trial":
        contexto.update(
            {
                "status": "trial_ativo",
                "variant": "info",
                "titulo": "Seu teste gratis esta ativo",
                "texto": "Voce esta no periodo de teste do TriLab. Aproveite para explorar seus treinos e, quando quiser, escolha um plano para continuar.",
                "detalhe": f"Faltam {dias_trial} dias para o fim do seu teste." if dias_trial is not None else None,
                "cta_label": "Ver planos",
                "cta_destino": "pages/planos.py",
                "mostrar_no_dashboard": True,
            }
        )
        return contexto

    if vinculo_encerrado and not avaliacao.get("tem_acesso"):
        contexto.update(
            {
                "status": "vinculo_encerrado",
                "variant": "danger",
                "titulo": "Seu vinculo com o treinador foi encerrado",
                "texto": "Para continuar usando o TriLab, escolha um plano ou vincule-se novamente a um treinador.",
                "detalhe": f"Ultimo treinador vinculado: {nome_treinador_encerrado}" if nome_treinador_encerrado else None,
                "cta_label": "Ver planos",
                "cta_destino": "pages/planos.py",
                "mostrar_no_dashboard": False,
                "mostrar_no_bloqueio": True,
            }
        )
        return contexto

    if not avaliacao.get("tem_acesso"):
        contexto.update(
            {
                "status": "sem_acesso",
                "variant": "danger",
                "titulo": "Seu periodo de teste terminou",
                "texto": "Para continuar usando o TriLab, escolha um plano ou treine com um treinador parceiro.",
                "cta_label": "Ver planos",
                "cta_destino": "pages/planos.py",
                "mostrar_no_dashboard": False,
                "mostrar_no_bloqueio": True,
            }
        )
        return contexto

    if status_assinatura == "ativa":
        contexto.update(
            {
                "status": "assinatura_ativa_propria",
                "variant": "success",
                "titulo": "Seu plano individual esta ativo",
                "texto": "Seu acesso esta liberado normalmente para acompanhar treinos, progresso e evolucoes na plataforma.",
                "mostrar_no_dashboard": False,
            }
        )
    return contexto


def avaliar_acesso_usuario(usuario):
    assinatura = garantir_assinatura_inicial(usuario)
    tipo_usuario = (usuario.get("tipo_usuario") or "atleta").strip().lower()
    status_assinatura = (assinatura or {}).get("status")

    if tipo_usuario == "treinador":
        tem_acesso = status_assinatura in STATUS_COM_ACESSO
        return {
            "tem_acesso": tem_acesso,
            "assinatura": assinatura,
            "motivo": None if tem_acesso else "treinador_trial_expirado",
            "tipo_usuario": tipo_usuario,
            "tem_treinador_ativo": False,
        }

    if tipo_usuario == "atleta":
        avaliacao = avaliar_acesso_atleta(usuario["id"])
        avaliacao["tipo_usuario"] = tipo_usuario
        return avaliacao

    return {
        "tem_acesso": status_assinatura in STATUS_COM_ACESSO,
        "assinatura": assinatura,
        "motivo": None,
        "tipo_usuario": tipo_usuario,
        "tem_treinador_ativo": False,
    }


def usuario_tem_acesso(usuario):
    avaliacao = avaliar_acesso_usuario(usuario)
    return bool(avaliacao["tem_acesso"]), avaliacao["assinatura"]


def buscar_pagamento_por_id(pagamento_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT pg.*, u.nome AS usuario_nome, u.tipo_usuario, p.nome AS plano_nome
        FROM pagamentos pg
        JOIN usuarios u ON u.id = pg.usuario_id
        LEFT JOIN assinaturas a ON a.id = pg.assinatura_id
        LEFT JOIN planos p ON p.id = a.plano_id
        WHERE pg.id = %s
        """,
        (pagamento_id,),
    )
    pagamento = _normalizar_pagamento(cursor.fetchone())
    conn.close()
    return pagamento


def gerar_pagamento_assinatura(usuario_id, assinatura_id, cupom_ou_regra=None, status_inicial="pendente", metodo_pagamento="manual", aplicado_por="usuario"):
    assinatura = buscar_assinatura_por_id(assinatura_id)
    if not assinatura:
        raise ValueError("Assinatura nao encontrada.")

    if cupom_ou_regra and cupom_ou_regra.get("codigo"):
        ok, motivo = validar_cupom_para_plano(cupom_ou_regra, assinatura)
        if not ok:
            raise ValueError(motivo)

    desconto_info = aplicar_desconto(assinatura["valor_total_cobrado"], cupom_ou_regra)
    status_pagamento = "bonificado" if desconto_info["bonificado"] else status_inicial
    retorno_gateway = criar_cobranca_gateway(
        usuario_id=usuario_id,
        assinatura_id=assinatura_id,
        valor=desconto_info["valor_final"],
        status_inicial=status_pagamento,
        metodo_pagamento=metodo_pagamento,
    )

    conn = conectar()
    cursor = conn.cursor()
    data_pagamento = _agora_iso() if status_pagamento in STATUS_FINANCEIROS_QUITADOS else None
    cursor.execute(
        """
        INSERT INTO pagamentos (
            usuario_id, assinatura_id, valor, valor_bruto, valor_desconto, valor_final,
            status, metodo_pagamento, data_pagamento, data_vencimento, referencia_externa,
            gateway, gateway_reference
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            usuario_id,
            assinatura_id,
            desconto_info["valor_final"],
            desconto_info["valor_bruto"],
            desconto_info["valor_desconto"],
            desconto_info["valor_final"],
            status_pagamento,
            metodo_pagamento,
            data_pagamento,
            assinatura.get("data_renovacao") or assinatura.get("data_fim"),
            retorno_gateway.get("gateway_reference"),
            retorno_gateway.get("gateway", "manual"),
            retorno_gateway.get("gateway_reference"),
        ),
    )
    pagamento_id = int(cursor.fetchone()["id"])
    _aplicar_e_registrar_desconto(cursor, usuario_id, assinatura_id, pagamento_id, desconto_info, cupom_ou_regra, aplicado_por)
    cursor.execute(
        """
        UPDATE assinaturas
        SET status = %s,
            valor = %s,
            valor_total_cobrado = %s,
            gateway_reference = COALESCE(gateway_reference, %s)
        WHERE id = %s
        """,
        (
            _status_pagamento_para_assinatura(status_pagamento),
            desconto_info["valor_final"],
            desconto_info["valor_bruto"],
            retorno_gateway.get("gateway_reference"),
            assinatura_id,
        ),
    )
    conn.commit()
    conn.close()
    return buscar_pagamento_por_id(pagamento_id)


def criar_assinatura_manual(usuario, plano, cupom_codigo=None):
    LOGGER.info(
        "[CHECKOUT_DEBUG] Iniciando criacao de assinatura manual/integrada | %s",
        _payload_log(
            {
                "funcao": "criar_assinatura_manual",
                "usuario_id": usuario.get("id"),
                "tipo_usuario": usuario.get("tipo_usuario"),
                "plano_codigo": plano.get("codigo"),
                "plano_tipo": plano.get("tipo_plano"),
                "cupom_codigo": cupom_codigo,
            }
        ),
    )
    retorno_gateway = criar_assinatura_gateway(usuario, plano)
    if not retorno_gateway.get("ok"):
        LOGGER.error(
            "[ASAAS_ERROR] Falha retornada pelo gateway na criacao da assinatura | %s",
            _payload_log(
                {
                    "funcao": "criar_assinatura_manual",
                    "usuario_id": usuario.get("id"),
                    "plano_codigo": plano.get("codigo"),
                    "gateway": retorno_gateway.get("gateway"),
                    "erro": retorno_gateway.get("erro"),
                    "status": retorno_gateway.get("status"),
                    "mensagem": retorno_gateway.get("mensagem"),
                    "url": retorno_gateway.get("url"),
                    "method": retorno_gateway.get("method"),
                    "path": retorno_gateway.get("path"),
                    "status_code": retorno_gateway.get("status_code"),
                    "source": retorno_gateway.get("source"),
                    "payload_enviado": retorno_gateway.get("request_payload"),
                    "params_enviados": retorno_gateway.get("request_params"),
                    "resposta_gateway": retorno_gateway.get("payload") or retorno_gateway.get("data"),
                    "response_text": retorno_gateway.get("response_text"),
                }
            ),
        )
        raise ValueError(retorno_gateway.get("mensagem") or "Falha ao criar assinatura no gateway.")
    inicio = _hoje()
    fim = _periodo_para_fim(inicio, plano.get("periodicidade"))
    calculo = None
    if plano.get("tipo_plano") == "treinador":
        calculo = calcular_valor_assinatura_treinador(usuario["id"], plano["id"], fim)

    cupom = buscar_cupom_por_codigo(cupom_codigo) if cupom_codigo else None
    if cupom_codigo and not cupom:
        raise ValueError("Cupom nao encontrado.")

    conn = conectar()
    cursor = conn.cursor()
    _encerrar_assinaturas_abertas(cursor, usuario["id"])
    assinatura_id = _payload_assinatura_normalizado(
        cursor,
        usuario["id"],
        plano,
        "pendente" if retorno_gateway.get("gateway") == "asaas" and plano.get("tipo_plano") == "atleta" else "ativa",
        inicio,
        fim,
        fim,
        calculo=calculo,
        gateway=retorno_gateway.get("gateway", "manual"),
        gateway_reference=retorno_gateway.get("gateway_reference"),
        renovacao_automatica=1,
    )
    cursor.execute(
        """
        UPDATE assinaturas
        SET asaas_subscription_id = %s
        WHERE id = %s
        """,
        (retorno_gateway.get("asaas_subscription_id"), assinatura_id),
    )
    conn.commit()
    conn.close()
    if retorno_gateway.get("gateway") != "asaas" or plano.get("tipo_plano") != "atleta":
        gerar_pagamento_assinatura(
            usuario["id"],
            assinatura_id,
            cupom_ou_regra=cupom,
            status_inicial="pago",
            metodo_pagamento=retorno_gateway.get("gateway", "manual"),
            aplicado_por="usuario" if cupom else "manual",
        )
    assinatura = buscar_assinatura_por_id(assinatura_id) or {}
    assinatura["invoice_url"] = retorno_gateway.get("invoice_url")
    assinatura["redirect_url"] = retorno_gateway.get("redirect_url") or retorno_gateway.get("invoice_url")
    assinatura["asaas_payment_id"] = retorno_gateway.get("asaas_payment_id")
    assinatura["payment_payload"] = retorno_gateway.get("payment_payload")
    assinatura["mensagem_gateway"] = retorno_gateway.get("mensagem")
    return assinatura


def assinar_plano_manual(usuario, plano_codigo, cupom_codigo=None):
    LOGGER.info(
        "[CHECKOUT_DEBUG] Entrada no fluxo assinar_plano_manual | %s",
        _payload_log(
            {
                "funcao": "assinar_plano_manual",
                "usuario_id": (usuario or {}).get("id"),
                "tipo_usuario": (usuario or {}).get("tipo_usuario"),
                "plano_codigo": plano_codigo,
                "cupom_codigo": cupom_codigo,
            }
        ),
    )
    usuario_atual = buscar_usuario_por_id(usuario["id"]) if usuario and usuario.get("id") else usuario
    diagnostico_checkout = diagnosticar_dados_checkout(usuario_atual)
    if not diagnostico_checkout["ok"]:
        LOGGER.warning(
            "[CHECKOUT_DEBUG] Fluxo interrompido por diagnostico de checkout | %s",
            _payload_log(
                {
                    "funcao": "assinar_plano_manual",
                    "usuario_id": (usuario_atual or {}).get("id"),
                    "diagnostico": diagnostico_checkout,
                }
            ),
        )
        return None, diagnostico_checkout["mensagem"]

    plano = buscar_plano_por_codigo(plano_codigo)
    if not plano or not int(plano.get("ativo", 0)):
        LOGGER.warning(
            "[CHECKOUT_DEBUG] Plano indisponivel no checkout | %s",
            _payload_log({"funcao": "assinar_plano_manual", "usuario_id": (usuario_atual or {}).get("id"), "plano_codigo": plano_codigo}),
        )
        return None, "Plano indisponivel."
    if plano["tipo_plano"] != usuario_atual.get("tipo_usuario"):
        LOGGER.warning(
            "[CHECKOUT_DEBUG] Plano divergente do perfil do usuario | %s",
            _payload_log(
                {
                    "funcao": "assinar_plano_manual",
                    "usuario_id": (usuario_atual or {}).get("id"),
                    "plano_codigo": plano_codigo,
                    "plano_tipo": plano.get("tipo_plano"),
                    "tipo_usuario": usuario_atual.get("tipo_usuario"),
                }
            ),
        )
        return None, "Este plano nao corresponde ao perfil da sua conta."
    if plano["tipo_plano"] == "atleta" and atleta_tem_treinador_ativo(usuario_atual["id"]):
        LOGGER.warning(
            "[CHECKOUT_DEBUG] Checkout individual bloqueado por vinculo ativo com treinador | %s",
            _payload_log(
                {
                    "funcao": "assinar_plano_manual",
                    "usuario_id": usuario_atual.get("id"),
                    "plano_codigo": plano_codigo,
                }
            ),
        )
        return None, "Seu acesso ja esta coberto por um treinador ativo. Nao ha cobranca individual para este perfil vinculado."
    try:
        LOGGER.info(
            "[CHECKOUT_DEBUG] Prosseguindo para criacao de assinatura | %s",
            _payload_log(
                {
                    "funcao": "assinar_plano_manual",
                    "usuario_id": usuario_atual.get("id"),
                    "plano_codigo": plano.get("codigo"),
                    "plano_tipo": plano.get("tipo_plano"),
                    "gateway_esperado": "asaas" if plano.get("tipo_plano") == "atleta" else "manual",
                }
            ),
        )
        assinatura = criar_assinatura_manual(usuario_atual, plano, cupom_codigo=cupom_codigo)
    except ValueError as exc:
        LOGGER.error(
            "[CHECKOUT_TRACE] Erro de negocio durante o checkout | %s",
            _payload_log(
                {
                    "funcao": "assinar_plano_manual",
                    "usuario_id": usuario_atual.get("id"),
                    "plano_codigo": plano.get("codigo"),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "traceback": traceback.format_exc(),
                }
            ),
        )
        return None, str(exc)
    except Exception as exc:
        LOGGER.error(
            "[CHECKOUT_TRACE] Erro inesperado durante o checkout | %s",
            _payload_log(
                {
                    "funcao": "assinar_plano_manual",
                    "usuario_id": usuario_atual.get("id"),
                    "plano_codigo": plano.get("codigo"),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "traceback": traceback.format_exc(),
                }
            ),
        )
        return None, "Erro ao iniciar pagamento. Verifique os logs com o marcador CHECKOUT_DEBUG."
    LOGGER.info(
        "[CHECKOUT_DEBUG] Checkout concluiu a etapa local de criacao de assinatura | %s",
        _payload_log(
            {
                "funcao": "assinar_plano_manual",
                "usuario_id": usuario_atual.get("id"),
                "plano_codigo": plano.get("codigo"),
                "assinatura_id": assinatura.get("id"),
                "gateway": assinatura.get("gateway"),
                "status_assinatura": assinatura.get("status"),
                "gateway_reference": assinatura.get("gateway_reference"),
            }
        ),
    )
    if assinatura.get("gateway") == "asaas" and plano.get("tipo_plano") == "atleta":
        if assinatura.get("invoice_url"):
            return assinatura, "Redirecionando voce para a cobranca do Asaas."
        return (
            assinatura,
            assinatura.get("mensagem_gateway")
            or "Assinatura criada no Asaas, mas nao foi possivel abrir a cobranca automaticamente. "
            "Acesse Minha Assinatura para acompanhar o status enquanto o webhook conclui a liberacao apos o pagamento.",
        )
    return assinatura, "Assinatura ativada manualmente para testes."


def cancelar_renovacao_automatica(usuario_id):
    assinatura = buscar_assinatura_atual(usuario_id)
    if not assinatura:
        return None, "Nenhuma assinatura encontrada."
    if assinatura.get("gateway_reference"):
        cancelar_assinatura_gateway(assinatura["gateway_reference"])
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE assinaturas SET renovacao_automatica = 0 WHERE id = %s", (assinatura["id"],))
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura["id"]), "Renovacao automatica desativada."


def expirar_assinatura_atual_para_teste(usuario_id):
    assinatura = buscar_assinatura_atual(usuario_id)
    if not assinatura:
        return None, "Nenhuma assinatura encontrada."
    novo_status = "expirada" if assinatura.get("status") == "trial" else "inadimplente"
    agora = _agora_iso()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE assinaturas SET status = %s, data_fim = %s WHERE id = %s", (novo_status, agora, assinatura["id"]))
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura["id"]), "Assinatura expirada para teste."


def resumo_status_assinatura(assinatura):
    if not assinatura:
        return {"titulo": "Sem assinatura", "descricao": "Nenhuma assinatura encontrada para esta conta."}
    titulo = {
        "ativa": "Assinatura ativa",
        "trial": "Periodo de teste",
        "pendente": "Assinatura pendente",
        "inadimplente": "Pagamento pendente",
        "cancelada": "Assinatura cancelada",
        "expirada": "Assinatura expirada",
    }.get(assinatura.get("status"), "Assinatura inativa")
    data_fim = assinatura.get("data_fim") or "sem data definida"
    descricao = (
        f"Plano: {assinatura.get('plano_nome', 'N/A')} | "
        f"Status: {status_para_exibicao(assinatura.get('status'))} | Vigencia ate: {data_fim}"
    )
    return {"titulo": titulo, "descricao": descricao}


def listar_pagamentos_admin(status=None, tipo_usuario=None, periodo_inicio=None, periodo_fim=None, plano_id=None):
    filtros = []
    params = []
    if status:
        filtros.append("pg.status = %s")
        params.append(status)
    if tipo_usuario:
        filtros.append("u.tipo_usuario = %s")
        params.append(tipo_usuario)
    if periodo_inicio:
        filtros.append("COALESCE(pg.data_vencimento, pg.created_at::text) >= %s")
        params.append(_date_to_iso(periodo_inicio))
    if periodo_fim:
        filtros.append("COALESCE(pg.data_vencimento, pg.created_at::text) <= %s")
        params.append(_date_to_iso(periodo_fim))
    if plano_id:
        filtros.append("a.plano_id = %s")
        params.append(plano_id)
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT
            pg.*,
            u.nome AS usuario_nome,
            u.tipo_usuario,
            p.nome AS plano_nome,
            p.codigo AS plano_codigo,
            a.status AS assinatura_status
        FROM pagamentos pg
        JOIN usuarios u ON u.id = pg.usuario_id
        LEFT JOIN assinaturas a ON a.id = pg.assinatura_id
        LEFT JOIN planos p ON p.id = a.plano_id
        {where_sql}
        ORDER BY COALESCE(pg.created_at, CURRENT_TIMESTAMP) DESC, pg.id DESC
        """,
        tuple(params),
    )
    itens = [_normalizar_pagamento(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def listar_descontos_aplicados_admin(periodo_inicio=None, periodo_fim=None):
    filtros = []
    params = []
    if periodo_inicio:
        filtros.append("d.created_at::date >= %s")
        params.append(_date_to_iso(periodo_inicio))
    if periodo_fim:
        filtros.append("d.created_at::date <= %s")
        params.append(_date_to_iso(periodo_fim))
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT
            d.*,
            u.nome AS usuario_nome,
            u.tipo_usuario,
            c.codigo AS cupom_codigo,
            p.nome AS plano_nome
        FROM descontos_aplicados d
        JOIN usuarios u ON u.id = d.usuario_id
        LEFT JOIN cupons_desconto c ON c.id = d.cupom_id
        LEFT JOIN assinaturas a ON a.id = d.assinatura_id
        LEFT JOIN planos p ON p.id = a.plano_id
        {where_sql}
        ORDER BY d.created_at DESC, d.id DESC
        """,
        tuple(params),
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def listar_pagamentos_treinador(treinador_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.*, u.nome AS atleta_nome, u.email AS atleta_email
        FROM cobrancas_alunos_treinador c
        JOIN usuarios u ON u.id = c.atleta_id
        WHERE c.treinador_id = %s
        ORDER BY COALESCE(c.data_vencimento, CURRENT_DATE) DESC, c.id DESC
        """,
        (treinador_id,),
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def listar_assinaturas_admin():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(_consulta_assinaturas_base() + " ORDER BY COALESCE(a.created_at, CURRENT_TIMESTAMP) DESC, a.id DESC")
    itens = [_normalizar_assinatura(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def listar_assinaturas_admin_filtradas(tipo_usuario=None, status=None, plano_id=None, periodo_inicio=None, periodo_fim=None, com_desconto=None, somente_trial=None):
    filtros = []
    params = []
    if tipo_usuario:
        filtros.append("u.tipo_usuario = %s")
        params.append(tipo_usuario)
    if status:
        filtros.append("a.status = %s")
        params.append(status)
    if plano_id:
        filtros.append("a.plano_id = %s")
        params.append(plano_id)
    if periodo_inicio:
        filtros.append("a.data_inicio >= %s")
        params.append(_date_to_iso(periodo_inicio))
    if periodo_fim:
        filtros.append("COALESCE(a.data_renovacao::text, a.data_fim, a.data_inicio) <= %s")
        params.append(_date_to_iso(periodo_fim))
    if com_desconto is True:
        filtros.append("EXISTS (SELECT 1 FROM descontos_aplicados d WHERE d.assinatura_id = a.id)")
    if somente_trial:
        filtros.append("a.status = 'trial'")
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT
            a.*,
            u.nome AS usuario_nome,
            u.email AS usuario_email,
            u.tipo_usuario,
            p.codigo AS plano_codigo,
            p.nome AS plano_nome,
            COALESCE(p.periodicidade, 'mensal') AS periodicidade,
            COALESCE(p.valor_base, p.preco_mensal) AS valor_base,
            COALESCE((
                SELECT SUM(d.valor_desconto)
                FROM descontos_aplicados d
                WHERE d.assinatura_id = a.id
            ), 0) AS desconto_total
        FROM assinaturas a
        JOIN usuarios u ON u.id = a.usuario_id
        JOIN planos p ON p.id = a.plano_id
        {where_sql}
        ORDER BY COALESCE(a.created_at, CURRENT_TIMESTAMP) DESC, a.id DESC
        """,
        tuple(params),
    )
    itens = []
    for item in cursor.fetchall():
        assinatura = _normalizar_assinatura(item)
        assinatura["usuario_nome"] = item.get("usuario_nome")
        assinatura["usuario_email"] = item.get("usuario_email")
        assinatura["tipo_usuario"] = item.get("tipo_usuario")
        assinatura["plano_codigo"] = item.get("plano_codigo")
        assinatura["desconto_total"] = _decimal_para_float(item.get("desconto_total") or 0)
        assinatura["valor_final"] = max(0.0, assinatura["valor_total_cobrado"] - assinatura["desconto_total"])
        itens.append(assinatura)
    conn.close()
    return itens


def atualizar_status_assinatura_admin(assinatura_id, novo_status):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE assinaturas SET status = %s WHERE id = %s", (novo_status, assinatura_id))
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura_id)


def trocar_plano_assinatura_admin(assinatura_id, novo_plano_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE assinaturas
        SET plano_id = %s,
            tipo_plano = (SELECT COALESCE(tipo_plano, tipo) FROM planos WHERE id = %s),
            valor_base_cobrado = (SELECT COALESCE(valor_base, preco_mensal) FROM planos WHERE id = %s),
            valor_total_cobrado = (
                SELECT COALESCE(valor_base, preco_mensal) + COALESCE(taxa_por_aluno_ativo, 0) * COALESCE(assinaturas.quantidade_alunos_ativos_fechamento, 0)
                FROM planos WHERE id = %s
            )
        WHERE id = %s
        """,
        (novo_plano_id, novo_plano_id, novo_plano_id, novo_plano_id, assinatura_id),
    )
    conn.commit()
    conn.close()
    return buscar_assinatura_por_id(assinatura_id)


def listar_historico_financeiro_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM pagamentos
        WHERE usuario_id = %s
        ORDER BY COALESCE(created_at, CURRENT_TIMESTAMP) DESC, id DESC
        """,
        (usuario_id,),
    )
    itens = [_normalizar_pagamento(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def atualizar_status_pagamento(pagamento_id, novo_status):
    conn = conectar()
    cursor = conn.cursor()
    data_pagamento = _agora_iso() if novo_status in STATUS_FINANCEIROS_QUITADOS else None
    cursor.execute(
        """
        UPDATE pagamentos
        SET status = %s,
            data_pagamento = COALESCE(%s, data_pagamento)
        WHERE id = %s
        RETURNING assinatura_id
        """,
        (novo_status, data_pagamento, pagamento_id),
    )
    linha = cursor.fetchone()
    if linha and linha.get("assinatura_id"):
        cursor.execute("UPDATE assinaturas SET status = %s WHERE id = %s", (_status_pagamento_para_assinatura(novo_status), linha["assinatura_id"]))
    conn.commit()
    conn.close()
    return buscar_pagamento_por_id(pagamento_id)


def gerar_cobranca_aluno_treinador(treinador_id, atleta_id, valor, periodicidade, descricao=None, data_vencimento=None):
    valor_decimal = _to_decimal(valor)
    vencimento = _parse_date(data_vencimento) or _periodo_para_fim(_hoje(), periodicidade)
    retorno_gateway = criar_cobranca_gateway(
        treinador_id=treinador_id,
        atleta_id=atleta_id,
        valor=float(valor_decimal),
        periodicidade=periodicidade,
        descricao=descricao,
    )
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO cobrancas_alunos_treinador (
            treinador_id, atleta_id, descricao, valor, periodicidade, status,
            data_vencimento, gateway, gateway_reference
        ) VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s, %s)
        RETURNING id
        """,
        (
            treinador_id,
            atleta_id,
            descricao or "Cobranca gerada pelo treinador",
            float(valor_decimal),
            periodicidade,
            _date_to_iso(vencimento),
            retorno_gateway.get("gateway", "asaas"),
            retorno_gateway.get("gateway_reference"),
        ),
    )
    cobranca_id = int(cursor.fetchone()["id"])
    conn.commit()
    conn.close()
    return buscar_cobranca_aluno_treinador(cobranca_id)


def buscar_cobranca_aluno_treinador(cobranca_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.*, u.nome AS atleta_nome, u.email AS atleta_email
        FROM cobrancas_alunos_treinador c
        JOIN usuarios u ON u.id = c.atleta_id
        WHERE c.id = %s
        """,
        (cobranca_id,),
    )
    item = _linha_para_dict(cursor.fetchone())
    conn.close()
    return item


def resumo_financeiro_admin():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        WITH receita_mes AS (
            SELECT COALESCE(SUM(valor_final), 0) AS total
            FROM pagamentos
            WHERE status = 'pago'
              AND DATE_TRUNC('month', COALESCE(created_at, CURRENT_TIMESTAMP)) = DATE_TRUNC('month', CURRENT_DATE)
        ),
        recorrencia_prevista AS (
            SELECT COALESCE(SUM(valor_total_cobrado), 0) AS total
            FROM assinaturas
            WHERE status IN ('ativa', 'trial', 'inadimplente')
              AND renovacao_automatica = 1
        ),
        atletas_solo AS (
            SELECT COUNT(*) AS total
            FROM usuarios u
            WHERE u.tipo_usuario = 'atleta'
              AND COALESCE(u.status_conta, 'ativo') = 'ativo'
              AND NOT EXISTS (
                  SELECT 1 FROM treinador_atleta ta
                  WHERE ta.atleta_id = u.id
                    AND COALESCE(ta.status_vinculo, ta.status) = 'ativo'
              )
        ),
        treinadores_ativos AS (
            SELECT COUNT(*) AS total
            FROM usuarios
            WHERE tipo_usuario = 'treinador'
              AND COALESCE(status_conta, 'ativo') = 'ativo'
        ),
        alunos_vinculados AS (
            SELECT COUNT(*) AS total
            FROM treinador_atleta ta
            JOIN usuarios u ON u.id = ta.atleta_id
            WHERE COALESCE(ta.status_vinculo, ta.status) = 'ativo'
              AND COALESCE(u.status_conta, 'ativo') = 'ativo'
        )
        SELECT
            receita_mes.total AS receita_total_mes,
            recorrencia_prevista.total AS receita_recorrente_prevista,
            atletas_solo.total AS quantidade_atletas_solo_ativos,
            treinadores_ativos.total AS quantidade_treinadores_ativos,
            alunos_vinculados.total AS total_alunos_ativos_vinculados,
            (SELECT COALESCE(SUM(valor_desconto), 0) FROM descontos_aplicados) AS total_descontos_aplicados,
            (SELECT COALESCE(SUM(valor_final), 0) FROM pagamentos WHERE status = 'atrasado') AS total_inadimplencia,
            (SELECT COUNT(*) FROM pagamentos WHERE status = 'pendente') AS total_pagamentos_pendentes,
            (SELECT COUNT(*) FROM pagamentos WHERE status = 'bonificado') AS total_pagamentos_bonificados
        FROM receita_mes
        CROSS JOIN recorrencia_prevista
        CROSS JOIN atletas_solo
        CROSS JOIN treinadores_ativos
        CROSS JOIN alunos_vinculados
        """
    )
    item = _linha_para_dict(cursor.fetchone()) or {}
    conn.close()
    return item


def gerar_resumo_financeiro_admin():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        WITH pagamentos_base AS (
            SELECT pg.*, u.tipo_usuario
            FROM pagamentos pg
            JOIN usuarios u ON u.id = pg.usuario_id
        ),
        atletas_solo AS (
            SELECT COUNT(*) AS total
            FROM usuarios u
            WHERE u.tipo_usuario = 'atleta'
              AND COALESCE(u.status_conta, 'ativo') = 'ativo'
              AND NOT EXISTS (
                  SELECT 1 FROM treinador_atleta ta
                  WHERE ta.atleta_id = u.id
                    AND COALESCE(ta.status_vinculo, ta.status, 'pendente') = 'ativo'
              )
        ),
        treinadores_ativos AS (
            SELECT COUNT(*) AS total
            FROM usuarios u
            WHERE u.tipo_usuario = 'treinador'
              AND COALESCE(u.status_conta, 'ativo') = 'ativo'
        ),
        alunos_vinculados AS (
            SELECT COUNT(*) AS total
            FROM treinador_atleta ta
            WHERE COALESCE(ta.status_vinculo, ta.status, 'pendente') = 'ativo'
        )
        SELECT
            (SELECT COALESCE(SUM(valor_final), 0) FROM pagamentos_base WHERE status = 'pago' AND DATE_TRUNC('month', COALESCE(created_at, CURRENT_TIMESTAMP)) = DATE_TRUNC('month', CURRENT_DATE)) AS receita_mes,
            (SELECT COALESCE(SUM(valor_total_cobrado), 0) FROM assinaturas WHERE status IN ('ativa', 'trial', 'pendente', 'inadimplente') AND renovacao_automatica = 1) AS receita_recorrente_prevista,
            (SELECT COUNT(*) FROM assinaturas WHERE status = 'ativa') AS assinaturas_ativas,
            (SELECT COUNT(*) FROM assinaturas WHERE status = 'inadimplente') AS assinaturas_inadimplentes,
            (SELECT COUNT(*) FROM assinaturas WHERE status = 'trial') AS assinaturas_trial,
            (SELECT COUNT(*) FROM pagamentos WHERE status = 'bonificado') AS total_bonificacoes,
            (SELECT COALESCE(SUM(valor_desconto), 0) FROM descontos_aplicados) AS total_descontos_aplicados,
            (SELECT total FROM treinadores_ativos) AS total_treinadores_ativos,
            (SELECT total FROM atletas_solo) AS total_atletas_solo_ativos,
            (SELECT total FROM alunos_vinculados) AS total_alunos_ativos_vinculados,
            (SELECT COALESCE(AVG(valor_total_cobrado), 0) FROM assinaturas a JOIN usuarios u ON u.id = a.usuario_id WHERE u.tipo_usuario = 'treinador' AND a.status IN ('ativa', 'inadimplente', 'pendente')) AS ticket_medio_treinador,
            (SELECT COALESCE(AVG(valor_total_cobrado), 0) FROM assinaturas a JOIN usuarios u ON u.id = a.usuario_id WHERE u.tipo_usuario = 'atleta' AND a.status IN ('ativa', 'inadimplente', 'pendente')) AS ticket_medio_atleta,
            (SELECT COALESCE(SUM(valor_final), 0) FROM pagamentos WHERE status = 'atrasado') AS total_inadimplencia,
            (SELECT COUNT(*) FROM pagamentos WHERE status = 'pendente') AS total_pagamentos_pendentes
        """
    )
    resumo = _linha_para_dict(cursor.fetchone()) or {}
    conn.close()
    return resumo


def serie_financeira_admin():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        WITH receita AS (
            SELECT TO_CHAR(DATE_TRUNC('month', COALESCE(created_at, CURRENT_TIMESTAMP)), 'YYYY-MM') AS periodo,
                   COALESCE(SUM(CASE WHEN status = 'pago' THEN valor_final ELSE 0 END), 0) AS receita,
                   COALESCE(SUM(valor_desconto), 0) AS descontos,
                   COUNT(*) FILTER (WHERE status = 'atrasado') AS inadimplentes
            FROM pagamentos
            GROUP BY 1
        ),
        assinaturas_mes AS (
            SELECT TO_CHAR(DATE_TRUNC('month', COALESCE(created_at, CURRENT_TIMESTAMP)), 'YYYY-MM') AS periodo,
                   COUNT(*) AS novas_assinaturas,
                   COUNT(*) FILTER (WHERE status = 'cancelada') AS cancelamentos
            FROM assinaturas
            GROUP BY 1
        ),
        usuarios_mes AS (
            SELECT TO_CHAR(DATE_TRUNC('month', data_criacao), 'YYYY-MM') AS periodo,
                   COUNT(*) FILTER (WHERE tipo_usuario = 'treinador') AS novos_treinadores,
                   COUNT(*) FILTER (WHERE tipo_usuario = 'atleta') AS novos_atletas
            FROM usuarios
            GROUP BY 1
        )
        SELECT
            COALESCE(r.periodo, a.periodo, u.periodo) AS periodo,
            COALESCE(r.receita, 0) AS receita,
            COALESCE(a.novas_assinaturas, 0) AS novas_assinaturas,
            COALESCE(a.cancelamentos, 0) AS cancelamentos,
            COALESCE(r.inadimplentes, 0) AS inadimplentes,
            COALESCE(r.descontos, 0) AS descontos_aplicados,
            COALESCE(u.novos_treinadores, 0) AS crescimento_treinadores,
            COALESCE(u.novos_atletas, 0) AS crescimento_atletas
        FROM receita r
        FULL JOIN assinaturas_mes a ON a.periodo = r.periodo
        FULL JOIN usuarios_mes u ON u.periodo = COALESCE(r.periodo, a.periodo)
        ORDER BY 1
        """
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def resumo_financeiro_treinador(treinador_id):
    assinatura = buscar_assinatura_atual(treinador_id)
    alunos_ativos = contar_alunos_ativos_treinador(treinador_id, _hoje())
    return {
        "assinatura_plataforma": {
            "plano_atual": assinatura.get("plano_nome") if assinatura else None,
            "valor_base": assinatura.get("valor_base_cobrado", 0) if assinatura else 0,
            "taxa_por_aluno_ativo": assinatura.get("taxa_por_aluno_ativo", 0) if assinatura else 0,
            "numero_alunos_ativos_momento": alunos_ativos,
            "previsao_proximo_fechamento": assinatura.get("data_renovacao") if assinatura else None,
            "historico_cobrancas_plataforma": listar_historico_financeiro_usuario(treinador_id),
        },
        "cobrancas_alunos": listar_pagamentos_treinador(treinador_id),
    }


def listar_treinadores_financeiro_admin():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            u.id AS treinador_id,
            u.nome AS treinador_nome,
            u.email AS treinador_email,
            a.id AS assinatura_id,
            a.status AS assinatura_status,
            p.nome AS plano_nome,
            COALESCE(a.valor_base_cobrado, p.valor_base, p.preco_mensal, 0) AS valor_base,
            COALESCE(p.taxa_por_aluno_ativo, 0) AS taxa_por_aluno_ativo,
            COALESCE(a.quantidade_alunos_ativos_fechamento, 0) AS alunos_fechamento,
            COALESCE(a.valor_total_cobrado, a.valor, 0) AS valor_total_cobrado,
            a.data_renovacao,
            (
                SELECT COUNT(*)
                FROM treinador_atleta ta
                WHERE ta.treinador_id = u.id
                  AND COALESCE(ta.status_vinculo, ta.status, 'pendente') = 'ativo'
            ) AS alunos_ativos_atualmente
        FROM usuarios u
        LEFT JOIN LATERAL (
            SELECT *
            FROM assinaturas ax
            WHERE ax.usuario_id = u.id
            ORDER BY COALESCE(ax.created_at, CURRENT_TIMESTAMP) DESC, ax.id DESC
            LIMIT 1
        ) a ON TRUE
        LEFT JOIN planos p ON p.id = a.plano_id
        WHERE u.tipo_usuario = 'treinador'
        ORDER BY u.nome
        """
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    for item in itens:
        item["valor_previsto_proximo_ciclo"] = _decimal_para_float(item.get("valor_base") or 0) + (
            _decimal_para_float(item.get("taxa_por_aluno_ativo") or 0) * int(item.get("alunos_ativos_atualmente") or 0)
        )
    return itens


def listar_cobrancas_alunos_admin(status=None, treinador_id=None):
    filtros = []
    params = []
    if status:
        filtros.append("c.status = %s")
        params.append(status)
    if treinador_id:
        filtros.append("c.treinador_id = %s")
        params.append(treinador_id)
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT
            c.*,
            t.nome AS treinador_nome,
            a.nome AS atleta_nome
        FROM cobrancas_alunos_treinador c
        JOIN usuarios t ON t.id = c.treinador_id
        JOIN usuarios a ON a.id = c.atleta_id
        {where_sql}
        ORDER BY COALESCE(c.created_at, CURRENT_TIMESTAMP) DESC, c.id DESC
        """,
        tuple(params),
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def listar_fechamentos_treinadores():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            a.id AS assinatura_id,
            u.id AS treinador_id,
            u.nome AS treinador_nome,
            u.email AS treinador_email,
            a.data_renovacao,
            p.nome AS plano_nome,
            COALESCE(a.valor_base_cobrado, p.valor_base, p.preco_mensal, 0) AS valor_base_cobrado,
            COALESCE(a.quantidade_alunos_ativos_fechamento, 0) AS quantidade_alunos_ativos_fechamento,
            COALESCE(a.valor_taxa_alunos, 0) AS valor_taxa_alunos,
            COALESCE(a.valor_total_cobrado, a.valor, 0) AS valor_total_cobrado,
            COALESCE((
                SELECT SUM(d.valor_desconto)
                FROM descontos_aplicados d
                WHERE d.assinatura_id = a.id
            ), 0) AS desconto_aplicado,
            GREATEST(
                COALESCE(a.valor_total_cobrado, a.valor, 0) - COALESCE((
                    SELECT SUM(d.valor_desconto)
                    FROM descontos_aplicados d
                    WHERE d.assinatura_id = a.id
                ), 0),
                0
            ) AS valor_final_cobrado
        FROM assinaturas a
        JOIN usuarios u ON u.id = a.usuario_id
        JOIN planos p ON p.id = a.plano_id
        WHERE u.tipo_usuario = 'treinador'
        ORDER BY COALESCE(a.data_renovacao, CURRENT_DATE) DESC, a.id DESC
        """
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def listar_cupons_desconto(ativo=None):
    filtros = []
    params = []
    if ativo is not None:
        filtros.append("ativo = %s")
        params.append(bool(ativo))
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM cupons_desconto {where_sql} ORDER BY created_at DESC, id DESC", tuple(params))
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def salvar_cupom_desconto(dados):
    codigo = (dados.get("codigo") or "").strip().upper()
    if not codigo:
        raise ValueError("Codigo do cupom e obrigatorio.")
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO cupons_desconto (
            codigo, descricao, tipo_desconto, valor_desconto, percentual_desconto,
            aplicavel_para, periodicidade_aplicavel, quantidade_max_uso, ativo,
            data_inicio, data_fim
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE SET
            descricao = EXCLUDED.descricao,
            tipo_desconto = EXCLUDED.tipo_desconto,
            valor_desconto = EXCLUDED.valor_desconto,
            percentual_desconto = EXCLUDED.percentual_desconto,
            aplicavel_para = EXCLUDED.aplicavel_para,
            periodicidade_aplicavel = EXCLUDED.periodicidade_aplicavel,
            quantidade_max_uso = EXCLUDED.quantidade_max_uso,
            ativo = EXCLUDED.ativo,
            data_inicio = EXCLUDED.data_inicio,
            data_fim = EXCLUDED.data_fim
        """,
        (
            codigo,
            dados.get("descricao"),
            dados.get("tipo_desconto"),
            float(_to_decimal(dados.get("valor_desconto"))),
            float(_to_decimal(dados.get("percentual_desconto"))),
            dados.get("aplicavel_para", "todos"),
            dados.get("periodicidade_aplicavel", "todos"),
            dados.get("quantidade_max_uso"),
            bool(dados.get("ativo", True)),
            _date_to_iso(dados.get("data_inicio")),
            _date_to_iso(dados.get("data_fim")),
        ),
    )
    conn.commit()
    conn.close()
    return buscar_cupom_por_codigo(codigo)


def aplicar_desconto_manual_admin(usuario_id, assinatura_id=None, pagamento_id=None, tipo_desconto="valor_fixo", valor_desconto=0, percentual_desconto=0, aplicado_por="admin", descricao=None):
    if pagamento_id:
        pagamento = buscar_pagamento_por_id(pagamento_id)
        if not pagamento:
            raise ValueError("Pagamento nao encontrado.")
        base = pagamento["valor_bruto"]
        assinatura_id = pagamento.get("assinatura_id")
    elif assinatura_id:
        assinatura = buscar_assinatura_por_id(assinatura_id)
        if not assinatura:
            raise ValueError("Assinatura nao encontrada.")
        base = assinatura["valor_total_cobrado"]
    else:
        raise ValueError("Assinatura ou pagamento obrigatorio para aplicar desconto.")

    regra = {
        "tipo_desconto": tipo_desconto,
        "valor_desconto": valor_desconto,
        "percentual_desconto": percentual_desconto,
        "descricao": descricao,
    }
    desconto_info = aplicar_desconto(base, regra)
    conn = conectar()
    cursor = conn.cursor()
    alvo_pagamento_id = pagamento_id
    if pagamento_id:
        status_pagamento = "bonificado" if desconto_info["bonificado"] else "pendente"
        cursor.execute(
            """
            UPDATE pagamentos
            SET valor_desconto = COALESCE(valor_desconto, 0) + %s,
                valor_final = %s,
                status = CASE WHEN %s THEN 'bonificado' ELSE status END
            WHERE id = %s
            """,
            (
                desconto_info["valor_desconto"],
                desconto_info["valor_final"],
                desconto_info["bonificado"],
                pagamento_id,
            ),
        )
        if assinatura_id:
            cursor.execute(
                "UPDATE assinaturas SET status = %s WHERE id = %s",
                (_status_pagamento_para_assinatura(status_pagamento), assinatura_id),
            )
    cursor.execute(
        """
        INSERT INTO descontos_aplicados (
            cupom_id, usuario_id, assinatura_id, pagamento_id, valor_bruto,
            valor_desconto, valor_final, aplicado_por
        ) VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            usuario_id,
            assinatura_id,
            alvo_pagamento_id,
            desconto_info["valor_bruto"],
            desconto_info["valor_desconto"],
            desconto_info["valor_final"],
            aplicado_por,
        ),
    )
    desconto_id = int(cursor.fetchone()["id"])
    conn.commit()
    conn.close()
    return {
        "id": desconto_id,
        "usuario_id": usuario_id,
        "assinatura_id": assinatura_id,
        "pagamento_id": alvo_pagamento_id,
        **desconto_info,
    }
