import base64
import logging
from datetime import datetime
from pathlib import Path

import streamlit as st

from core.email_verificacao import avaliar_email_verificacao_obrigatoria, email_verificacao_obrigatoria
from core.email_tokens import (
    TOKEN_TIPO_RESET_SENHA,
    atualizar_email_pendente_verificacao,
    confirmar_email_por_token,
    inspecionar_token_email,
    redefinir_senha_por_token,
    solicitar_reset_senha_por_email,
    solicitar_verificacao_email,
)
from core.email_service import email_envio_habilitado
from core.financeiro import criar_trial_assinatura
from core.lancamento import cadastro_publico_permite_treinador
from core.objetivos import (
    OBJETIVO_PADRAO_FRONT,
    objetivos_expostos_no_front,
    rotulo_objetivo_front,
)
from core.permissoes import conta_ativa, email_verificado
from core.sessao_persistente import (
    browser_key_disponivel,
    capturar_browser_key_da_url,
    diagnosticar_sessao_persistente_atual,
    garantir_sessao_persistente_atual,
    injetar_bridge_navegador,
    preparar_rotacao_browser_key,
    registrar_sessao_persistente,
    restaurar_usuario_persistente,
    revogar_sessao_persistente_atual,
    tocar_sessao_persistente_atual,
)
from core.treinador import buscar_convite_por_token, definir_vinculo_treinador_atleta
from core.ui import apply_global_styles, auth_card_end, auth_card_start
from core.usuarios import (
    autenticar_usuario,
    buscar_usuario_por_email,
    buscar_usuario_por_id,
    criar_usuario,
    tentar_bootstrap_primeiro_admin,
    validar_cpf,
    validar_cref,
    validar_telefone,
)


LOGGER = logging.getLogger("trilab.auth")
ADMIN_DIAGNOSTIC_EMAIL = "murilo_nevescontato@hotmail.com"
ASSETS_DIR = Path.cwd() / "assets"
LOGO_TRILAB_LADO = ASSETS_DIR / "logo_trilab_lado.png"
LOGO_TRILAB_CIMA = ASSETS_DIR / "logo_trilab_cima.png"
CHECKOUT_PAGE = "pages/pagamento_manual.py"
AUTH_ACTION_PARAM = "auth_action"
AUTH_TOKEN_PARAM = "token"


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


def _email_admin_diagnostico(email):
    return (email or "").strip().lower() == ADMIN_DIAGNOSTIC_EMAIL


def _usuario_admin_diagnostico(usuario):
    return bool(usuario and _email_admin_diagnostico(usuario.get("email")))


def encerrar_sessao_atual(destino_modo="Login"):
    usuario = st.session_state.get("usuario")
    if usuario:
        revogar_sessao_persistente_atual(usuario.get("id"))
    preparar_rotacao_browser_key()
    for chave in list(st.session_state.keys()):
        if chave == "browser_key_reset_nonce":
            continue
        del st.session_state[chave]
    if destino_modo:
        st.session_state["auth_modo"] = destino_modo
    _abrir_app(destino_modo)


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


def _auth_action_da_url():
    try:
        return (st.query_params.get(AUTH_ACTION_PARAM) or "").strip().lower()
    except Exception:
        return ""


def _auth_token_da_url():
    try:
        return (st.query_params.get(AUTH_TOKEN_PARAM) or "").strip()
    except Exception:
        return ""


def limpar_auth_query_params():
    try:
        if AUTH_ACTION_PARAM in st.query_params:
            del st.query_params[AUTH_ACTION_PARAM]
        if AUTH_TOKEN_PARAM in st.query_params:
            del st.query_params[AUTH_TOKEN_PARAM]
    except Exception:
        pass


def _abrir_app(modo=None):
    if modo:
        st.session_state["auth_modo"] = modo
    try:
        st.switch_page("app.py")
    except Exception:
        st.info("Abra a pagina principal do app para continuar.")


def obter_usuario_logado():
    capturar_browser_key_da_url()
    usuario = st.session_state.get("usuario")
    if usuario is None:
        usuario = restaurar_usuario_persistente()
        if usuario:
            st.session_state["usuario"] = usuario
            st.session_state["usuario_origem"] = "sessao_persistente"
    return usuario


def garantir_usuario_em_pagina(chave_contexto, exigir_email_confirmado=False, permitir_publico=False):
    injetar_bridge_navegador()
    capturar_browser_key_da_url()
    usuario = obter_usuario_logado()
    if usuario is None:
        if permitir_publico:
            return None
        st.warning("Voce precisa estar logado para acessar esta pagina.")
        if st.button("Ir para login", use_container_width=True, key=f"{chave_contexto}_ir_login"):
            _abrir_app("Login")
        st.stop()

    if not garantir_sessao_persistente_atual(usuario, contexto=chave_contexto):
        st.session_state["usuario"] = None
        st.warning("Sua sessao expirou. Entre novamente para continuar.")
        if st.button("Entrar novamente", use_container_width=True, key=f"{chave_contexto}_sessao_expirada"):
            _abrir_app("Login")
        st.stop()

    tocar_sessao_persistente_atual(usuario["id"])
    usuario = buscar_usuario_por_id(usuario["id"]) or usuario
    st.session_state["usuario"] = usuario

    if not conta_ativa(usuario):
        st.error("Sua conta esta inativa, suspensa ou cancelada. Fale com o suporte.")
        if st.button("Voltar para o app", use_container_width=True, key=f"{chave_contexto}_conta_inativa"):
            _abrir_app()
        st.stop()

    avaliacao_email = avaliar_email_verificacao_obrigatoria(usuario, contexto=f"{chave_contexto}:page_gate")
    if exigir_email_confirmado and avaliacao_email.get("obrigatoria"):
        LOGGER.warning(
            "[EMAIL_PENDING] Pagina redirecionada para pendencia email=%s usuario_id=%s contexto=%s motivo=%s",
            usuario.get("email"),
            usuario.get("id"),
            chave_contexto,
            avaliacao_email.get("motivo"),
        )
        render_bloqueio_email_pendente(usuario)
        st.stop()

    return usuario


def _headers_requisicao():
    try:
        headers = getattr(st.context, "headers", {}) or {}
    except Exception:
        headers = {}
    return headers


def _ip_requisicao():
    headers = _headers_requisicao()
    candidatos = [
        headers.get("x-forwarded-for"),
        headers.get("X-Forwarded-For"),
        headers.get("x-real-ip"),
        headers.get("X-Real-Ip"),
    ]
    for valor in candidatos:
        if valor:
            return str(valor).split(",")[0].strip()[:200]
    return ""


def _user_agent_requisicao():
    headers = _headers_requisicao()
    for chave in ("user-agent", "User-Agent"):
        valor = headers.get(chave)
        if valor:
            return str(valor)[:500]
    return ""


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


def _tem_checkout_pendente():
    return bool((st.session_state.get("plano_checkout") or "").strip() or st.session_state.get("checkout_id"))


def _ir_para_checkout_se_pendente():
    if not _tem_checkout_pendente():
        return False
    try:
        st.switch_page(CHECKOUT_PAGE)
    except Exception:
        st.info("Abra a pagina de checkout no menu lateral para continuar sua assinatura.")
    return True


def _aplicar_auth_mode():
    auth_modo = (st.session_state.get("auth_modo") or "").strip().lower()
    if auth_modo == "cadastro":
        st.caption("Finalize seu cadastro para continuar para o checkout.")
    elif auth_modo == "login":
        st.caption("Entre na sua conta para continuar para o checkout.")


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


def _mensagem_email_pendente():
    notice = st.session_state.pop("email_pending_notice", None)
    if not notice:
        return
    status = notice.get("status")
    mensagem = notice.get("mensagem")
    if not mensagem:
        return
    if status in {"envio_falhou", "rate_limited", "erro"}:
        st.warning(mensagem)
    elif status in {"confirmado", "ja_verificado"}:
        st.success(mensagem)
    else:
        st.info(mensagem)


def _registrar_notice_email_pendente(resultado=None, mensagem_padrao=None):
    resultado = resultado or {}
    mensagem = resultado.get("mensagem") or mensagem_padrao
    if not mensagem:
        return
    st.session_state["email_pending_notice"] = {
        "status": resultado.get("status") or "info",
        "mensagem": mensagem,
    }


def render_aviso_email_pendente_passivo(usuario):
    if not usuario or email_verificado(usuario):
        st.session_state.pop("email_pending_notice", None)
        return

    notice = st.session_state.pop("email_pending_notice", None)
    if not notice or not notice.get("mensagem"):
        return

    status = notice.get("status")
    mensagem = notice.get("mensagem")
    if status in {"envio_falhou", "rate_limited", "erro"}:
        st.warning(mensagem)
    else:
        st.info(mensagem)
    avaliacao_email = avaliar_email_verificacao_obrigatoria(usuario, contexto="app_passive_notice")
    if avaliacao_email.get("obrigatoria"):
        st.caption("Sua conta ainda precisa confirmar o e-mail antes do acesso completo.")
    else:
        st.caption("O acesso continua normal para esta conta. Se precisar, voce pode reenviar ou corrigir o e-mail em Meu perfil.")


def tela_login():
    _capturar_convite_em_sessao()
    apply_global_styles()
    st.markdown(_logo_auth_html(), unsafe_allow_html=True)
    _aplicar_auth_mode()

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

    if not enviar:
        return
    if not email.strip() or not senha.strip():
        st.warning("Preencha e-mail e senha.")
        return

    email_normalizado = email.strip().lower()
    LOGGER.info(
        "[AUTH_FLOW] Tentativa de login email=%s browser_key_presente=%s",
        email_normalizado,
        browser_key_disponivel(),
    )
    if _email_admin_diagnostico(email_normalizado):
        LOGGER.warning(
            "[ADMIN_AUTH] Tentativa de login admin email=%s browser_key_presente=%s",
            email_normalizado,
            browser_key_disponivel(),
        )

    usuario = autenticar_usuario(email, senha)
    if not usuario:
        LOGGER.warning("[LOGIN_BLOCK] Login bloqueado email=%s motivo=credenciais_invalidas", email_normalizado)
        if _email_admin_diagnostico(email_normalizado):
            LOGGER.warning("[ADMIN_AUTH] Falha de autenticacao admin email=%s motivo=credenciais_invalidas", email_normalizado)
        st.warning("E-mail ou senha incorretos.")
        return
    if not conta_ativa(usuario):
        LOGGER.warning(
            "[LOGIN_BLOCK] Login bloqueado email=%s usuario_id=%s motivo=conta_inativa status_conta=%s",
            usuario.get("email"),
            usuario.get("id"),
            usuario.get("status_conta"),
        )
        if _usuario_admin_diagnostico(usuario):
            LOGGER.warning(
                "[ADMIN_AUTH] Login admin bloqueado por status_conta email=%s usuario_id=%s status_conta=%s",
                usuario.get("email"),
                usuario.get("id"),
                usuario.get("status_conta"),
            )
        st.warning("Sua conta esta inativa, suspensa ou cancelada. Fale com o suporte.")
        return

    usuario = tentar_bootstrap_primeiro_admin(usuario["id"], usuario["email"])
    if _usuario_admin_diagnostico(usuario):
        LOGGER.warning(
            "[ADMIN_AUTH] Admin autenticado email=%s usuario_id=%s tipo_usuario=%s is_admin=%s status_conta=%s email_verificado=%s",
            usuario.get("email"),
            usuario.get("id"),
            usuario.get("tipo_usuario"),
            usuario.get("is_admin"),
            usuario.get("status_conta"),
            usuario.get("email_verificado"),
        )
    LOGGER.info(
        "[AUTH_FLOW] Credenciais validas email=%s usuario_id=%s tipo_usuario=%s status_conta=%s email_verificado=%s",
        usuario.get("email"),
        usuario.get("id"),
        usuario.get("tipo_usuario"),
        usuario.get("status_conta"),
        usuario.get("email_verificado"),
    )

    convite_token = (st.session_state.get("convite_treinador_token") or "").strip()
    if convite_token and usuario.get("tipo_usuario") != "atleta":
        st.warning("Este link de convite e valido apenas para atletas.")
        st.session_state.pop("convite_treinador_token", None)
        _limpar_convite_da_url()
    elif convite_token:
        st.session_state["convite_treinador_resposta_pendente"] = convite_token

    sessao_registrada = registrar_sessao_persistente(usuario["id"], usuario=usuario, contexto="login")
    if not sessao_registrada:
        diagnostico = diagnosticar_sessao_persistente_atual(usuario.get("id"))
        LOGGER.warning(
            "[SESSION_PERSISTENCE_ERROR] Login seguira com sessao basica email=%s usuario_id=%s diagnostico=%s",
            usuario.get("email"),
            usuario.get("id"),
            diagnostico,
        )
        if _usuario_admin_diagnostico(usuario):
            LOGGER.warning(
                "[ADMIN_SESSION] Login admin sem sessao persistente email=%s usuario_id=%s diagnostico=%s",
                usuario.get("email"),
                usuario.get("id"),
                diagnostico,
            )

    st.session_state["usuario"] = usuario
    st.session_state["usuario_origem"] = "credenciais"
    LOGGER.info(
        "[AUTH_FLOW] Sessao basica criada email=%s usuario_id=%s sessao_persistente=%s",
        usuario.get("email"),
        usuario.get("id"),
        sessao_registrada,
    )
    st.session_state.setdefault("mostrar_overview", False)
    avaliacao_email = avaliar_email_verificacao_obrigatoria(usuario, contexto="login_success")
    if avaliacao_email.get("obrigatoria"):
        LOGGER.info(
            "[EMAIL_PENDING] Login autenticado com pendencia usuario_id=%s email=%s tipo_usuario=%s motivo=%s",
            usuario.get("id"),
            usuario.get("email"),
            usuario.get("tipo_usuario"),
            avaliacao_email.get("motivo"),
        )
        st.session_state["email_pending_notice"] = {
            "status": "pendente",
            "mensagem": "Seu login foi concluido. Para liberar o acesso completo, confirme o link enviado para o seu e-mail.",
        }
    elif _ir_para_checkout_se_pendente():
        return
    st.rerun()


def _tela_cadastro_tab():
    if cadastro_publico_permite_treinador():
        tipo_usuario = st.selectbox("Perfil", ["atleta", "treinador"], key="cad_tipo")
    else:
        tipo_usuario = "atleta"
        st.caption("Perfil disponivel neste lancamento: atleta.")

    with st.form("form_cadastro_auth"):
        nome = st.text_input("Nome", key="cad_nome", placeholder="Seu nome completo")
        email = st.text_input("Email", key="cad_email", placeholder="voce@exemplo.com")
        cpf = st.text_input("CPF", key="cad_cpf", placeholder="123.456.789-09")
        telefone = st.text_input("Telefone", key="cad_telefone", placeholder="(16) 99999-9999")
        cref = ""
        if tipo_usuario == "treinador":
            cref = st.text_input("CREF", key="cad_cref", placeholder="Ex.: 123456-G/SP")
        senha = st.text_input("Senha", type="password", key="cad_senha", placeholder="Crie uma senha")
        sexo = st.selectbox("Sexo", ["masculino", "feminino", "outro"], key="cad_sexo")
        objetivo = OBJETIVO_PADRAO_FRONT
        if tipo_usuario == "atleta":
            objetivos_front = objetivos_expostos_no_front()
            objetivo = st.selectbox(
                "Objetivo inicial",
                objetivos_front,
                format_func=rotulo_objetivo_front,
                disabled=len(objetivos_front) == 1,
                key="cad_objetivo",
            )

        aceitou_termos = st.checkbox("Li e aceito os [Termos de Uso](/termos)", key="cad_aceitou_termos")
        aceitou_privacidade = st.checkbox(
            "Autorizo o tratamento dos meus dados conforme a [Politica de Privacidade](/privacidade)",
            key="cad_aceitou_privacidade",
        )
        if not cadastro_publico_permite_treinador():
            st.caption("No lancamento inicial, o cadastro publico esta disponivel apenas para atletas. Treinadores ja cadastrados continuam acessando normalmente.")
        enviar = st.form_submit_button("Criar conta", use_container_width=True)

    if not enviar:
        return

    if not cadastro_publico_permite_treinador():
        tipo_usuario = "atleta"

    campos_obrigatorios = [nome.strip(), email.strip(), senha.strip(), cpf.strip(), telefone.strip()]
    if tipo_usuario == "treinador":
        campos_obrigatorios.append(cref.strip())
    if not all(campos_obrigatorios):
        st.warning("Preencha nome, e-mail, CPF, telefone e senha." + (" O CREF e obrigatorio para treinador." if tipo_usuario == "treinador" else ""))
        return

    if not aceitou_termos or not aceitou_privacidade:
        st.warning("Aceite os termos e a politica para continuar.")
        return

    cpf_ok, cpf_msg = validar_cpf(cpf)
    if not cpf_ok:
        st.warning(cpf_msg)
        return

    telefone_ok, telefone_msg = validar_telefone(telefone)
    if not telefone_ok:
        st.warning(telefone_msg)
        return

    if tipo_usuario == "treinador":
        cref_ok, cref_msg = validar_cref(cref, obrigatorio=True)
        if not cref_ok:
            st.warning(cref_msg)
            return
    else:
        cref_msg = None

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
                "cpf": cpf_msg,
                "telefone": telefone_msg,
                "cref": cref_msg,
                "senha": senha,
                "sexo": sexo,
                "tipo_usuario": tipo_usuario,
                "objetivo": objetivo,
                "onboarding_completo": 0 if tipo_usuario == "atleta" else 1,
                "aceitou_termos": 1,
                "aceitou_privacidade": 1,
                "data_consentimento": datetime.now().isoformat(timespec="seconds"),
                "email_verificado": 0,
                "email_verificado_em": None,
            }
        )
        criar_trial_assinatura(usuario_id, tipo_usuario)
    except Exception as exc:
        LOGGER.exception("[EMAIL_VERIFY] Falha ao criar usuario email=%s erro=%s", email.strip().lower(), exc)
        st.warning("Nao foi possivel concluir o cadastro agora. Tente novamente em alguns instantes.")
        return

    usuario = buscar_usuario_por_id(usuario_id)
    LOGGER.info(
        "[EMAIL_VERIFY] Conta criada com e-mail pendente usuario_id=%s email=%s tipo_usuario=%s",
        usuario_id,
        _mask_email(email),
        tipo_usuario,
    )
    convite_token = (st.session_state.get("convite_treinador_token") or "").strip()
    convite = buscar_convite_por_token(convite_token) if convite_token and tipo_usuario == "atleta" else None
    if convite:
        definir_vinculo_treinador_atleta(convite["treinador_id"], usuario_id, status="ativo")
        st.session_state.pop("convite_treinador_token", None)
        st.session_state.pop("convite_treinador_resposta_pendente", None)
        _limpar_convite_da_url()

    resultado_email = None
    if email_envio_habilitado():
        try:
            LOGGER.info(
                "[EMAIL_VERIFY_FLOW] Disparando verificacao inicial apos cadastro usuario_id=%s email=%s",
                usuario_id,
                _mask_email(email),
            )
            resultado_email = solicitar_verificacao_email(
                usuario_id,
                criado_ip=_ip_requisicao(),
                criado_user_agent=_user_agent_requisicao(),
                origem="cadastro",
            )
        except Exception as exc:
            LOGGER.exception(
                "[EMAIL_VERIFY_FLOW] Falha ao solicitar verificacao inicial usuario_id=%s erro=%s",
                usuario_id,
                exc,
            )
            resultado_email = {
                "status": "envio_falhou",
                "mensagem": "Conta criada. Nao conseguimos enviar o e-mail agora, mas voce pode reenviar na proxima tela.",
            }
    else:
        LOGGER.info(
            "[EMAIL_VERIFY_FLOW] Envio automatico de verificacao nao executado usuario_id=%s motivo=email_disabled",
            usuario_id,
        )
        resultado_email = {
            "status": "envio_desabilitado",
            "mensagem": "Conta criada com sucesso. O envio de e-mail esta indisponivel no momento, mas seu acesso continua normal.",
        }
    sessao_registrada = registrar_sessao_persistente(usuario["id"], usuario=usuario, contexto="cadastro")
    if not sessao_registrada:
        LOGGER.warning(
            "[SESSION_PERSISTENCE_ERROR] Cadastro seguira com sessao basica email=%s usuario_id=%s diagnostico=%s",
            usuario.get("email"),
            usuario.get("id"),
            diagnosticar_sessao_persistente_atual(usuario.get("id")),
        )

    st.session_state["usuario"] = usuario
    st.session_state["usuario_origem"] = "cadastro"
    LOGGER.info(
        "[AUTH_FLOW] Sessao basica criada apos cadastro email=%s usuario_id=%s sessao_persistente=%s",
        usuario.get("email"),
        usuario.get("id"),
        sessao_registrada,
    )
    st.session_state.setdefault("mostrar_overview", False)
    if not email_verificado(usuario):
        _registrar_notice_email_pendente(
            resultado_email,
            mensagem_padrao="Conta criada. Enviamos um link para confirmar seu e-mail.",
        )
    st.rerun()


def _tela_recuperacao_tab():
    with st.form("form_recuperacao_auth"):
        email = st.text_input("Email", key="rec_email", placeholder="voce@exemplo.com")
        enviar = st.form_submit_button("Enviar link", use_container_width=True)

    if not enviar:
        return
    if not email.strip():
        st.warning("Informe o e-mail da conta.")
        return

    try:
        resultado = solicitar_reset_senha_por_email(
            email,
            criado_ip=_ip_requisicao(),
            criado_user_agent=_user_agent_requisicao(),
        )
        LOGGER.info("[EMAIL_RESET] Solicitacao publica recebida status=%s", resultado.get("status"))
    except Exception as exc:
        LOGGER.exception("[EMAIL_RESET] Falha ao iniciar recuperacao por e-mail erro=%s", exc)
        resultado = {
            "mensagem": "Se existir uma conta com esse e-mail, enviaremos as instrucoes para redefinir a senha.",
        }
    st.info(resultado.get("mensagem") or "Se existir uma conta com esse e-mail, enviaremos as instrucoes para redefinir a senha.")


def _botao_continuar_pos_auth(label="Voltar para entrar"):
    if st.button(label, use_container_width=True):
        limpar_auth_query_params()
        _abrir_app("Login")


def _render_auth_shell(titulo, subtitulo, renderizador):
    apply_global_styles()
    st.markdown(_logo_auth_html(), unsafe_allow_html=True)
    auth_card_start(titulo, subtitulo)
    renderizador()
    auth_card_end()


def render_pagina_verificacao_email():
    _render_auth_shell("Confirmacao de e-mail", "Validando o link enviado para sua conta.", _render_confirmacao_email_publica)


def render_pagina_reset_senha():
    _render_auth_shell("Redefinir senha", "Use o link do e-mail para criar uma nova senha.", _render_reset_publico)


def render_fluxo_publico_auth():
    action = _auth_action_da_url()
    if action not in {"verify_email", "reset_password", "forgot_password"}:
        return False

    if action == "verify_email":
        render_pagina_verificacao_email()
        return True

    if action == "forgot_password":
        render_pagina_esqueci_senha()
        return True

    render_pagina_reset_senha()
    return True


def render_pagina_esqueci_senha():
    _render_auth_shell(
        "Esqueci a senha",
        "Informe seu e-mail para receber um link de redefinicao.",
        _render_solicitacao_reset_publico,
    )


def _render_confirmacao_email_publica():
    token = _auth_token_da_url()
    if not token:
        st.error("Link invalido.")
        _botao_continuar_pos_auth()
        return

    try:
        resultado = confirmar_email_por_token(token)
    except Exception as exc:
        LOGGER.exception("[EMAIL_VERIFY] Falha ao confirmar token publico erro=%s", exc)
        resultado = {
            "ok": False,
            "mensagem": "Nao foi possivel validar este link agora. Tente reenviar a confirmacao em alguns instantes.",
        }
    if resultado.get("ok"):
        usuario_resultado = resultado.get("usuario")
        usuario_sessao = st.session_state.get("usuario")
        if usuario_sessao and usuario_resultado and int(usuario_sessao.get("id") or 0) == int(usuario_resultado.get("id") or 0):
            st.session_state["usuario"] = usuario_resultado
        st.success(resultado.get("mensagem") or "E-mail confirmado com sucesso.")
        if st.button("Continuar para o app", type="primary", use_container_width=True):
            limpar_auth_query_params()
            if _tem_checkout_pendente() and usuario_resultado and email_verificado(usuario_resultado):
                _ir_para_checkout_se_pendente()
                return
            _abrir_app()
        return

    st.warning(resultado.get("mensagem") or "Nao foi possivel validar este link.")
    st.caption("Entre na sua conta para reenviar um novo link de confirmacao, se precisar.")
    _botao_continuar_pos_auth("Voltar para entrar")


def _render_reset_publico():
    token = _auth_token_da_url()
    if not token:
        st.error("Link invalido.")
        _botao_continuar_pos_auth()
        return

    try:
        diagnostico = inspecionar_token_email(token, TOKEN_TIPO_RESET_SENHA)
    except Exception as exc:
        LOGGER.exception("[EMAIL_RESET] Falha ao inspecionar token publico erro=%s", exc)
        diagnostico = {
            "ok": False,
            "mensagem": "Nao foi possivel validar este link agora. Solicite um novo e-mail de recuperacao.",
        }
    if not diagnostico.get("ok"):
        st.warning(diagnostico.get("mensagem") or "Nao foi possivel validar este link.")
        st.caption("Solicite um novo e-mail de recuperacao na tela de login.")
        _botao_continuar_pos_auth("Voltar para entrar")
        return

    with st.form("form_reset_publico"):
        nova_senha = st.text_input("Nova senha", type="password")
        confirmar_senha = st.text_input("Confirmar nova senha", type="password")
        salvar = st.form_submit_button("Salvar nova senha", use_container_width=True)

    if not salvar:
        return
    if not nova_senha:
        st.error("Informe a nova senha.")
        return
    if not confirmar_senha:
        st.error("Confirme a nova senha.")
        return
    if nova_senha != confirmar_senha:
        st.error("A confirmacao da nova senha nao confere.")
        return

    try:
        resultado = redefinir_senha_por_token(token, nova_senha)
    except Exception as exc:
        LOGGER.exception("[EMAIL_RESET] Falha ao redefinir senha por token erro=%s", exc)
        resultado = {
            "ok": False,
            "mensagem": "Nao foi possivel redefinir a senha agora. Solicite um novo link e tente novamente.",
        }
    if not resultado.get("ok"):
        st.error(resultado.get("mensagem") or "Nao foi possivel redefinir a senha.")
        return

    usuario_sessao = st.session_state.get("usuario")
    if usuario_sessao and int(usuario_sessao.get("id") or 0) == int(resultado.get("usuario_id") or 0):
        st.session_state.pop("usuario", None)
        preparar_rotacao_browser_key()
    st.success(resultado.get("mensagem") or "Senha atualizada com sucesso.")
    if st.button("Ir para entrar", type="primary", use_container_width=True):
        limpar_auth_query_params()
        _abrir_app("Login")


def _render_solicitacao_reset_publico():
    _tela_recuperacao_tab()
    st.caption("Se existir uma conta com esse e-mail, enviaremos as instrucoes para redefinir a senha.")
    _botao_continuar_pos_auth()


def render_bloqueio_email_pendente(usuario, on_logout=None):
    usuario_atual = buscar_usuario_por_id(usuario["id"]) or usuario
    st.session_state["usuario"] = usuario_atual
    avaliacao_email = avaliar_email_verificacao_obrigatoria(usuario_atual, contexto="pending_screen")
    if email_verificado(usuario_atual) or not avaliacao_email.get("obrigatoria"):
        LOGGER.info(
            "[EMAIL_PENDING] Bloqueio dispensado usuario_id=%s obrigatoria=%s motivo=%s email_verificado=%s",
            usuario_atual.get("id"),
            avaliacao_email.get("obrigatoria"),
            avaliacao_email.get("motivo"),
            email_verificado(usuario_atual),
        )
        st.rerun()
    if on_logout is None:
        on_logout = encerrar_sessao_atual

    LOGGER.warning(
        "[EMAIL_PENDING] Acesso limitado por e-mail pendente email=%s usuario_id=%s tipo_usuario=%s motivo=%s",
        usuario_atual.get("email"),
        usuario_atual.get("id"),
        usuario_atual.get("tipo_usuario"),
        avaliacao_email.get("motivo"),
    )

    st.title("Confirme seu e-mail")
    _mensagem_email_pendente()
    st.info("Seu login foi concluido com sucesso, mas essa conta ainda precisa confirmar o e-mail para liberar o acesso completo.")
    st.write(
        "Enviamos um link de confirmacao para "
        f"{usuario_atual.get('email') or 'o e-mail cadastrado'}. "
        "Voce pode reenviar o e-mail, corrigir o endereco informado ou sair da conta."
    )
    if usuario_atual.get("ultimo_envio_verificacao_em"):
        st.caption(f"Ultimo envio registrado: {usuario_atual.get('ultimo_envio_verificacao_em')}")

    col_reenviar, col_status, col_sair = st.columns(3)
    with col_reenviar:
        if st.button("Reenviar e-mail", type="primary", use_container_width=True):
            LOGGER.info("[EMAIL_PENDING] Reenvio solicitado usuario_id=%s", usuario_atual["id"])
            try:
                resultado = solicitar_verificacao_email(
                    usuario_atual["id"],
                    criado_ip=_ip_requisicao(),
                    criado_user_agent=_user_agent_requisicao(),
                    origem="email_pending_screen",
                )
            except Exception as exc:
                LOGGER.exception(
                    "[EMAIL_PENDING] Falha ao reenviar verificacao usuario_id=%s erro=%s",
                    usuario_atual["id"],
                    exc,
                )
                resultado = {
                    "status": "erro",
                    "mensagem": "Nao foi possivel reenviar o e-mail agora. Tente novamente em alguns instantes.",
                }
            st.session_state["email_pending_notice"] = {
                "status": resultado.get("status"),
                "mensagem": resultado.get("mensagem"),
            }
            st.rerun()
    with col_status:
        if st.button("Ja confirmei", use_container_width=True):
            LOGGER.info("[EMAIL_PENDING] Confirmacao manual consultada usuario_id=%s", usuario_atual["id"])
            usuario_refresh = buscar_usuario_por_id(usuario_atual["id"])
            if usuario_refresh and email_verificado(usuario_refresh):
                st.session_state["usuario"] = usuario_refresh
                st.session_state["email_pending_notice"] = {
                    "status": "confirmado",
                    "mensagem": "E-mail confirmado com sucesso.",
                }
                st.rerun()
            st.info("Ainda nao encontramos a confirmacao. Tente novamente em alguns instantes.")
    with col_sair:
        if st.button("Sair", use_container_width=True):
            LOGGER.info("[EMAIL_PENDING] Logout solicitado na tela de pendencia usuario_id=%s", usuario_atual["id"])
            on_logout()

    with st.form(f"form_corrigir_email_{usuario_atual['id']}"):
        novo_email = st.text_input(
            "Corrigir e-mail",
            value=usuario_atual.get("email") or "",
            placeholder="voce@exemplo.com",
        )
        salvar_email = st.form_submit_button("Salvar e reenviar link", use_container_width=True)

    if not salvar_email:
        return

    LOGGER.info("[EMAIL_PENDING] Troca de e-mail solicitada usuario_id=%s", usuario_atual["id"])
    try:
        resultado = atualizar_email_pendente_verificacao(
            usuario_atual["id"],
            novo_email,
            criado_ip=_ip_requisicao(),
            criado_user_agent=_user_agent_requisicao(),
        )
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        LOGGER.exception(
            "[EMAIL_PENDING] Falha ao atualizar email pendente usuario_id=%s erro=%s",
            usuario_atual["id"],
            exc,
        )
        st.error("Nao foi possivel atualizar o e-mail agora. Tente novamente em alguns instantes.")
        return

    usuario_refresh = resultado.get("usuario") or buscar_usuario_por_id(usuario_atual["id"])
    if usuario_refresh:
        st.session_state["usuario"] = usuario_refresh
    st.session_state["email_pending_notice"] = {
        "status": resultado.get("status"),
        "mensagem": resultado.get("mensagem") or "Enviamos um novo link para o e-mail atualizado.",
    }
    st.rerun()
