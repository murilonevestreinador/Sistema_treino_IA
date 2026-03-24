import hashlib
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests

from core.banco import conectar


DEFAULT_GATEWAY = "asaas"
STATUS_QUITADOS = {"pago", "bonificado"}
CENTAVOS = Decimal("0.01")
EVENTOS_PAGAMENTO = {
    "PAYMENT_CREATED": "pendente",
    "PAYMENT_CONFIRMED": "pago",
    "PAYMENT_RECEIVED": "pago",
    "PAYMENT_OVERDUE": "atrasado",
    "PAYMENT_DELETED": "cancelado",
    "PAYMENT_REFUNDED": "estornado",
    "PAYMENT_REFUND_IN_PROGRESS": "estornado",
    "PAYMENT_CHARGEBACK_REQUESTED": "atrasado",
    "PAYMENT_RESTORED": "pendente",
}


def _agora():
    return datetime.now()


def _agora_iso():
    return _agora().isoformat(timespec="seconds")


def _to_decimal(valor):
    if valor in (None, ""):
        return Decimal("0")
    return Decimal(str(valor)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


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


def _status_pagamento_para_assinatura(status_pagamento):
    mapa = {
        "pago": "ativa",
        "bonificado": "ativa",
        "pendente": "trial",
        "atrasado": "inadimplente",
        "cancelado": "cancelada",
        "estornado": "cancelada",
    }
    return mapa.get(status_pagamento, "inadimplente")


def _payload_json(payload):
    return json.dumps(payload or {}, ensure_ascii=True, sort_keys=True, default=str)


def _buscar_configuracao_asaas():
    return {
        "api_key": (os.getenv("ASAAS_API_KEY") or "").strip(),
        "base_url": (os.getenv("ASAAS_BASE_URL") or "").strip().rstrip("/"),
        "webhook_token": (os.getenv("ASAAS_WEBHOOK_TOKEN") or "").strip(),
        "app_env": (os.getenv("APP_ENV") or "").strip().lower(),
    }


def validar_configuracao_asaas():
    config = _buscar_configuracao_asaas()
    faltando = [chave for chave, valor in config.items() if chave != "app_env" and not valor]
    return {
        "ok": not faltando,
        "faltando": faltando,
        "config": config,
        "mensagem": "Configuracao Asaas carregada." if not faltando else f"Variaveis ausentes: {', '.join(faltando)}",
    }


def get_asaas_headers():
    validacao = validar_configuracao_asaas()
    if not validacao["ok"]:
        raise RuntimeError(validacao["mensagem"])
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": validacao["config"]["api_key"],
        "User-Agent": "TriLab-Treinamento/Asaas-Integration",
    }


def _asaas_request(method, path, payload=None, params=None, timeout=20):
    config = validar_configuracao_asaas()
    if not config["ok"]:
        return {"ok": False, "erro": "configuracao", "mensagem": config["mensagem"]}

    url = f"{config['config']['base_url']}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=get_asaas_headers(),
            json=payload,
            params=params,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return {"ok": False, "erro": "conexao", "mensagem": str(exc), "url": url}

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:500]}

    if response.ok:
        return {"ok": True, "status_code": response.status_code, "data": body, "url": url}

    mensagem = None
    if isinstance(body, dict):
        mensagem = body.get("message")
        errors = body.get("errors")
        if not mensagem and isinstance(errors, list) and errors:
            mensagem = "; ".join(
                item.get("description") or item.get("code") or str(item)
                for item in errors
                if item
            )
    return {
        "ok": False,
        "erro": "api",
        "status_code": response.status_code,
        "mensagem": mensagem or f"Erro HTTP {response.status_code}",
        "data": body,
        "url": url,
    }


def testar_conexao_asaas():
    resultado = _asaas_request("GET", "/v3/finance/getPaymentCheckoutConfig")
    if resultado["ok"]:
        return {
            "sucesso": True,
            "erro": None,
            "mensagem": "Conexao com Asaas Sandbox validada com sucesso.",
            "ambiente": validar_configuracao_asaas()["config"].get("app_env"),
            "url": resultado.get("url"),
            "data": resultado.get("data"),
        }
    return {
        "sucesso": False,
        "erro": resultado.get("erro"),
        "mensagem": resultado.get("mensagem"),
        "ambiente": validar_configuracao_asaas()["config"].get("app_env"),
        "url": resultado.get("url"),
        "data": resultado.get("data"),
    }


def _buscar_usuario_existente(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    usuario = cursor.fetchone()
    conn.close()
    return dict(usuario) if usuario else None


def _atualizar_asaas_customer_usuario(usuario_id, asaas_customer_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET asaas_customer_id = %s
        WHERE id = %s
        """,
        (asaas_customer_id, usuario_id),
    )
    conn.commit()
    conn.close()


def _buscar_customer_por_email(email):
    if not email:
        return None
    resultado = _asaas_request("GET", "/v3/customers", params={"email": email})
    if not resultado["ok"]:
        return None
    data = resultado.get("data") or {}
    if not isinstance(data, dict):
        return None
    itens = data.get("data") or []
    return itens[0] if itens else None


def criar_customer_asaas(usuario):
    usuario_id = usuario.get("id")
    usuario_db = _buscar_usuario_existente(usuario_id) if usuario_id else None
    asaas_customer_id = (usuario.get("asaas_customer_id") or (usuario_db or {}).get("asaas_customer_id") or "").strip()
    if asaas_customer_id:
        return {
            "ok": True,
            "gateway": DEFAULT_GATEWAY,
            "status": "existente",
            "asaas_customer_id": asaas_customer_id,
            "gateway_reference": asaas_customer_id,
            "payload": None,
        }

    customer_existente = _buscar_customer_por_email((usuario.get("email") or "").strip().lower())
    if customer_existente and customer_existente.get("id"):
        if usuario_id:
            _atualizar_asaas_customer_usuario(usuario_id, customer_existente["id"])
        return {
            "ok": True,
            "gateway": DEFAULT_GATEWAY,
            "status": "reutilizado",
            "asaas_customer_id": customer_existente["id"],
            "gateway_reference": customer_existente["id"],
            "payload": customer_existente,
        }

    payload = {
        "name": (usuario.get("nome") or "").strip(),
        "email": (usuario.get("email") or "").strip().lower(),
    }
    if usuario.get("cpf_cnpj"):
        payload["cpfCnpj"] = str(usuario.get("cpf_cnpj")).strip()
    if usuario.get("mobilePhone"):
        payload["mobilePhone"] = str(usuario.get("mobilePhone")).strip()
    if usuario.get("telefone"):
        payload["mobilePhone"] = str(usuario.get("telefone")).strip()

    resultado = _asaas_request("POST", "/v3/customers", payload=payload)
    if not resultado["ok"]:
        return {
            "ok": False,
            "gateway": DEFAULT_GATEWAY,
            "status": "erro",
            "mensagem": resultado.get("mensagem"),
            "payload": resultado.get("data"),
        }

    customer = resultado["data"]
    if usuario_id and customer.get("id"):
        _atualizar_asaas_customer_usuario(usuario_id, customer["id"])
    return {
        "ok": True,
        "gateway": DEFAULT_GATEWAY,
        "status": "criado",
        "asaas_customer_id": customer.get("id"),
        "gateway_reference": customer.get("id"),
        "payload": customer,
    }


def _proximo_vencimento(plano):
    base = _parse_date(plano.get("nextDueDate")) or (_agora() + timedelta(days=1)).date()
    return base.isoformat()


def _ciclo_asaas(plano):
    periodicidade = (plano.get("periodicidade") or "mensal").strip().lower()
    mapa = {
        "mensal": "MONTHLY",
        "anual": "YEARLY",
        "semanal": "WEEKLY",
        "quinzenal": "BIWEEKLY",
    }
    return mapa.get(periodicidade, "MONTHLY")


def criar_assinatura_asaas(customer_id, plano):
    payload = {
        "customer": customer_id,
        "billingType": (plano.get("billingType") or "UNDEFINED").strip().upper(),
        "nextDueDate": _proximo_vencimento(plano),
        "value": float(_to_decimal(plano.get("valor_base") or plano.get("valor") or plano.get("preco_mensal") or 0)),
        "cycle": _ciclo_asaas(plano),
        "description": (plano.get("description") or plano.get("descricao") or plano.get("nome") or "Assinatura TriLab TREINAMENTO").strip(),
    }
    resultado = _asaas_request("POST", "/v3/subscriptions", payload=payload)
    if not resultado["ok"]:
        return {
            "ok": False,
            "gateway": DEFAULT_GATEWAY,
            "status": "erro",
            "mensagem": resultado.get("mensagem"),
            "payload": resultado.get("data"),
        }

    assinatura = resultado["data"]
    return {
        "ok": True,
        "gateway": DEFAULT_GATEWAY,
        "status": "pendente",
        "asaas_subscription_id": assinatura.get("id"),
        "gateway_reference": assinatura.get("id"),
        "payload": assinatura,
    }


def criar_cobranca_gateway(**dados):
    return {
        "ok": True,
        "status": dados.get("status_inicial", "pendente"),
        "gateway_reference": dados.get("gateway_reference") or dados.get("referencia_externa"),
        "gateway": dados.get("gateway") or DEFAULT_GATEWAY,
        "payload": dict(dados),
    }


def consultar_status_gateway(gateway_reference):
    if not gateway_reference:
        return {"ok": False, "gateway": DEFAULT_GATEWAY, "status": "erro", "mensagem": "Referencia ausente."}
    resultado = _asaas_request("GET", f"/v3/subscriptions/{gateway_reference}")
    if not resultado["ok"]:
        return {
            "ok": False,
            "gateway": DEFAULT_GATEWAY,
            "gateway_reference": gateway_reference,
            "status": "erro",
            "mensagem": resultado.get("mensagem"),
        }
    return {
        "ok": True,
        "gateway": DEFAULT_GATEWAY,
        "gateway_reference": gateway_reference,
        "status": "consultado",
        "payload": resultado.get("data"),
    }


def _normalizar_headers(headers):
    if not headers:
        return {}
    return {str(chave).lower(): valor for chave, valor in dict(headers).items()}


def _extrair_pagamento_payload(payload):
    if not isinstance(payload, dict):
        return {}
    payment = payload.get("payment")
    if isinstance(payment, dict):
        return payment
    return payload


def _dedupe_key(payload):
    evento = (payload or {}).get("event") or ""
    payment = _extrair_pagamento_payload(payload)
    bruto = _payload_json({
        "event": evento,
        "payment_id": payment.get("id"),
        "subscription": payment.get("subscription"),
        "status": payment.get("status"),
        "dateCreated": payment.get("dateCreated"),
        "value": payment.get("value"),
    })
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _registrar_evento_recebido(cursor, payload, headers, dedupe_key):
    payment = _extrair_pagamento_payload(payload)
    cursor.execute(
        """
        INSERT INTO webhook_eventos_asaas (
            dedupe_key, evento, asaas_event_id, asaas_payment_id, asaas_subscription_id,
            status_processamento, payload, headers
        ) VALUES (%s, %s, %s, %s, %s, 'recebido', %s, %s)
        ON CONFLICT (dedupe_key) DO NOTHING
        RETURNING id
        """,
        (
            dedupe_key,
            (payload or {}).get("event"),
            str((payload or {}).get("id") or "") or None,
            str(payment.get("id") or "") or None,
            str(payment.get("subscription") or "") or None,
            _payload_json(payload),
            _payload_json(headers),
        ),
    )
    linha = cursor.fetchone()
    return linha["id"] if linha else None


def _atualizar_evento_processamento(cursor, evento_id, status, erro=None):
    cursor.execute(
        """
        UPDATE webhook_eventos_asaas
        SET status_processamento = %s,
            erro = %s,
            processado_em = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (status, erro, evento_id),
    )


def _buscar_assinatura_por_gateway(cursor, asaas_subscription_id, gateway_reference=None):
    cursor.execute(
        """
        SELECT *
        FROM assinaturas
        WHERE asaas_subscription_id = %s
           OR gateway_reference = %s
        ORDER BY COALESCE(created_at, CURRENT_TIMESTAMP) DESC, id DESC
        LIMIT 1
        """,
        (asaas_subscription_id, gateway_reference or asaas_subscription_id),
    )
    linha = cursor.fetchone()
    return dict(linha) if linha else None


def _buscar_usuario_por_customer(cursor, asaas_customer_id):
    if not asaas_customer_id:
        return None
    cursor.execute(
        """
        SELECT *
        FROM usuarios
        WHERE asaas_customer_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (asaas_customer_id,),
    )
    linha = cursor.fetchone()
    return dict(linha) if linha else None


def _upsert_pagamento_webhook(cursor, pagamento_payload, assinatura):
    usuario_id = assinatura["usuario_id"] if assinatura else None
    if not usuario_id:
        usuario = _buscar_usuario_por_customer(cursor, pagamento_payload.get("customer"))
        usuario_id = usuario["id"] if usuario else None
    if not usuario_id:
        raise ValueError("Usuario interno nao encontrado para o pagamento do Asaas.")

    valor = float(_to_decimal(pagamento_payload.get("value") or pagamento_payload.get("netValue") or 0))
    status_interno = EVENTOS_PAGAMENTO.get((pagamento_payload.get("_evento") or "").upper(), "pendente")
    data_pagamento = pagamento_payload.get("clientPaymentDate") or pagamento_payload.get("paymentDate")
    data_vencimento = pagamento_payload.get("dueDate")
    referencia_externa = pagamento_payload.get("id")
    gateway_reference = pagamento_payload.get("invoiceUrl") or referencia_externa

    cursor.execute(
        """
        SELECT id, status, assinatura_id
        FROM pagamentos
        WHERE asaas_payment_id = %s
           OR referencia_externa = %s
           OR gateway_reference = %s
        ORDER BY COALESCE(created_at, CURRENT_TIMESTAMP) DESC, id DESC
        LIMIT 1
        """,
        (referencia_externa, referencia_externa, gateway_reference),
    )
    existente = cursor.fetchone()

    if existente:
        cursor.execute(
            """
            UPDATE pagamentos
            SET usuario_id = COALESCE(usuario_id, %s),
                assinatura_id = COALESCE(assinatura_id, %s),
                valor = %s,
                valor_bruto = COALESCE(%s, valor_bruto),
                valor_final = %s,
                status = %s,
                metodo_pagamento = COALESCE(%s, metodo_pagamento),
                data_pagamento = COALESCE(%s, data_pagamento),
                data_vencimento = COALESCE(%s, data_vencimento),
                referencia_externa = %s,
                asaas_payment_id = %s,
                gateway = %s,
                gateway_reference = %s
            WHERE id = %s
            RETURNING id
            """,
            (
                usuario_id,
                assinatura["id"] if assinatura else None,
                valor,
                valor,
                valor,
                status_interno,
                (pagamento_payload.get("billingType") or "").lower() or None,
                data_pagamento if status_interno in STATUS_QUITADOS else None,
                data_vencimento,
                referencia_externa,
                referencia_externa,
                DEFAULT_GATEWAY,
                gateway_reference,
                existente["id"],
            ),
        )
        return int(cursor.fetchone()["id"]), status_interno

    cursor.execute(
        """
        INSERT INTO pagamentos (
            usuario_id, assinatura_id, valor, valor_bruto, valor_desconto, valor_final,
            status, metodo_pagamento, data_pagamento, data_vencimento, referencia_externa,
            asaas_payment_id, gateway, gateway_reference
        ) VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            usuario_id,
            assinatura["id"] if assinatura else None,
            valor,
            valor,
            valor,
            status_interno,
            (pagamento_payload.get("billingType") or "").lower() or None,
            data_pagamento if status_interno in STATUS_QUITADOS else None,
            data_vencimento,
            referencia_externa,
            referencia_externa,
            DEFAULT_GATEWAY,
            gateway_reference,
        ),
    )
    return int(cursor.fetchone()["id"]), status_interno


def _atualizar_assinatura_por_pagamento(cursor, assinatura, pagamento_payload, status_pagamento):
    if not assinatura:
        return
    data_fim = pagamento_payload.get("nextDueDate") or assinatura.get("data_fim")
    cursor.execute(
        """
        UPDATE assinaturas
        SET status = %s,
            data_renovacao = COALESCE(%s, data_renovacao),
            data_fim = COALESCE(%s, data_fim),
            gateway = %s,
            gateway_reference = COALESCE(%s, gateway_reference),
            asaas_subscription_id = COALESCE(%s, asaas_subscription_id)
        WHERE id = %s
        """,
        (
            _status_pagamento_para_assinatura(status_pagamento),
            pagamento_payload.get("dueDate"),
            data_fim,
            DEFAULT_GATEWAY,
            pagamento_payload.get("subscription"),
            pagamento_payload.get("subscription"),
            assinatura["id"],
        ),
    )


def processar_webhook_asaas(payload, headers):
    headers_normalizados = _normalizar_headers(headers)
    token_recebido = (headers_normalizados.get("asaas-access-token") or "").strip()
    token_esperado = validar_configuracao_asaas()["config"].get("webhook_token")

    if not token_esperado:
        return {"ok": False, "status_code": 500, "mensagem": "ASAAS_WEBHOOK_TOKEN nao configurado."}
    if token_recebido != token_esperado:
        return {"ok": False, "status_code": 403, "mensagem": "Token do webhook invalido."}

    evento = (payload or {}).get("event") or ""
    payment = _extrair_pagamento_payload(payload)
    payment["_evento"] = evento
    dedupe_key = _dedupe_key(payload)

    conn = conectar()
    cursor = conn.cursor()
    try:
        evento_id = _registrar_evento_recebido(cursor, payload, headers_normalizados, dedupe_key)
        if not evento_id:
            conn.commit()
            return {
                "ok": True,
                "status_code": 200,
                "mensagem": "Evento ja processado anteriormente.",
                "idempotente": True,
                "evento": evento,
                "dedupe_key": dedupe_key,
            }

        assinatura = _buscar_assinatura_por_gateway(cursor, payment.get("subscription"), payment.get("subscription"))
        if evento in EVENTOS_PAGAMENTO:
            pagamento_id, status_pagamento = _upsert_pagamento_webhook(cursor, payment, assinatura)
            _atualizar_assinatura_por_pagamento(cursor, assinatura, payment, status_pagamento)
        else:
            pagamento_id = None
            status_pagamento = None

        _atualizar_evento_processamento(cursor, evento_id, "processado")
        conn.commit()
        return {
            "ok": True,
            "status_code": 200,
            "mensagem": "Webhook processado com sucesso.",
            "evento": evento,
            "pagamento_id": pagamento_id,
            "status_pagamento": status_pagamento,
            "idempotente": False,
            "dedupe_key": dedupe_key,
        }
    except Exception as exc:
        conn.rollback()
        try:
            cursor.execute(
                """
                UPDATE webhook_eventos_asaas
                SET status_processamento = 'erro',
                    erro = %s,
                    processado_em = CURRENT_TIMESTAMP
                WHERE dedupe_key = %s
                """,
                (str(exc), dedupe_key),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        return {"ok": False, "status_code": 500, "mensagem": str(exc), "evento": evento, "dedupe_key": dedupe_key}
    finally:
        conn.close()


def cancelar_assinatura_gateway(gateway_reference):
    if not gateway_reference:
        return {"ok": False, "gateway": DEFAULT_GATEWAY, "status": "erro", "mensagem": "Referencia ausente."}
    resultado = _asaas_request("DELETE", f"/v3/subscriptions/{gateway_reference}")
    if not resultado["ok"]:
        return {
            "ok": False,
            "gateway_reference": gateway_reference,
            "gateway": DEFAULT_GATEWAY,
            "status": "erro",
            "mensagem": resultado.get("mensagem"),
        }
    return {
        "ok": True,
        "gateway_reference": gateway_reference,
        "gateway": DEFAULT_GATEWAY,
        "status": "cancelada",
    }


def listar_eventos_webhook_asaas(limite=20):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM webhook_eventos_asaas
        ORDER BY recebido_em DESC, id DESC
        LIMIT %s
        """,
        (int(limite),),
    )
    itens = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return itens


def resumo_operacional_asaas():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM usuarios WHERE asaas_customer_id IS NOT NULL AND btrim(asaas_customer_id) <> '') AS total_customers,
            (SELECT COUNT(*) FROM assinaturas WHERE asaas_subscription_id IS NOT NULL AND btrim(asaas_subscription_id) <> '') AS total_assinaturas,
            (SELECT COUNT(*) FROM webhook_eventos_asaas) AS total_webhooks,
            (SELECT COUNT(*) FROM webhook_eventos_asaas WHERE status_processamento = 'erro') AS total_webhooks_com_erro
        """
    )
    resumo = dict(cursor.fetchone() or {})
    cursor.execute(
        """
        SELECT id, nome, email, asaas_customer_id
        FROM usuarios
        WHERE asaas_customer_id IS NOT NULL AND btrim(asaas_customer_id) <> ''
        ORDER BY id DESC
        LIMIT 1
        """
    )
    resumo["ultimo_customer"] = dict(cursor.fetchone() or {})
    cursor.execute(
        """
        SELECT a.id, a.usuario_id, a.status, a.asaas_subscription_id, u.nome AS usuario_nome
        FROM assinaturas a
        JOIN usuarios u ON u.id = a.usuario_id
        WHERE a.asaas_subscription_id IS NOT NULL AND btrim(a.asaas_subscription_id) <> ''
        ORDER BY COALESCE(a.created_at, CURRENT_TIMESTAMP) DESC, a.id DESC
        LIMIT 1
        """
    )
    resumo["ultima_assinatura"] = dict(cursor.fetchone() or {})
    conn.close()
    resumo["conexao"] = testar_conexao_asaas()
    resumo["ultimos_webhooks"] = listar_eventos_webhook_asaas(10)
    return resumo


def criar_customer_gateway(usuario):
    if (usuario.get("tipo_usuario") or "").strip().lower() != "atleta":
        return {
            "ok": True,
            "gateway": "manual",
            "status": "ignorado",
            "gateway_reference": None,
            "payload": {"motivo": "Fluxo Asaas restrito ao atleta solo nesta etapa."},
        }
    return criar_customer_asaas(usuario)


def criar_assinatura_gateway(usuario, plano):
    if (usuario.get("tipo_usuario") or "").strip().lower() != "atleta" or (plano.get("tipo_plano") or "").strip().lower() != "atleta":
        return {
            "ok": True,
            "gateway": "manual",
            "status": "ativa",
            "gateway_reference": f"manual-subscription-{usuario.get('id')}-{plano.get('codigo')}",
            "payload": {"motivo": "Fluxo Asaas restrito ao atleta solo nesta etapa."},
        }
    customer = criar_customer_asaas(usuario)
    if not customer.get("ok"):
        return customer
    dados_plano = dict(plano or {})
    dados_plano.setdefault("description", f"Assinatura {dados_plano.get('nome') or 'TriLab TREINAMENTO'}")
    return criar_assinatura_asaas(customer["asaas_customer_id"], dados_plano)


def processar_webhook_gateway(payload):
    return processar_webhook_asaas(payload, {})
