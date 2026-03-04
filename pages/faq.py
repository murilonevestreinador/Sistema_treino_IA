import streamlit as st


st.set_page_config(page_title="FAQ", layout="wide")
st.title("FAQ")

with st.expander("A TriLab e para quem?"):
    st.write("Para corredores que precisam de treinos de forca com periodizacao, com ou sem acompanhamento de treinador.")

with st.expander("Existe diferenca entre atleta e treinador?"):
    st.write("Sim. Atletas usam a plataforma para executar e acompanhar os treinos. Treinadores acompanham atletas vinculados e podem ajustar os treinos.")

with st.expander("Como funciona o periodo de teste?"):
    st.write("Todo novo cadastro recebe 7 dias de teste. Depois disso, e necessario ter uma assinatura ativa para acessar as areas internas.")

with st.expander("Ja existe integracao com gateway?"):
    st.write("Ainda nao. O MVP usa ativacao manual de assinatura e ja deixa a base pronta para futura integracao via webhook.")
