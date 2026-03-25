from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.financeiro import (
    alterar_status_plano,
    aplicar_desconto_manual_admin,
    atualizar_plano_admin,
    atualizar_status_assinatura_admin,
    atualizar_status_pagamento,
    buscar_plano_por_id,
    duplicar_plano,
    gerar_resumo_financeiro_admin,
    listar_assinaturas_admin_filtradas,
    listar_cobrancas_alunos_admin,
    listar_cupons_desconto,
    listar_descontos_aplicados_admin,
    listar_fechamentos_treinadores,
    listar_historico_financeiro_usuario,
    listar_pagamentos_admin,
    listar_planos_admin,
    listar_treinadores_financeiro_admin,
    salvar_cupom_desconto,
    salvar_plano_admin,
    serie_financeira_admin,
    trocar_plano_assinatura_admin,
)
from core.pagamentos_gateway import resumo_operacional_asaas, testar_conexao_asaas, validar_configuracao_asaas
from core.permissoes import validar_admin


def _formatar_data(valor):
    if not valor:
        return "-"
    return str(valor).replace("T", " ")[:19]


def _formatar_moeda(valor):
    return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _formatar_percentual(valor):
    return "-" if valor is None else f"{float(valor):.1f}%"


def _sincronizar_editor_plano():
    plano_selecionado = st.session_state["financeiro_plano_editor_id"]
    st.session_state["financeiro_plano_editor_alvo_id"] = plano_selecionado
    st.session_state["financeiro_plano_editor_plano_id"] = None if plano_selecionado == "novo" else int(plano_selecionado)


def _render_cards(metricas):
    for inicio in range(0, len(metricas), 4):
        cols = st.columns(min(4, len(metricas) - inicio))
        for col, item in zip(cols, metricas[inicio:inicio + 4]):
            with col:
                st.markdown(
                    f"""
                    <div style="border-radius:22px;border:1px solid var(--tri-border);background:color-mix(in srgb, var(--tri-surface) 96%, transparent);padding:1rem 1.05rem;box-shadow:var(--tri-shadow-soft);margin-bottom:.85rem">
                        <div style="font-size:.82rem;color:var(--tri-text-soft);margin-bottom:.25rem">{item['titulo']}</div>
                        <div style="font-size:1.55rem;font-weight:800;color:var(--tri-text-strong)">{item['valor']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _render_visao_geral():
    resumo = gerar_resumo_financeiro_admin()
    _render_cards([
        {"titulo": "Receita do Mes", "valor": _formatar_moeda(resumo.get("receita_mes"))},
        {"titulo": "Receita Recorrente Prevista", "valor": _formatar_moeda(resumo.get("receita_recorrente_prevista"))},
        {"titulo": "Assinaturas Ativas", "valor": int(resumo.get("assinaturas_ativas") or 0)},
        {"titulo": "Assinaturas Inadimplentes", "valor": int(resumo.get("assinaturas_inadimplentes") or 0)},
        {"titulo": "Trials", "valor": int(resumo.get("assinaturas_trial") or 0)},
        {"titulo": "Bonificacoes", "valor": int(resumo.get("total_bonificacoes") or 0)},
        {"titulo": "Descontos Aplicados", "valor": _formatar_moeda(resumo.get("total_descontos_aplicados"))},
        {"titulo": "Treinadores Ativos", "valor": int(resumo.get("total_treinadores_ativos") or 0)},
        {"titulo": "Atletas Solo Ativos", "valor": int(resumo.get("total_atletas_solo_ativos") or 0)},
        {"titulo": "Alunos Ativos Vinculados", "valor": int(resumo.get("total_alunos_ativos_vinculados") or 0)},
        {"titulo": "Ticket Medio Treinador", "valor": _formatar_moeda(resumo.get("ticket_medio_treinador"))},
        {"titulo": "Ticket Medio Atleta", "valor": _formatar_moeda(resumo.get("ticket_medio_atleta"))},
    ])

    serie = pd.DataFrame(serie_financeira_admin())
    if serie.empty:
        st.info("Ainda nao ha dados suficientes para os graficos financeiros.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Receita e descontos por mes")
        st.line_chart(
            serie.set_index("periodo")[["receita", "descontos_aplicados"]],
            use_container_width=True,
        )
    with col2:
        st.markdown("#### Assinaturas, cancelamentos e inadimplencia")
        st.bar_chart(
            serie.set_index("periodo")[["novas_assinaturas", "cancelamentos", "inadimplentes"]],
            use_container_width=True,
        )

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("#### Crescimento de treinadores e atletas")
        st.line_chart(
            serie.set_index("periodo")[["crescimento_treinadores", "crescimento_atletas"]],
            use_container_width=True,
        )
    with col4:
        st.markdown("#### Base consolidada")
        tabela = serie.rename(
            columns={
                "periodo": "Periodo",
                "receita": "Receita",
                "novas_assinaturas": "Novas Assinaturas",
                "cancelamentos": "Cancelamentos",
                "inadimplentes": "Inadimplentes",
                "descontos_aplicados": "Descontos",
                "crescimento_treinadores": "Treinadores",
                "crescimento_atletas": "Atletas",
            }
        )
        st.dataframe(tabela, use_container_width=True, hide_index=True)


def _render_planos(admin, registrar_log_admin):
    planos = listar_planos_admin(incluir_inativos=True)
    st.dataframe(pd.DataFrame([{
        "ID": p["id"],
        "Ordem": p.get("ordem_exibicao", 0),
        "Nome": p["nome"],
        "Codigo": p["codigo"],
        "Tipo": p["tipo_plano"],
        "Periodicidade": p["periodicidade"],
        "Valor Base": _formatar_moeda(p["valor_base"]),
        "Taxa/Aluno": _formatar_moeda(p["taxa_por_aluno_ativo"]),
        "Ativo": "Sim" if p.get("ativo") else "Nao",
    } for p in planos]), use_container_width=True, hide_index=True)

    with st.expander("Criar ou editar plano", expanded=False):
        opcoes_planos = ["novo"] + [p["id"] for p in planos]
        alvo_editor = st.session_state.get("financeiro_plano_editor_alvo_id", "novo")
        if alvo_editor not in opcoes_planos:
            alvo_editor = "novo"
            st.session_state["financeiro_plano_editor_alvo_id"] = alvo_editor
        if st.session_state.get("financeiro_plano_editor_id") != alvo_editor:
            st.session_state["financeiro_plano_editor_id"] = alvo_editor
        plano_selecionado = st.selectbox(
            "Plano para editar",
            opcoes_planos,
            format_func=lambda valor: "Novo plano" if valor == "novo" else next(f"{p['nome']} ({p['codigo']})" for p in planos if p["id"] == valor),
            key="financeiro_plano_editor_id",
            on_change=_sincronizar_editor_plano,
        )
        plano_id_em_edicao = None if plano_selecionado == "novo" else int(plano_selecionado)
        st.session_state["financeiro_plano_editor_alvo_id"] = plano_selecionado
        st.session_state["financeiro_plano_editor_plano_id"] = plano_id_em_edicao
        plano = next((p for p in planos if p["id"] == plano_id_em_edicao), None)
        sufixo_form = str(plano_selecionado)
        with st.form(f"form_plano_admin_{sufixo_form}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                codigo = st.text_input("Codigo", value=plano.get("codigo") if plano else "", key=f"financeiro_plano_codigo_{sufixo_form}")
                nome = st.text_input("Nome", value=plano.get("nome") if plano else "", key=f"financeiro_plano_nome_{sufixo_form}")
                tipo_plano = st.selectbox(
                    "Tipo",
                    ["atleta", "treinador"],
                    index=["atleta", "treinador"].index(plano.get("tipo_plano", "atleta") if plano else "atleta"),
                    key=f"financeiro_plano_tipo_{sufixo_form}",
                )
            with col2:
                periodicidade = st.selectbox(
                    "Periodicidade",
                    ["mensal", "anual"],
                    index=["mensal", "anual"].index(plano.get("periodicidade", "mensal") if plano else "mensal"),
                    key=f"financeiro_plano_periodicidade_{sufixo_form}",
                )
                valor_base = st.number_input(
                    "Valor base",
                    min_value=0.0,
                    value=float(plano.get("valor_base") or 0.0) if plano else 0.0,
                    step=10.0,
                    key=f"financeiro_plano_valor_{sufixo_form}",
                )
                taxa_por_aluno = st.number_input(
                    "Taxa por aluno ativo",
                    min_value=0.0,
                    value=float(plano.get("taxa_por_aluno_ativo") or 0.0) if plano else 0.0,
                    step=5.0,
                    key=f"financeiro_plano_taxa_{sufixo_form}",
                )
            with col3:
                ordem_exibicao = st.number_input(
                    "Ordem de exibicao",
                    min_value=0,
                    value=int(plano.get("ordem_exibicao") or 0) if plano else 0,
                    step=1,
                    key=f"financeiro_plano_ordem_{sufixo_form}",
                )
                limite_atletas = st.number_input(
                    "Limite atletas (0 sem limite)",
                    min_value=0,
                    value=int(plano.get("limite_atletas") or 0) if plano and plano.get("limite_atletas") else 0,
                    step=1,
                    key=f"financeiro_plano_limite_{sufixo_form}",
                )
                ativo = st.checkbox("Ativo", value=bool(plano.get("ativo", 1)) if plano else True, key=f"financeiro_plano_ativo_{sufixo_form}")
            descricao = st.text_area("Descricao", value=plano.get("descricao") if plano else "", key=f"financeiro_plano_descricao_{sufixo_form}")
            beneficios = st.text_area("Beneficios", value=plano.get("beneficios") if plano else "", key=f"financeiro_plano_beneficios_{sufixo_form}")
            salvar = st.form_submit_button("Salvar plano", use_container_width=True)
        if salvar:
            payload = {
                "codigo": codigo,
                "nome": nome,
                "tipo_plano": tipo_plano,
                "periodicidade": periodicidade,
                "valor_base": valor_base,
                "taxa_por_aluno_ativo": taxa_por_aluno,
                "descricao": descricao,
                "beneficios": beneficios,
                "ordem_exibicao": ordem_exibicao,
                "limite_atletas": limite_atletas or None,
                "ativo": ativo,
            }
            try:
                plano_id_para_salvar = st.session_state.get("financeiro_plano_editor_plano_id")
                if plano_id_para_salvar is not None:
                    if not buscar_plano_por_id(plano_id_para_salvar):
                        raise ValueError("Plano selecionado nao foi encontrado para edicao.")
                    plano_salvo = atualizar_plano_admin(plano_id_para_salvar, payload)
                else:
                    plano_salvo = salvar_plano_admin(payload)
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Nao foi possivel salvar o plano: {exc}")
            else:
                st.session_state["financeiro_plano_editor_alvo_id"] = plano_salvo["id"]
                st.session_state["financeiro_plano_editor_id"] = plano_salvo["id"]
                st.session_state["financeiro_plano_editor_plano_id"] = plano_salvo["id"]
                registrar_log_admin(admin["id"], "salvou plano financeiro", "plano", plano_salvo["id"], plano_salvo["codigo"])
                st.success("Plano salvo com sucesso.")
                st.rerun()

    if planos:
        col_a, col_b = st.columns(2)
        plano_acao_id = st.selectbox("Selecionar plano", [p["id"] for p in planos], format_func=lambda valor: next(f"{p['nome']} ({p['codigo']})" for p in planos if p["id"] == valor))
        with col_a:
            if st.button("Duplicar plano", use_container_width=True):
                novo = duplicar_plano(plano_acao_id)
                registrar_log_admin(admin["id"], "duplicou plano financeiro", "plano", plano_acao_id, novo["codigo"])
                st.success("Plano duplicado.")
                st.rerun()
        with col_b:
            plano_alvo = buscar_plano_por_id(plano_acao_id)
            if st.button("Ativar/Desativar plano", use_container_width=True):
                alterar_status_plano(plano_acao_id, not bool(plano_alvo.get("ativo")))
                registrar_log_admin(admin["id"], "alterou status do plano", "plano", plano_acao_id, plano_alvo["codigo"])
                st.success("Status do plano atualizado.")
                st.rerun()


def _render_cupons_promocoes(admin, registrar_log_admin):
    cupons = listar_cupons_desconto()
    descontos = listar_descontos_aplicados_admin()
    col1, col2 = st.columns([1.1, 1])
    with col1:
        st.markdown("#### Cupons e promocoes")
        if cupons:
            st.dataframe(pd.DataFrame(cupons), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cupom cadastrado.")
    with col2:
        st.markdown("#### Historico de descontos aplicados")
        if descontos:
            st.dataframe(pd.DataFrame(descontos), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum desconto aplicado ainda.")

    with st.form("form_cupom_promocao_admin"):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            codigo = st.text_input("Codigo do cupom")
            tipo_desconto = st.selectbox("Tipo desconto", ["percentual", "valor_fixo", "gratuidade"])
            aplicavel_para = st.selectbox("Aplicavel para", ["todos", "atleta", "treinador"])
        with col_b:
            descricao = st.text_input("Descricao")
            percentual_desconto = st.number_input("Percentual", min_value=0.0, max_value=100.0, value=0.0, step=5.0)
            periodicidade_aplicavel = st.selectbox("Periodicidade", ["todos", "mensal", "anual"])
        with col_c:
            valor_desconto = st.number_input("Valor fixo", min_value=0.0, value=0.0, step=10.0)
            quantidade_max_uso = st.number_input("Maximo de usos", min_value=0, value=0, step=1)
            ativo = st.checkbox("Ativo", value=True)
        data_inicio = st.date_input("Data inicio", value=date.today(), key="financeiro_cupom_inicio")
        data_fim = st.date_input("Data fim", value=date.today() + timedelta(days=60), key="financeiro_cupom_fim")
        salvar = st.form_submit_button("Salvar cupom/promocao", use_container_width=True)
    if salvar:
        cupom = salvar_cupom_desconto({
            "codigo": codigo,
            "descricao": descricao,
            "tipo_desconto": tipo_desconto,
            "valor_desconto": valor_desconto,
            "percentual_desconto": percentual_desconto,
            "aplicavel_para": aplicavel_para,
            "periodicidade_aplicavel": periodicidade_aplicavel,
            "quantidade_max_uso": quantidade_max_uso or None,
            "ativo": ativo,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        })
        registrar_log_admin(admin["id"], "salvou cupom/promocao", "cupom", cupom["id"], cupom["codigo"])
        st.success("Cupom salvo com sucesso.")
        st.rerun()

    st.markdown("#### Aplicar desconto manual")
    with st.form("form_desconto_manual_admin"):
        col_x, col_y, col_z = st.columns(3)
        with col_x:
            usuario_id = st.number_input("Usuario ID", min_value=1, value=1, step=1)
            assinatura_id = st.number_input("Assinatura ID (opcional)", min_value=0, value=0, step=1)
        with col_y:
            pagamento_id = st.number_input("Pagamento ID (opcional)", min_value=0, value=0, step=1)
            tipo_desconto = st.selectbox("Tipo", ["valor_fixo", "percentual", "gratuidade"], key="manual_desconto_tipo")
        with col_z:
            valor_desconto = st.number_input("Valor desconto", min_value=0.0, value=0.0, step=10.0, key="manual_desconto_valor")
            percentual_desconto = st.number_input("Percentual desconto", min_value=0.0, max_value=100.0, value=0.0, step=5.0, key="manual_desconto_percentual")
        aplicar = st.form_submit_button("Aplicar desconto manual", use_container_width=True)
    if aplicar:
        desconto = aplicar_desconto_manual_admin(
            usuario_id=int(usuario_id),
            assinatura_id=int(assinatura_id) or None,
            pagamento_id=int(pagamento_id) or None,
            tipo_desconto=tipo_desconto,
            valor_desconto=valor_desconto,
            percentual_desconto=percentual_desconto,
            aplicado_por="admin",
        )
        registrar_log_admin(admin["id"], "aplicou desconto manual", "desconto", desconto["id"], f"usuario={usuario_id}")
        st.success("Desconto manual aplicado.")
        st.rerun()


def _render_assinaturas(admin, registrar_log_admin):
    planos = listar_planos_admin()
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        tipo_usuario = st.selectbox("Tipo usuario", ["", "atleta", "treinador"], format_func=lambda x: x or "Todos", key="assinaturas_tipo")
    with col2:
        status = st.selectbox("Status", ["", "trial", "pendente", "ativa", "inadimplente", "cancelada", "expirada"], format_func=lambda x: x or "Todos", key="assinaturas_status")
    with col3:
        plano_id = st.selectbox("Plano", [0] + [p["id"] for p in planos], format_func=lambda x: "Todos" if x == 0 else next(p["nome"] for p in planos if p["id"] == x), key="assinaturas_plano")
    with col4:
        data_inicio = st.date_input("Periodo inicial", value=date.today() - timedelta(days=120), key="assinaturas_inicio")
    with col5:
        data_fim = st.date_input("Periodo final", value=date.today(), key="assinaturas_fim")
    with col6:
        com_desconto = st.selectbox("Com desconto", ["todos", "sim", "nao"], key="assinaturas_desconto")

    itens = listar_assinaturas_admin_filtradas(
        tipo_usuario=tipo_usuario or None,
        status=status or None,
        plano_id=plano_id or None,
        periodo_inicio=data_inicio.isoformat(),
        periodo_fim=data_fim.isoformat(),
        com_desconto=True if com_desconto == "sim" else None,
        somente_trial=False,
    )
    st.dataframe(pd.DataFrame([{
        "ID": item["id"],
        "Usuario": item.get("usuario_nome"),
        "Tipo": item.get("tipo_usuario"),
        "Plano": item.get("plano_nome"),
        "Status": item.get("status"),
        "Inicio": item.get("data_inicio"),
        "Renovacao": item.get("data_renovacao"),
        "Base": _formatar_moeda(item.get("valor_base_cobrado")),
        "Alunos Fech.": int(item.get("quantidade_alunos_ativos_fechamento") or 0),
        "Taxa Alunos": _formatar_moeda(item.get("valor_taxa_alunos")),
        "Total": _formatar_moeda(item.get("valor_total_cobrado")),
        "Desconto": _formatar_moeda(item.get("desconto_total")),
        "Valor Final": _formatar_moeda(item.get("valor_final")),
    } for item in itens]), use_container_width=True, hide_index=True)

    if not itens:
        return
    assinatura_id = st.selectbox("Selecionar assinatura", [item["id"] for item in itens], format_func=lambda x: next(f"{item['usuario_nome']} | {item['plano_nome']} | {item['status']}" for item in itens if item["id"] == x))
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        novo_status = st.selectbox("Novo status assinatura", ["trial", "pendente", "ativa", "inadimplente", "cancelada", "expirada"])
        if st.button("Atualizar status assinatura", use_container_width=True):
            atualizar_status_assinatura_admin(assinatura_id, novo_status)
            registrar_log_admin(admin["id"], "alterou status da assinatura", "assinatura", assinatura_id, novo_status)
            st.success("Status da assinatura atualizado.")
            st.rerun()
    with col_b:
        novo_plano_id = st.selectbox("Trocar plano", [p["id"] for p in planos], format_func=lambda x: next(p["nome"] for p in planos if p["id"] == x))
        if st.button("Trocar plano da assinatura", use_container_width=True):
            trocar_plano_assinatura_admin(assinatura_id, novo_plano_id)
            registrar_log_admin(admin["id"], "trocou plano da assinatura", "assinatura", assinatura_id, f"plano={novo_plano_id}")
            st.success("Plano da assinatura atualizado.")
            st.rerun()
    with col_c:
        if st.button("Bonificar proxima cobranca", use_container_width=True):
            assinatura = next(item for item in itens if item["id"] == assinatura_id)
            aplicar_desconto_manual_admin(
                usuario_id=assinatura["usuario_id"],
                assinatura_id=assinatura_id,
                tipo_desconto="gratuidade",
                aplicado_por="admin",
            )
            registrar_log_admin(admin["id"], "bonificou assinatura", "assinatura", assinatura_id, "gratuidade")
            st.success("Bonificacao registrada.")
            st.rerun()


def _render_pagamentos(admin, registrar_log_admin):
    planos = listar_planos_admin()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        status = st.selectbox("Status pagamento", ["", "pago", "pendente", "atrasado", "cancelado", "estornado", "bonificado"], format_func=lambda x: x or "Todos", key="pagamentos_status")
    with col2:
        tipo_usuario = st.selectbox("Tipo usuario", ["", "atleta", "treinador"], format_func=lambda x: x or "Todos", key="pagamentos_tipo")
    with col3:
        plano_id = st.selectbox("Plano", [0] + [p["id"] for p in planos], format_func=lambda x: "Todos" if x == 0 else next(p["nome"] for p in planos if p["id"] == x), key="pagamentos_plano")
    with col4:
        data_inicio = st.date_input("Vencimento de", value=date.today() - timedelta(days=90), key="pagamentos_inicio")
    with col5:
        data_fim = st.date_input("Vencimento ate", value=date.today(), key="pagamentos_fim")

    pagamentos = listar_pagamentos_admin(status or None, tipo_usuario or None, data_inicio.isoformat(), data_fim.isoformat(), plano_id or None)
    st.dataframe(pd.DataFrame([{
        "ID": p["id"],
        "Usuario": p.get("usuario_nome"),
        "Tipo": p.get("tipo_usuario"),
        "Plano": p.get("plano_nome"),
        "Valor Bruto": _formatar_moeda(p.get("valor_bruto")),
        "Desconto": _formatar_moeda(p.get("valor_desconto")),
        "Valor Final": _formatar_moeda(p.get("valor_final")),
        "Vencimento": _formatar_data(p.get("data_vencimento")),
        "Pagamento": _formatar_data(p.get("data_pagamento")),
        "Status": p.get("status"),
        "Metodo": p.get("metodo_pagamento"),
        "Referencia": p.get("referencia_externa"),
    } for p in pagamentos]), use_container_width=True, hide_index=True)

    if not pagamentos:
        return
    pagamento_id = st.selectbox("Selecionar pagamento", [p["id"] for p in pagamentos], format_func=lambda x: next(f"{p['usuario_nome']} | {p['status']} | {p['id']}" for p in pagamentos if p["id"] == x))
    col_a, col_b = st.columns([1, 1.4])
    with col_a:
        novo_status = st.selectbox("Nova acao", ["pago", "cancelado", "atrasado", "pendente", "estornado", "bonificado"], key="pagamentos_novo_status")
        if st.button("Aplicar status no pagamento", use_container_width=True):
            atualizar_status_pagamento(pagamento_id, novo_status)
            registrar_log_admin(admin["id"], "alterou status do pagamento", "pagamento", pagamento_id, novo_status)
            st.success("Pagamento atualizado.")
            st.rerun()
    with col_b:
        usuario_id = next(p["usuario_id"] for p in pagamentos if p["id"] == pagamento_id)
        historico = listar_historico_financeiro_usuario(usuario_id)
        st.markdown("#### Historico financeiro do usuario")
        st.dataframe(pd.DataFrame(historico), use_container_width=True, hide_index=True)


def _render_treinadores(admin, registrar_log_admin):
    itens = listar_treinadores_financeiro_admin()
    st.dataframe(pd.DataFrame([{
        "Treinador": item.get("treinador_nome"),
        "Email": item.get("treinador_email"),
        "Plano Atual": item.get("plano_nome"),
        "Valor Base": _formatar_moeda(item.get("valor_base")),
        "Taxa/Aluno": _formatar_moeda(item.get("taxa_por_aluno_ativo")),
        "Alunos Atuais": int(item.get("alunos_ativos_atualmente") or 0),
        "Alunos no Fechamento": int(item.get("alunos_fechamento") or 0),
        "Proximo Ciclo": _formatar_moeda(item.get("valor_previsto_proximo_ciclo")),
        "Status": item.get("assinatura_status"),
        "Renovacao": _formatar_data(item.get("data_renovacao")),
    } for item in itens]), use_container_width=True, hide_index=True)
    if not itens:
        return
    treinador_id = st.selectbox("Selecionar treinador", [item["treinador_id"] for item in itens], format_func=lambda x: next(item["treinador_nome"] for item in itens if item["treinador_id"] == x))
    treinador = next(item for item in itens if item["treinador_id"] == treinador_id)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Detalhes financeiros")
        st.json(treinador)
    with col2:
        st.markdown("#### Historico financeiro")
        st.dataframe(pd.DataFrame(listar_historico_financeiro_usuario(treinador_id)), use_container_width=True, hide_index=True)
    if treinador.get("assinatura_id") and st.button("Bonificar treinador selecionado", use_container_width=True):
        aplicar_desconto_manual_admin(
            usuario_id=treinador_id,
            assinatura_id=treinador["assinatura_id"],
            tipo_desconto="gratuidade",
            aplicado_por="admin",
        )
        registrar_log_admin(admin["id"], "bonificou treinador", "usuario", treinador_id, treinador["treinador_nome"])
        st.success("Bonificacao aplicada ao treinador.")
        st.rerun()


def _render_cobrancas_alunos():
    itens = listar_cobrancas_alunos_admin()
    if not itens:
        st.info("Nenhuma cobranca de aluno registrada.")
        return
    st.dataframe(pd.DataFrame([{
        "Treinador": item.get("treinador_nome"),
        "Atleta": item.get("atleta_nome"),
        "Descricao": item.get("descricao"),
        "Valor": _formatar_moeda(item.get("valor")),
        "Periodicidade": item.get("periodicidade"),
        "Status": item.get("status"),
        "Vencimento": _formatar_data(item.get("data_vencimento")),
        "Pagamento": _formatar_data(item.get("data_pagamento")),
    } for item in itens]), use_container_width=True, hide_index=True)


def _render_fechamentos():
    itens = listar_fechamentos_treinadores()
    if not itens:
        st.info("Nenhum fechamento de treinador disponivel ainda.")
        return
    st.dataframe(pd.DataFrame([{
        "Treinador": item.get("treinador_nome"),
        "Renovacao": _formatar_data(item.get("data_renovacao")),
        "Plano Base": item.get("plano_nome"),
        "Valor Base": _formatar_moeda(item.get("valor_base_cobrado")),
        "Alunos Fechamento": int(item.get("quantidade_alunos_ativos_fechamento") or 0),
        "Taxa Alunos": _formatar_moeda(item.get("valor_taxa_alunos")),
        "Valor Total": _formatar_moeda(item.get("valor_total_cobrado")),
        "Desconto": _formatar_moeda(item.get("desconto_aplicado")),
        "Valor Final": _formatar_moeda(item.get("valor_final_cobrado")),
    } for item in itens]), use_container_width=True, hide_index=True)


def _render_relatorios():
    serie = pd.DataFrame(serie_financeira_admin())
    if serie.empty:
        st.info("Sem dados para relatorios financeiros.")
        return
    st.markdown("#### Serie financeira consolidada")
    st.dataframe(serie, use_container_width=True, hide_index=True)


def _render_asaas():
    config = validar_configuracao_asaas()
    conexao = testar_conexao_asaas() if config.get("ok") else {"sucesso": False, "mensagem": config.get("mensagem")}
    resumo = resumo_operacional_asaas() if config.get("ok") else {"ultimos_webhooks": []}
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Configuracao", "OK" if config.get("ok") else "Pendente")
    with col2:
        st.metric("Conexao", "Online" if conexao.get("sucesso") else "Erro")
    with col3:
        st.metric("Customers", int(resumo.get("total_customers") or 0))
    with col4:
        st.metric("Webhooks", int(resumo.get("total_webhooks") or 0))
    st.caption(conexao.get("mensagem") or "")
    eventos = resumo.get("ultimos_webhooks") or []
    if eventos:
        st.dataframe(pd.DataFrame(eventos), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum evento de webhook Asaas registrado.")


def render_financeiro_admin(admin, registrar_log_admin):
    validar_admin(admin)
    st.markdown("## Financeiro Admin")
    st.caption("Operacao financeira, precificacao, descontos, assinaturas, pagamentos e visao executiva do negocio.")
    abas = st.tabs([
        "Visao Geral",
        "Planos",
        "Cupons e Promocoes",
        "Assinaturas",
        "Pagamentos",
        "Treinadores",
        "Cobrancas dos Alunos",
        "Fechamentos",
        "Relatorios",
        "Asaas Sandbox",
    ])
    with abas[0]:
        _render_visao_geral()
    with abas[1]:
        _render_planos(admin, registrar_log_admin)
    with abas[2]:
        _render_cupons_promocoes(admin, registrar_log_admin)
    with abas[3]:
        _render_assinaturas(admin, registrar_log_admin)
    with abas[4]:
        _render_pagamentos(admin, registrar_log_admin)
    with abas[5]:
        _render_treinadores(admin, registrar_log_admin)
    with abas[6]:
        _render_cobrancas_alunos()
    with abas[7]:
        _render_fechamentos()
    with abas[8]:
        _render_relatorios()
    with abas[9]:
        _render_asaas()
