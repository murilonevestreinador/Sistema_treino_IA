import streamlit as st

from core.auth import render_pagina_verificacao_email
from core.ui import inject_app_icons


st.set_page_config(page_title="Confirmar e-mail", layout="centered")
inject_app_icons()
render_pagina_verificacao_email()
