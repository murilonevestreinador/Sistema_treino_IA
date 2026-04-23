import json
import logging

import tornado.web

from core.pagamentos_gateway import processar_webhook_asaas, validar_configuracao_asaas


LOGGER = logging.getLogger("trilab.asaas.webhook")


class AsaasWebhookHandler(tornado.web.RequestHandler):
    def check_xsrf_cookie(self):
        # Webhooks externos nao enviam o cookie XSRF usado pelo frontend do Streamlit.
        return

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        config = validar_configuracao_asaas()
        self.set_status(200 if config.get("ok") else 500)
        self.finish(
            json.dumps(
                {
                    "ok": bool(config.get("ok")),
                    "endpoint": "/webhooks/asaas",
                    "mensagem": "Endpoint de webhook Asaas disponivel." if config.get("ok") else config.get("mensagem"),
                },
                ensure_ascii=True,
            )
        )

    def post(self):
        try:
            payload = json.loads(self.request.body.decode("utf-8") or "{}")
        except Exception:
            LOGGER.warning("Webhook Asaas recebido com JSON invalido.")
            self.set_status(400)
            self.finish(json.dumps({"ok": False, "mensagem": "Payload JSON invalido."}, ensure_ascii=True))
            return

        headers = {chave: valor for chave, valor in self.request.headers.get_all()}
        LOGGER.info(
            "[ASAAS_WEBHOOK] Webhook Asaas recebido: evento=%s, payment_id=%s",
            (payload or {}).get("event"),
            ((payload or {}).get("payment") or {}).get("id"),
        )
        resultado = processar_webhook_asaas(payload, headers)
        LOGGER.info(
            "[ASAAS_WEBHOOK] Webhook Asaas finalizado: status_code=%s, ok=%s, mensagem=%s",
            resultado.get("status_code"),
            resultado.get("ok"),
            resultado.get("mensagem"),
        )
        self.set_status(int(resultado.get("status_code") or (200 if resultado.get("ok") else 500)))
        self.finish(json.dumps(resultado, ensure_ascii=True, default=str))
