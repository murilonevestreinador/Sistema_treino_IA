import streamlit as st

from core.auth import render_pagina_esqueci_senha
from core.ui import inject_app_icons


st.set_page_config(page_title="Esqueci a senha", layout="centered")
inject_app_icons()
render_pagina_esqueci_senha()
