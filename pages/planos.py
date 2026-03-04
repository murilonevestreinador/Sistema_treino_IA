import streamlit as st

from core.financeiro import listar_planos_ativos


def _ir_para_app(modo=None):
    if modo:
        st.session_state["auth_modo"] = modo
    try:
        st.switch_page("app.py")
    except Exception:
        st.info("Abra a pagina inicial do app para continuar.")


def _ir_para_pagamento(plano_codigo):
    st.session_state["plano_checkout"] = plano_codigo
    try:
        st.switch_page("pages/pagamento_manual.py")
    except Exception:
        st.info("Abra a pagina Pagamento Manual no menu lateral para continuar.")


st.set_page_config(page_title="Planos e Precos", layout="wide")
st.title("Planos e Precos")
st.write(
    "Escolha o plano ideal para usar a TriLab TREINAMENTO com treinos de forca para corredores, periodizacao e adaptacao por feedback."
)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Perfil Atleta")
    st.write("Acesso individual com checklist, historico e acompanhamento do proprio progresso.")
with col_b:
    st.subheader("Perfil Treinador")
    st.write("Gestao de atletas vinculados, acompanhamento e edicao de treinos pela mesma plataforma.")

usuario = st.session_state.get("usuario")
if not usuario:
    col_cta1, col_cta2 = st.columns(2)
    with col_cta1:
        if st.button("Criar conta", key="planos_criar_conta", use_container_width=True):
            _ir_para_app("Cadastro")
    with col_cta2:
        if st.button("Entrar", key="planos_entrar", use_container_width=True):
            _ir_para_app("Login")

planos = listar_planos_ativos()
if not planos:
    st.warning("Nenhum plano disponivel no momento.")
else:
    colunas = st.columns(len(planos))
    for indice, plano in enumerate(planos):
        with colunas[indice]:
            st.markdown(
                f"""
                <div style="border:1px solid rgba(18,58,52,0.08); border-radius:18px; padding:1rem; background:white; min-height:280px;">
                    <h3 style="margin-top:0;">{plano['nome']}</h3>
                    <p><strong>R$ {plano['preco_mensal']:.2f}/mes</strong></p>
                    <p>Perfil: {plano['tipo'].capitalize()}</p>
                    <p>{'Limite de ' + str(plano['limite_atletas']) + ' atletas' if plano['limite_atletas'] else 'Uso individual com acesso total ao app'}</p>
                    <p>Inclui periodizacao, ajustes por feedback e base pronta para evolucao do treinamento.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if usuario:
                if st.button("Assinar", key=f"assinar_{plano['codigo']}", use_container_width=True):
                    if usuario.get("tipo_usuario") == plano["tipo"]:
                        _ir_para_pagamento(plano["codigo"])
                    else:
                        st.error("Este plano nao corresponde ao perfil da sua conta.")
            else:
                if st.button("Assinar", key=f"assinar_publico_{plano['codigo']}", use_container_width=True):
                    _ir_para_app("Cadastro")

if usuario:
    st.markdown("---")
    st.caption("Teste interno: o checkout manual ativa a assinatura imediatamente para acelerar validacao do fluxo SaaS.")
