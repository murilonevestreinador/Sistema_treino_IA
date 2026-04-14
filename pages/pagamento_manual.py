import json
import logging

import streamlit as st
import streamlit.components.v1 as components

from core.auth import garantir_usuario_em_pagina
from core.financeiro import (
    aplicar_desconto,
    assinar_plano_manual,
    atleta_tem_treinador_ativo,
    buscar_cupom_por_codigo,
    buscar_plano_por_codigo,
    listar_planos_ativos,
    validar_cupom_para_plano,
)
from core.lancamento import pode_exibir_planos_treinador_publicamente
from core.ui import inject_app_icons
from core.usuarios import diagnosticar_dados_checkout, formatar_cpf, formatar_telefone


LOGGER = logging.getLogger("trilab.checkout.ui")


def _ir_para(nome_pagina):
    try:
        st.switch_page(nome_pagina)
    except Exception:
        st.info("Use o menu lateral para continuar.")


def _ir_para_perfil():
    st.session_state["secao_app"] = "perfil"
    _ir_para("app.py")


def _redirecionar_para_pagamento_asaas(url, mensagem):
    st.info(mensagem)
    components.html(
        f"""
        <script>
        const targetUrl = {json.dumps(url)};
        const parentWindow = window.top || window.parent || window;
        if (targetUrl) {{
            parentWindow.location.assign(targetUrl);
        }}
        </script>
        """,
        height=0,
    )
    st.caption("Se o redirecionamento nao acontecer automaticamente em alguns segundos, use o botao abaixo.")
    st.link_button("Abrir pagamento no Asaas", url, use_container_width=True)


st.set_page_config(page_title="Pagamento Manual", layout="wide")
inject_app_icons()
usuario = garantir_usuario_em_pagina("pagina_pagamento_manual", exigir_email_confirmado=True)
if usuario:
    st.title("Checkout")
    st.write("Revise o plano escolhido, aplique um cupom se quiser e siga com a contratacao.")
    diagnostico_checkout = diagnosticar_dados_checkout(usuario)
    plano_codigo = st.session_state.get("plano_checkout")
    plano = buscar_plano_por_codigo(plano_codigo) if plano_codigo else None
    planos_validos = [p for p in listar_planos_ativos() if p["tipo_plano"] == usuario.get("tipo_usuario")]
    atleta_coberto_por_treinador = (
        (usuario.get("tipo_usuario") or "").strip().lower() == "atleta"
        and atleta_tem_treinador_ativo(usuario["id"])
    )
    exibir_planos_treinador = pode_exibir_planos_treinador_publicamente(usuario)

    if not plano:
        st.error("Nenhum plano selecionado para checkout.")
        if planos_validos and st.button("Escolher plano", use_container_width=True):
            _ir_para("pages/planos.py")
    elif plano["tipo_plano"] != usuario.get("tipo_usuario"):
        st.error("O plano selecionado nao corresponde ao perfil da sua conta.")
        st.session_state.pop("plano_checkout", None)
        if st.button("Voltar para planos", use_container_width=True):
            _ir_para("pages/planos.py")
    elif plano["tipo_plano"] == "treinador" and not exibir_planos_treinador:
        st.error("A adesao publica de planos de treinador esta temporariamente indisponivel no lancamento.")
        st.session_state.pop("plano_checkout", None)
        if st.button("Voltar para planos", use_container_width=True):
            _ir_para("pages/planos.py")
    elif atleta_coberto_por_treinador and plano["tipo_plano"] == "atleta":
        st.info("Seu acesso ja esta coberto por um treinador com vinculo ativo. O checkout individual foi bloqueado para evitar cobranca duplicada.")
        if st.button("Voltar para o app", use_container_width=True):
            _ir_para("app.py")
    else:
        st.subheader("Resumo do checkout")
        col_resumo, col_precos = st.columns([1.15, 0.85])
        with col_resumo:
            st.write(f"Usuario: {usuario.get('nome', 'Usuario')}")
            st.write(f"Perfil: {usuario.get('tipo_usuario', 'atleta').capitalize()}")
            st.write(f"CPF: {formatar_cpf(usuario.get('cpf')) or 'Nao informado'}")
            st.write(f"Telefone: {formatar_telefone(usuario.get('telefone')) or 'Nao informado'}")
            st.write(f"Plano: {plano['nome']}")
            st.write(f"Periodicidade: {plano['periodicidade']}")
            st.write(f"Codigo do plano: {plano['codigo']}")
        with col_precos:
            st.metric("Valor base", f"R$ {plano['valor_base']:.2f}")
        if plano["tipo_plano"] == "treinador":
            st.write(f"Taxa por aluno ativo: R$ {plano['taxa_por_aluno_ativo']:.2f}")
            st.caption("Na renovacao, o valor final usa snapshot dos alunos ativos vinculados na data de fechamento.")
        cupom_codigo = st.text_input("Cupom de desconto (opcional)").strip().upper()
        cupom = buscar_cupom_por_codigo(cupom_codigo) if cupom_codigo else None
        desconto_info = aplicar_desconto(plano["valor_base"], cupom) if cupom else aplicar_desconto(plano["valor_base"], None)
        cupom_valido = False
        mensagem_cupom = ""
        if cupom_codigo:
            if not cupom:
                mensagem_cupom = "Cupom nao encontrado."
            else:
                cupom_valido, mensagem_cupom = validar_cupom_para_plano(cupom, plano)
                if cupom_valido:
                    desconto_info = aplicar_desconto(plano["valor_base"], cupom)
        if cupom_codigo and mensagem_cupom and not cupom_valido:
            st.warning(mensagem_cupom)
        elif cupom_codigo and cupom_valido:
            st.success(f"Cupom aplicado. Desconto de R$ {desconto_info['valor_desconto']:.2f}.")

        st.markdown("#### Valor final")
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            st.metric("Valor bruto", f"R$ {desconto_info['valor_bruto']:.2f}")
        with col_v2:
            st.metric("Desconto", f"R$ {desconto_info['valor_desconto']:.2f}")
        with col_v3:
            st.metric("Valor final", f"R$ {desconto_info['valor_final']:.2f}")

        if plano["tipo_plano"] == "atleta":
            st.info("Ao continuar, vamos criar o customer e a assinatura no Asaas. O acesso sera liberado quando o webhook confirmar o pagamento.")
        else:
            st.info("Ao continuar, a assinatura sera ativada no fluxo atual e seguira a politica do plano do treinador.")

        if not diagnostico_checkout["ok"]:
            st.warning(diagnostico_checkout["mensagem"])
            if st.button("Completar cadastro no perfil", type="primary", use_container_width=True):
                _ir_para_perfil()
            st.stop()

        col_confirmar, col_voltar = st.columns(2)
        with col_confirmar:
            if st.button("Continuar para pagamento", type="primary", use_container_width=True):
                LOGGER.info(
                    "[CHECKOUT_DEBUG] Clique no botao Continuar para pagamento | usuario_id=%s plano_codigo=%s tipo_usuario=%s cupom=%s pagina=%s",
                    usuario.get("id"),
                    plano.get("codigo"),
                    usuario.get("tipo_usuario"),
                    cupom_codigo or "",
                    "pages/pagamento_manual.py",
                )
                assinatura, mensagem = assinar_plano_manual(usuario, plano["codigo"], cupom_codigo=cupom_codigo or None)
                if assinatura:
                    LOGGER.info(
                        "[CHECKOUT_DEBUG] Checkout retornou sucesso para a UI | usuario_id=%s assinatura_id=%s gateway=%s status=%s",
                        usuario.get("id"),
                        assinatura.get("id"),
                        assinatura.get("gateway"),
                        assinatura.get("status"),
                    )
                    st.session_state.pop("plano_checkout", None)
                    redirect_url = (assinatura.get("redirect_url") or assinatura.get("invoice_url") or "").strip()
                    fluxo_asaas = assinatura.get("gateway") == "asaas" and plano.get("tipo_plano") == "atleta"
                    if fluxo_asaas and redirect_url:
                        LOGGER.info(
                            "[CHECKOUT_DEBUG] Redirecionando usuario para invoiceUrl do Asaas | usuario_id=%s assinatura_id=%s asaas_payment_id=%s",
                            usuario.get("id"),
                            assinatura.get("id"),
                            assinatura.get("asaas_payment_id"),
                        )
                        _redirecionar_para_pagamento_asaas(redirect_url, mensagem)
                        st.stop()
                    if fluxo_asaas:
                        LOGGER.warning(
                            "[CHECKOUT_DEBUG] Assinatura criada sem invoiceUrl para redirecionamento imediato | usuario_id=%s assinatura_id=%s",
                            usuario.get("id"),
                            assinatura.get("id"),
                        )
                        st.warning(mensagem)
                        if st.button("Ir para Minha Assinatura", type="primary", use_container_width=True, key="checkout_ir_minha_assinatura"):
                            _ir_para("pages/minha_assinatura.py")
                        st.stop()
                    st.success(mensagem)
                    _ir_para("pages/minha_assinatura.py")
                else:
                    LOGGER.error(
                        "[CHECKOUT_DEBUG] Checkout retornou falha para a UI | usuario_id=%s plano_codigo=%s mensagem=%s",
                        usuario.get("id"),
                        plano.get("codigo"),
                        mensagem,
                    )
                    st.error(f"{mensagem} Verifique os logs com os marcadores CHECKOUT_DEBUG/ASAAS_ERROR.")
        with col_voltar:
            if st.button("Voltar para planos", use_container_width=True):
                _ir_para("pages/planos.py")
