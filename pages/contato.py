import streamlit as st

from core.ui import inject_app_icons

st.set_page_config(page_title="Contato", layout="wide")
inject_app_icons()
st.title("Contato")

st.markdown(
    """
    Para duvidas, suporte ou solicitacoes relacionadas a plataforma:

    **TriLab Treinamento LTDA**  
    CNPJ: 53.843.912/0001-91  
    Email: [suporte@trilabtreinamento.com](mailto:suporte@trilabtreinamento.com)
    """
)
