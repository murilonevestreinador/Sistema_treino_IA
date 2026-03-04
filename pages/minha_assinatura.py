import streamlit as st

from core.financeiro import (
    buscar_assinatura_atual,
    cancelar_renovacao_automatica,
    expirar_assinatura_atual_para_teste,
    listar_assinaturas_usuario,
    resumo_status_assinatura,
    status_para_exibicao,
)


def _ir_para_app():
    try:
        st.switch_page("app.py")
    except Exception:
        st.info("Abra a pagina principal do app para continuar.")


st.set_page_config(page_title="Minha Assinatura", layout="wide")
st.title("Minha Assinatura")

usuario = st.session_state.get("usuario")
if not usuario:
    st.warning("Voce precisa estar logado para acessar esta pagina.")
    if st.button("Ir para login", use_container_width=True):
        st.session_state["auth_modo"] = "Login"
        _ir_para_app()
else:
    assinatura = buscar_assinatura_atual(usuario["id"])
    resumo = resumo_status_assinatura(assinatura)

    st.subheader(resumo["titulo"])
    st.write(resumo["descricao"])

    if not assinatura:
        st.info("Nenhuma assinatura ativa ou historica encontrada.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Status", status_para_exibicao(assinatura["status"]))
        with col2:
            st.metric("Inicio", assinatura["data_inicio"])
        with col3:
            st.metric("Fim", assinatura.get("data_fim") or "Sem data")

        st.write(f"Plano: {assinatura['plano_nome']}")
        st.write(f"Gateway: {assinatura.get('gateway') or 'manual'}")
        st.write(
            "Renovacao automatica: "
            + ("Ativa" if int(assinatura.get("renovacao_automatica", 0)) else "Desativada")
        )

        col_cancelar, col_planos = st.columns(2)
        with col_cancelar:
            if st.button("Cancelar renovacao", use_container_width=True):
                _, mensagem = cancelar_renovacao_automatica(usuario["id"])
                st.success(mensagem)
                st.rerun()
        with col_planos:
            if st.button("Ver Planos", use_container_width=True):
                try:
                    st.switch_page("pages/planos.py")
                except Exception:
                    st.info("Abra a pagina Planos no menu lateral.")

        if assinatura["status"] in {"inadimplente", "inativa", "cancelada"}:
            st.warning("Acesso bloqueado ate que exista uma assinatura ativa ou periodo de teste valido.")

        st.markdown("---")
        st.caption("Ferramenta de teste interno")
        if st.button("Simular expiracao agora", use_container_width=True):
            _, mensagem = expirar_assinatura_atual_para_teste(usuario["id"])
            st.warning(mensagem)
            st.rerun()

    historico = listar_assinaturas_usuario(usuario["id"])
    if historico:
        st.markdown("---")
        st.subheader("Historico")
        for item in historico:
            st.write(
                f"{item['plano_nome']} | {status_para_exibicao(item['status'])} | inicio: {item['data_inicio']} | fim: {item.get('data_fim') or 'sem data'}"
            )
