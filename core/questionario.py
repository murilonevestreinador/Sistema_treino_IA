from datetime import date

import streamlit as st

from core.cronograma import gerar_cronograma, gerar_mensagem_usuario
from core.usuarios import atualizar_usuario_onboarding


def tela_questionario(usuario):
    st.title("Primeiro acesso do atleta")
    st.write("Preencha seu onboarding esportivo para gerar o planejamento inicial.")

    hoje = date.today()
    tem_prova = st.checkbox("Tenho uma prova alvo", key="onboarding_tem_prova")

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
        local_treino = st.selectbox("Local de treino", ["academia", "casa", "hibrido"])
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
        "local_treino": local_treino,
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
