import os
from pathlib import Path

from tornado.routing import PathMatches, Rule

from core.webhooks_asaas import AsaasWebhookHandler


def _registrar_rota_webhook_streamlit():
    from streamlit.web.server import server as st_server

    if getattr(st_server.Server, "_trilab_asaas_webhook_patch", False):
        return

    original_create_app = st_server.Server._create_app

    def patched_create_app(self):
        app = original_create_app(self)
        regex = st_server.make_url_path_regex(
            st_server.config.get_option("server.baseUrlPath"),
            "webhooks/asaas",
            trailing_slash="optional",
        )
        regra = Rule(PathMatches(regex), AsaasWebhookHandler)

        regras = list(app.wildcard_router.rules)
        if not any(getattr(item.target, "__name__", "") == "AsaasWebhookHandler" for item in regras):
            regras.insert(0, regra)
            app.wildcard_router.rules[:] = regras
        return app

    st_server.Server._create_app = patched_create_app
    st_server.Server._trilab_asaas_webhook_patch = True


def _streamlit_flag_options():
    porta = int((os.getenv("PORT") or "8501").strip())
    return {
        "server_port": porta,
        "server_address": "0.0.0.0",
        "server_headless": True,
        "browser_gatherUsageStats": False,
    }


def main():
    app_path = Path(__file__).with_name("app.py").resolve()
    if not app_path.exists():
        raise FileNotFoundError(f"Arquivo principal nao encontrado: {app_path}")

    _registrar_rota_webhook_streamlit()

    from streamlit.web import bootstrap

    bootstrap.run(
        str(app_path),
        False,
        [],
        _streamlit_flag_options(),
    )


if __name__ == "__main__":
    main()
