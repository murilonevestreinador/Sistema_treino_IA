import streamlit as st

from core.auth import garantir_usuario_em_pagina
from core.financeiro import atleta_tem_treinador_ativo, listar_planos_ativos
from core.lancamento import pode_exibir_planos_treinador_publicamente
from core.ui import inject_app_icons


CHECKOUT_PAGE = "pages/pagamento_manual.py"


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
        st.switch_page(CHECKOUT_PAGE)
    except Exception:
        st.info("Abra a pagina Pagamento Manual no menu lateral para continuar.")


st.set_page_config(page_title="Planos e Precos", layout="wide")
inject_app_icons()
usuario = garantir_usuario_em_pagina("pagina_planos", exigir_email_confirmado=True, permitir_publico=True)
st.title("Planos e Precos")
st.write(
    "Escolha o plano ideal para usar a TriLab TREINAMENTO com treinos de forca para corredores, periodizacao e adaptacao por feedback."
)
exibir_planos_treinador = pode_exibir_planos_treinador_publicamente(usuario)
atleta_coberto_por_treinador = bool(
    usuario
    and (usuario.get("tipo_usuario") or "").strip().lower() == "atleta"
    and atleta_tem_treinador_ativo(usuario["id"])
)

st.subheader("Perfil Atleta")
st.write("Acesso individual com checklist, historico e acompanhamento do proprio progresso.")
if not exibir_planos_treinador:
    st.info("No lancamento inicial, a adesao publica esta focada em atletas.")
else:
    st.markdown("---")
    st.subheader("Perfil Treinador")
    st.write("Gestao de atletas vinculados, acompanhamento e edicao de treinos pela mesma plataforma.")

if not usuario:
    col_cta1, col_cta2 = st.columns(2)
    with col_cta1:
        if st.button("Criar conta", key="planos_criar_conta", use_container_width=True):
            _ir_para_app("Cadastro")
    with col_cta2:
        if st.button("Entrar", key="planos_entrar", use_container_width=True):
            _ir_para_app("Login")

planos = listar_planos_ativos()
if not exibir_planos_treinador:
    planos = [plano for plano in planos if plano["tipo_plano"] == "atleta"]
elif usuario and (usuario.get("tipo_usuario") or "").strip().lower() == "treinador":
    planos = [plano for plano in planos if plano["tipo_plano"] == "treinador"]

if not planos:
    st.warning("Nenhum plano disponivel no momento.")
else:
    if atleta_coberto_por_treinador:
        st.info("Seu acesso como atleta ja esta coberto por um treinador com vinculo ativo. Nao ha assinatura individual para esta conta vinculada.")
    colunas = st.columns(len(planos))
    for indice, plano in enumerate(planos):
        with colunas[indice]:
            st.markdown(
                f"""
                <div style="border:1px solid rgba(18,58,52,0.08); border-radius:18px; padding:1rem; background:white; min-height:280px;">
                    <h3 style="margin-top:0;">{plano['nome']}</h3>
                    <p><strong>R$ {plano['valor_base']:.2f}/{plano['periodicidade']}</strong></p>
                    <p>Perfil: {plano['tipo_plano'].capitalize()}</p>
                    <p>{'Taxa adicional por aluno ativo: R$ ' + f"{plano['taxa_por_aluno_ativo']:.2f}" if plano['tipo_plano'] == 'treinador' else 'Uso individual com acesso total ao app'}</p>
                    <p>Inclui periodizacao, ajustes por feedback e base pronta para evolucao do treinamento.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if usuario:
                if atleta_coberto_por_treinador and plano["tipo_plano"] == "atleta":
                    st.caption("Conta coberta pelo treinador vinculado.")
                elif st.button("Assinar", key=f"assinar_{plano['codigo']}", use_container_width=True):
                    if usuario.get("tipo_usuario") == plano["tipo_plano"]:
                        _ir_para_pagamento(plano["codigo"])
                    else:
                        st.error("Este plano nao corresponde ao perfil da sua conta.")
            else:
                if st.button("Assinar", key=f"assinar_publico_{plano['codigo']}", use_container_width=True):
                    st.session_state["plano_checkout"] = plano["codigo"]
                    _ir_para_app("Cadastro")

if usuario:
    st.markdown("---")
    st.caption("Teste interno: o checkout manual ativa a assinatura imediatamente para acelerar validacao do fluxo SaaS.")
