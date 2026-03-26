import streamlit as st

from core.ui import inject_app_icons

st.set_page_config(page_title="FAQ", layout="wide")
inject_app_icons()
st.title("FAQ")

with st.expander("A TriLab e para quem?"):
    st.write("No lancamento inicial, a TriLab esta focada em atletas que precisam de treinos de forca com periodizacao para corrida.")

with st.expander("Existe diferenca entre atleta e treinador?"):
    st.write("Sim. A plataforma ja possui estrutura para atletas e treinadores, mas no lancamento o fluxo publico de entrada esta aberto apenas para atletas.")

with st.expander("Como funciona o periodo de teste?"):
    st.write("Todo novo cadastro recebe 14 dias de teste. Depois disso, o acesso continua para quem tiver assinatura ativa e, no caso do atleta, tambem para quem estiver vinculado a um treinador ativo.")

with st.expander("Ja existe integracao com gateway?"):
    st.write("Ainda nao. O MVP usa ativacao manual de assinatura e ja deixa a base pronta para futura integracao via webhook.")
