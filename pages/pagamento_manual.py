import streamlit as st

from core.financeiro import assinar_plano_manual, buscar_plano_por_codigo, listar_planos_ativos
from core.ui import inject_app_icons


def _ir_para(nome_pagina):
    try:
        st.switch_page(nome_pagina)
    except Exception:
        st.info("Use o menu lateral para continuar.")


st.set_page_config(page_title="Pagamento Manual", layout="wide")
inject_app_icons()
st.title("Pagamento Manual")
st.write("MVP interno para simular a compra sem gateway. No futuro, esta etapa sera integrada ao Asaas via API e webhook.")

usuario = st.session_state.get("usuario")
if not usuario:
    st.warning("Voce precisa estar logado para testar a ativacao manual.")
    if st.button("Ir para login", use_container_width=True):
        st.session_state["auth_modo"] = "Login"
        _ir_para("app.py")
else:
    plano_codigo = st.session_state.get("plano_checkout")
    plano = buscar_plano_por_codigo(plano_codigo) if plano_codigo else None
    planos_validos = [p for p in listar_planos_ativos() if p["tipo"] == usuario.get("tipo_usuario")]

    if not plano and planos_validos:
        plano = planos_validos[0]

    if not plano:
        st.error("Nenhum plano disponivel para este perfil.")
    else:
        st.subheader("Resumo do pagamento")
        st.write(f"Usuario: {usuario.get('nome', 'Usuario')}")
        st.write(f"Perfil: {usuario.get('tipo_usuario', 'atleta').capitalize()}")
        st.write(f"Plano: {plano['nome']}")
        st.write(f"Valor mensal: R$ {plano['preco_mensal']:.2f}")
        if plano.get("limite_atletas"):
            st.write(f"Limite de atletas: {plano['limite_atletas']}")

        st.info("Ao confirmar, a assinatura sera ativada manualmente para testes internos.")

        col_confirmar, col_voltar = st.columns(2)
        with col_confirmar:
            if st.button("Confirmar assinatura manual", use_container_width=True):
                assinatura, mensagem = assinar_plano_manual(usuario, plano["codigo"])
                if assinatura:
                    st.success(mensagem)
                    st.session_state.pop("plano_checkout", None)
                    _ir_para("pages/minha_assinatura.py")
                else:
                    st.error(mensagem)
        with col_voltar:
            if st.button("Voltar para planos", use_container_width=True):
                _ir_para("pages/planos.py")
