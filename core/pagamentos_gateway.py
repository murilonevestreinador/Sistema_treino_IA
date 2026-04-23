import hashlib
import json
import logging
import os
import traceback
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter, sleep

import requests

from core.banco import conectar
from core.usuarios import diagnosticar_dados_checkout


LOGGER = logging.getLogger("trilab.asaas.gateway")
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


def _mask_secret(value, prefix=6, suffix=4):
    texto = str(value or "").strip()
    if not texto:
        return ""
    if len(texto) <= prefix + suffix:
        return "*" * len(texto)
    return f"{texto[:prefix]}...{texto[-suffix:]}"


def _mask_email(value):
    texto = str(value or "").strip()
    if "@" not in texto:
        return texto
    local, dominio = texto.split("@", 1)
    if len(local) <= 2:
        local_mask = "*" * len(local)
    else:
        local_mask = f"{local[:2]}***"
    return f"{local_mask}@{dominio}"


def _mask_phone(value):
    texto = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not texto:
        return value
    if len(texto) <= 4:
        return "*" * len(texto)
    return f"{texto[:2]}***{texto[-2:]}"


def _mask_document(value):
    texto = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not texto:
        return value
    if len(texto) <= 4:
        return "*" * len(texto)
    return f"{texto[:3]}***{texto[-2:]}"


def _sanitize_for_log(value, field_name=""):
    campo = (field_name or "").lower()
    if isinstance(value, dict):
        return {chave: _sanitize_for_log(valor, chave) for chave, valor in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_log(item, field_name) for item in value]
    if value is None:
        return None
    if "token" in campo or "api_key" in campo or "access_token" in campo or "authorization" in campo:
        return _mask_secret(value)
    if "email" in campo:
        return _mask_email(value)
    if "cpf" in campo or "cnpj" in campo:
        return _mask_document(value)
    if "phone" in campo or "telefone" in campo or "mobile" in campo:
        return _mask_phone(value)
    return value


def _log_checkout_debug(prefixo, mensagem, **contexto):
    if contexto:
        LOGGER.info("%s %s | %s", prefixo, mensagem, _payload_json(_sanitize_for_log(contexto)))
    else:
        LOGGER.info("%s %s", prefixo, mensagem)


def _normalizar_texto_asaas(valor):
    texto = str(valor or "").strip().lower()
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


def _coletar_erros_asaas(resultado):
    itens = []
    if not isinstance(resultado, dict):
        return itens

    if resultado.get("mensagem"):
        itens.append(
            {
                "field": "",
                "code": "",
                "description": resultado.get("mensagem"),
            }
        )

    data = resultado.get("data")
    if not isinstance(data, dict):
        return itens

    if data.get("message"):
        itens.append(
            {
                "field": "",
                "code": "",
                "description": data.get("message"),
            }
        )

    errors = data.get("errors")
    if not isinstance(errors, list):
        return itens

    for item in errors:
        if isinstance(item, dict):
            itens.append(
                {
                    "field": item.get("field") or item.get("property") or item.get("param") or item.get("parameterName") or "",
                    "code": item.get("code") or "",
                    "description": item.get("description") or item.get("message") or "",
                }
            )
        elif item:
            itens.append({"field": "", "code": "", "description": str(item)})
    return itens


def _erro_customer_invalido_asaas(resultado):
    if not isinstance(resultado, dict) or resultado.get("ok"):
        return False

    termos_customer = ("customer", "cliente")
    termos_invalidade = (
        "invalido",
        "invalid",
        "inexistente",
        "nao existe",
        "nao encontrado",
        "not found",
        "does not exist",
        "nao informado",
        "must be informed",
        "must be provided",
        "obrigatorio",
        "required",
        "missing",
    )

    for item in _coletar_erros_asaas(resultado):
        campo = _normalizar_texto_asaas(item.get("field"))
        codigo = _normalizar_texto_asaas(item.get("code"))
        descricao = _normalizar_texto_asaas(item.get("description"))
        composto = " ".join(parte for parte in (campo, codigo, descricao) if parte).strip()
        if not composto:
            continue

        customer_relacionado = any(termo in campo for termo in termos_customer) or any(termo in composto for termo in termos_customer)
        if not customer_relacionado:
            continue

        if any(termo in composto for termo in termos_invalidade):
            return True

        if any(termo in campo for termo in termos_customer) and not descricao and not codigo:
            return True

    return False


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


def _normalizar_path_asaas(base_url, path):
    base_normalizada = (base_url or "").strip().rstrip("/")
    path_original = str(path or "").strip()
    path_normalizada = path_original if path_original.startswith("/") else f"/{path_original.lstrip('/')}"
    if base_normalizada.endswith("/v3") and path_normalizada.startswith("/v3/"):
        path_normalizada = path_normalizada[3:]
    elif base_normalizada.endswith("/v3") and path_normalizada == "/v3":
        path_normalizada = "/"
    return path_normalizada or "/"


def _asaas_request(method, path, payload=None, params=None, timeout=20):
    config = validar_configuracao_asaas()
    if not config["ok"]:
        LOGGER.error(
            "[ASAAS_ERROR] Configuracao invalida antes da chamada HTTP | %s",
            _payload_json(
                {
                    "funcao": "_asaas_request",
                    "method": method,
                    "path": path,
                    "base_url": config.get("config", {}).get("base_url"),
                    "app_env": config.get("config", {}).get("app_env"),
                    "faltando": config.get("faltando"),
                }
            ),
        )
        return {"ok": False, "erro": "configuracao", "mensagem": config["mensagem"]}

    path_normalizado = _normalizar_path_asaas(config["config"]["base_url"], path)
    url = f"{config['config']['base_url']}{path_normalizado}"
    headers = get_asaas_headers()
    inicio = perf_counter()
    _log_checkout_debug(
        "[ASAAS_DEBUG]",
        "Preparando request para API Asaas",
        funcao="_asaas_request",
        method=method,
        path=path,
        path_normalizado=path_normalizado,
        base_url=config["config"].get("base_url"),
        final_url=url,
        params=params,
        payload=payload,
        headers=headers,
        app_env=config["config"].get("app_env"),
        asaas_api_key_masked=_mask_secret(config["config"].get("api_key")),
    )
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            params=params,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        elapsed_ms = round((perf_counter() - inicio) * 1000, 2)
        LOGGER.error(
            "[ASAAS_ERROR] Excecao durante request para API Asaas | %s",
            _payload_json(
                {
                    "funcao": "_asaas_request",
                    "method": method,
                    "path": path,
                    "path_normalizado": path_normalizado,
                    "final_url": url,
                    "params": params,
                    "payload": _sanitize_for_log(payload),
                    "headers": _sanitize_for_log(headers),
                    "elapsed_ms": elapsed_ms,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "traceback": traceback.format_exc(),
                }
            ),
        )
        return {
            "ok": False,
            "erro": "conexao",
            "mensagem": str(exc),
            "url": url,
            "method": method,
            "path": path_normalizado,
            "request_payload": payload,
            "request_params": params,
            "elapsed_ms": elapsed_ms,
            "source": "asaas_api",
        }
    except Exception as exc:
        elapsed_ms = round((perf_counter() - inicio) * 1000, 2)
        LOGGER.error(
            "[CHECKOUT_TRACE] Excecao inesperada antes de processar resposta do Asaas | %s",
            _payload_json(
                {
                    "funcao": "_asaas_request",
                    "method": method,
                    "path": path,
                    "path_normalizado": path_normalizado,
                    "final_url": url,
                    "params": params,
                    "payload": _sanitize_for_log(payload),
                    "headers": _sanitize_for_log(headers),
                    "elapsed_ms": elapsed_ms,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "traceback": traceback.format_exc(),
                }
            ),
        )
        return {
            "ok": False,
            "erro": "interno_gateway",
            "mensagem": str(exc),
            "url": url,
            "method": method,
            "path": path_normalizado,
            "request_payload": payload,
            "request_params": params,
            "elapsed_ms": elapsed_ms,
            "source": "internal_gateway",
        }

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:500]}
    elapsed_ms = round((perf_counter() - inicio) * 1000, 2)
    response_headers = dict(response.headers or {})
    final_url = response.url or url
    _log_checkout_debug(
        "[ASAAS_DEBUG]",
        "Resposta recebida da API Asaas",
        funcao="_asaas_request",
        method=method,
        path=path_normalizado,
        final_url=final_url,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
        response_headers=response_headers,
        response_text=response.text,
        response_json=body,
    )

    if response.ok:
        return {
            "ok": True,
            "status_code": response.status_code,
            "data": body,
            "url": final_url,
            "method": method,
            "path": path_normalizado,
            "request_payload": payload,
            "request_params": params,
            "response_text": response.text,
            "response_headers": response_headers,
            "elapsed_ms": elapsed_ms,
            "source": "asaas_api",
        }

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
    LOGGER.error(
        "[ASAAS_ERROR] Falha HTTP retornada pela API Asaas | %s",
        _payload_json(
            {
                "funcao": "_asaas_request",
                "method": method,
                "path": path_normalizado,
                "final_url": final_url,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "payload": _sanitize_for_log(payload),
                "params": _sanitize_for_log(params),
                "response_headers": _sanitize_for_log(response_headers),
                "response_text": response.text,
                "response_json": _sanitize_for_log(body),
            }
        ),
    )
    return {
        "ok": False,
        "erro": "api",
        "status_code": response.status_code,
        "mensagem": mensagem or f"Erro HTTP {response.status_code}",
        "data": body,
        "url": final_url,
        "method": method,
        "path": path,
        "request_payload": payload,
        "request_params": params,
        "response_text": response.text,
        "response_headers": response_headers,
        "elapsed_ms": elapsed_ms,
        "source": "asaas_api",
    }


def testar_conexao_asaas():
    resultado = _asaas_request("GET", "/finance/getPaymentCheckoutConfig")
    if resultado["ok"]:
        return {
            "sucesso": True,
            "erro": None,
            "mensagem": "Conexao com a API do Asaas validada com sucesso.",
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
    resultado = _asaas_request("GET", "/customers", params={"email": email})
    if not resultado["ok"]:
        return None
    data = resultado.get("data") or {}
    if not isinstance(data, dict):
        return None
    itens = data.get("data") or []
    return itens[0] if itens else None


def criar_customer_asaas(usuario, ignorar_customer_salvo=False):
    usuario_id = usuario.get("id")
    usuario_db = _buscar_usuario_existente(usuario_id) if usuario_id else None
    usuario_integrado = dict(usuario_db or {})
    usuario_integrado.update(usuario or {})
    _log_checkout_debug(
        "[CHECKOUT_DEBUG]",
        "Entrando na etapa de customer Asaas",
        funcao="criar_customer_asaas",
        usuario_id=usuario_integrado.get("id"),
        tipo_usuario=usuario_integrado.get("tipo_usuario"),
        email=usuario_integrado.get("email"),
        asaas_customer_id=usuario_integrado.get("asaas_customer_id"),
        ignorar_customer_salvo=ignorar_customer_salvo,
    )
    diagnostico = diagnosticar_dados_checkout(usuario_integrado)
    if not diagnostico["ok"]:
        LOGGER.warning(
            "[CHECKOUT_DEBUG] Checkout bloqueado por dados incompletos antes do customer Asaas | %s",
            _payload_json(
                {
                    "funcao": "criar_customer_asaas",
                    "usuario_id": usuario_integrado.get("id"),
                    "tipo_usuario": usuario_integrado.get("tipo_usuario"),
                    "diagnostico": _sanitize_for_log(diagnostico),
                }
            ),
        )
        return {
            "ok": False,
            "gateway": DEFAULT_GATEWAY,
            "status": "dados_incompletos",
            "mensagem": diagnostico["mensagem"],
            "payload": diagnostico,
        }

    asaas_customer_id = (usuario_integrado.get("asaas_customer_id") or "").strip()
    if asaas_customer_id and not ignorar_customer_salvo:
        _log_checkout_debug(
            "[ASAAS_DEBUG]",
            "Usuario ja possui customer Asaas salvo",
            funcao="criar_customer_asaas",
            usuario_id=usuario_integrado.get("id"),
            asaas_customer_id=asaas_customer_id,
        )
        return {
            "ok": True,
            "gateway": DEFAULT_GATEWAY,
            "status": "existente",
            "asaas_customer_id": asaas_customer_id,
            "gateway_reference": asaas_customer_id,
            "payload": None,
        }
    if asaas_customer_id and ignorar_customer_salvo:
        _log_checkout_debug(
            "[ASAAS_RECOVERY]",
            "Ignorando customer salvo para refazer resolucao no ambiente atual",
            funcao="criar_customer_asaas",
            usuario_id=usuario_integrado.get("id"),
            asaas_customer_id=asaas_customer_id,
        )

    customer_existente = _buscar_customer_por_email((usuario_integrado.get("email") or "").strip().lower())
    if customer_existente and customer_existente.get("id"):
        if usuario_id:
            _atualizar_asaas_customer_usuario(usuario_id, customer_existente["id"])
        _log_checkout_debug(
            "[ASAAS_DEBUG]",
            "Customer Asaas existente reutilizado por email",
            funcao="criar_customer_asaas",
            usuario_id=usuario_integrado.get("id"),
            asaas_customer_id=customer_existente.get("id"),
            customer=customer_existente,
        )
        return {
            "ok": True,
            "gateway": DEFAULT_GATEWAY,
            "status": "reutilizado",
            "asaas_customer_id": customer_existente["id"],
            "gateway_reference": customer_existente["id"],
            "payload": customer_existente,
        }

    payload = {
        "name": (usuario_integrado.get("nome") or "").strip(),
        "email": (usuario_integrado.get("email") or "").strip().lower(),
    }
    if usuario_integrado.get("cpf") or usuario_integrado.get("cpf_cnpj"):
        payload["cpfCnpj"] = str(usuario_integrado.get("cpf") or usuario_integrado.get("cpf_cnpj")).strip()
    if usuario_integrado.get("telefone") or usuario_integrado.get("mobilePhone"):
        payload["mobilePhone"] = str(usuario_integrado.get("telefone") or usuario_integrado.get("mobilePhone")).strip()

    _log_checkout_debug(
        "[ASAAS_DEBUG]",
        "Criando novo customer Asaas",
        funcao="criar_customer_asaas",
        usuario_id=usuario_integrado.get("id"),
        payload=payload,
    )
    resultado = _asaas_request("POST", "/customers", payload=payload)
    if not resultado["ok"]:
        LOGGER.error(
            "[ASAAS_ERROR] Falha ao criar customer Asaas | %s",
            _payload_json(
                {
                    "funcao": "criar_customer_asaas",
                    "usuario_id": usuario_integrado.get("id"),
                    "resultado": _sanitize_for_log(resultado),
                }
            ),
        )
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


def _recuperar_customer_asaas_invalido(usuario, customer_id_antigo, assinatura_resultado):
    _log_checkout_debug(
        "[ASAAS_RECOVERY]",
        "Customer salvo invalido, recriando customer",
        funcao="_recuperar_customer_asaas_invalido",
        usuario_id=usuario.get("id"),
        customer_id_antigo=customer_id_antigo,
        erro_assinatura=assinatura_resultado,
    )
    customer_recuperado = criar_customer_asaas(usuario, ignorar_customer_salvo=True)
    if not customer_recuperado.get("ok"):
        LOGGER.error(
            "[ASAAS_ERROR] [ASAAS_RECOVERY] Falha ao recuperar customer invalido no Asaas | %s",
            _payload_json(
                {
                    "funcao": "_recuperar_customer_asaas_invalido",
                    "usuario_id": usuario.get("id"),
                    "customer_id_antigo": customer_id_antigo,
                    "resultado_customer": _sanitize_for_log(customer_recuperado),
                }
            ),
        )
        mensagem = customer_recuperado.get("mensagem") or "Falha ao recriar customer no Asaas."
        return {
            **customer_recuperado,
            "mensagem": f"Falha ao recuperar o customer do Asaas para o ambiente atual: {mensagem}",
            "status": "erro_recuperacao_customer",
        }

    novo_customer_id = customer_recuperado.get("asaas_customer_id")
    if customer_recuperado.get("status") == "criado":
        _log_checkout_debug(
            "[ASAAS_RECOVERY]",
            "Novo customer criado com sucesso",
            funcao="_recuperar_customer_asaas_invalido",
            usuario_id=usuario.get("id"),
            customer_id_antigo=customer_id_antigo,
            novo_customer_id=novo_customer_id,
        )
    else:
        _log_checkout_debug(
            "[ASAAS_RECOVERY]",
            "Customer do ambiente atual recuperado com sucesso",
            funcao="_recuperar_customer_asaas_invalido",
            usuario_id=usuario.get("id"),
            customer_id_antigo=customer_id_antigo,
            novo_customer_id=novo_customer_id,
            status_customer=customer_recuperado.get("status"),
        )
    if usuario.get("id") and novo_customer_id:
        _log_checkout_debug(
            "[ASAAS_RECOVERY]",
            "Customer atualizado no banco",
            funcao="_recuperar_customer_asaas_invalido",
            usuario_id=usuario.get("id"),
            customer_id_antigo=customer_id_antigo,
            novo_customer_id=novo_customer_id,
        )
    return customer_recuperado


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


def _listar_cobrancas_assinatura_asaas(asaas_subscription_id):
    return _asaas_request("GET", f"/subscriptions/{asaas_subscription_id}/payments")


def _extrair_lista_asaas(resultado):
    data = (resultado or {}).get("data")
    if isinstance(data, dict):
        itens = data.get("data") or []
        return itens if isinstance(itens, list) else []
    return data if isinstance(data, list) else []


def _ordenar_data_asaas(valor, padrao):
    texto = str(valor or "").strip()
    return texto or padrao


def _prioridade_status_cobranca_asaas(status):
    status_normalizado = str(status or "").strip().upper()
    prioridades = {
        "PENDING": 0,
        "OVERDUE": 1,
        "AWAITING_RISK_ANALYSIS": 2,
    }
    return prioridades.get(status_normalizado, 9)


def _selecionar_cobranca_inicial_asaas(cobrancas):
    itens = [dict(item) for item in (cobrancas or []) if isinstance(item, dict)]
    if not itens:
        return None
    return sorted(
        itens,
        key=lambda item: (
            _prioridade_status_cobranca_asaas(item.get("status")),
            _ordenar_data_asaas(item.get("dueDate"), "9999-12-31"),
            _ordenar_data_asaas(item.get("dateCreated"), "9999-12-31T23:59:59"),
            str(item.get("id") or ""),
        ),
    )[0]


def _buscar_invoice_url_assinatura_asaas(asaas_subscription_id, tentativas=3, intervalo_segundos=0.6):
    if not asaas_subscription_id:
        LOGGER.error(
            "[ASAAS_ERROR] Assinatura criada sem identificador valido para buscar cobrancas | %s",
            _payload_json(
                {
                    "funcao": "_buscar_invoice_url_assinatura_asaas",
                    "asaas_subscription_id": asaas_subscription_id,
                }
            ),
        )
        return {
            "ok": False,
            "erro": "assinatura_sem_id",
            "mensagem": "A assinatura foi criada sem um identificador valido para buscar a cobranca inicial.",
            "resultado": None,
            "cobranca": None,
            "invoice_url": None,
        }
    ultimo_resultado = None
    ultima_cobranca = None
    for tentativa in range(1, tentativas + 1):
        _log_checkout_debug(
            "[ASAAS_DEBUG]",
            "Buscando cobrancas da assinatura",
            funcao="_buscar_invoice_url_assinatura_asaas",
            asaas_subscription_id=asaas_subscription_id,
            tentativa=tentativa,
            tentativas=tentativas,
        )
        resultado = _listar_cobrancas_assinatura_asaas(asaas_subscription_id)
        ultimo_resultado = resultado
        if not resultado.get("ok"):
            if tentativa < tentativas:
                sleep(intervalo_segundos)
                continue
            LOGGER.error(
                "[ASAAS_ERROR] Assinatura criada, mas a consulta das cobrancas falhou | %s",
                _payload_json(
                    {
                        "funcao": "_buscar_invoice_url_assinatura_asaas",
                        "asaas_subscription_id": asaas_subscription_id,
                        "tentativa": tentativa,
                        "resultado": _sanitize_for_log(resultado),
                    }
                ),
            )
            return {
                "ok": False,
                "erro": "consulta_cobrancas_falhou",
                "mensagem": resultado.get("mensagem") or "Nao foi possivel consultar as cobrancas da assinatura no Asaas.",
                "resultado": resultado,
                "cobranca": None,
                "invoice_url": None,
            }

        cobrancas = _extrair_lista_asaas(resultado)
        cobranca = _selecionar_cobranca_inicial_asaas(cobrancas)
        ultima_cobranca = cobranca
        if cobranca:
            _log_checkout_debug(
                "[ASAAS_DEBUG]",
                "Cobranca selecionada para redirecionamento",
                funcao="_buscar_invoice_url_assinatura_asaas",
                asaas_subscription_id=asaas_subscription_id,
                tentativa=tentativa,
                cobranca=cobranca,
            )
            invoice_url = (cobranca.get("invoiceUrl") or "").strip()
            if invoice_url:
                _log_checkout_debug(
                    "[ASAAS_DEBUG]",
                    "invoiceUrl encontrado",
                    funcao="_buscar_invoice_url_assinatura_asaas",
                    asaas_subscription_id=asaas_subscription_id,
                    tentativa=tentativa,
                    asaas_payment_id=cobranca.get("id"),
                    invoice_url=invoice_url,
                )
                return {
                    "ok": True,
                    "erro": None,
                    "mensagem": None,
                    "resultado": resultado,
                    "cobranca": cobranca,
                    "invoice_url": invoice_url,
                }
        if tentativa < tentativas:
            sleep(intervalo_segundos)

    if ultima_cobranca:
        LOGGER.error(
            "[ASAAS_ERROR] Assinatura criada, mas invoiceUrl ausente | %s",
            _payload_json(
                {
                    "funcao": "_buscar_invoice_url_assinatura_asaas",
                    "asaas_subscription_id": asaas_subscription_id,
                    "cobranca": _sanitize_for_log(ultima_cobranca),
                    "resultado": _sanitize_for_log(ultimo_resultado),
                }
            ),
        )
        return {
            "ok": False,
            "erro": "invoice_url_ausente",
            "mensagem": "A cobranca inicial foi encontrada, mas o invoiceUrl nao foi retornado pelo Asaas.",
            "resultado": ultimo_resultado,
            "cobranca": ultima_cobranca,
            "invoice_url": None,
        }

    LOGGER.error(
        "[ASAAS_ERROR] Assinatura criada, mas cobranca nao encontrada | %s",
        _payload_json(
            {
                "funcao": "_buscar_invoice_url_assinatura_asaas",
                "asaas_subscription_id": asaas_subscription_id,
                "resultado": _sanitize_for_log(ultimo_resultado),
            }
        ),
    )
    return {
        "ok": False,
        "erro": "cobranca_nao_encontrada",
        "mensagem": "A assinatura foi criada, mas nenhuma cobranca inicial foi encontrada no Asaas.",
        "resultado": ultimo_resultado,
        "cobranca": None,
        "invoice_url": None,
    }


def _valor_plano_decimal(plano, *chaves):
    for chave in chaves:
        valor = plano.get(chave)
        if valor is not None and valor != "":
            return _to_decimal(valor)
    return Decimal("0")


def _payload_atualizacao_primeira_cobranca(cobranca, plano, valor_bruto, valor_desconto, external_reference):
    billing_type = (cobranca.get("billingType") or plano.get("billingType") or "UNDEFINED").strip().upper()
    due_date = _date_to_iso(cobranca.get("dueDate") or plano.get("nextDueDate") or _proximo_vencimento(plano))
    description = (
        cobranca.get("description")
        or plano.get("description")
        or plano.get("descricao")
        or plano.get("nome")
        or "Assinatura TriLab TREINAMENTO"
    )
    payload = {
        "billingType": billing_type,
        "value": float(valor_bruto),
        "dueDate": due_date,
        "description": str(description).strip(),
    }
    if external_reference:
        payload["externalReference"] = external_reference
    if valor_desconto > 0:
        payload["discount"] = {
            "value": float(valor_desconto),
            "dueDateLimitDays": 0,
        }
    return payload


def _aplicar_desconto_primeira_cobranca_asaas(cobranca, plano, valor_bruto, valor_desconto, valor_final, external_reference):
    asaas_payment_id = (cobranca or {}).get("id")
    if not asaas_payment_id:
        return {
            "ok": False,
            "erro": "primeira_cobranca_sem_id",
            "mensagem": "A primeira cobranca da assinatura foi encontrada sem id no Asaas.",
            "cobranca": cobranca,
        }

    payload = _payload_atualizacao_primeira_cobranca(cobranca, plano, valor_bruto, valor_desconto, external_reference)
    _log_checkout_debug(
        "[CHECKOUT_FIRST_PAYMENT]",
        "Aplicando cupom somente na primeira cobranca Asaas",
        funcao="_aplicar_desconto_primeira_cobranca_asaas",
        asaas_payment_id=asaas_payment_id,
        asaas_subscription_id=cobranca.get("subscription"),
        external_reference=external_reference,
        valor_assinatura_bruto=float(valor_bruto),
        valor_desconto_primeira_cobranca=float(valor_desconto),
        valor_final_primeira_cobranca=float(valor_final),
        renovacoes_futuras_valor=float(valor_bruto),
        payload=payload,
    )
    resultado = _asaas_request("PUT", f"/payments/{asaas_payment_id}", payload=payload)
    if not resultado.get("ok"):
        LOGGER.error(
            "[CHECKOUT_FIRST_PAYMENT] Falha ao aplicar desconto na primeira cobranca Asaas | %s",
            _payload_json(
                {
                    "asaas_payment_id": asaas_payment_id,
                    "asaas_subscription_id": cobranca.get("subscription"),
                    "payload": _sanitize_for_log(payload),
                    "resultado": _sanitize_for_log(resultado),
                }
            ),
        )
        return {
            "ok": False,
            "erro": "desconto_primeira_cobranca_falhou",
            "mensagem": resultado.get("mensagem") or "Nao foi possivel aplicar o desconto na primeira cobranca do Asaas.",
            "resultado": resultado,
            "cobranca": cobranca,
        }

    cobranca_atualizada = resultado.get("data") or cobranca
    _log_checkout_debug(
        "[CHECKOUT_FIRST_PAYMENT]",
        "Primeira cobranca Asaas atualizada com desconto unico",
        funcao="_aplicar_desconto_primeira_cobranca_asaas",
        asaas_payment_id=asaas_payment_id,
        asaas_subscription_id=cobranca.get("subscription"),
        valor_assinatura_bruto=float(valor_bruto),
        valor_desconto_primeira_cobranca=float(valor_desconto),
        valor_final_primeira_cobranca=float(valor_final),
        renovacoes_futuras_valor=float(valor_bruto),
        cobranca=cobranca_atualizada,
    )
    return {
        "ok": True,
        "erro": None,
        "mensagem": None,
        "resultado": resultado,
        "cobranca": cobranca_atualizada,
    }


def _cancelar_assinatura_por_falha_primeira_cobranca(asaas_subscription_id, motivo, contexto=None):
    if not asaas_subscription_id:
        return None
    LOGGER.error(
        "[CHECKOUT_FIRST_PAYMENT] Cancelando assinatura criada sem desconto correto na primeira cobranca | %s",
        _payload_json(
            {
                "asaas_subscription_id": asaas_subscription_id,
                "motivo": motivo,
                "contexto": _sanitize_for_log(contexto or {}),
            }
        ),
    )
    return _asaas_request("DELETE", f"/subscriptions/{asaas_subscription_id}")


def criar_assinatura_asaas(customer_id, plano):
    valor_assinatura = _valor_plano_decimal(plano, "valor_assinatura", "checkout_valor_bruto", "valor_base", "valor", "preco_mensal")
    valor_desconto_primeira = _valor_plano_decimal(plano, "checkout_valor_desconto")
    valor_final_primeira = _valor_plano_decimal(plano, "checkout_valor_final")
    if valor_final_primeira <= 0 and valor_desconto_primeira <= 0:
        valor_final_primeira = valor_assinatura
    elif valor_final_primeira < 0:
        valor_final_primeira = Decimal("0")
    payload = {
        "customer": customer_id,
        "billingType": (plano.get("billingType") or "UNDEFINED").strip().upper(),
        "nextDueDate": _proximo_vencimento(plano),
        "value": float(valor_assinatura),
        "cycle": _ciclo_asaas(plano),
        "description": (plano.get("description") or plano.get("descricao") or plano.get("nome") or "Assinatura TriLab TREINAMENTO").strip(),
    }
    external_reference = (plano.get("externalReference") or plano.get("external_reference") or "").strip()
    if external_reference:
        payload["externalReference"] = external_reference
    _log_checkout_debug(
        "[CHECKOUT_ASAAS]",
        "Criando assinatura Asaas com valores persistidos do checkout",
        funcao="criar_assinatura_asaas",
        customer_id=customer_id,
        plano_codigo=plano.get("codigo"),
        plano_tipo=plano.get("tipo_plano") or plano.get("tipo"),
        external_reference=external_reference,
        valor_assinatura_bruto=float(valor_assinatura),
        valor_desconto_primeira_cobranca=float(valor_desconto_primeira),
        valor_final_primeira_cobranca=float(valor_final_primeira),
        renovacoes_futuras_valor=float(valor_assinatura),
        payload=payload,
    )
    resultado = _asaas_request("POST", "/subscriptions", payload=payload)
    if not resultado["ok"]:
        LOGGER.error(
            "[ASAAS_ERROR] Falha ao criar assinatura Asaas | %s",
            _payload_json(
                {
                    "funcao": "criar_assinatura_asaas",
                    "customer_id": customer_id,
                    "plano_codigo": plano.get("codigo"),
                    "resultado": _sanitize_for_log(resultado),
                }
            ),
        )
        return {
            "ok": False,
            "gateway": DEFAULT_GATEWAY,
            "status": "erro",
            "mensagem": resultado.get("mensagem"),
            "payload": resultado.get("data"),
        }

    assinatura = resultado["data"]
    asaas_subscription_id = assinatura.get("id")
    _log_checkout_debug(
        "[ASAAS_DEBUG]",
        "Assinatura criada com sucesso",
        funcao="criar_assinatura_asaas",
        customer_id=customer_id,
        plano_codigo=plano.get("codigo"),
        asaas_subscription_id=asaas_subscription_id,
        assinatura=assinatura,
    )
    cobranca_inicial = _buscar_invoice_url_assinatura_asaas(asaas_subscription_id)
    mensagem_redirecionamento = None
    invoice_url = None
    asaas_payment_id = None
    cobranca_payload = None
    if cobranca_inicial.get("ok"):
        cobranca_payload = cobranca_inicial.get("cobranca")
        invoice_url = cobranca_inicial.get("invoice_url")
        asaas_payment_id = (cobranca_payload or {}).get("id")
    else:
        mensagem_redirecionamento = (
            "Assinatura criada no Asaas, mas nao foi possivel abrir a cobranca automaticamente. "
            "Voce pode acompanhar o status em Minha Assinatura."
        )
        cobranca_payload = cobranca_inicial.get("cobranca")

    first_payment_discount_applied = False
    if valor_desconto_primeira > 0:
        if not cobranca_payload or not (cobranca_payload or {}).get("id"):
            cancelamento = _cancelar_assinatura_por_falha_primeira_cobranca(
                asaas_subscription_id,
                "cobranca_inicial_nao_encontrada_para_desconto",
                {"cobranca_inicial": cobranca_inicial},
            )
            return {
                "ok": False,
                "gateway": DEFAULT_GATEWAY,
                "status": "erro_primeira_cobranca",
                "mensagem": "Assinatura criada no Asaas, mas a primeira cobranca nao foi encontrada para aplicar o cupom. A assinatura foi cancelada para evitar cobranca cheia.",
                "asaas_subscription_id": asaas_subscription_id,
                "cancelamento_payload": cancelamento,
                "payload": assinatura,
            }
        ajuste_primeira = _aplicar_desconto_primeira_cobranca_asaas(
            cobranca_payload,
            plano,
            valor_assinatura,
            valor_desconto_primeira,
            valor_final_primeira,
            external_reference,
        )
        if not ajuste_primeira.get("ok"):
            cancelamento = _cancelar_assinatura_por_falha_primeira_cobranca(
                asaas_subscription_id,
                "falha_ao_aplicar_desconto_na_primeira_cobranca",
                ajuste_primeira,
            )
            return {
                "ok": False,
                "gateway": DEFAULT_GATEWAY,
                "status": "erro_primeira_cobranca",
                "mensagem": "Assinatura criada no Asaas, mas nao foi possivel aplicar o cupom somente na primeira cobranca. A assinatura foi cancelada para evitar desconto recorrente incorreto ou cobranca cheia.",
                "asaas_subscription_id": asaas_subscription_id,
                "asaas_payment_id": asaas_payment_id,
                "cancelamento_payload": cancelamento,
                "payload": assinatura,
                "payment_payload": cobranca_payload,
                "first_payment_discount_result": ajuste_primeira,
            }
        cobranca_payload = ajuste_primeira.get("cobranca") or cobranca_payload
        invoice_url = (cobranca_payload or {}).get("invoiceUrl") or invoice_url
        asaas_payment_id = (cobranca_payload or {}).get("id") or asaas_payment_id
        first_payment_discount_applied = True
    return {
        "ok": True,
        "gateway": DEFAULT_GATEWAY,
        "status": "pendente",
        "mensagem": mensagem_redirecionamento,
        "asaas_subscription_id": asaas_subscription_id,
        "asaas_payment_id": asaas_payment_id,
        "invoice_url": invoice_url,
        "redirect_url": invoice_url,
        "gateway_reference": asaas_subscription_id,
        "payload": assinatura,
        "payment_payload": cobranca_payload,
        "subscription_value": float(valor_assinatura),
        "future_payments_value": float(valor_assinatura),
        "first_payment_discount_applied": first_payment_discount_applied,
        "first_payment_valor_bruto": float(valor_assinatura),
        "first_payment_valor_desconto": float(valor_desconto_primeira),
        "first_payment_valor_final": float(valor_final_primeira),
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
    resultado = _asaas_request("GET", f"/subscriptions/{gateway_reference}")
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


def _eh_payload_teste_manual(payload, payment):
    if not isinstance(payload, dict):
        return False
    if bool(payload.get("manual_test")):
        return True
    payment_id = str((payment or {}).get("id") or "")
    customer_id = str((payment or {}).get("customer") or "")
    return payment_id.startswith("pay_test_") or customer_id.startswith("cus_test_")


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


def _valor_desconto_pagamento_asaas(pagamento_payload):
    desconto = (pagamento_payload or {}).get("discount")
    if not isinstance(desconto, dict):
        return Decimal("0")
    valor = desconto.get("value")
    if valor in (None, ""):
        return Decimal("0")
    return max(Decimal("0"), _to_decimal(valor))


def _upsert_pagamento_webhook(cursor, pagamento_payload, assinatura):
    usuario_id = assinatura["usuario_id"] if assinatura else None
    if not usuario_id:
        usuario = _buscar_usuario_por_customer(cursor, pagamento_payload.get("customer"))
        usuario_id = usuario["id"] if usuario else None
    if not usuario_id:
        raise ValueError("Usuario interno nao encontrado para o pagamento do Asaas.")

    valor_bruto = _to_decimal(pagamento_payload.get("value") or pagamento_payload.get("netValue") or 0)
    valor_desconto = min(valor_bruto, _valor_desconto_pagamento_asaas(pagamento_payload))
    valor_final = max(Decimal("0"), valor_bruto - valor_desconto).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    valor = float(valor_final)
    valor_bruto_float = float(valor_bruto)
    valor_desconto_float = float(valor_desconto)
    valor_final_float = float(valor_final)
    status_interno = EVENTOS_PAGAMENTO.get((pagamento_payload.get("_evento") or "").upper(), "pendente")
    data_pagamento = pagamento_payload.get("clientPaymentDate") or pagamento_payload.get("paymentDate")
    data_vencimento = pagamento_payload.get("dueDate")
    referencia_externa = pagamento_payload.get("id")
    gateway_reference = pagamento_payload.get("invoiceUrl") or referencia_externa

    cursor.execute(
        """
        SELECT id, status, assinatura_id, valor_desconto, valor_final
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
                valor = CASE
                    WHEN %s > 0 THEN %s
                    ELSE COALESCE(valor_final, %s)
                END,
                valor_bruto = COALESCE(valor_bruto, %s),
                valor_desconto = CASE
                    WHEN %s > 0 THEN %s
                    ELSE COALESCE(valor_desconto, 0)
                END,
                valor_final = CASE
                    WHEN %s > 0 THEN %s
                    ELSE COALESCE(valor_final, %s)
                END,
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
                valor_desconto_float,
                valor_final_float,
                valor_bruto_float,
                valor_bruto_float,
                valor_desconto_float,
                valor_desconto_float,
                valor_desconto_float,
                valor_final_float,
                valor_bruto_float,
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            usuario_id,
            assinatura["id"] if assinatura else None,
            valor,
            valor_bruto_float,
            valor_desconto_float,
            valor_final_float,
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


def _atualizar_checkout_por_webhook(cursor, pagamento_payload, pagamento_id, status_pagamento):
    asaas_payment_id = pagamento_payload.get("id")
    asaas_subscription_id = pagamento_payload.get("subscription")
    external_reference = pagamento_payload.get("externalReference")
    if not asaas_payment_id and not asaas_subscription_id and not external_reference:
        return

    if status_pagamento in STATUS_QUITADOS:
        status_checkout = "concluido"
    elif status_pagamento in {"cancelado", "estornado"}:
        status_checkout = "cancelado"
    else:
        status_checkout = "asaas_criado"

    cursor.execute(
        """
        UPDATE checkouts_pendentes
        SET status = %s,
            pagamento_id = COALESCE(%s, pagamento_id),
            asaas_payment_id = COALESCE(%s, asaas_payment_id),
            asaas_subscription_id = COALESCE(%s, asaas_subscription_id),
            atualizado_em = CURRENT_TIMESTAMP
        WHERE (asaas_payment_id = %s AND %s IS NOT NULL)
           OR (asaas_subscription_id = %s AND %s IS NOT NULL)
           OR (external_reference = %s AND %s IS NOT NULL)
        """,
        (
            status_checkout,
            pagamento_id,
            asaas_payment_id,
            asaas_subscription_id,
            asaas_payment_id,
            asaas_payment_id,
            asaas_subscription_id,
            asaas_subscription_id,
            external_reference,
            external_reference,
        ),
    )
    if cursor.rowcount:
        LOGGER.info(
            "[CHECKOUT_STATE] Checkout atualizado a partir do webhook Asaas | %s",
            _payload_json(
                {
                    "asaas_payment_id": asaas_payment_id,
                    "asaas_subscription_id": asaas_subscription_id,
                    "pagamento_id": pagamento_id,
                    "status_pagamento": status_pagamento,
                    "status_checkout": status_checkout,
                }
            ),
        )


def processar_webhook_asaas(payload, headers):
    headers_normalizados = _normalizar_headers(headers)
    token_recebido = (headers_normalizados.get("asaas-access-token") or "").strip()
    token_esperado = validar_configuracao_asaas()["config"].get("webhook_token")
    evento = (payload or {}).get("event") or ""
    payment = _extrair_pagamento_payload(payload)

    if not token_esperado:
        LOGGER.error("Webhook Asaas rejeitado: ASAAS_WEBHOOK_TOKEN nao configurado.")
        return {"ok": False, "status_code": 500, "mensagem": "ASAAS_WEBHOOK_TOKEN nao configurado."}
    if token_recebido != token_esperado:
        LOGGER.warning(
            "Webhook Asaas rejeitado por token invalido: evento=%s payment_id=%s",
            evento,
            payment.get("id"),
        )
        return {"ok": False, "status_code": 403, "mensagem": "Token do webhook invalido."}

    LOGGER.info("Processando webhook Asaas: evento=%s payment_id=%s", evento, payment.get("id"))
    if _eh_payload_teste_manual(payload, payment):
        LOGGER.info("Webhook Asaas identificado como teste manual: evento=%s payment_id=%s", evento, payment.get("id"))
        return {
            "ok": True,
            "status_code": 200,
            "mensagem": "Webhook de teste recebido com sucesso.",
            "evento": evento,
            "teste_manual": True,
        }
    payment["_evento"] = evento
    dedupe_key = _dedupe_key(payload)

    conn = conectar()
    cursor = conn.cursor()
    try:
        evento_id = _registrar_evento_recebido(cursor, payload, headers_normalizados, dedupe_key)
        if not evento_id:
            conn.commit()
            LOGGER.info("Webhook Asaas idempotente: evento=%s dedupe_key=%s", evento, dedupe_key)
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
            if not assinatura:
                usuario_gateway = _buscar_usuario_por_customer(cursor, payment.get("customer"))
                status_sem_usuario = EVENTOS_PAGAMENTO.get(evento.upper(), "pendente")
                if not usuario_gateway and status_sem_usuario not in STATUS_QUITADOS:
                    _atualizar_evento_processamento(cursor, evento_id, "ignorado")
                    conn.commit()
                    LOGGER.warning(
                        "[ASAAS_WEBHOOK] Evento nao consolidado ignorado sem usuario local: evento=%s payment_id=%s subscription=%s customer=%s status=%s",
                        evento,
                        payment.get("id"),
                        payment.get("subscription"),
                        payment.get("customer"),
                        status_sem_usuario,
                    )
                    return {
                        "ok": True,
                        "status_code": 200,
                        "mensagem": "Evento nao consolidado ignorado sem usuario local.",
                        "evento": evento,
                        "status_pagamento": status_sem_usuario,
                        "idempotente": False,
                        "dedupe_key": dedupe_key,
                    }
            pagamento_id, status_pagamento = _upsert_pagamento_webhook(cursor, payment, assinatura)
            _atualizar_assinatura_por_pagamento(cursor, assinatura, payment, status_pagamento)
            _atualizar_checkout_por_webhook(cursor, payment, pagamento_id, status_pagamento)
        else:
            pagamento_id = None
            status_pagamento = None

        _atualizar_evento_processamento(cursor, evento_id, "processado")
        conn.commit()
        LOGGER.info(
            "Webhook Asaas processado com sucesso: evento=%s pagamento_id=%s status=%s",
            evento,
            pagamento_id,
            status_pagamento,
        )
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
        LOGGER.exception("Erro ao processar webhook Asaas: evento=%s dedupe_key=%s", evento, dedupe_key)
        return {"ok": False, "status_code": 500, "mensagem": str(exc), "evento": evento, "dedupe_key": dedupe_key}
    finally:
        conn.close()


def cancelar_assinatura_gateway(gateway_reference):
    if not gateway_reference:
        return {"ok": False, "gateway": DEFAULT_GATEWAY, "status": "erro", "mensagem": "Referencia ausente."}
    resultado = _asaas_request("DELETE", f"/subscriptions/{gateway_reference}")
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
    _log_checkout_debug(
        "[CHECKOUT_DEBUG]",
        "Entrando no gateway de customer",
        funcao="criar_customer_gateway",
        usuario_id=usuario.get("id"),
        tipo_usuario=usuario.get("tipo_usuario"),
    )
    if (usuario.get("tipo_usuario") or "").strip().lower() != "atleta":
        return {
            "ok": True,
            "gateway": "manual",
            "status": "ignorado",
            "gateway_reference": None,
            "payload": {"motivo": "Fluxo Asaas restrito ao atleta solo nesta etapa."},
        }
    return criar_customer_asaas(usuario)


def criar_assinatura_gateway(usuario, plano, checkout=None):
    _log_checkout_debug(
        "[CHECKOUT_ASAAS]",
        "Entrando no gateway de assinatura",
        funcao="criar_assinatura_gateway",
        checkout_id=(checkout or {}).get("id"),
        external_reference=(checkout or {}).get("external_reference") or plano.get("externalReference"),
        usuario_id=usuario.get("id"),
        tipo_usuario=usuario.get("tipo_usuario"),
        plano_codigo=plano.get("codigo"),
        plano_tipo=plano.get("tipo_plano") or plano.get("tipo"),
        valor_bruto=(checkout or {}).get("valor_bruto") or plano.get("valor_base"),
        valor_desconto=(checkout or {}).get("valor_desconto") or 0,
        valor_final_primeira_cobranca=(checkout or {}).get("valor_final") or plano.get("checkout_valor_final") or plano.get("valor_base"),
        renovacoes_futuras_valor=(checkout or {}).get("valor_bruto") or plano.get("valor_assinatura") or plano.get("valor_base"),
    )
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
        LOGGER.error(
            "[ASAAS_ERROR] Fluxo interrompido antes da assinatura por falha no customer | %s",
            _payload_json(
                {
                    "funcao": "criar_assinatura_gateway",
                    "usuario_id": usuario.get("id"),
                    "plano_codigo": plano.get("codigo"),
                    "customer_resultado": _sanitize_for_log(customer),
                }
            ),
        )
        return customer
    dados_plano = dict(plano or {})
    dados_plano.setdefault("description", f"Assinatura {dados_plano.get('nome') or 'TriLab TREINAMENTO'}")
    assinatura = criar_assinatura_asaas(customer["asaas_customer_id"], dados_plano)
    if assinatura.get("ok") or not _erro_customer_invalido_asaas(assinatura):
        return assinatura

    _log_checkout_debug(
        "[ASAAS_RECOVERY]",
        "Erro de customer invalido detectado na criacao da assinatura",
        funcao="criar_assinatura_gateway",
        usuario_id=usuario.get("id"),
        plano_codigo=plano.get("codigo"),
        customer_id=customer.get("asaas_customer_id"),
        assinatura_resultado=assinatura,
    )
    customer_recuperado = _recuperar_customer_asaas_invalido(usuario, customer.get("asaas_customer_id"), assinatura)
    if not customer_recuperado.get("ok"):
        return customer_recuperado

    _log_checkout_debug(
        "[ASAAS_RECOVERY]",
        "Retentando criacao da assinatura",
        funcao="criar_assinatura_gateway",
        usuario_id=usuario.get("id"),
        plano_codigo=plano.get("codigo"),
        customer_id=customer_recuperado.get("asaas_customer_id"),
    )
    segunda_tentativa = criar_assinatura_asaas(customer_recuperado["asaas_customer_id"], dados_plano)
    if not segunda_tentativa.get("ok"):
        LOGGER.error(
            "[ASAAS_ERROR] [ASAAS_RECOVERY] Segunda tentativa de criacao da assinatura falhou | %s",
            _payload_json(
                {
                    "funcao": "criar_assinatura_gateway",
                    "usuario_id": usuario.get("id"),
                    "plano_codigo": plano.get("codigo"),
                    "customer_id_antigo": customer.get("asaas_customer_id"),
                    "customer_id_novo": customer_recuperado.get("asaas_customer_id"),
                    "resultado_segunda_tentativa": _sanitize_for_log(segunda_tentativa),
                }
            ),
        )
    return segunda_tentativa


def processar_webhook_gateway(payload):
    return processar_webhook_asaas(payload, {})
