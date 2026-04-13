import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.email_service import (  # noqa: E402
    enviar_email_reset_senha,
    enviar_email_verificacao,
    montar_link_reset_senha,
    montar_link_verificacao_email,
    resolver_url_base_publica,
)


def main():
    parser = argparse.ArgumentParser(description="Envia um e-mail transacional de teste usando a configuracao atual.")
    parser.add_argument("email", help="Endereco de destino para o teste")
    parser.add_argument(
        "--tipo",
        choices=["verificacao", "reset"],
        default="verificacao",
        help="Tipo de template a enviar",
    )
    parser.add_argument("--nome", default="Teste", help="Primeiro nome exibido no template")
    args = parser.parse_args()

    email = (args.email or "").strip().lower()
    if not email or "@" not in email:
        print("Informe um e-mail de destino valido.")
        raise SystemExit(1)

    base_url = resolver_url_base_publica(obrigatorio=False)
    expira_em = datetime.now() + timedelta(hours=1)

    if args.tipo == "reset":
        link = montar_link_reset_senha("teste-reset-manual", base_url=base_url)
        resultado = enviar_email_reset_senha(args.nome, email, link, expira_em)
    else:
        link = montar_link_verificacao_email("teste-verificacao-manual", base_url=base_url)
        resultado = enviar_email_verificacao(args.nome, email, link, expira_em)

    print(f"base_url={base_url}")
    print(f"tipo={args.tipo}")
    print(f"email={email}")
    print(f"ok={resultado.get('ok')}")
    print(f"provider={resultado.get('provider')}")
    print(f"message_id={resultado.get('message_id')}")
    if not resultado.get("ok"):
        print(f"erro={resultado.get('erro')}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
