from datetime import date, datetime, timedelta
import secrets

import pandas as pd
import streamlit as st

from core.admin_financeiro import render_financeiro_admin
from core.banco import conectar
from core.financeiro import (
    atualizar_status_pagamento as financeiro_atualizar_status_pagamento,
    listar_cupons_desconto,
    listar_historico_financeiro_usuario,
    listar_pagamentos_admin as financeiro_listar_pagamentos_admin,
    listar_planos_ativos,
    resumo_financeiro_admin as financeiro_resumo_financeiro_admin,
    salvar_cupom_desconto,
)
from core.pagamentos_gateway import resumo_operacional_asaas, testar_conexao_asaas, validar_configuracao_asaas
from core.permissoes import validar_admin
from core.usuarios import (
    alterar_papel_usuario_por_admin,
    atualizar_status_conta,
    listar_usuarios,
    redefinir_senha_usuario,
)


def _fetch_all(sql, params=()):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return rows


def _fetch_one(sql, params=()):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _execute(sql, params=()):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    conn.close()


def registrar_log_admin(admin_id, acao, alvo_tipo, alvo_id=None, detalhes=None):
    _execute(
        """
        INSERT INTO admin_logs (admin_id, acao, alvo_tipo, alvo_id, detalhes)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (admin_id, acao, alvo_tipo, alvo_id, detalhes),
    )


def _aplicar_estilo_admin():
    st.markdown(
        """
        <style>
        .admin-hero{padding:1.2rem 1.25rem;border-radius:28px;background:radial-gradient(circle at top right, color-mix(in srgb, var(--tri-text-on-header) 12%, transparent), transparent 24%),linear-gradient(135deg,var(--tri-header-start) 0%,var(--tri-primary) 55%,var(--tri-header-end) 100%);color:var(--tri-text-on-header);box-shadow:var(--tri-shadow-strong);margin-bottom:1rem}
        .admin-hero h1{margin:0;color:var(--tri-text-on-header);font-size:2rem}
        .admin-hero p{margin:.35rem 0 0;color:color-mix(in srgb, var(--tri-text-on-header) 80%, transparent)}
        .admin-card{border-radius:22px;border:1px solid var(--tri-border);background:color-mix(in srgb, var(--tri-surface) 96%, transparent);padding:1rem 1.05rem;box-shadow:var(--tri-shadow-soft);margin-bottom:.85rem}
        .admin-card strong{display:block;font-size:1.55rem;color:var(--tri-text-strong)}
        .admin-card span{color:var(--tri-text-soft);font-size:.92rem}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _formatar_data(valor):
    if not valor:
        return "-"
    return str(valor).replace("T", " ")[:19]


def _formatar_percentual(valor):
    return "-" if valor is None else f"{float(valor):.1f}%"


def _formatar_moeda(valor):
    return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cards_metricas(metricas):
    for inicio in range(0, len(metricas), 4):
        cols = st.columns(min(4, len(metricas) - inicio))
        for col, item in zip(cols, metricas[inicio:inicio + 4]):
            with col:
                st.markdown(
                    f"<div class='admin-card'><strong>{item['valor']}</strong><span>{item['titulo']}</span></div>",
                    unsafe_allow_html=True,
                )


def _obter_dashboard_admin():
    return _fetch_one(
        """
        WITH ur AS (
            SELECT
                COUNT(*) AS total_usuarios,
                COUNT(*) FILTER (WHERE tipo_usuario = 'atleta') AS total_atletas,
                COUNT(*) FILTER (WHERE tipo_usuario = 'treinador') AS total_treinadores,
                COUNT(*) FILTER (WHERE tipo_usuario = 'admin') AS total_admins
            FROM usuarios
        ),
        ast AS (
            SELECT COUNT(*) AS atletas_sem_treinador
            FROM usuarios u
            WHERE u.tipo_usuario = 'atleta'
              AND NOT EXISTS (
                  SELECT 1 FROM treinador_atleta ta
                  WHERE ta.atleta_id = u.id AND ta.status = 'ativo'
              )
        ),
        vr AS (
            SELECT
                COUNT(DISTINCT atleta_id) FILTER (WHERE status = 'ativo') AS atletas_vinculados,
                AVG(qtd) AS media_atletas_por_treinador
            FROM (
                SELECT treinador_id, COUNT(*) FILTER (WHERE status = 'ativo') AS qtd
                FROM treinador_atleta
                GROUP BY treinador_id
            ) base
            FULL JOIN treinador_atleta ta ON ta.treinador_id = base.treinador_id
        ),
        ar AS (
            SELECT
                COUNT(*) FILTER (WHERE status = 'ativa') AS assinaturas_ativas,
                COUNT(*) FILTER (WHERE status = 'trial') AS assinaturas_trial,
                COUNT(*) FILTER (WHERE status = 'inadimplente') AS assinaturas_inadimplentes
            FROM assinaturas
        ),
        ts AS (
            SELECT COUNT(*) AS concluidos_semana
            FROM treinos_realizados
            WHERE feito = 1
              AND COALESCE(data_realizada, feito_em) >= CURRENT_DATE - INTERVAL '7 days'
        ),
        ad AS (
            SELECT ROUND(100.0 * COALESCE(SUM(realizados.concluidos), 0) / NULLIF(SUM(planejados.total), 0), 1) AS media_aderencia
            FROM (
                SELECT COALESCE(atleta_id, usuario_id) AS atleta_ref, semana_numero, COUNT(*) FILTER (WHERE feito = 1) AS concluidos
                FROM treinos_realizados
                GROUP BY COALESCE(atleta_id, usuario_id), semana_numero
            ) realizados
            FULL JOIN (
                SELECT COALESCE(atleta_id, usuario_id) AS atleta_ref, semana_numero, COUNT(*) AS total
                FROM treinos_gerados tg, LATERAL jsonb_object_keys(tg.json_treino::jsonb) chave
                GROUP BY COALESCE(atleta_id, usuario_id), semana_numero
            ) planejados
            ON planejados.atleta_ref = realizados.atleta_ref
           AND planejados.semana_numero = realizados.semana_numero
        )
        SELECT ur.*, ast.atletas_sem_treinador, COALESCE(vr.atletas_vinculados, 0) AS atletas_vinculados,
               ar.assinaturas_ativas, ar.assinaturas_trial, ar.assinaturas_inadimplentes,
               ROUND(COALESCE(vr.media_atletas_por_treinador, 0), 2) AS media_atletas_por_treinador,
               ts.concluidos_semana, COALESCE(ad.media_aderencia, 0) AS media_aderencia
        FROM ur CROSS JOIN ast CROSS JOIN ar CROSS JOIN ts CROSS JOIN ad
        LEFT JOIN vr ON TRUE
        """
    ) or {}


def _serie_usuarios_por_mes():
    return _fetch_all(
        """
        SELECT TO_CHAR(DATE_TRUNC('month', data_criacao), 'YYYY-MM') AS periodo,
               COUNT(*) AS novos_usuarios,
               COUNT(*) FILTER (WHERE tipo_usuario = 'atleta') AS novos_atletas,
               COUNT(*) FILTER (WHERE tipo_usuario = 'treinador') AS novos_treinadores,
               COUNT(*) FILTER (WHERE tipo_usuario = 'admin') AS novos_admins
        FROM usuarios
        GROUP BY 1
        ORDER BY 1
        """
    )


def _serie_financeira_admin():
    return _fetch_all(
        """
        SELECT TO_CHAR(DATE_TRUNC('month', COALESCE(created_at, CURRENT_TIMESTAMP)), 'YYYY-MM') AS periodo,
               COUNT(*) FILTER (WHERE status = 'ativa') AS assinaturas_ativas,
               COUNT(*) FILTER (WHERE status = 'trial') AS trials,
               COUNT(*) FILTER (WHERE status = 'cancelada') AS cancelamentos,
               COUNT(*) FILTER (WHERE status = 'inadimplente') AS inadimplentes,
               SUM(CASE WHEN status IN ('ativa','cancelada','inadimplente') THEN COALESCE(valor, 0) ELSE 0 END) AS receita
        FROM assinaturas
        GROUP BY 1
        ORDER BY 1
        """
    )


def _serie_operacional_admin():
    return _fetch_all(
        """
        WITH planejado AS (
            SELECT DATE_TRUNC('week', COALESCE(created_at, CURRENT_TIMESTAMP))::date AS semana,
                   COUNT(*) AS total_planejado
            FROM treinos_gerados tg, LATERAL jsonb_object_keys(tg.json_treino::jsonb) chave
            GROUP BY 1
        ),
        concluido AS (
            SELECT DATE_TRUNC('week', COALESCE(data_realizada, feito_em))::date AS semana,
                   COUNT(*) FILTER (WHERE feito = 1) AS total_concluido
            FROM treinos_realizados
            GROUP BY 1
        )
        SELECT TO_CHAR(COALESCE(p.semana, c.semana), 'YYYY-MM-DD') AS semana,
               COALESCE(c.total_concluido, 0) AS treinos_concluidos,
               ROUND(100.0 * COALESCE(c.total_concluido, 0) / NULLIF(COALESCE(p.total_planejado, 0), 0), 1) AS aderencia_media
        FROM planejado p
        FULL JOIN concluido c ON c.semana = p.semana
        ORDER BY 1
        """
    )


def _listar_treinadores_admin():
    return _fetch_all(
        """
        WITH aderencia AS (
            SELECT planejado.atleta_id,
                   ROUND(100.0 * COALESCE(realizado.concluidos, 0) / NULLIF(planejado.total_planejado, 0), 1) AS aderencia
            FROM (
                SELECT COALESCE(atleta_id, usuario_id) AS atleta_id, COUNT(*) AS total_planejado
                FROM treinos_gerados tg, LATERAL jsonb_object_keys(tg.json_treino::jsonb) chave
                GROUP BY COALESCE(atleta_id, usuario_id)
            ) planejado
            LEFT JOIN (
                SELECT COALESCE(atleta_id, usuario_id) AS atleta_id, COUNT(*) FILTER (WHERE feito = 1) AS concluidos
                FROM treinos_realizados
                GROUP BY COALESCE(atleta_id, usuario_id)
            ) realizado ON realizado.atleta_id = planejado.atleta_id
        )
        SELECT u.id, u.nome, u.email, u.status_conta, u.data_criacao,
               COUNT(DISTINCT ta.atleta_id) FILTER (WHERE ta.status = 'ativo') AS atletas_vinculados,
               COUNT(DISTINCT ta.atleta_id) FILTER (WHERE ta.status = 'ativo' AND EXISTS (
                   SELECT 1 FROM treinos_realizados tr
                   WHERE COALESCE(tr.atleta_id, tr.usuario_id) = ta.atleta_id
                     AND COALESCE(tr.data_realizada, tr.feito_em) >= CURRENT_DATE - INTERVAL '21 days'
               )) AS atletas_ativos,
               COUNT(DISTINCT ta.atleta_id) FILTER (WHERE ta.status = 'ativo' AND NOT EXISTS (
                   SELECT 1 FROM treinos_realizados tr
                   WHERE COALESCE(tr.atleta_id, tr.usuario_id) = ta.atleta_id
                     AND COALESCE(tr.data_realizada, tr.feito_em) >= CURRENT_DATE - INTERVAL '21 days'
               )) AS sem_atividade_recente,
               a.status AS assinatura_status, p.nome AS plano_nome,
               COALESCE(SUM(CASE WHEN ap.status IN ('ativa','cancelada','inadimplente') THEN COALESCE(ap.valor, 0) ELSE 0 END), 0) AS receita_gerada,
               ROUND(AVG(ad.aderencia), 1) AS aderencia_media
        FROM usuarios u
        LEFT JOIN treinador_atleta ta ON ta.treinador_id = u.id
        LEFT JOIN LATERAL (
            SELECT * FROM assinaturas ax WHERE ax.usuario_id = u.id ORDER BY COALESCE(ax.created_at, CURRENT_TIMESTAMP) DESC, ax.id DESC LIMIT 1
        ) a ON TRUE
        LEFT JOIN planos p ON p.id = a.plano_id
        LEFT JOIN LATERAL (
            SELECT *
            FROM assinaturas ay
            WHERE ay.usuario_id = ta.atleta_id
            ORDER BY COALESCE(ay.created_at, CURRENT_TIMESTAMP) DESC, ay.id DESC
            LIMIT 1
        ) ap ON TRUE
        LEFT JOIN aderencia ad ON ad.atleta_id = ta.atleta_id
        WHERE u.tipo_usuario = 'treinador'
        GROUP BY u.id, a.status, p.nome
        ORDER BY u.nome
        """
    )


def _listar_atletas_admin():
    return _fetch_all(
        """
        WITH aderencia AS (
            SELECT planejado.atleta_id,
                   ROUND(100.0 * COALESCE(realizado.concluidos, 0) / NULLIF(planejado.total_planejado, 0), 1) AS aderencia
            FROM (
                SELECT COALESCE(atleta_id, usuario_id) AS atleta_id, COUNT(*) AS total_planejado
                FROM treinos_gerados tg, LATERAL jsonb_object_keys(tg.json_treino::jsonb) chave
                GROUP BY COALESCE(atleta_id, usuario_id)
            ) planejado
            LEFT JOIN (
                SELECT COALESCE(atleta_id, usuario_id) AS atleta_id, COUNT(*) FILTER (WHERE feito = 1) AS concluidos
                FROM treinos_realizados
                GROUP BY COALESCE(atleta_id, usuario_id)
            ) realizado ON realizado.atleta_id = planejado.atleta_id
        ),
        fase_atual AS (
            SELECT DISTINCT ON (COALESCE(atleta_id, usuario_id))
                   COALESCE(atleta_id, usuario_id) AS atleta_id, fase
            FROM treinos_gerados
            ORDER BY COALESCE(atleta_id, usuario_id), semana_numero DESC, id DESC
        ),
        ultima_atividade AS (
            SELECT COALESCE(atleta_id, usuario_id) AS atleta_id,
                   MAX(COALESCE(data_realizada, feito_em)) AS ultima_data
            FROM treinos_realizados
            GROUP BY COALESCE(atleta_id, usuario_id)
        )
        SELECT u.id, u.nome, u.email, u.status_conta, u.data_criacao,
               ta.treinador_id, COALESCE(t.nome, 'Sem treinador') AS treinador_exibicao,
               a.status AS assinatura_status, p.nome AS plano_nome,
               COALESCE(ad.aderencia, 0) AS aderencia_semanal,
               COALESCE(fa.fase, '-') AS fase_atual,
               COALESCE(EXTRACT(DAY FROM CURRENT_TIMESTAMP - ua.ultima_data)::int, NULL) AS dias_sem_treinar
        FROM usuarios u
        LEFT JOIN LATERAL (
            SELECT * FROM treinador_atleta tx
            WHERE tx.atleta_id = u.id AND tx.status = 'ativo'
            ORDER BY tx.created_at DESC, tx.id DESC LIMIT 1
        ) ta ON TRUE
        LEFT JOIN usuarios t ON t.id = ta.treinador_id
        LEFT JOIN LATERAL (
            SELECT * FROM assinaturas ax WHERE ax.usuario_id = u.id ORDER BY COALESCE(ax.created_at, CURRENT_TIMESTAMP) DESC, ax.id DESC LIMIT 1
        ) a ON TRUE
        LEFT JOIN planos p ON p.id = a.plano_id
        LEFT JOIN aderencia ad ON ad.atleta_id = u.id
        LEFT JOIN fase_atual fa ON fa.atleta_id = u.id
        LEFT JOIN ultima_atividade ua ON ua.atleta_id = u.id
        WHERE u.tipo_usuario = 'atleta'
        ORDER BY u.nome
        """
    )


def _listar_vinculos_admin():
    return _fetch_all(
        """
        SELECT ta.id, ta.treinador_id, tu.nome AS treinador_nome,
               ta.atleta_id, au.nome AS atleta_nome, ta.status, ta.created_at
        FROM treinador_atleta ta
        JOIN usuarios tu ON tu.id = ta.treinador_id
        JOIN usuarios au ON au.id = ta.atleta_id
        ORDER BY ta.created_at DESC, ta.id DESC
        """
    )


def _resumo_financeiro_admin():
    return financeiro_resumo_financeiro_admin()


def _listar_pagamentos_admin(status=None, tipo_usuario=None, plano=None, data_inicio=None, data_fim=None):
    planos = {item["tipo_plano"]: item["id"] for item in listar_planos_ativos()}
    plano_id = planos.get(plano) if plano else None
    return financeiro_listar_pagamentos_admin(status, tipo_usuario, data_inicio, data_fim, plano_id)


def _historico_financeiro_usuario(usuario_id):
    return listar_historico_financeiro_usuario(usuario_id)


def _listar_logs_admin(limite=50):
    return _fetch_all(
        """
        SELECT l.id, l.acao, l.alvo_tipo, l.alvo_id, l.detalhes, l.created_at, u.nome AS admin_nome
        FROM admin_logs l
        JOIN usuarios u ON u.id = l.admin_id
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT %s
        """,
        (int(limite),),
    )


def _atualizar_pagamento_status(admin_id, pagamento_id, novo_status):
    pagamento = _fetch_one("SELECT id, status FROM pagamentos WHERE id = %s", (pagamento_id,))
    if not pagamento:
        return False, "Pagamento nao encontrado."
    financeiro_atualizar_status_pagamento(pagamento_id, novo_status)
    registrar_log_admin(admin_id, f"alterou pagamento para {novo_status}", "pagamento", pagamento_id, f"status anterior: {pagamento['status']}")
    return True, "Pagamento atualizado."


def _atualizar_vinculo_status(admin_id, vinculo_id, novo_status):
    vinculo = _fetch_one("SELECT id, status FROM treinador_atleta WHERE id = %s", (vinculo_id,))
    if not vinculo:
        return False, "Vinculo nao encontrado."
    _execute("UPDATE treinador_atleta SET status = %s WHERE id = %s", (novo_status, vinculo_id))
    registrar_log_admin(admin_id, f"alterou vinculo para {novo_status}", "vinculo", vinculo_id, f"status anterior: {vinculo['status']}")
    return True, "Vinculo atualizado."


def _render_dashboard():
    resumo = _obter_dashboard_admin()
    _cards_metricas([
        {"titulo": "Total de usuarios", "valor": int(resumo.get("total_usuarios") or 0)},
        {"titulo": "Total de atletas", "valor": int(resumo.get("total_atletas") or 0)},
        {"titulo": "Total de treinadores", "valor": int(resumo.get("total_treinadores") or 0)},
        {"titulo": "Total de admins", "valor": int(resumo.get("total_admins") or 0)},
        {"titulo": "Atletas sem treinador", "valor": int(resumo.get("atletas_sem_treinador") or 0)},
        {"titulo": "Atletas vinculados", "valor": int(resumo.get("atletas_vinculados") or 0)},
        {"titulo": "Assinaturas ativas", "valor": int(resumo.get("assinaturas_ativas") or 0)},
        {"titulo": "Assinaturas em trial", "valor": int(resumo.get("assinaturas_trial") or 0)},
        {"titulo": "Assinaturas inadimplentes", "valor": int(resumo.get("assinaturas_inadimplentes") or 0)},
        {"titulo": "Media atletas por treinador", "valor": float(resumo.get("media_atletas_por_treinador") or 0)},
        {"titulo": "Treinos concluidos na semana", "valor": int(resumo.get("concluidos_semana") or 0)},
        {"titulo": "Media de aderencia", "valor": _formatar_percentual(resumo.get("media_aderencia"))},
    ])

    col1, col2 = st.columns(2)
    usuarios_mes = pd.DataFrame(_serie_usuarios_por_mes())
    financeiro_mes = pd.DataFrame(_serie_financeira_admin())
    operacao_semana = pd.DataFrame(_serie_operacional_admin())
    with col1:
        st.markdown("### Novos usuarios por mes")
        if not usuarios_mes.empty:
            st.bar_chart(usuarios_mes.set_index("periodo")[["novos_usuarios", "novos_atletas", "novos_treinadores"]], use_container_width=True)
        else:
            st.info("Sem dados de usuarios.")
    with col2:
        st.markdown("### Receita e assinaturas")
        if not financeiro_mes.empty:
            st.line_chart(financeiro_mes.set_index("periodo")[["receita", "assinaturas_ativas", "trials"]], use_container_width=True)
        else:
            st.info("Sem dados financeiros.")
    st.markdown("### Operacao semanal")
    if not operacao_semana.empty:
        st.line_chart(operacao_semana.set_index("semana")[["treinos_concluidos", "aderencia_media"]], use_container_width=True)
    else:
        st.info("Sem dados operacionais.")


def _render_usuarios(admin):
    col_busca, col_tipo, col_status = st.columns([2.2, 1, 1])
    with col_busca:
        busca = st.text_input("Buscar por nome ou email")
    with col_tipo:
        tipo = st.selectbox("Tipo", ["", "atleta", "treinador", "admin"], format_func=lambda x: x or "Todos")
    with col_status:
        status = st.selectbox("Status", ["", "ativo", "inativo", "suspenso", "cancelado"], format_func=lambda x: x or "Todos")
    usuarios = listar_usuarios(busca=busca, tipo_usuario=tipo or None, status_conta=status or None)
    st.dataframe(pd.DataFrame([{
        "ID": u["id"], "Nome": u["nome"], "Email": u["email"], "Tipo": u["tipo_usuario"],
        "Status conta": u.get("status_conta", "ativo"), "Criado em": _formatar_data(u.get("data_criacao")),
        "Plano": u.get("plano_nome") or "-", "Assinatura": u.get("assinatura_status") or "-"
    } for u in usuarios]), use_container_width=True, hide_index=True)
    if not usuarios:
        return
    usuario_id = st.selectbox("Selecionar usuario", [u["id"] for u in usuarios], format_func=lambda valor: next(f"{u['nome']} ({u['email']})" for u in usuarios if u["id"] == valor))
    usuario = next(u for u in usuarios if u["id"] == usuario_id)
    col1, col2, col3 = st.columns(3)
    with col1:
        novo_status = st.selectbox("Novo status", ["ativo", "inativo", "suspenso", "cancelado"], index=["ativo", "inativo", "suspenso", "cancelado"].index(usuario.get("status_conta", "ativo")))
        if st.button("Salvar status", key=f"admin_status_{usuario_id}", use_container_width=True):
            atualizar_status_conta(usuario_id, novo_status)
            registrar_log_admin(admin["id"], f"alterou status para {novo_status}", "usuario", usuario_id, usuario["email"])
            st.rerun()
    with col2:
        novo_tipo = st.selectbox("Novo papel", ["atleta", "treinador", "admin"], index=["atleta", "treinador", "admin"].index(usuario["tipo_usuario"]))
        mudanca_envuelve_admin = usuario["tipo_usuario"] == "admin" or novo_tipo == "admin"
        if mudanca_envuelve_admin:
            st.caption("Alteracao de privilegio administrativo: disponivel apenas para admins autenticados.")
        acao_papel = "Salvar papel"
        if usuario["tipo_usuario"] != "admin" and novo_tipo == "admin":
            acao_papel = "Promover para admin"
        elif usuario["tipo_usuario"] == "admin" and novo_tipo != "admin":
            acao_papel = "Remover privilegio admin"
        if st.button(acao_papel, key=f"admin_tipo_{usuario_id}", use_container_width=True):
            ok, mensagem, usuario_atualizado = alterar_papel_usuario_por_admin(admin["id"], usuario_id, novo_tipo)
            if ok:
                if usuario["tipo_usuario"] != "admin" and novo_tipo == "admin":
                    log_acao = "promoveu usuario para admin"
                elif usuario["tipo_usuario"] == "admin" and novo_tipo != "admin":
                    log_acao = f"removeu privilegio admin e definiu papel {novo_tipo}"
                else:
                    log_acao = f"alterou papel para {novo_tipo}"
                registrar_log_admin(admin["id"], log_acao, "usuario", usuario_id, usuario["email"])
                st.success(mensagem)
                if int(admin.get("id") or 0) == int(usuario_id) and usuario_atualizado:
                    st.session_state["usuario"] = usuario_atualizado
                st.rerun()
            st.error(mensagem)
    with col3:
        if st.button("Gerar senha temporaria", key=f"admin_pwd_{usuario_id}", use_container_width=True):
            senha = secrets.token_urlsafe(8)
            redefinir_senha_usuario(usuario_id, senha)
            registrar_log_admin(admin["id"], "redefiniu senha", "usuario", usuario_id, usuario["email"])
            st.warning(f"Senha temporaria: {senha}")


def _render_treinadores():
    dados = _listar_treinadores_admin()
    st.dataframe(pd.DataFrame([{
        "ID": i["id"], "Nome": i["nome"], "Email": i["email"], "Atletas vinculados": int(i.get("atletas_vinculados") or 0),
        "Atletas ativos": int(i.get("atletas_ativos") or 0), "Sem atividade recente": int(i.get("sem_atividade_recente") or 0),
        "Plano": i.get("plano_nome") or "-", "Assinatura": i.get("assinatura_status") or "-",
        "Aderencia media": _formatar_percentual(i.get("aderencia_media")), "Receita gerada": _formatar_moeda(i.get("receita_gerada")),
        "Criado em": _formatar_data(i.get("data_criacao"))
    } for i in dados]), use_container_width=True, hide_index=True)
    if dados:
        treinador_id = st.selectbox("Detalhar treinador", [i["id"] for i in dados], format_func=lambda valor: next(i["nome"] for i in dados if i["id"] == valor))
        st.dataframe(pd.DataFrame(_fetch_all(
            """
            SELECT ta.id, au.nome AS atleta, ta.status, ta.created_at
            FROM treinador_atleta ta
            JOIN usuarios au ON au.id = ta.atleta_id
            WHERE ta.treinador_id = %s
            ORDER BY ta.created_at DESC
            """,
            (treinador_id,),
        )), use_container_width=True, hide_index=True)


def _render_atletas():
    dados = _listar_atletas_admin()
    st.dataframe(pd.DataFrame([{
        "ID": i["id"], "Nome": i["nome"], "Email": i["email"], "Treinador": i["treinador_exibicao"],
        "Status conta": i["status_conta"], "Plano": i.get("plano_nome") or "-", "Assinatura": i.get("assinatura_status") or "-",
        "Aderencia": _formatar_percentual(i.get("aderencia_semanal")), "Fase atual": i.get("fase_atual") or "-",
        "Dias sem treinar": i.get("dias_sem_treinar") if i.get("dias_sem_treinar") is not None else "-"
    } for i in dados]), use_container_width=True, hide_index=True)


def _render_vinculos(admin):
    vinculos = _listar_vinculos_admin()
    st.dataframe(pd.DataFrame(vinculos), use_container_width=True, hide_index=True)
    sem_treinador = len([item for item in _listar_atletas_admin() if item.get("treinador_id") is None])
    st.caption(f"Atletas sem treinador: {sem_treinador}")
    if not vinculos:
        return
    vinculo_id = st.selectbox("Selecionar vinculo", [v["id"] for v in vinculos], format_func=lambda valor: next(f"{v['treinador_nome']} -> {v['atleta_nome']} ({v['status']})" for v in vinculos if v["id"] == valor))
    novo_status = st.selectbox("Novo status do vinculo", ["ativo", "pendente", "encerrado", "recusado"])
    if st.button("Atualizar vinculo", use_container_width=True):
        ok, mensagem = _atualizar_vinculo_status(admin["id"], vinculo_id, novo_status)
        if ok:
            st.success(mensagem)
            st.rerun()
        st.error(mensagem)


def _render_financeiro(admin):
    render_financeiro_admin(admin, registrar_log_admin)


def _render_bi():
    usuarios_mes = pd.DataFrame(_serie_usuarios_por_mes())
    financeiro_mes = pd.DataFrame(_serie_financeira_admin())
    operacao = pd.DataFrame(_serie_operacional_admin())
    if not usuarios_mes.empty:
        st.markdown("#### Novos usuarios por mes")
        st.dataframe(usuarios_mes, use_container_width=True, hide_index=True)
    if not financeiro_mes.empty:
        st.markdown("#### Assinaturas, trials e churn")
        st.dataframe(financeiro_mes, use_container_width=True, hide_index=True)
    if not operacao.empty:
        st.markdown("#### Treinos concluidos e aderencia media por semana")
        st.dataframe(operacao, use_container_width=True, hide_index=True)


def _render_logs():
    logs = _listar_logs_admin()
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum log administrativo registrado ainda.")


def tela_area_admin(admin):
    validar_admin(admin)
    _aplicar_estilo_admin()
    st.markdown(
        """
        <div class="admin-hero">
            <h1>Painel administrativo</h1>
            <p>Visao executiva do TriLab TREINAMENTO com operacao, usuarios, vinculos, financeiro e BI em um unico lugar.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    abas = st.tabs(["Dashboard", "Usuarios", "Treinadores", "Atletas", "Vinculos", "Financeiro", "BI", "Logs"])
    with abas[0]:
        _render_dashboard()
    with abas[1]:
        _render_usuarios(admin)
    with abas[2]:
        _render_treinadores()
    with abas[3]:
        _render_atletas()
    with abas[4]:
        _render_vinculos(admin)
    with abas[5]:
        _render_financeiro(admin)
    with abas[6]:
        _render_bi()
    with abas[7]:
        _render_logs()
