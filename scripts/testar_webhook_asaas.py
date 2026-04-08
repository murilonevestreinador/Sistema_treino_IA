import argparse
import json
import os
import sys

import requests


DEFAULT_URL = "https://app.trilabtreinamento.com/webhooks/asaas"
PAYLOAD_TESTE = {
    "manual_test": True,
    "event": "PAYMENT_RECEIVED",
    "payment": {
        "id": "pay_test_123",
        "customer": "cus_test_123",
        "value": 39.90,
        "status": "RECEIVED",
    },
}


def _parse_args():
    parser = argparse.ArgumentParser(description="Teste manual do webhook Asaas.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL do endpoint do webhook.")
    parser.add_argument(
        "--modo",
        choices=("correto", "incorreto"),
        default="correto",
        help="Usa o token correto (env/--token) ou um token propositalmente invalido.",
    )
    parser.add_argument("--token", default="", help="Token manual para sobrescrever ASAAS_WEBHOOK_TOKEN.")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout da requisicao em segundos.")
    return parser.parse_args()


def _resolver_token(args):
    if args.modo == "incorreto":
        return "token-incorreto-teste"
    token = (args.token or os.getenv("ASAAS_WEBHOOK_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Informe --token ou defina ASAAS_WEBHOOK_TOKEN para o modo correto.")
    return token


def main():
    args = _parse_args()
    token = _resolver_token(args)

    headers = {
        "Content-Type": "application/json",
        "asaas-access-token": token,
    }

    print(f"URL: {args.url}")
    print(f"Modo: {args.modo}")
    print(f"Token enviado: {'*' * 8 if args.modo == 'correto' else token}")
    print("Payload:")
    print(json.dumps(PAYLOAD_TESTE, ensure_ascii=True, indent=2))

    try:
        response = requests.post(
            args.url,
            headers=headers,
            json=PAYLOAD_TESTE,
            timeout=args.timeout,
        )
    except requests.RequestException as exc:
        print(f"Erro de requisicao: {exc}")
        return 1

    print(f"Status code: {response.status_code}")
    try:
        body = response.json()
        print("Resposta JSON:")
        print(json.dumps(body, ensure_ascii=True, indent=2))
    except ValueError:
        print("Resposta texto:")
        print(response.text)

    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
