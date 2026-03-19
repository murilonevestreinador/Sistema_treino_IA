import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.usuarios import buscar_usuario_por_email, atualizar_tipo_usuario  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Promove um usuario existente para admin a partir do e-mail."
    )
    parser.add_argument("email", help="E-mail da conta que deve virar admin")
    args = parser.parse_args()

    email = (args.email or "").strip().lower()
    if not email:
        print("Informe um e-mail valido.")
        raise SystemExit(1)

    usuario = buscar_usuario_por_email(email)
    if not usuario:
        print(f"Usuario nao encontrado: {email}")
        raise SystemExit(1)

    usuario_atualizado = atualizar_tipo_usuario(usuario["id"], "admin")
    print(
        "Conta promovida com sucesso:",
        f"id={usuario_atualizado['id']}",
        f"email={usuario_atualizado['email']}",
        f"tipo={usuario_atualizado['tipo_usuario']}",
        f"is_admin={usuario_atualizado['is_admin']}",
    )


if __name__ == "__main__":
    main()
