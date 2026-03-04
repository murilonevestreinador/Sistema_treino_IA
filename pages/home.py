import streamlit as st


st.set_page_config(page_title="Home", layout="wide")
st.title("TriLab TREINAMENTO")
st.write(
    "Treinos de forca para corredores com periodizacao, adaptacao por feedback e acompanhamento opcional entre atleta e treinador."
)

col_atleta, col_treinador = st.columns(2)
with col_atleta:
    st.subheader("Perfil Atleta")
    st.write("Receba treinos personalizados, acompanhe checklist, historico e ajuste sua rotina com base no seu feedback.")
with col_treinador:
    st.subheader("Perfil Treinador")
    st.write("Acompanhe atletas vinculados, ajuste treinos da semana e use a plataforma como camada de gestao.")

col_cta1, col_cta2 = st.columns(2)
with col_cta1:
    if st.button("Criar conta", use_container_width=True):
        st.session_state["auth_modo"] = "Cadastro"
        try:
            st.switch_page("app.py")
        except Exception:
            st.info("Abra a pagina principal do app para continuar.")
with col_cta2:
    if st.button("Entrar", use_container_width=True):
        st.session_state["auth_modo"] = "Login"
        try:
            st.switch_page("app.py")
        except Exception:
            st.info("Abra a pagina principal do app para continuar.")
