from datetime import date

import streamlit as st

from core.cronograma import gerar_cronograma, gerar_mensagem_usuario
from core.equipamentos import (
    AMBIENTES_TREINO_FORCA,
    EQUIPAMENTO_OPCOES,
    ambiente_requer_inventario,
    normalizar_ambiente_treino_forca,
    rotulo_ambiente_treino,
    rotulo_equipamento,
)
from core.usuarios import atualizar_usuario_onboarding


def tela_questionario(usuario):
    st.title("Primeiro acesso do atleta")
    st.write("Preencha seu onboarding esportivo para gerar o planejamento inicial.")

    hoje = date.today()
    tem_prova = st.checkbox("Tenho uma prova alvo", key="onboarding_tem_prova")
    ambiente_atual = normalizar_ambiente_treino_forca(
        usuario.get("ambiente_treino_forca"),
        usuario.get("local_treino"),
    )

    with st.form("form_questionario_atleta"):
        data_prova = None
        distancia_prova = ""
        if tem_prova:
            data_prova = st.date_input("Data da prova", min_value=hoje)
            distancia_prova = st.selectbox("Dist\u00e2ncia da prova", ["5km", "10km", "21km", "42km", "outra"])

        objetivo = st.selectbox("Objetivo", ["performance", "saude", "completar prova"])
        distancia_principal = st.selectbox("Dist\u00e2ncia principal", ["5km", "10km", "21km", "42km", "outra"])
        tempo_pratica = st.selectbox("Tempo de pr\u00e1tica", ["iniciante", "6 meses", "1 ano", "2+ anos"])
        treinos_corrida_semana = st.number_input("Treinos de corrida por semana", min_value=0, max_value=7, value=3)
        treinos_musculacao_semana = st.number_input(
            "Treinos de muscula\u00e7\u00e3o por semana",
            min_value=1,
            max_value=5,
            value=max(1, int(usuario.get("treinos_musculacao_semana") or 3)),
        )
        ambiente_treino_forca = st.selectbox(
            "Ambiente de treino de forca",
            AMBIENTES_TREINO_FORCA,
            index=AMBIENTES_TREINO_FORCA.index(ambiente_atual),
            format_func=rotulo_ambiente_treino,
        )
        equipamentos_disponiveis = []
        if ambiente_requer_inventario(ambiente_treino_forca):
            st.caption("Selecione manualmente os equipamentos disponiveis. Quando a planilha tiver `banco/barra`, o exercicio exigira os dois.")
            equipamentos_disponiveis = st.multiselect(
                "Equipamentos disponiveis",
                EQUIPAMENTO_OPCOES,
                default=usuario.get("equipamentos_disponiveis") or [],
                format_func=rotulo_equipamento,
            )
        experiencia_musculacao = st.selectbox(
            "Experi\u00eancia com muscula\u00e7\u00e3o",
            ["iniciante", "intermediario", "avancado"],
        )
        historico_lesao = st.selectbox(
            "Hist\u00f3rico de les\u00e3o",
            ["nenhuma", "joelho", "lombar", "ombro", "coluna"],
        )
        dor_atual = st.selectbox(
            "Dor atual",
            ["nenhuma", "leve", "moderada", "forte"],
        )

        enviar = st.form_submit_button("Finalizar question\u00e1rio")

    if not enviar:
        return

    if tem_prova and not data_prova:
        st.error("A data da prova \u00e9 obrigat\u00f3ria quando voc\u00ea marca que tem prova.")
        return

    dados_onboarding = {
        "objetivo": objetivo,
        "distancia_principal": distancia_principal,
        "tempo_pratica": tempo_pratica,
        "treinos_corrida_semana": int(treinos_corrida_semana),
        "tem_prova": tem_prova,
        "data_prova": data_prova.isoformat() if data_prova else None,
        "distancia_prova": distancia_prova,
        "treinos_musculacao_semana": int(treinos_musculacao_semana),
        "local_treino": ambiente_treino_forca,
        "ambiente_treino_forca": ambiente_treino_forca,
        "equipamentos_disponiveis": equipamentos_disponiveis,
        "experiencia_musculacao": experiencia_musculacao,
        "historico_lesao": historico_lesao,
        "dor_atual": dor_atual,
    }

    usuario_atualizado = atualizar_usuario_onboarding(usuario["id"], dados_onboarding)
    cronograma, fases, total_semanas = gerar_cronograma(usuario_atualizado)
    mensagem = gerar_mensagem_usuario(usuario_atualizado, fases, total_semanas)

    st.session_state["usuario"] = usuario_atualizado
    st.session_state["cronograma"] = cronograma
    st.session_state["fases"] = fases
    st.session_state["mensagem_onboarding"] = mensagem
    st.session_state["mostrar_overview"] = True
    st.rerun()
