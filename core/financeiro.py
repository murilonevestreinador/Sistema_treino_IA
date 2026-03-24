from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from core.banco import conectar
from core.pagamentos_gateway import (
    cancelar_assinatura_gateway,
    criar_assinatura_gateway,
    criar_cobranca_gateway,
)


TRIAL_DIAS = 7
STATUS_COM_ACESSO = {"ativa", "trial"}
STATUS_FINANCEIROS_QUITADOS = {"pago", "bonificado"}
CENTAVOS = Decimal("0.01")


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
        ORDER BY COALESCE(tipo_plano, tipo), periodicidade, COALESCE(valor_base, preco_mensal)
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


def usuario_tem_acesso(usuario):
    assinatura = garantir_assinatura_inicial(usuario)
    return bool(assinatura and assinatura.get("status") in STATUS_COM_ACESSO), assinatura


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
    retorno_gateway = criar_assinatura_gateway(usuario, plano)
    if not retorno_gateway.get("ok"):
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
    return buscar_assinatura_por_id(assinatura_id)


def assinar_plano_manual(usuario, plano_codigo, cupom_codigo=None):
    plano = buscar_plano_por_codigo(plano_codigo)
    if not plano or not int(plano.get("ativo", 0)):
        return None, "Plano indisponivel."
    if plano["tipo_plano"] != usuario.get("tipo_usuario"):
        return None, "Este plano nao corresponde ao perfil da sua conta."
    try:
        assinatura = criar_assinatura_manual(usuario, plano, cupom_codigo=cupom_codigo)
    except ValueError as exc:
        return None, str(exc)
    if assinatura.get("gateway") == "asaas" and plano.get("tipo_plano") == "atleta":
        return assinatura, "Assinatura criada no Asaas Sandbox. O acesso sera liberado quando o webhook confirmar o pagamento."
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
