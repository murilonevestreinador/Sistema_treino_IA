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
st.title("Checkout")
st.write("Fluxo inicial de assinatura. Para atleta solo, a assinatura sera criada no Asaas Sandbox e o status sera atualizado via webhook.")

usuario = st.session_state.get("usuario")
if not usuario:
    st.warning("Voce precisa estar logado para testar a ativacao manual.")
    if st.button("Ir para login", use_container_width=True):
        st.session_state["auth_modo"] = "Login"
        _ir_para("app.py")
else:
    plano_codigo = st.session_state.get("plano_checkout")
    plano = buscar_plano_por_codigo(plano_codigo) if plano_codigo else None
    planos_validos = [p for p in listar_planos_ativos() if p["tipo_plano"] == usuario.get("tipo_usuario")]

    if not plano and planos_validos:
        plano = planos_validos[0]

    if not plano:
        st.error("Nenhum plano disponivel para este perfil.")
    else:
        st.subheader("Resumo do pagamento")
        st.write(f"Usuario: {usuario.get('nome', 'Usuario')}")
        st.write(f"Perfil: {usuario.get('tipo_usuario', 'atleta').capitalize()}")
        st.write(f"Plano: {plano['nome']}")
        st.write(f"Valor base: R$ {plano['valor_base']:.2f}")
        st.write(f"Periodicidade: {plano['periodicidade']}")
        if plano["tipo_plano"] == "treinador":
            st.write(f"Taxa por aluno ativo: R$ {plano['taxa_por_aluno_ativo']:.2f}")
            st.caption("Na renovacao, o valor final usa snapshot dos alunos ativos vinculados na data de fechamento.")
        cupom_codigo = st.text_input("Cupom de desconto (opcional)").strip().upper()

        if plano["tipo_plano"] == "atleta":
            st.info("Ao confirmar, vamos criar o customer e a assinatura no Asaas Sandbox. O acesso sera liberado quando o webhook confirmar o pagamento.")
        else:
            st.info("Ao confirmar, a assinatura sera ativada manualmente para testes internos.")

        col_confirmar, col_voltar = st.columns(2)
        with col_confirmar:
            if st.button("Confirmar assinatura", use_container_width=True):
                assinatura, mensagem = assinar_plano_manual(usuario, plano["codigo"], cupom_codigo=cupom_codigo or None)
                if assinatura:
                    st.success(mensagem)
                    st.session_state.pop("plano_checkout", None)
                    _ir_para("pages/minha_assinatura.py")
                else:
                    st.error(mensagem)
        with col_voltar:
            if st.button("Voltar para planos", use_container_width=True):
                _ir_para("pages/planos.py")
