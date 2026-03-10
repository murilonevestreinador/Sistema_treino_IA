from datetime import date, datetime

import streamlit as st

from core.area_treinador import tela_area_treinador
from core.auth import tela_login
from core.banco import garantir_colunas_e_tabelas
from core.cronograma import gerar_cronograma, gerar_mensagem_usuario
from core.dashboard import tela_dashboard
from core.financeiro import garantir_assinatura_inicial, resumo_status_assinatura, usuario_tem_acesso
from core.perfil import tela_meu_perfil
from core.questionario import tela_questionario
from core.treinador import (
    buscar_convite_por_token,
    buscar_status_vinculo,
    buscar_tema_por_atleta,
    buscar_tema_treinador,
    definir_vinculo_treinador_atleta,
    tema_padrao_treinador,
)
from core.treino import resetar_planejamento_atleta
from core.ui import TEMA_PADRAO, aplicar_tema
from core.usuarios import redefinir_objetivo_atleta


st.set_page_config(page_title="TriLab TREINAMENTO", layout="wide")


def inicializar_sessao():
    defaults = {
        "usuario": None,
        "mostrar_overview": False,
        "mensagem_onboarding": "",
        "secao_atleta": "visao_geral",
        "secao_app": "principal",
        "treino_aberto_nome": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def fazer_logout():
    for chave in list(st.session_state.keys()):
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
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; padding: 0.5rem 0 1rem 0; font-size: 0.95rem;">
            <a href="/termos" target="_self">Termos de Uso</a>
            &nbsp;|&nbsp;
            <a href="/privacidade" target="_self">Politica de Privacidade</a>
            &nbsp;|&nbsp;
            <a href="/contato" target="_self">Contato</a>
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
    with st.sidebar:
        st.markdown("## TriLab TREINAMENTO")
        st.markdown("### Publico")
        st.markdown(
            """
            - [Planos e Precos](/planos)
            - [FAQ](/faq)
            - [Contato](/contato)
            - [Termos de Uso](/termos)
            - [Politica de Privacidade](/privacidade)
            """
        )

        if not usuario:
            return

        st.divider()
        st.markdown(f"**Conta:** {usuario.get('nome', 'Usuario')}")
        if assinatura:
            resumo = resumo_status_assinatura(assinatura)
            st.caption(resumo["titulo"])

        if usuario.get("tipo_usuario") == "atleta":
            st.markdown("### Atleta")
            if st.button("Area do Atleta", key="sb_area_atleta", use_container_width=True):
                st.session_state["secao_app"] = "principal"
                st.session_state["secao_atleta"] = "visao_geral"
                st.rerun()
            if st.button("Treinos", key="sb_treinos_atleta", use_container_width=True):
                st.session_state["secao_app"] = "principal"
                st.session_state["secao_atleta"] = "treinos"
                st.rerun()
            st.markdown("- Historico (na area do atleta)")
        else:
            st.markdown("### Treinador")
            if st.button("Area do Treinador", key="sb_area_treinador", use_container_width=True):
                st.session_state["secao_app"] = "principal"
                st.rerun()
            st.markdown("- Atletas (na area do treinador)")
            st.markdown("- BI e relatorios (na area do treinador)")

        st.markdown("### Financeiro")
        chave_menu = "menu_financeiro_aberto"
        if chave_menu not in st.session_state:
            st.session_state[chave_menu] = False

        if st.button("Financeiro", key="sb_financeiro", use_container_width=True):
            st.session_state[chave_menu] = not st.session_state[chave_menu]
            st.rerun()

        if st.session_state.get(chave_menu):
            if st.button("Minha Assinatura", key="sb_minha_assinatura", use_container_width=True):
                _abrir_pagina_sidebar("pages/minha_assinatura.py")
            if st.button("Planos", key="sb_planos", use_container_width=True):
                _abrir_pagina_sidebar("pages/planos.py")
            if st.button("Suporte / Contato", key="sb_contato", use_container_width=True):
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
    col_titulo, col_menu = st.columns([4, 1])
    with col_titulo:
        nome_exibicao = usuario.get("apelido") or usuario.get("nome", "Usu\u00e1rio")
        st.caption(f"{nome_exibicao} | {usuario.get('tipo_usuario', 'atleta').capitalize()}")
    with col_menu:
        with st.popover("Menu"):
            st.write(f"Usu\u00e1rio: {usuario.get('nome', 'Usu\u00e1rio')}")
            if usuario.get("apelido"):
                st.write(f"Apelido: {usuario['apelido']}")
            st.write(f"Perfil: {usuario.get('tipo_usuario', 'atleta')}")
            if usuario.get("tipo_usuario") == "atleta":
                st.divider()
                st.write("Navega\u00e7\u00e3o")
                col_area, col_treinos, col_perfil = st.columns(3)
                with col_area:
                    if st.button("Minha \u00e1rea", key="btn_menu_area", use_container_width=True):
                        st.session_state["secao_app"] = "principal"
                        st.session_state["secao_atleta"] = "visao_geral"
                        st.rerun()
                with col_treinos:
                    if st.button("Treinos", key="btn_menu_treinos", use_container_width=True):
                        st.session_state["secao_app"] = "principal"
                        st.session_state["secao_atleta"] = "treinos"
                        st.rerun()
                with col_perfil:
                    if st.button("Meu perfil", key="btn_menu_perfil_atleta", use_container_width=True):
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
            else:
                st.divider()
                st.write("Navega\u00e7\u00e3o")
                col_painel, col_perfil = st.columns(2)
                with col_painel:
                    if st.button("Painel", key="btn_menu_painel_treinador", use_container_width=True):
                        st.session_state["secao_app"] = "principal"
                        st.rerun()
                with col_perfil:
                    if st.button("Meu perfil", key="btn_menu_perfil_treinador", use_container_width=True):
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
    sincronizar_convite_da_url()
    aplicar_tema(TEMA_PADRAO["cor_primaria"], TEMA_PADRAO["cor_secundaria"])

    if "usuario" not in st.session_state:
        st.session_state["usuario"] = None

    usuario = st.session_state.get("usuario")
    if usuario is None:
        tela_login()
        return

    tema_usuario = _obter_tema_usuario(usuario)
    st.session_state["tema_app"] = tema_usuario
    aplicar_tema(tema_usuario.get("cor_primaria"), tema_usuario.get("cor_secundaria"))

    assinatura = garantir_assinatura_inicial(usuario)
    renderizar_sidebar(usuario, assinatura)
    renderizar_menu_superior(usuario)
    renderizar_convite_treinador(usuario)

    if st.session_state.get("secao_app") == "perfil":
        conta_excluida = tela_meu_perfil(usuario)
        if conta_excluida:
            fazer_logout()
        renderizar_rodape()
        return

    tem_acesso, assinatura = usuario_tem_acesso(usuario)
    if not tem_acesso:
        renderizar_assinatura_necessaria(assinatura)
        renderizar_rodape()
        return

    if usuario.get("tipo_usuario") == "treinador":
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
