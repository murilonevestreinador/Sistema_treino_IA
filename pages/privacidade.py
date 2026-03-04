from pathlib import Path

import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]
ARQUIVO_PRIVACIDADE = BASE_DIR / "legal" / "privacidade.md"


st.set_page_config(page_title="Politica de Privacidade", layout="wide")
st.title("Politica de Privacidade")

with ARQUIVO_PRIVACIDADE.open("r", encoding="utf-8") as arquivo:
    texto = arquivo.read()

st.markdown(texto)
