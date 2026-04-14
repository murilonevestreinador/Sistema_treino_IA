import streamlit as st

from core.auth import garantir_usuario_em_pagina
from core.financeiro import (
    atleta_tem_treinador_ativo,
    buscar_assinatura_atual,
    cancelar_renovacao_automatica,
    expirar_assinatura_atual_para_teste,
    listar_assinaturas_usuario,
    resumo_status_assinatura,
    status_para_exibicao,
)
from core.ui import inject_app_icons


def _ir_para_app():
    try:
        st.switch_page("app.py")
    except Exception:
        st.info("Abra a pagina principal do app para continuar.")


st.set_page_config(page_title="Minha Assinatura", layout="wide")
inject_app_icons()
usuario = garantir_usuario_em_pagina("pagina_minha_assinatura", exigir_email_confirmado=True)
if usuario:
    st.title("Minha Assinatura")
    assinatura = buscar_assinatura_atual(usuario["id"])
    resumo = resumo_status_assinatura(assinatura)
    atleta_coberto_por_treinador = (
        (usuario.get("tipo_usuario") or "").strip().lower() == "atleta"
        and atleta_tem_treinador_ativo(usuario["id"])
    )

    st.subheader(resumo["titulo"])
    st.write(resumo["descricao"])
    if atleta_coberto_por_treinador:
        st.info("Seu acesso como atleta esta coberto por um treinador com vinculo ativo. Voce nao precisa de assinatura individual enquanto esse vinculo estiver valido.")

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
        st.write(f"Periodicidade: {assinatura.get('periodicidade') or '-'}")
        st.write(f"Valor base cobrado: R$ {float(assinatura.get('valor_base_cobrado') or 0):.2f}")
        if assinatura.get("plano_tipo") == "treinador":
            st.write(f"Alunos ativos no fechamento: {int(assinatura.get('quantidade_alunos_ativos_fechamento') or 0)}")
            st.write(f"Taxa por alunos no fechamento: R$ {float(assinatura.get('valor_taxa_alunos') or 0):.2f}")
        st.write(f"Valor total cobrado: R$ {float(assinatura.get('valor_total_cobrado') or 0):.2f}")
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
