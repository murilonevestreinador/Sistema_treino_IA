import json
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from html import escape
from urllib.parse import urlencode

import requests

from core.env import bool_env

LOGGER = logging.getLogger("trilab.email.service")
RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_PUBLIC_APP_URL = "https://app.trilabtreinamento.com"


def _mask_email(valor):
    texto = str(valor or "").strip()
    if "@" not in texto:
        return texto
    local, dominio = texto.split("@", 1)
    if len(local) <= 2:
        local_mask = "*" * len(local)
    else:
        local_mask = f"{local[:2]}***"
    return f"{local_mask}@{dominio}"


def resolver_url_base_publica(obrigatorio=False):
    # Em producao, configure APP_BASE_URL com a URL publica usada nos links transacionais.
    candidatos = [
        ("APP_BASE_URL", os.getenv("APP_BASE_URL", "")),
        ("PUBLIC_APP_URL", os.getenv("PUBLIC_APP_URL", "")),
        ("DEFAULT_PUBLIC_APP_URL", DEFAULT_PUBLIC_APP_URL),
        ("RENDER_EXTERNAL_URL", os.getenv("RENDER_EXTERNAL_URL", "")),
    ]

    for nome_env, url in candidatos:
        url_limpa = (url or "").strip().rstrip("/")
        if url_limpa:
            if nome_env != "APP_BASE_URL":
                LOGGER.warning(
                    "[EMAIL_SERVICE] Usando %s como fallback de URL publica. Configure APP_BASE_URL em producao.",
                    nome_env,
                )
            return url_limpa

    hostname_render = (os.getenv("RENDER_EXTERNAL_HOSTNAME", "") or "").strip().strip("/")
    if hostname_render:
        LOGGER.warning(
            "[EMAIL_SERVICE] Usando RENDER_EXTERNAL_HOSTNAME como fallback de URL publica. Configure APP_BASE_URL em producao."
        )
        return f"https://{hostname_render}"

    if obrigatorio:
        raise RuntimeError("APP_BASE_URL e obrigatoria para envio de e-mail transacional.")
    return ""


def montar_link_publico(query_params=None, base_url=None, caminho=""):
    envio_real = _provider_normalizado() not in {"disabled", "log"}
    url_base = (base_url or resolver_url_base_publica(obrigatorio=envio_real)).strip().rstrip("/")
    caminho_limpo = (caminho or "").strip()
    if caminho_limpo and not caminho_limpo.startswith("/"):
        caminho_limpo = f"/{caminho_limpo}"
    query = urlencode({chave: valor for chave, valor in (query_params or {}).items() if valor not in (None, "")})
    destino = f"{url_base}{caminho_limpo}" if url_base else (caminho_limpo or "/")
    if not query:
        return destino
    separador = "&" if "?" in destino else "?"
    return f"{destino}{separador}{query}"


def _provider_normalizado():
    provider = (os.getenv("EMAIL_PROVIDER") or "").strip().lower()
    email_habilitado = bool_env("EMAIL_ENABLED", False, logger=LOGGER, contexto="email_provider")
    if not email_habilitado:
        return "disabled"
    if provider == "log":
        return "log"
    return provider or "resend"


def email_envio_habilitado():
    return _provider_normalizado() != "disabled"


def _email_from():
    return (os.getenv("EMAIL_FROM") or "").strip()


def _email_reply_to():
    return (os.getenv("EMAIL_REPLY_TO") or "").strip() or None


def _resend_api_key():
    return (os.getenv("RESEND_API_KEY") or "").strip()


def _email_layout_html(titulo, texto, cta_label=None, cta_link=None, rodape=None):
    bloco_cta = ""
    if cta_label and cta_link:
        cta_link_seguro = escape(str(cta_link), quote=True)
        bloco_cta = (
            f'<p style="margin:24px 0;">'
            f'<a href="{cta_link_seguro}" '
            f'style="display:inline-block;padding:12px 18px;border-radius:999px;'
            f'background:#E73529;color:#ffffff;text-decoration:none;font-weight:700;">{escape(str(cta_label))}</a>'
            f"</p>"
            f'<p style="margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.6;">'
            f'Se o botao nao abrir, copie e cole este link no navegador:<br>'
            f'<a href="{cta_link_seguro}" style="color:#023363;word-break:break-all;">{cta_link_seguro}</a>'
            f"</p>"
        )
    rodape_html = (
        f'<p style="margin-top:24px;color:#64748b;font-size:13px;">{escape(str(rodape))}</p>' if rodape else ""
    )
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:620px;margin:0 auto;'
        'padding:24px;border:1px solid #d9e2ec;border-radius:20px;background:#ffffff;">'
        '<div style="margin-bottom:16px;font-size:12px;font-weight:700;letter-spacing:.08em;'
        'text-transform:uppercase;color:#023363;">TriLab TREINAMENTO</div>'
        f'<h2 style="margin:0 0 12px;color:#0f172a;">{escape(str(titulo))}</h2>'
        f'<p style="margin:0;color:#475569;line-height:1.7;">{escape(str(texto))}</p>'
        f"{bloco_cta}"
        f"{rodape_html}"
        "</div>"
    )


def _enviar_via_log(destino, assunto, html, texto=None, metadados=None):
    LOGGER.info(
        "[EMAIL_SERVICE] Provedor log destino=%s assunto=%s metadados=%s",
        _mask_email(destino),
        assunto,
        json.dumps(metadados or {}, ensure_ascii=True, sort_keys=True, default=str),
    )
    return {"ok": True, "provider": "log", "message_id": None}


def _enviar_via_smtp(destino, assunto, html, texto=None):
    host = (os.getenv("SMTP_HOST") or "").strip()
    porta = int((os.getenv("SMTP_PORT") or "587").strip() or 587)
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    password = os.getenv("SMTP_PASSWORD") or ""
    remetente = _email_from()
    reply_to = _email_reply_to()
    usar_tls = bool_env("SMTP_USE_TLS", True, logger=LOGGER, contexto="smtp")
    usar_ssl = bool_env("SMTP_USE_SSL", False, logger=LOGGER, contexto="smtp")

    if not host or not remetente:
        raise RuntimeError("SMTP_HOST e EMAIL_FROM sao obrigatorios para envio SMTP.")

    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = remetente
    mensagem["To"] = destino
    if reply_to:
        mensagem["Reply-To"] = reply_to
    mensagem.set_content(texto or "Abra este e-mail em um cliente com suporte a HTML.")
    mensagem.add_alternative(html, subtype="html")

    if usar_ssl:
        contexto_ssl = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, porta, timeout=15, context=contexto_ssl) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(mensagem)
        return {"ok": True, "provider": "smtp", "message_id": None}

    with smtplib.SMTP(host, porta, timeout=15) as smtp:
        smtp.ehlo()
        if usar_tls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(mensagem)
    return {"ok": True, "provider": "smtp", "message_id": None}


def _enviar_via_resend(destino, assunto, html, texto=None):
    api_key = _resend_api_key()
    remetente = _email_from()
    reply_to = _email_reply_to()

    if not api_key:
        raise RuntimeError("RESEND_API_KEY e obrigatoria para o provider resend.")
    if not remetente:
        raise RuntimeError("EMAIL_FROM e obrigatorio para o provider resend.")

    payload = {
        "from": remetente,
        "to": [destino],
        "subject": assunto,
        "html": html,
    }
    if texto:
        payload["text"] = texto
    if reply_to:
        payload["reply_to"] = reply_to

    LOGGER.info(
        "[EMAIL_SERVICE] Tentando envio via Resend destino=%s assunto=%s remetente_configurado=%s reply_to_configurado=%s",
        _mask_email(destino),
        assunto,
        bool(remetente),
        bool(reply_to),
    )
    resposta = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    if resposta.status_code >= 400:
        corpo_erro = (resposta.text or "").strip().replace("\n", " ")[:500]
        raise RuntimeError(f"Resend retornou HTTP {resposta.status_code}: {corpo_erro}")

    try:
        corpo = resposta.json()
    except ValueError:
        corpo = {}
    return {"ok": True, "provider": "resend", "message_id": corpo.get("id")}


def enviar_email(destino, assunto, html, texto=None, metadados=None):
    provider = _provider_normalizado()
    LOGGER.info(
        "[EMAIL_SERVICE] Provider configurado=%s destino=%s tipo=%s",
        provider,
        _mask_email(destino),
        (metadados or {}).get("tipo"),
    )
    if provider == "disabled":
        LOGGER.warning(
            "[EMAIL_SERVICE] Envio desabilitado destino=%s assunto=%s provider=%s",
            _mask_email(destino),
            assunto,
            provider,
        )
        return {"ok": False, "provider": provider, "erro": "Envio de e-mail desabilitado."}

    try:
        if provider == "log":
            resultado = _enviar_via_log(destino, assunto, html, texto=texto, metadados=metadados)
        elif provider == "resend":
            resultado = _enviar_via_resend(destino, assunto, html, texto=texto)
        elif provider == "smtp":
            resultado = _enviar_via_smtp(destino, assunto, html, texto=texto)
        else:
            raise RuntimeError(f"EMAIL_PROVIDER invalido: {provider}. Use resend, smtp ou log.")
        LOGGER.info(
            "[EMAIL_SERVICE] E-mail enviado destino=%s assunto=%s provider=%s message_id=%s",
            _mask_email(destino),
            assunto,
            resultado.get("provider"),
            resultado.get("message_id"),
        )
        return resultado
    except Exception as exc:
        LOGGER.exception(
            "[EMAIL_SERVICE] Falha ao enviar destino=%s assunto=%s provider=%s erro=%s",
            _mask_email(destino),
            assunto,
            provider,
            exc,
        )
        return {"ok": False, "provider": provider, "erro": str(exc)}


def enviar_email_verificacao(nome_destino, email_destino, link_confirmacao, expira_em):
    nome = (nome_destino or "Atleta").strip().split()[0]
    expira_label = expira_em.strftime("%d/%m/%Y %H:%M") if isinstance(expira_em, datetime) else str(expira_em)
    assunto = "Confirme seu e-mail no TriLab"
    texto = (
        f"{nome}, confirme seu e-mail para liberar o acesso ao TriLab.\n\n"
        f"Abra este link: {link_confirmacao}\n\n"
        f"Valido ate {expira_label}."
    )
    html = _email_layout_html(
        "Confirme seu e-mail",
        f"{nome}, confirme seu e-mail para liberar o acesso ao TriLab. O link abaixo fica valido ate {expira_label}.",
        cta_label="Confirmar e-mail",
        cta_link=link_confirmacao,
        rodape="Se voce nao criou essa conta, pode ignorar esta mensagem.",
    )
    return enviar_email(
        email_destino,
        assunto,
        html,
        texto=texto,
        metadados={"tipo": "verificacao_email"},
    )


def enviar_email_reset_senha(nome_destino, email_destino, link_reset, expira_em):
    nome = (nome_destino or "Atleta").strip().split()[0]
    expira_label = expira_em.strftime("%d/%m/%Y %H:%M") if isinstance(expira_em, datetime) else str(expira_em)
    assunto = "Redefina sua senha no TriLab"
    texto = (
        f"{nome}, recebemos um pedido para redefinir sua senha.\n\n"
        f"Abra este link: {link_reset}\n\n"
        f"Valido ate {expira_label}."
    )
    html = _email_layout_html(
        "Redefina sua senha",
        f"{nome}, recebemos um pedido para redefinir sua senha. Use o link abaixo ate {expira_label}.",
        cta_label="Redefinir senha",
        cta_link=link_reset,
        rodape="Se voce nao pediu essa alteracao, ignore este e-mail e sua senha continuara igual.",
    )
    return enviar_email(
        email_destino,
        assunto,
        html,
        texto=texto,
        metadados={"tipo": "reset_senha"},
    )
