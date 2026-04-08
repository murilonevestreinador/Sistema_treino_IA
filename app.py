import logging
from datetime import date, datetime

import streamlit as st

from core.area_treinador import tela_area_treinador
from core.admin import tela_area_admin
from core.auth import render_bloqueio_email_pendente, render_fluxo_publico_auth, tela_login
from core.banco import garantir_colunas_e_tabelas
from core.bloqueio_acesso import render_bloqueio_atleta, render_bloqueio_treinador
from core.cronograma import gerar_cronograma, gerar_mensagem_usuario
from core.dashboard import tela_dashboard
from core.financeiro import (
    avaliar_acesso_usuario,
    garantir_assinatura_inicial,
    obter_status_interface_atleta,
    resumo_status_assinatura,
)
from core.perfil import tela_meu_perfil
from core.permissoes import conta_ativa, eh_admin, eh_atleta, eh_treinador, email_verificado
from core.questionario import tela_questionario
from core.sessao_persistente import (
    capturar_browser_key_da_url,
    diagnosticar_sessao_persistente_atual,
    garantir_sessao_persistente_atual,
    injetar_bridge_navegador,
    preparar_rotacao_browser_key,
    restaurar_usuario_persistente,
    revogar_sessao_persistente_atual,
    tocar_sessao_persistente_atual,
)
from core.treinador import (
    buscar_convite_por_token,
    buscar_status_vinculo,
    buscar_tema_por_atleta,
    buscar_tema_treinador,
    definir_vinculo_treinador_atleta,
    tema_padrao_treinador,
)
from core.treino import resetar_planejamento_atleta
from core.ui import TEMA_PADRAO, aplicar_tema, apply_global_styles, inject_app_icons
from core.usuarios import redefinir_objetivo_atleta


st.set_page_config(page_title="TriLab TREINAMENTO", layout="wide")
LOGGER = logging.getLogger("trilab.app")
ADMIN_DIAGNOSTIC_EMAIL = "murilo_nevescontato@hotmail.com"


def _usuario_admin_diagnostico(usuario):
    return bool(usuario and (usuario.get("email") or "").strip().lower() == ADMIN_DIAGNOSTIC_EMAIL)


def _aplicar_estilo_shell_app():
    st.markdown(
        """
        <style>
        .trilab-topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding: 1.1rem 1.2rem;
            border-radius: 26px;
            border: 1px solid var(--tri-border);
            background: linear-gradient(135deg, var(--tri-header-start) 0%, var(--tri-header-end) 100%);
            color: var(--tri-text-on-header);
            box-shadow: var(--tri-shadow-strong);
            margin-bottom: 1rem;
        }
        .trilab-topbar h1 {
            margin: 0;
            color: var(--tri-text-on-header);
            font-size: 1.75rem;
        }
        .trilab-topbar p {
            margin: 0.3rem 0 0;
            color: color-mix(in srgb, var(--tri-text-on-header) 80%, transparent);
        }
        .trilab-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.3rem 0.7rem;
            border-radius: 999px;
            background: color-mix(in srgb, var(--tri-text-on-header) 14%, transparent);
            border: 1px solid color-mix(in srgb, var(--tri-text-on-header) 16%, transparent);
            color: var(--tri-text-on-header);
            font-size: 0.75rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .sidebar-shell {
            padding: 0.25rem 0 0.4rem;
        }
        .sidebar-brand {
            padding: 0.95rem 1rem;
            border-radius: 20px;
            background: linear-gradient(135deg, color-mix(in srgb, var(--tri-text-on-header) 10%, transparent) 0%, transparent 100%);
            border: 1px solid color-mix(in srgb, var(--tri-text-on-header) 12%, transparent);
            margin-bottom: 0.9rem;
        }
        .sidebar-brand h2 {
            margin: 0;
            color: var(--tri-text-on-header);
            font-size: 1.1rem;
        }
        .sidebar-brand p {
            margin: 0.3rem 0 0;
            color: color-mix(in srgb, var(--tri-text-on-header) 72%, transparent);
            font-size: 0.88rem;
            line-height: 1.45;
        }
        .sidebar-section-title {
            margin: 1rem 0 0.45rem;
            font-size: 0.76rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: color-mix(in srgb, var(--tri-text-on-header) 52%, transparent);
            font-weight: 800;
        }
        .sidebar-link-list {
            padding: 0.85rem 0.95rem;
            border-radius: 18px;
            background: color-mix(in srgb, var(--tri-text-on-header) 6%, transparent);
            border: 1px solid color-mix(in srgb, var(--tri-text-on-header) 8%, transparent);
            line-height: 1.8;
            margin-bottom: 0.85rem;
        }
        .sidebar-link-list a {
            color: color-mix(in srgb, var(--tri-text-on-header) 92%, transparent);
        }
        .sidebar-account {
            padding: 0.85rem 0.95rem;
            border-radius: 18px;
            background: color-mix(in srgb, var(--tri-text-on-header) 6%, transparent);
            border: 1px solid color-mix(in srgb, var(--tri-text-on-header) 8%, transparent);
            margin-bottom: 0.75rem;
        }
        .sidebar-account strong {
            color: var(--tri-text-on-header);
            display: block;
        }
        .sidebar-account span {
            color: color-mix(in srgb, var(--tri-text-on-header) 72%, transparent);
            font-size: 0.88rem;
        }
        .footer-shell {
            margin-top: 1.5rem;
            padding: 1rem 1.1rem 1.25rem;
            border-top: 1px solid var(--tri-border);
            text-align: center;
            color: var(--tri-text-soft);
            font-size: 0.92rem;
        }
        .footer-shell a {
            margin: 0 0.45rem;
        }
        .empty-shell {
            padding: 1.1rem 1.2rem;
            border-radius: 22px;
            border: 1px dashed var(--tri-border-strong);
            background: color-mix(in srgb, var(--tri-surface) 78%, transparent);
        }
        @media (max-width: 768px) {
            .trilab-topbar {
                display: block;
                padding: 1rem;
                border-radius: 20px;
            }
            .trilab-topbar h1 {
                font-size: 1.45rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inicializar_sessao():
    defaults = {
        "usuario": None,
        "mostrar_overview": False,
        "mensagem_onboarding": "",
        "secao_atleta": "visao_geral",
        "secao_app": "principal",
        "treino_aberto": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def fazer_logout():
    usuario = st.session_state.get("usuario")
    if usuario:
        revogar_sessao_persistente_atual(usuario.get("id"))
    preparar_rotacao_browser_key()
    for chave in list(st.session_state.keys()):
        if chave == "browser_key_reset_nonce":
            continue
        del st.session_state[chave]
    st.rerun()


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


def sincronizar_convite_da_url():
    token = _token_convite_da_url()
    if token:
        st.session_state["convite_treinador_token"] = token


def _data_para_formulario(data_texto):
    if not data_texto:
        return date.today()
    try:
        return datetime.strptime(str(data_texto), "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def renderizar_rodape():
    st.markdown(
        """
        <div class="footer-shell">
            <a href="/termos" target="_self">Termos de Uso</a>
            <a href="/privacidade" target="_self">Politica de Privacidade</a>
            <a href="/contato" target="_self">Contato</a>
            <div style="margin-top:0.45rem;">TriLab TREINAMENTO • plataforma de treinamento para corredores.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _abrir_pagina_sidebar(destino):
    try:
        st.switch_page(destino)
    except Exception:
        st.info("Use o menu lateral para abrir esta pagina.")


def renderizar_sidebar(usuario=None, assinatura=None):
    secao_app = st.session_state.get("secao_app", "principal")
    secao_atleta = st.session_state.get("secao_atleta", "visao_geral")
    secao_treinador = st.session_state.get("secao_treinador", "visao_geral")

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-shell">
                <div class="sidebar-brand">
                    <h2>TriLab TREINAMENTO</h2>
                    <p>Planejamento esportivo premium com foco em clareza, consistencia e performance.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sidebar-section-title">Publico</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="sidebar-link-list">
                <div><a href="/planos" target="_self">Planos e Precos</a></div>
                <div><a href="/faq" target="_self">FAQ</a></div>
                <div><a href="/contato" target="_self">Contato</a></div>
                <div><a href="/termos" target="_self">Termos de Uso</a></div>
                <div><a href="/privacidade" target="_self">Politica de Privacidade</a></div>
            </div>
            """
            ,
            unsafe_allow_html=True,
        )

        if not usuario:
            return

        st.divider()
        st.markdown(
            f"""
            <div class="sidebar-account">
                <strong>{usuario.get('nome', 'Usuario')}</strong>
                <span>Perfil {usuario.get('tipo_usuario', 'atleta')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if assinatura:
            resumo = resumo_status_assinatura(assinatura)
            st.caption(resumo["titulo"])

        if eh_admin(usuario):
            st.markdown('<div class="sidebar-section-title">Admin</div>', unsafe_allow_html=True)
            if st.button(
                "Painel Admin",
                key="sb_area_admin",
                type="primary" if secao_app == "principal" else "secondary",
                use_container_width=True,
            ):
                st.session_state["secao_app"] = "principal"
                st.rerun()
            st.caption("Usuarios, financeiro, BI e auditoria centralizados no admin.")
        elif eh_atleta(usuario):
            st.markdown('<div class="sidebar-section-title">Atleta</div>', unsafe_allow_html=True)
            if st.button(
                "Area do Atleta",
                key="sb_area_atleta",
                type="primary" if secao_app == "principal" and secao_atleta == "visao_geral" else "secondary",
                use_container_width=True,
            ):
                st.session_state["secao_app"] = "principal"
                st.session_state["secao_atleta"] = "visao_geral"
                st.rerun()
            if st.button(
                "Treinos",
                key="sb_treinos_atleta",
                type="primary" if secao_app == "principal" and secao_atleta == "treinos" else "secondary",
                use_container_width=True,
            ):
                st.session_state["secao_app"] = "principal"
                st.session_state["secao_atleta"] = "treinos"
                st.rerun()
            st.caption("Historico disponivel dentro da area do atleta.")
        else:
            st.markdown('<div class="sidebar-section-title">Treinador</div>', unsafe_allow_html=True)
            if st.button(
                "Area do Treinador",
                key="sb_area_treinador",
                type="primary" if secao_app == "principal" and secao_treinador in {"visao_geral", "atletas", "bi"} else "secondary",
                use_container_width=True,
            ):
                st.session_state["secao_app"] = "principal"
                st.rerun()
            st.caption("Atletas, BI e relatorios ficam centralizados no painel do treinador.")

        st.markdown('<div class="sidebar-section-title">Financeiro</div>', unsafe_allow_html=True)
        chave_menu = "menu_financeiro_aberto"
        if chave_menu not in st.session_state:
            st.session_state[chave_menu] = False

        if st.button(
            "Financeiro",
            key="sb_financeiro",
            type="primary" if st.session_state.get(chave_menu) else "secondary",
            use_container_width=True,
        ):
            st.session_state[chave_menu] = not st.session_state[chave_menu]
            st.rerun()

        if st.session_state.get(chave_menu):
            if st.button("Minha Assinatura", key="sb_minha_assinatura", type="secondary", use_container_width=True):
                _abrir_pagina_sidebar("pages/minha_assinatura.py")
            if st.button("Planos", key="sb_planos", type="secondary", use_container_width=True):
                _abrir_pagina_sidebar("pages/planos.py")
            if st.button("Suporte / Contato", key="sb_contato", type="secondary", use_container_width=True):
                _abrir_pagina_sidebar("pages/contato.py")
def renderizar_assinatura_necessaria(assinatura):
    st.title("Assinatura necessaria")
    resumo = resumo_status_assinatura(assinatura)
    st.warning("Seu acesso as areas internas foi bloqueado porque nao ha uma assinatura valida ativa.")
    st.write(resumo["descricao"])
    st.markdown(
        """
        <a href="/planos" target="_self">Ver Planos</a>
        &nbsp;|&nbsp;
        <a href="/minha_assinatura" target="_self">Minha Assinatura</a>
        """,
        unsafe_allow_html=True,
    )


def renderizar_menu_superior(usuario):
    secao_app = st.session_state.get("secao_app", "principal")
    secao_atleta = st.session_state.get("secao_atleta", "visao_geral")

    col_titulo, col_menu = st.columns([5, 1.2])
    with col_titulo:
        nome_exibicao = usuario.get("apelido") or usuario.get("nome", "Usu\u00e1rio")
        st.markdown(
            f"""
            <div class="trilab-topbar">
                <div>
                    <div class="trilab-badge">{usuario.get('tipo_usuario', 'atleta')}</div>
                    <h1>TriLab TREINAMENTO</h1>
                    <p>{nome_exibicao}, acompanhe seu plano com um fluxo limpo, esportivo e profissional.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_menu:
        with st.popover("Menu"):
            st.write(f"Usu\u00e1rio: {usuario.get('nome', 'Usu\u00e1rio')}")
            if usuario.get("apelido"):
                st.write(f"Apelido: {usuario['apelido']}")
            st.write(f"Perfil: {usuario.get('tipo_usuario', 'atleta')}")
            if eh_atleta(usuario):
                st.divider()
                st.write("Navega\u00e7\u00e3o")
                col_area, col_treinos, col_perfil = st.columns(3)
                with col_area:
                    if st.button(
                        "Minha \u00e1rea",
                        key="btn_menu_area",
                        type="primary" if secao_app == "principal" and secao_atleta == "visao_geral" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["secao_app"] = "principal"
                        st.session_state["secao_atleta"] = "visao_geral"
                        st.rerun()
                with col_treinos:
                    if st.button(
                        "Treinos",
                        key="btn_menu_treinos",
                        type="primary" if secao_app == "principal" and secao_atleta == "treinos" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["secao_app"] = "principal"
                        st.session_state["secao_atleta"] = "treinos"
                        st.rerun()
                with col_perfil:
                    if st.button(
                        "Meu perfil",
                        key="btn_menu_perfil_atleta",
                        type="primary" if secao_app == "perfil" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["secao_app"] = "perfil"
                        st.rerun()
                st.divider()
                st.write("Redefinir objetivo")
                with st.form("form_redefinir_objetivo_menu"):
                    objetivo = st.selectbox(
                        "Objetivo",
                        ["performance", "saude", "completar prova"],
                        index=["performance", "saude", "completar prova"].index(
                            usuario.get("objetivo", "performance")
                            if usuario.get("objetivo", "performance") in {"performance", "saude", "completar prova"}
                            else "performance"
                        ),
                    )
                    tem_prova = st.checkbox("Tenho uma prova principal", value=bool(usuario.get("tem_prova")))
                    data_prova = None
                    distancia_prova = ""
                    if tem_prova:
                        data_prova = st.date_input(
                            "Nova data da prova",
                            value=_data_para_formulario(usuario.get("data_prova")),
                            format="YYYY-MM-DD",
                        )
                        distancia_prova = st.selectbox(
                            "Dist\u00e2ncia da prova",
                            ["5km", "10km", "21km", "42km", "outra"],
                            index=["5km", "10km", "21km", "42km", "outra"].index(
                                usuario.get("distancia_prova", "10km")
                                if usuario.get("distancia_prova", "10km") in {"5km", "10km", "21km", "42km", "outra"}
                                else "10km"
                            ),
                        )
                    distancia_principal = st.selectbox(
                        "Dist\u00e2ncia principal",
                        ["5km", "10km", "21km", "42km", "outra"],
                        index=["5km", "10km", "21km", "42km", "outra"].index(
                            usuario.get("distancia_principal", "10km")
                            if usuario.get("distancia_principal", "10km") in {"5km", "10km", "21km", "42km", "outra"}
                            else "10km"
                        ),
                    )
                    treinos_musculacao_semana = st.number_input(
                        "Treinos de muscula\u00e7\u00e3o por semana",
                        min_value=1,
                        max_value=5,
                        value=max(1, min(5, int(usuario.get("treinos_musculacao_semana") or 3))),
                    )
                    confirmar_redefinicao = st.checkbox(
                        "Confirmo que desejo recalcular meu planejamento para este novo objetivo."
                    )
                    salvar_objetivo = st.form_submit_button("Salvar novo objetivo")

                if salvar_objetivo:
                    if not confirmar_redefinicao:
                        st.error("Confirme a redefini\u00e7\u00e3o para atualizar seu planejamento.")
                    elif tem_prova and not data_prova:
                        st.error("A nova data da prova \u00e9 obrigat\u00f3ria quando houver prova principal.")
                    else:
                        usuario_atualizado = redefinir_objetivo_atleta(
                            usuario["id"],
                            {
                                "objetivo": objetivo,
                                "tem_prova": tem_prova,
                                "data_prova": data_prova.isoformat() if data_prova else None,
                                "distancia_prova": distancia_prova,
                                "distancia_principal": distancia_principal,
                                "treinos_musculacao_semana": int(treinos_musculacao_semana),
                            },
                        )
                        resetar_planejamento_atleta(usuario["id"])
                        cronograma, fases, total = gerar_cronograma(usuario_atualizado)
                        st.session_state["usuario"] = usuario_atualizado
                        st.session_state["cronograma"] = cronograma
                        st.session_state["fases"] = fases
                        st.session_state["total_semanas"] = total
                        st.session_state["mensagem_onboarding"] = gerar_mensagem_usuario(
                            usuario_atualizado,
                            fases,
                            total,
                        )
                        fase_atual = cronograma[0]["fase"] if cronograma else "base"
                        data_resumo = data_prova.isoformat() if data_prova else "sem prova definida"
                        st.session_state["aviso_redefinicao_objetivo"] = {
                            "mensagem": "Seu treino e sua periodiza\u00e7\u00e3o foram atualizados com base no novo objetivo.",
                            "data_prova": data_resumo,
                            "fase_atual": fase_atual,
                            "treinos_semana": int(treinos_musculacao_semana),
                        }
                        st.success("Objetivo redefinido. Seu planejamento foi recalculado.")
                        st.rerun()
                st.divider()
            elif eh_treinador(usuario):
                st.divider()
                st.write("Navega\u00e7\u00e3o")
                col_painel, col_perfil = st.columns(2)
                with col_painel:
                    if st.button(
                        "Painel",
                        key="btn_menu_painel_treinador",
                        type="primary" if secao_app == "principal" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["secao_app"] = "principal"
                        st.rerun()
                with col_perfil:
                    if st.button(
                        "Meu perfil",
                        key="btn_menu_perfil_treinador",
                        type="primary" if secao_app == "perfil" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["secao_app"] = "perfil"
                        st.rerun()
                st.divider()
            else:
                st.divider()
                if st.button(
                    "Painel admin",
                    key="btn_menu_painel_admin",
                    type="primary" if secao_app == "principal" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["secao_app"] = "principal"
                    st.rerun()
                if st.button(
                    "Meu perfil",
                    key="btn_menu_perfil_admin",
                    type="primary" if secao_app == "perfil" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["secao_app"] = "perfil"
                    st.rerun()
                st.divider()
            if st.button("Logout", key="btn_logout_global", use_container_width=True):
                fazer_logout()


def renderizar_convite_treinador(usuario):
    aviso = st.session_state.pop("aviso_vinculo_treinador", None)
    if aviso:
        st.success(aviso)

    if usuario.get("tipo_usuario") != "atleta":
        return

    token = (
        st.session_state.get("convite_treinador_resposta_pendente")
        or st.session_state.get("convite_treinador_token")
        or ""
    ).strip()
    if not token:
        return

    convite = buscar_convite_por_token(token)
    if not convite:
        st.session_state.pop("convite_treinador_token", None)
        st.session_state.pop("convite_treinador_resposta_pendente", None)
        _limpar_convite_da_url()
        st.warning("O link de convite n\u00e3o \u00e9 v\u00e1lido ou n\u00e3o est\u00e1 mais ativo.")
        return

    vinculo = buscar_status_vinculo(convite["treinador_id"], usuario["id"])
    if vinculo and vinculo["status"] == "ativo":
        st.session_state.pop("convite_treinador_token", None)
        st.session_state.pop("convite_treinador_resposta_pendente", None)
        _limpar_convite_da_url()
        return

    st.info(
        f"{convite['treinador_nome']} ({convite['treinador_email']}) quer se vincular a voc\u00ea como treinador."
    )
    col_aceitar, col_recusar = st.columns(2)
    with col_aceitar:
        if st.button("Sim, vincular", key=f"aceitar_link_treinador_{convite['treinador_id']}"):
            definir_vinculo_treinador_atleta(convite["treinador_id"], usuario["id"], status="ativo")
            st.session_state["aviso_vinculo_treinador"] = (
                f"Seu perfil agora est\u00e1 vinculado ao treinador {convite['treinador_nome']}."
            )
            st.session_state.pop("convite_treinador_token", None)
            st.session_state.pop("convite_treinador_resposta_pendente", None)
            _limpar_convite_da_url()
            st.rerun()
    with col_recusar:
        if st.button("N\u00e3o", key=f"recusar_link_treinador_{convite['treinador_id']}"):
            if vinculo and vinculo["status"] == "pendente":
                definir_vinculo_treinador_atleta(convite["treinador_id"], usuario["id"], status="recusado")
            st.session_state.pop("convite_treinador_token", None)
            st.session_state.pop("convite_treinador_resposta_pendente", None)
            _limpar_convite_da_url()
            st.rerun()


def _obter_tema_usuario(usuario):
    if not usuario:
        return dict(TEMA_PADRAO)

    if usuario.get("tipo_usuario") == "treinador":
        return buscar_tema_treinador(usuario["id"])

    if usuario.get("tipo_usuario") == "atleta":
        return buscar_tema_por_atleta(usuario["id"])

    return tema_padrao_treinador()


def main():
    garantir_colunas_e_tabelas()
    inicializar_sessao()
    injetar_bridge_navegador()
    capturar_browser_key_da_url()
    sincronizar_convite_da_url()
    inject_app_icons()
    apply_global_styles()
    _aplicar_estilo_shell_app()
    aplicar_tema(
        TEMA_PADRAO["cor_primaria"],
        TEMA_PADRAO["cor_secundaria"],
        TEMA_PADRAO["cor_botao"],
        TEMA_PADRAO["cor_cards"],
        TEMA_PADRAO["cor_header"],
    )

    if "usuario" not in st.session_state:
        st.session_state["usuario"] = None

    usuario = st.session_state.get("usuario")
    if usuario is None:
        usuario = restaurar_usuario_persistente()
        if usuario:
            st.session_state["usuario"] = usuario

    if render_fluxo_publico_auth():
        return

    if usuario is None:
        tela_login()
        return

    if not garantir_sessao_persistente_atual(usuario, contexto="app_main"):
        if _usuario_admin_diagnostico(usuario):
            LOGGER.warning(
                "[ADMIN_SESSION] App invalidou sessao admin email=%s usuario_id=%s diagnostico=%s",
                usuario.get("email"),
                usuario.get("id"),
                diagnosticar_sessao_persistente_atual(usuario.get("id")),
            )
        st.session_state["usuario"] = None
        st.session_state["auth_modo"] = "Login"
        st.warning("Sua sessao expirou. Entre novamente para continuar.")
        tela_login()
        return
    tocar_sessao_persistente_atual(usuario["id"])
    if not conta_ativa(usuario):
        st.error("Sua conta esta inativa, suspensa ou cancelada. Entre em contato com o suporte.")
        if st.button("Fazer logout", use_container_width=True):
            fazer_logout()
        return

    if not email_verificado(usuario):
        render_bloqueio_email_pendente(usuario, fazer_logout)
        renderizar_rodape()
        return

    tema_usuario = _obter_tema_usuario(usuario)
    st.session_state["tema_app"] = tema_usuario
    aplicar_tema(
        tema_usuario.get("cor_primaria"),
        tema_usuario.get("cor_secundaria"),
        tema_usuario.get("cor_botao"),
        tema_usuario.get("cor_cards"),
        tema_usuario.get("cor_header"),
    )

    assinatura = None if eh_admin(usuario) else garantir_assinatura_inicial(usuario)
    renderizar_sidebar(usuario, assinatura)
    renderizar_menu_superior(usuario)
    renderizar_convite_treinador(usuario)

    if st.session_state.get("secao_app") == "perfil":
        conta_excluida = tela_meu_perfil(usuario)
        if conta_excluida:
            fazer_logout()
        renderizar_rodape()
        return

    if eh_admin(usuario):
        if _usuario_admin_diagnostico(usuario):
            LOGGER.warning(
                "[ADMIN_ACCESS] Admin autorizado email=%s usuario_id=%s tipo_usuario=%s is_admin=%s",
                usuario.get("email"),
                usuario.get("id"),
                usuario.get("tipo_usuario"),
                usuario.get("is_admin"),
            )
        tela_area_admin(usuario)
        renderizar_rodape()
        return

    avaliacao_acesso = avaliar_acesso_usuario(usuario)
    assinatura = avaliacao_acesso["assinatura"]
    if not avaliacao_acesso["tem_acesso"]:
        if eh_treinador(usuario):
            render_bloqueio_treinador(fazer_logout)
        else:
            render_bloqueio_atleta(usuario, fazer_logout, obter_status_interface_atleta(usuario["id"]))
        renderizar_rodape()
        return

    if eh_treinador(usuario):
        tela_area_treinador(usuario)
        renderizar_rodape()
        return

    if int(usuario.get("onboarding_completo", 0)) == 0:
        tela_questionario(usuario)
        renderizar_rodape()
        return

    tela_dashboard(usuario)
    renderizar_rodape()


main()
