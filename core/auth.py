import base64
from datetime import datetime
from pathlib import Path

import streamlit as st

from core.financeiro import criar_trial_assinatura
from core.permissoes import conta_ativa
from core.sessao_persistente import registrar_sessao_persistente
from core.treinador import buscar_convite_por_token, definir_vinculo_treinador_atleta
from core.ui import apply_global_styles, auth_card_end, auth_card_start
from core.usuarios import (
    autenticar_usuario,
    buscar_usuario_por_email,
    criar_usuario,
)


ASSETS_DIR = Path.cwd() / "assets"
LOGO_TRILAB_LADO = ASSETS_DIR / "logo_trilab_lado.png"
LOGO_TRILAB_CIMA = ASSETS_DIR / "logo_trilab_cima.png"


def _token_convite_da_url():
    try:
        return (st.query_params.get("convite") or "").strip()
    except Exception:
        return ""


def _limpar_convite_da_url():
    try:
        if "convite" in st.query_params:
            del st.query_params["convite"]
    except Exception:
        pass


def _capturar_convite_em_sessao():
    token_url = _token_convite_da_url()
    if token_url:
        st.session_state["convite_treinador_token"] = token_url

    token = (st.session_state.get("convite_treinador_token") or "").strip()
    if not token:
        return None

    convite = buscar_convite_por_token(token)
    if convite:
        return convite

    st.session_state.pop("convite_treinador_token", None)
    _limpar_convite_da_url()
    return None


def _logo_auth_html():
    if not LOGO_TRILAB_LADO.exists() or not LOGO_TRILAB_CIMA.exists():
        return """
        <div class="auth-brand">
            <h1>TriLab TREINAMENTO</h1>
            <p>Acesse sua conta ou crie um novo acesso em poucos passos.</p>
        </div>
        """

    logo_lado = base64.b64encode(LOGO_TRILAB_LADO.read_bytes()).decode("ascii")
    logo_cima = base64.b64encode(LOGO_TRILAB_CIMA.read_bytes()).decode("ascii")
    return f"""
    <div class="auth-brand">
        <img class="auth-brand-logo auth-brand-logo-desktop" src="data:image/png;base64,{logo_lado}" alt="Logo TriLab horizontal">
        <img class="auth-brand-logo auth-brand-logo-mobile" src="data:image/png;base64,{logo_cima}" alt="Logo TriLab vertical">
        <p>Acesse sua conta ou crie um novo acesso em poucos passos.</p>
    </div>
    """


def tela_login():
    _capturar_convite_em_sessao()
    apply_global_styles()
    st.markdown(_logo_auth_html(), unsafe_allow_html=True)

    aba_entrar, aba_cadastro, aba_recuperar = st.tabs(["Entrar", "Criar conta", "Esqueci a senha"])

    with aba_entrar:
        auth_card_start("Entrar", "Use seu e-mail e senha para acessar o sistema.")
        _tela_login_tab()
        auth_card_end()

    with aba_cadastro:
        auth_card_start("Criar conta", "Cadastre-se para comecar seu periodo de teste.")
        _tela_cadastro_tab()
        auth_card_end()

    with aba_recuperar:
        auth_card_start("Esqueci a senha", "Recupere o acesso a sua conta.")
        _tela_recuperacao_tab()
        auth_card_end()


def _tela_login_tab():
    with st.form("form_login_auth"):
        email = st.text_input("Email", key="login_email", placeholder="voce@exemplo.com")
        senha = st.text_input("Senha", type="password", key="login_senha", placeholder="Digite sua senha")
        enviar = st.form_submit_button("Entrar", use_container_width=True)

    if enviar:
        if not email.strip() or not senha.strip():
            st.warning("Preencha e-mail e senha.")
            return

        usuario = autenticar_usuario(email, senha)
        if not usuario:
            st.warning("E-mail ou senha incorretos.")
            return
        if not conta_ativa(usuario):
            st.warning("Sua conta esta inativa, suspensa ou cancelada. Fale com o suporte.")
            return

        convite_token = (st.session_state.get("convite_treinador_token") or "").strip()
        if convite_token and usuario.get("tipo_usuario") != "atleta":
            st.warning("Este link de convite \u00e9 v\u00e1lido apenas para atletas.")
            st.session_state.pop("convite_treinador_token", None)
            _limpar_convite_da_url()
        elif convite_token:
            st.session_state["convite_treinador_resposta_pendente"] = convite_token

        st.session_state["usuario"] = usuario
        registrar_sessao_persistente(usuario["id"])
        st.session_state.setdefault("mostrar_overview", False)
        st.rerun()

def _tela_cadastro_tab():
    tipo_usuario = st.selectbox("Perfil", ["atleta", "treinador"], key="cad_tipo")

    with st.form("form_cadastro_auth"):
        nome = st.text_input("Nome", key="cad_nome", placeholder="Seu nome completo")
        email = st.text_input("Email", key="cad_email", placeholder="voce@exemplo.com")
        senha = st.text_input("Senha", type="password", key="cad_senha", placeholder="Crie uma senha")
        sexo = st.selectbox("Sexo", ["masculino", "feminino", "outro"], key="cad_sexo")
        objetivo = "performance"
        if tipo_usuario == "atleta":
            objetivo = st.selectbox(
                "Objetivo inicial",
                ["performance", "saude", "completar prova"],
                key="cad_objetivo",
            )

        aceitou_termos = st.checkbox("Li e aceito os [Termos de Uso](/termos)", key="cad_aceitou_termos")
        aceitou_privacidade = st.checkbox(
            "Autorizo o tratamento dos meus dados conforme a [Politica de Privacidade](/privacidade)",
            key="cad_aceitou_privacidade",
        )
        enviar = st.form_submit_button("Criar conta", use_container_width=True)

    if not enviar:
        return

    if not nome.strip() or not email.strip() or not senha.strip():
        st.warning("Preencha nome, e-mail e senha.")
        return

    if not aceitou_termos or not aceitou_privacidade:
        st.warning("Aceite os termos e a politica para continuar.")
        return

    if buscar_usuario_por_email(email):
        if st.session_state.get("convite_treinador_token"):
            st.warning("Ja existe um usuario com este e-mail. Faca login por este link para decidir sobre o vinculo.")
        else:
            st.warning("Ja existe um usuario com este e-mail.")
        return

    try:
        usuario_id = criar_usuario(
            {
                "nome": nome,
                "email": email,
                "senha": senha,
                "sexo": sexo,
                "tipo_usuario": tipo_usuario,
                "objetivo": objetivo,
                "onboarding_completo": 0 if tipo_usuario == "atleta" else 1,
                "aceitou_termos": 1,
                "aceitou_privacidade": 1,
                "data_consentimento": datetime.now().isoformat(timespec="seconds"),
            }
        )
        criar_trial_assinatura(usuario_id, tipo_usuario)
    except Exception as exc:
        st.warning(f"Erro ao criar usuario: {exc}")
        return

    convite_token = (st.session_state.get("convite_treinador_token") or "").strip()
    convite = buscar_convite_por_token(convite_token) if convite_token and tipo_usuario == "atleta" else None
    if convite:
        definir_vinculo_treinador_atleta(convite["treinador_id"], usuario_id, status="ativo")
        st.success(f"Conta criada e vinculada automaticamente a {convite['treinador_nome']}.")
        st.session_state.pop("convite_treinador_token", None)
        st.session_state.pop("convite_treinador_resposta_pendente", None)
        _limpar_convite_da_url()
    else:
        st.success("Conta criada com sucesso.")

    st.info("Use a aba 'Entrar' para acessar.")


def _tela_recuperacao_tab():
    with st.form("form_recuperacao_auth"):
        email = st.text_input("Email", key="rec_email", placeholder="voce@exemplo.com")
        enviar = st.form_submit_button("Enviar link", use_container_width=True)

    if not enviar:
        return

    if not email.strip():
        st.warning("Informe o e-mail da conta.")
        return

    st.info("Fluxo em construcao.")
    print(f"[TriLab] Recuperacao solicitada para: {email.strip().lower()}")
