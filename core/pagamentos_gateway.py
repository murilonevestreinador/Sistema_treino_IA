from datetime import datetime


def criar_assinatura_gateway(usuario, plano):
    # No futuro, integrar com Asaas via API e webhook.
    referencia = f"manual-{usuario['id']}-{plano['codigo']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {
        "status": "ativa",
        "gateway_reference": referencia,
        "gateway": "manual",
    }


def cancelar_assinatura_gateway(gateway_reference):
    # No futuro, integrar com Asaas via API e webhook.
    return {
        "ok": True,
        "gateway_reference": gateway_reference,
        "gateway": "manual",
    }
