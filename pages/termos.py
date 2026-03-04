from pathlib import Path

import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]
ARQUIVO_TERMOS = BASE_DIR / "legal" / "termos.md"


st.set_page_config(page_title="Termos de Uso", layout="wide")
st.title("Termos de Uso")

with ARQUIVO_TERMOS.open("r", encoding="utf-8") as arquivo:
    texto = arquivo.read()

st.markdown(texto)
