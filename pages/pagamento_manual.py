import json
import logging

import streamlit as st
import streamlit.components.v1 as components

from core.auth import garantir_usuario_em_pagina
from core.financeiro import (
    assinar_plano_manual,
    atleta_tem_treinador_ativo,
    buscar_checkout_aberto_usuario,
    buscar_checkout_pendente,
    buscar_plano_por_codigo,
    listar_planos_ativos,
    salvar_checkout_pendente,
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


def _checkout_id_da_url():
    try:
        return (st.query_params.get("checkout_id") or "").strip()
    except Exception:
        return ""


def _sincronizar_checkout_navegacao(checkout):
    if not checkout:
        return
    st.session_state["checkout_id"] = checkout["id"]
    st.session_state["checkout_external_reference"] = checkout.get("external_reference")
    st.session_state["plano_checkout"] = checkout.get("plano_codigo")
    try:
        st.query_params["checkout_id"] = str(checkout["id"])
    except Exception:
        pass


def _resolver_checkout(usuario):
    checkout_id = st.session_state.get("checkout_id") or _checkout_id_da_url()
    plano_codigo_sessao = (st.session_state.get("plano_checkout") or "").strip()
    checkout = None

    if checkout_id:
        checkout = buscar_checkout_pendente(checkout_id, usuario["id"])
        if not checkout:
            LOGGER.warning(
                "[CHECKOUT_STATE] Checkout da URL/sessao nao encontrado | usuario_id=%s checkout_id=%s",
                usuario.get("id"),
                checkout_id,
            )

    if not checkout and plano_codigo_sessao:
        try:
            checkout = salvar_checkout_pendente(usuario, plano_codigo_sessao)
            LOGGER.info(
                "[CHECKOUT_STATE] Checkout criado a partir do plano em sessao | usuario_id=%s checkout_id=%s plano_codigo=%s",
                usuario.get("id"),
                checkout.get("id"),
                plano_codigo_sessao,
            )
        except Exception as exc:
            LOGGER.exception(
                "[CHECKOUT_ERROR] Falha ao criar checkout a partir do plano em sessao | usuario_id=%s plano_codigo=%s",
                usuario.get("id"),
                plano_codigo_sessao,
            )
            return None, str(exc)

    if not checkout:
        checkout = buscar_checkout_aberto_usuario(usuario["id"])
        if checkout:
            LOGGER.info(
                "[CHECKOUT_STATE] Checkout aberto recuperado do backend | usuario_id=%s checkout_id=%s plano_codigo=%s",
                usuario.get("id"),
                checkout.get("id"),
                checkout.get("plano_codigo"),
            )

    if checkout:
        _sincronizar_checkout_navegacao(checkout)
    return checkout, None


st.set_page_config(page_title="Pagamento Manual", layout="wide")
inject_app_icons()
usuario = garantir_usuario_em_pagina("pagina_pagamento_manual", exigir_email_confirmado=True)
if usuario:
    st.title("Checkout")
    st.write("Revise o plano escolhido, aplique um cupom se quiser e siga com a contratacao.")
    diagnostico_checkout = diagnosticar_dados_checkout(usuario)
    checkout, erro_checkout = _resolver_checkout(usuario)
    if erro_checkout:
        st.error(f"Nao foi possivel recuperar o checkout: {erro_checkout}")
        if st.button("Escolher plano", use_container_width=True):
            _ir_para("pages/planos.py")
        st.stop()

    plano_codigo = checkout.get("plano_codigo") if checkout else st.session_state.get("plano_checkout")
    plano = buscar_plano_por_codigo(plano_codigo) if plano_codigo else None
    planos_validos = [p for p in listar_planos_ativos() if p["tipo_plano"] == usuario.get("tipo_usuario")]
    atleta_coberto_por_treinador = (
        (usuario.get("tipo_usuario") or "").strip().lower() == "atleta"
        and atleta_tem_treinador_ativo(usuario["id"])
    )
    exibir_planos_treinador = pode_exibir_planos_treinador_publicamente(usuario)

    if not plano:
        LOGGER.warning(
            "[CHECKOUT_STATE] Nenhum plano/checkout disponivel para renderizar | usuario_id=%s checkout_id=%s plano_sessao=%s",
            usuario.get("id"),
            st.session_state.get("checkout_id"),
            st.session_state.get("plano_checkout"),
        )
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
        checkout_status = checkout.get("status")
        checkout_bloqueado = checkout_status in {"asaas_criado", "concluido", "cancelado"}
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
            st.metric("Valor base", f"R$ {checkout['valor_bruto']:.2f}")
        if plano["tipo_plano"] == "treinador":
            st.write(f"Taxa por aluno ativo: R$ {plano['taxa_por_aluno_ativo']:.2f}")
            st.caption("Na renovacao, o valor final usa snapshot dos alunos ativos vinculados na data de fechamento.")
        cupom_key = f"checkout_cupom_{checkout['id']}"
        if cupom_key not in st.session_state:
            st.session_state[cupom_key] = checkout.get("cupom_codigo") or ""
        cupom_codigo = st.text_input("Cupom de desconto (opcional)", key=cupom_key, disabled=checkout_bloqueado).strip().upper()

        if not checkout_bloqueado:
            try:
                checkout = salvar_checkout_pendente(usuario, plano["codigo"], cupom_codigo=cupom_codigo or None, checkout_id=checkout["id"])
                _sincronizar_checkout_navegacao(checkout)
            except Exception as exc:
                LOGGER.exception(
                    "[CHECKOUT_ERROR] Falha ao validar/persistir cupom no checkout | usuario_id=%s checkout_id=%s cupom=%s",
                    usuario.get("id"),
                    checkout.get("id"),
                    cupom_codigo,
                )
                st.error(f"Nao foi possivel validar o cupom: {exc}")
                st.stop()

        cupom_invalido = bool(cupom_codigo and not checkout.get("cupom_codigo"))
        mensagem_cupom = checkout.get("mensagem_cupom") or ""
        if cupom_invalido:
            st.warning(mensagem_cupom or "Cupom invalido.")
        elif checkout.get("cupom_codigo"):
            st.success(f"Cupom aplicado. Desconto de R$ {checkout['valor_desconto']:.2f}.")

        st.markdown("#### Valor final")
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            st.metric("Valor bruto", f"R$ {checkout['valor_bruto']:.2f}")
        with col_v2:
            st.metric("Desconto", f"R$ {checkout['valor_desconto']:.2f}")
        with col_v3:
            st.metric("Primeira cobranca", f"R$ {checkout['valor_final']:.2f}")
        if checkout.get("valor_desconto", 0) > 0:
            st.caption(f"Renovacoes futuras seguirao no valor cheio de R$ {checkout['valor_bruto']:.2f}.")

        if checkout_status == "asaas_criado":
            st.info("A cobranca deste checkout ja foi criada no Asaas. O plano e o cupom foram recuperados do backend.")
            if checkout.get("redirect_url"):
                st.link_button("Abrir pagamento no Asaas", checkout["redirect_url"], use_container_width=True)
        elif checkout_status == "concluido":
            st.success("Este checkout ja foi concluido e recuperado do backend.")
        elif checkout_status == "cancelado":
            st.warning("Este checkout foi cancelado. Escolha um plano novamente para iniciar uma nova cobranca.")

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
            continuar_desabilitado = cupom_invalido or checkout_bloqueado
            if st.button("Continuar para pagamento", type="primary", use_container_width=True, disabled=continuar_desabilitado):
                LOGGER.info(
                    "[CHECKOUT] Clique no botao Continuar para pagamento | usuario_id=%s checkout_id=%s plano_codigo=%s tipo_usuario=%s cupom=%s valor_bruto=%s valor_desconto=%s valor_final=%s pagina=%s",
                    usuario.get("id"),
                    checkout.get("id"),
                    plano.get("codigo"),
                    usuario.get("tipo_usuario"),
                    checkout.get("cupom_codigo") or "",
                    checkout.get("valor_bruto"),
                    checkout.get("valor_desconto"),
                    checkout.get("valor_final"),
                    "pages/pagamento_manual.py",
                )
                assinatura, mensagem = assinar_plano_manual(
                    usuario,
                    plano["codigo"],
                    cupom_codigo=checkout.get("cupom_codigo"),
                    checkout_id=checkout.get("id"),
                )
                if assinatura:
                    LOGGER.info(
                        "[CHECKOUT] Checkout retornou sucesso para a UI | usuario_id=%s checkout_id=%s assinatura_id=%s gateway=%s status=%s",
                        usuario.get("id"),
                        assinatura.get("checkout_id") or checkout.get("id"),
                        assinatura.get("id"),
                        assinatura.get("gateway"),
                        assinatura.get("status"),
                    )
                    redirect_url = (assinatura.get("redirect_url") or assinatura.get("invoice_url") or "").strip()
                    fluxo_asaas = assinatura.get("gateway") == "asaas" and plano.get("tipo_plano") == "atleta"
                    if fluxo_asaas and redirect_url:
                        st.session_state["checkout_id"] = assinatura.get("checkout_id") or checkout.get("id")
                        st.session_state["plano_checkout"] = plano.get("codigo")
                        LOGGER.info(
                            "[CHECKOUT_ASAAS] Redirecionando usuario para invoiceUrl do Asaas | usuario_id=%s checkout_id=%s assinatura_id=%s asaas_payment_id=%s",
                            usuario.get("id"),
                            assinatura.get("checkout_id") or checkout.get("id"),
                            assinatura.get("id"),
                            assinatura.get("asaas_payment_id"),
                        )
                        _redirecionar_para_pagamento_asaas(redirect_url, mensagem)
                        st.stop()
                    if fluxo_asaas:
                        LOGGER.warning(
                            "[CHECKOUT_ASAAS] Assinatura criada sem invoiceUrl para redirecionamento imediato | usuario_id=%s checkout_id=%s assinatura_id=%s",
                            usuario.get("id"),
                            assinatura.get("checkout_id") or checkout.get("id"),
                            assinatura.get("id"),
                        )
                        st.warning(mensagem)
                        if st.button("Ir para Minha Assinatura", type="primary", use_container_width=True, key="checkout_ir_minha_assinatura"):
                            _ir_para("pages/minha_assinatura.py")
                        st.stop()
                    st.success(mensagem)
                    st.session_state.pop("checkout_id", None)
                    st.session_state.pop("checkout_external_reference", None)
                    st.session_state.pop("plano_checkout", None)
                    _ir_para("pages/minha_assinatura.py")
                else:
                    LOGGER.error(
                        "[CHECKOUT_ERROR] Checkout retornou falha para a UI | usuario_id=%s checkout_id=%s plano_codigo=%s mensagem=%s",
                        usuario.get("id"),
                        checkout.get("id"),
                        plano.get("codigo"),
                        mensagem,
                    )
                    st.error(f"{mensagem} Verifique os logs com os marcadores CHECKOUT_ERROR/CHECKOUT_ASAAS.")
        with col_voltar:
            if st.button("Voltar para planos", use_container_width=True):
                _ir_para("pages/planos.py")
