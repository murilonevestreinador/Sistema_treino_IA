import base64
from urllib.parse import parse_qs, urlparse

import streamlit as st
import streamlit.components.v1 as components

from core.carga import rotulo_categoria_movimento
from core.cronograma import buscar_semana_por_numero, gerar_cronograma, obter_semana_atual
from core.exercicios import carregar_exercicios
from core.financeiro import obter_status_interface_atleta
from core.progresso import (
    buscar_avaliacao_referencia,
    buscar_ultima_execucao,
    buscar_progresso_semana,
    calcular_progresso_semanal,
    historico_progresso,
    listar_avaliacoes_forca,
    listar_execucao_treino,
    marcar_treino_feito,
    registrar_preferencia_substituicao,
    salvar_avaliacao_forca,
    salvar_execucao_exercicio,
    salvar_feedback_treino,
)
from core.treinador import listar_convites_pendentes_do_atleta, resolver_logo_treinador
from core.treino import buscar_treino_gerado, obter_ou_gerar_treino_semana, resetar_treinos_futuros


def _registrar_dialog_video():
    if not hasattr(st, "dialog"):
        return None

    @st.dialog("Vídeo do exercício")
    def _render_dialog_video():
        exercicio = st.session_state.get("exercicio_video_aberto")
        if not exercicio:
            return

        st.markdown(f"**{exercicio['nome']}**")
        link_yt = exercicio.get("link_yt")
        if link_yt:
            _render_player_video(link_yt)
        else:
            st.info("Nenhum vídeo cadastrado para este exercício.")

        if st.button("Fechar janela", key="btn_fechar_modal_video", use_container_width=True):
            st.session_state.pop("exercicio_video_aberto", None)
            st.rerun()

    return _render_dialog_video


_RENDER_DIALOG_VIDEO = _registrar_dialog_video()


def _submeter_feedback_pendente(feedback, feedback_tipo, feedback_contexto_ruim, exercicio_escolhido, motivo_exercicio_ruim):
    salvar_feedback_treino(
        feedback["atleta_id"],
        feedback["semana_numero"],
        feedback["nome_treino"],
        feedback_tipo,
        feedback_contexto_ruim=feedback_contexto_ruim,
        exercicio_substituir=exercicio_escolhido,
        motivo_exercicio_ruim=motivo_exercicio_ruim,
    )

    if feedback_tipo == "muito ruim" and exercicio_escolhido:
        exercicio_atual = next(
            (item for item in feedback["exercicios"] if item["nome"] == exercicio_escolhido),
            None,
        )
        if exercicio_atual:
            registrar_preferencia_substituicao(
                feedback["atleta_id"],
                {
                    "nome": exercicio_atual["nome"],
                    "categoria": exercicio_atual.get("categoria"),
                    "principal_musculo": exercicio_atual.get("principal_musculo"),
                    "motivo": motivo_exercicio_ruim,
                },
            )
            resetar_treinos_futuros(feedback["atleta_id"], feedback["semana_numero"])
            st.session_state["mensagem_feedback_treino"] = (
                "Obrigado pelo feedback. Vamos substituir esse exercicio nos proximos treinos."
            )
        else:
            st.session_state["mensagem_feedback_treino"] = "Obrigado pelo feedback."
    else:
        st.session_state["mensagem_feedback_treino"] = "Obrigado e ate o proximo treino."

    st.session_state.pop("feedback_pendente", None)
    st.rerun()


def _render_formulario_feedback(feedback):
    st.markdown(f"**Treino {feedback['nome_treino']}**")
    feedback_tipo = st.radio(
        "Como foi esse treino?",
        ["muito bom", "neutro", "muito ruim"],
        horizontal=True,
        key=f"feedback_tipo_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
    )
    feedback_contexto_ruim = None
    exercicio_escolhido = None
    motivo_exercicio_ruim = None

    if feedback_tipo == "muito ruim":
        feedback_contexto_ruim = "muito_ruim"
        motivo_exercicio_ruim = st.selectbox(
            "Por que foi muito ruim?",
            [
                "dor em um exercicio",
                "nao gostou do exercicio",
                "exercicio ficou desconfortavel",
                "nao tem o equipamento na academia",
            ],
            key=f"motivo_ruim_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
        )
        nomes_exercicios = [item["nome"] for item in feedback["exercicios"]]
        exercicio_escolhido = st.selectbox(
            "Qual exercicio do treino gerou esse desconforto?",
            nomes_exercicios,
            key=f"exercicio_ruim_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
        )

    col_enviar, col_fechar = st.columns(2)
    with col_enviar:
        if st.button(
            "Enviar feedback",
            key=f"enviar_feedback_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
            use_container_width=True,
        ):
            _submeter_feedback_pendente(
                feedback,
                feedback_tipo,
                feedback_contexto_ruim,
                exercicio_escolhido,
                motivo_exercicio_ruim,
            )
    with col_fechar:
        if st.button(
            "Fechar janela",
            key=f"fechar_feedback_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
            use_container_width=True,
        ):
            st.session_state.pop("feedback_pendente", None)
            st.rerun()


def _registrar_dialog_feedback():
    if not hasattr(st, "dialog"):
        return None

    @st.dialog("Feedback do treino")
    def _render_dialog_feedback():
        feedback = st.session_state.get("feedback_pendente")
        if not feedback:
            return
        _render_formulario_feedback(feedback)

    return _render_dialog_feedback


_RENDER_DIALOG_FEEDBACK = _registrar_dialog_feedback()


def _foto_perfil_bytes(usuario):
    foto_perfil = usuario.get("foto_perfil")
    if not foto_perfil:
        return None
    try:
        return base64.b64decode(foto_perfil)
    except Exception:
        return None


def _url_embed_youtube(url):
    try:
        parsed = urlparse(str(url).strip())
    except Exception:
        return None

    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").strip("/")
    video_id = None

    if "youtu.be" in host:
        video_id = path.split("/")[0] if path else None
    elif "youtube.com" in host:
        partes = [parte for parte in path.split("/") if parte]
        if partes[:1] == ["shorts"] and len(partes) >= 2:
            video_id = partes[1]
        elif partes[:1] == ["embed"] and len(partes) >= 2:
            video_id = partes[1]
        elif partes[:1] == ["watch"]:
            video_id = parse_qs(parsed.query).get("v", [None])[0]

    if not video_id:
        return None

    return f"https://www.youtube.com/embed/{video_id}"


def _render_player_video(url):
    url_embed = _url_embed_youtube(url)
    if url_embed:
        components.iframe(url_embed, height=315)
        return
    st.video(url)


def _aplicar_estilo_dashboard():
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, color-mix(in srgb, var(--tri-primary) 14%, transparent), transparent 24%),
                radial-gradient(circle at bottom right, color-mix(in srgb, var(--tri-secondary) 12%, transparent), transparent 22%),
                linear-gradient(180deg, var(--tri-bg) 0%, var(--tri-surface) 100%);
        }
        .athlete-banner {
            padding: 1.2rem 1.35rem;
            border-radius: 24px;
            background: linear-gradient(135deg, var(--tri-header-start) 0%, var(--tri-primary) 62%, var(--tri-header-end) 100%);
            color: var(--tri-text-on-header);
            box-shadow: var(--tri-shadow-strong);
            margin-bottom: 1rem;
        }
        .athlete-banner h1 {
            margin: 0;
            font-size: 2rem;
        }
        .athlete-banner p {
            margin: 0.35rem 0 0;
            color: color-mix(in srgb, var(--tri-text-on-header) 80%, transparent);
        }
        .metric-card, .workout-detail, .history-card {
            border-radius: 22px;
            border: 1px solid var(--tri-border);
            background: color-mix(in srgb, var(--tri-surface) 96%, transparent);
            padding: 1rem 1.05rem;
            box-shadow: var(--tri-shadow-soft);
            margin-bottom: 0.9rem;
        }
        .metric-card strong,
        .history-card strong {
            display: block;
            color: var(--tri-text-strong);
            margin-bottom: 0.2rem;
        }
        .section-shell {
            border-radius: 24px;
            border: 1px solid var(--tri-border);
            background:
                radial-gradient(circle at top right, color-mix(in srgb, var(--tri-primary) 10%, transparent), transparent 34%),
                color-mix(in srgb, var(--tri-surface) 90%, transparent);
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .section-shell h3 {
            margin: 0 0 0.35rem;
            color: var(--tri-text-strong);
        }
        .section-shell p {
            margin: 0;
            color: var(--tri-text-soft);
        }
        .workout-card {
            border-radius: 22px;
            border: 1px solid var(--tri-border);
            background: color-mix(in srgb, var(--tri-surface) 98%, transparent);
            padding: 1rem;
            min-height: 150px;
            box-shadow: var(--tri-shadow-soft);
            margin-bottom: 0.7rem;
        }
        .workout-card.active {
            border-color: var(--tri-border-strong);
            box-shadow: var(--tri-shadow-card);
            background: linear-gradient(135deg, var(--tri-bg-soft) 0%, var(--tri-surface) 100%);
        }
        .execution-shell {
            border-radius: 24px;
            border: 1px solid var(--tri-border);
            background: color-mix(in srgb, var(--tri-surface) 98%, transparent);
            padding: 1.05rem;
            box-shadow: var(--tri-shadow-card);
            margin-bottom: 1rem;
        }
        .execution-toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.95rem;
        }
        .execution-toolbar h3 {
            margin: 0;
            color: var(--tri-text-strong);
        }
        .execution-toolbar p {
            margin: 0.2rem 0 0;
            color: var(--tri-text-soft);
        }
        .workout-card .eyebrow {
            display: inline-block;
            font-size: 0.72rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--tri-secondary);
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .workout-card h4 {
            margin: 0 0 0.35rem;
            color: var(--tri-text-strong);
            font-size: 1.15rem;
        }
        .workout-card p {
            margin: 0;
            color: var(--tri-text-soft);
            line-height: 1.45;
        }
        .status-pill {
            display: inline-block;
            margin-top: 0.8rem;
            padding: 0.22rem 0.6rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
        }
        .status-pill.done {
            background: var(--tri-success-bg);
            color: var(--tri-success-text);
            border: 1px solid var(--tri-success-border);
        }
        .status-pill.pending {
            background: var(--tri-bg-soft);
            color: var(--tri-text);
            border: 1px solid var(--tri-border);
        }
        .exercise-card {
            border-radius: 18px;
            border: 1px solid var(--tri-border);
            background: color-mix(in srgb, var(--tri-bg-soft) 94%, transparent);
            padding: 0.85rem 0.95rem;
            margin-bottom: 0.55rem;
        }
        .exercise-card strong {
            display: block;
            color: var(--tri-text-strong);
            margin-bottom: 0.18rem;
        }
        .exercise-card span {
            color: var(--tri-text-soft);
            font-size: 0.92rem;
            display: block;
        }
        .exercise-card .exercise-guidance {
            margin-top: 0.4rem;
            color: var(--tri-text);
            font-size: 0.9rem;
            line-height: 1.4;
        }
        .detail-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.9rem;
        }
        .detail-header h3 {
            margin: 0;
            color: var(--tri-text-strong);
        }
        .detail-header p {
            margin: 0.15rem 0 0;
            color: var(--tri-text-soft);
        }
        .evaluation-shell {
            border-radius: 24px;
            border: 1px solid var(--tri-warning-border);
            background:
                radial-gradient(circle at top right, color-mix(in srgb, var(--tri-warning) 16%, transparent), transparent 34%),
                linear-gradient(135deg, var(--tri-warning-bg) 0%, var(--tri-surface) 100%);
            padding: 1rem 1.05rem;
            margin-bottom: 1rem;
            box-shadow: var(--tri-shadow-soft);
        }
        .evaluation-shell h3 {
            margin: 0;
            color: var(--tri-text-strong);
        }
        .evaluation-shell p {
            margin: 0.45rem 0 0;
            color: var(--tri-text-soft);
            line-height: 1.5;
        }
        .evaluation-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.7rem;
            margin-top: 0.85rem;
        }
        .evaluation-tip {
            border-radius: 16px;
            background: color-mix(in srgb, var(--tri-surface) 72%, transparent);
            padding: 0.7rem 0.8rem;
            border: 1px solid var(--tri-border);
        }
        .evaluation-tip strong {
            display: block;
            color: var(--tri-text-strong);
            margin-bottom: 0.15rem;
        }
        .exercise-card.evaluation {
            border-color: var(--tri-warning-border);
            background: linear-gradient(135deg, var(--tri-warning-bg) 0%, var(--tri-surface) 100%);
            box-shadow: var(--tri-shadow-soft);
        }
        .badge-evaluation {
            display: inline-block;
            margin-bottom: 0.4rem;
            padding: 0.18rem 0.55rem;
            border-radius: 999px;
            background: var(--tri-danger-bg);
            color: var(--tri-danger-text);
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .evaluation-entry {
            border-radius: 18px;
            border: 1px solid var(--tri-warning-border);
            background: linear-gradient(135deg, var(--tri-warning-bg) 0%, var(--tri-surface) 100%);
            padding: 0.95rem 1rem;
            margin-bottom: 0.9rem;
        }
        .evaluation-entry h4 {
            margin: 0;
            color: var(--tri-text-strong);
        }
        .evaluation-entry p {
            margin: 0.3rem 0 0;
            color: var(--tri-text-soft);
            line-height: 1.45;
        }
        .evaluation-summary {
            border-radius: 18px;
            border: 1px solid var(--tri-success-border);
            background: linear-gradient(135deg, var(--tri-success-bg) 0%, var(--tri-surface) 100%);
            padding: 0.95rem 1rem;
            margin-bottom: 0.85rem;
        }
        .evaluation-summary strong {
            color: var(--tri-text-strong);
        }
        .nav-chip-row .stButton > button {
            width: 100%;
        }
        .access-status-card {
            border-radius: 24px;
            border: 1px solid var(--tri-border);
            padding: 1rem 1.05rem;
            margin: 0 0 1rem;
            box-shadow: var(--tri-shadow-soft);
        }
        .access-status-card.success {
            border-color: var(--tri-success-border);
            background: linear-gradient(135deg, var(--tri-success-bg) 0%, var(--tri-surface) 100%);
        }
        .access-status-card.info {
            border-color: var(--tri-info-border);
            background: linear-gradient(135deg, var(--tri-info-bg) 0%, var(--tri-surface) 100%);
        }
        .access-status-card.warning {
            border-color: var(--tri-warning-border);
            background: linear-gradient(135deg, var(--tri-warning-bg) 0%, var(--tri-surface) 100%);
        }
        .access-status-card.danger {
            border-color: var(--tri-danger-border);
            background: linear-gradient(135deg, var(--tri-danger-bg) 0%, var(--tri-surface) 100%);
        }
        .access-status-card h3 {
            margin: 0;
            color: var(--tri-text-strong);
            font-size: 1.08rem;
        }
        .access-status-card p {
            margin: 0.45rem 0 0;
            color: var(--tri-text-soft);
            line-height: 1.55;
        }
        .access-status-detail {
            margin-top: 0.65rem;
            color: var(--tri-text);
            font-weight: 600;
        }
        @media (max-width: 768px) {
            .block-container {
                padding-top: 0.9rem;
                padding-left: 0.85rem;
                padding-right: 0.85rem;
                padding-bottom: 1rem;
            }
            .athlete-banner {
                padding: 0.95rem 1rem;
                border-radius: 14px;
                margin-bottom: 0.8rem;
            }
            .athlete-banner h1 {
                font-size: 1.35rem;
            }
            .athlete-banner p {
                font-size: 0.9rem;
            }
            .access-status-card {
                border-radius: 14px;
                padding: 0.85rem 0.9rem;
            }
            .metric-card, .workout-detail, .history-card, .section-shell {
                border-radius: 14px;
                padding: 0.8rem 0.85rem;
                margin-bottom: 0.7rem;
            }
            .workout-card {
                border-radius: 14px;
                min-height: 132px;
                padding: 0.85rem;
            }
            .exercise-card {
                border-radius: 12px;
                padding: 0.75rem 0.8rem;
            }
            .detail-header {
                display: block;
            }
            .stButton > button, .stFormSubmitButton > button {
                width: 100%;
                min-height: 2.8rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_convites_pendentes(usuario):
    convites = listar_convites_pendentes_do_atleta(usuario["id"])
    if not convites:
        return

    st.info("Existe um vinculo com treinador aguardando definicao.")
    for convite in convites:
        st.write(f"{convite['treinador_nome']} ({convite['treinador_email']})")
    st.caption("Quando o convite vier por link, a confirmacao aparece automaticamente no topo do app.")


def _abrir_pagina_dashboard(destino):
    try:
        st.switch_page(destino)
    except Exception:
        st.info("Use o menu lateral para abrir esta pagina.")


def _render_status_acesso_atleta(usuario):
    contexto = obter_status_interface_atleta(usuario["id"])
    if not contexto.get("mostrar_no_dashboard"):
        return

    st.markdown(
        f"""
        <div class="access-status-card {contexto.get('variant', 'info')}">
            <h3>{contexto.get('titulo', '')}</h3>
            <p>{contexto.get('texto', '')}</p>
            {f"<div class='access-status-detail'>{contexto['detalhe']}</div>" if contexto.get('detalhe') else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if contexto.get("cta_label") and contexto.get("cta_destino"):
        if st.button(
            contexto["cta_label"],
            key=f"cta_status_atleta_{contexto['status']}",
            type="secondary",
            use_container_width=False,
        ):
            _abrir_pagina_dashboard(contexto["cta_destino"])


def _render_overview_inicial():
    mensagem = st.session_state.get("mensagem_onboarding")
    st.subheader("Bem-vindo ao seu planejamento")
    if mensagem:
        st.success(mensagem)
    if st.button("Ir para minha \u00e1rea", key="btn_ir_area"):
        st.session_state["mostrar_overview"] = False
        st.rerun()


def _abrir_feedback_pendente(usuario_id, semana_numero, nome_treino, exercicios):
    st.session_state.pop("exercicio_video_aberto", None)
    st.session_state["feedback_pendente"] = {
        "atleta_id": usuario_id,
        "semana_numero": semana_numero,
        "nome_treino": nome_treino,
        "exercicios": exercicios,
    }


def _render_feedback_pendente(nome_treino_esperado=None):
    feedback = st.session_state.get("feedback_pendente")
    if not feedback:
        return
    if nome_treino_esperado and feedback.get("nome_treino") != nome_treino_esperado:
        return

    if _RENDER_DIALOG_FEEDBACK:
        _RENDER_DIALOG_FEEDBACK()
        return

    st.markdown("---")
    with st.container():
        st.subheader(f"Feedback do treino {feedback['nome_treino']}")
        _render_formulario_feedback(feedback)


def _render_card_exercicios(exercicios):
    for indice, exercicio in enumerate(exercicios):
        col_info, col_video = st.columns([5, 1])
        with col_info:
            orientacao_carga = exercicio.get("orientacao_carga")
            carga_exibida = exercicio.get("carga_sugerida")
            if carga_exibida is not None:
                peso_texto = f"{carga_exibida} kg"
            else:
                peso_texto = exercicio.get("carga") or "-"
            complemento_carga = f'<span class="exercise-guidance">{orientacao_carga}</span>' if orientacao_carga else ""
            badge_avaliacao = (
                '<div class="badge-evaluation">Avaliacao</div>'
                if exercicio.get("modo_carga") == "avaliacao"
                else ""
            )
            classe_avaliacao = "evaluation" if exercicio.get("modo_carga") == "avaliacao" else ""
            st.markdown(
                (
                    f'<div class="exercise-card {classe_avaliacao}">'
                    f"{badge_avaliacao}"
                    f"<strong>{exercicio['nome']}</strong>"
                    f"<span>Series {exercicio['series']} | Reps {exercicio['reps']} | "
                    f"Descanso {exercicio['descanso']} | Peso {peso_texto} | RPE alvo {exercicio.get('rpe', '-')}</span>"
                    f"{complemento_carga}"
                    f"</div>"
                ),
                unsafe_allow_html=True,
            )
        with col_video:
            if st.button(
                "Vídeo",
                key=f"video_exercicio_{indice}_{exercicio['nome']}",
                disabled=not exercicio.get("link_yt"),
                use_container_width=True,
            ):
                st.session_state["exercicio_video_aberto"] = exercicio
                st.rerun()


def _render_resumo_avaliacao_concluida(usuario_id, semana_numero):
    resumo = st.session_state.get(f"resumo_avaliacao_{usuario_id}_{semana_numero}")
    if not resumo:
        return

    st.markdown(
        """
        <div class="evaluation-summary">
            <strong>Resumo da avaliacao concluida</strong>
            <div>Perfeito. Usaremos esses dados para ajustar melhor suas cargas a partir da proxima semana.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for item in resumo:
        st.caption(
            f"{item['exercicio']} | carga {item['carga']} kg | reps {item['reps']} | RPE {item['rpe']}"
        )


def _render_guia_avaliacao_semana(semana, exercicios):
    if semana["semana"] != 2:
        return

    exercicios_avaliativos = [item for item in exercicios if item.get("modo_carga") == "avaliacao"]
    if not exercicios_avaliativos:
        return

    st.markdown(
        """
        <div class="evaluation-shell">
            <h3>Avaliacao de carga da semana</h3>
            <p>Nesta semana, alguns exercicios serao usados como referencia para ajustar melhor suas cargas nas proximas sessoes. Escolha uma carga desafiadora, mas segura, mantendo boa tecnica e sem chegar a falha.</p>
            <div class="evaluation-grid">
                <div class="evaluation-tip">
                    <strong>Objetivo</strong>
                    Encontrar uma carga segura e representativa.
                </div>
                <div class="evaluation-tip">
                    <strong>Prioridade</strong>
                    Tecnica, controle e boa execucao continuam em primeiro lugar.
                </div>
                <div class="evaluation-tip">
                    <strong>Sem falhar</strong>
                    Nao busque esforco maximo. Pare antes da falha.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Exercicios de avaliacao neste treino: {len(exercicios_avaliativos)}")


def _render_contexto_carga_semana(semana, avaliacoes):
    if semana["semana"] == 1:
        st.info("Semana 1: foco em tecnica, execucao, amplitude e controle. Nao ha teste de carga nesta semana.")
        return
    if semana["semana"] == 2:
        st.warning("Semana 2: os exercicios-base marcados como avaliacao de carga devem registrar peso usado, repeticoes e RPE.")
        return

    total_avaliacoes = len(avaliacoes or [])
    if total_avaliacoes:
        st.success(
            f"Semana {semana['semana']}: as cargas sugeridas usam a avaliacao da semana 2, a fase {semana['fase']} e os registros de RPE/dor."
        )
    else:
        st.info("Ainda nao ha avaliacao de carga salva. As orientacoes seguem qualitativas ate existir referencia.")


def _salvar_execucao_treino_atleta(usuario, semana, nome_treino, exercicios, rerun_apos_salvar=True):
    prefixo = f"exec_{usuario['id']}_{semana['semana']}_{nome_treino}"
    payload = []
    avaliacoes_salvas = 0
    erros = []
    resumo_avaliacoes = []

    for indice, exercicio in enumerate(exercicios):
        series_realizadas = int(st.session_state.get(f"{prefixo}_series_{indice}", exercicio.get("series") or 0) or 0)
        reps_realizadas = int(st.session_state.get(f"{prefixo}_reps_{indice}", exercicio.get("reps") or 0) or 0)
        carga_realizada = float(st.session_state.get(f"{prefixo}_carga_{indice}", 0.0) or 0.0)
        rpe_real = float(st.session_state.get(f"{prefixo}_rpe_{indice}", 0.0) or 0.0)
        dor = (st.session_state.get(f"{prefixo}_dor_{indice}", "") or "").strip() or None
        observacao = (st.session_state.get(f"{prefixo}_obs_{indice}", "") or "").strip() or None

        item = {
            **exercicio,
            "series_realizadas": series_realizadas,
            "reps_realizadas": reps_realizadas,
            "carga_realizada": carga_realizada if carga_realizada > 0 else None,
            "rpe_real": rpe_real if rpe_real > 0 else None,
            "dor": dor,
            "observacao": observacao,
        }
        payload.append(item)

        if exercicio.get("modo_carga") == "avaliacao":
            if carga_realizada <= 0:
                erros.append(f"{exercicio['nome']}: informe uma carga utilizada maior que zero.")
            if reps_realizadas <= 0:
                erros.append(f"{exercicio['nome']}: informe repeticoes realizadas acima de zero.")
            if not 5 <= rpe_real <= 10:
                erros.append(f"{exercicio['nome']}: selecione um RPE entre 5 e 10.")
            resumo_avaliacoes.append(
                {
                    "exercicio": exercicio["nome"],
                    "carga": round(carga_realizada, 1),
                    "reps": reps_realizadas,
                    "rpe": round(rpe_real, 1),
                }
            )

    if erros:
        for erro in erros:
            st.error(erro)
        return False

    for item in payload:
        if item.get("modo_carga") == "avaliacao":
            avaliacao = salvar_avaliacao_forca(
                usuario["id"],
                semana["semana"],
                semana["fase"],
                item.get("categoria_movimento"),
                item.get("nome"),
                item.get("carga_realizada"),
                item.get("reps_realizadas"),
                item.get("rpe_real"),
            )
            if avaliacao:
                avaliacoes_salvas += 1

    salvar_execucao_exercicio(usuario["id"], semana["semana"], semana["fase"], nome_treino, payload)
    if avaliacoes_salvas:
        resetar_treinos_futuros(usuario["id"], semana["semana"])
        st.session_state[f"resumo_avaliacao_{usuario['id']}_{semana['semana']}"] = resumo_avaliacoes

    st.session_state["mensagem_execucao_carga"] = (
        f"Execucao de {nome_treino} salva."
        + (f" {avaliacoes_salvas} avaliacao(oes) de carga atualizada(s)." if avaliacoes_salvas else "")
    )
    if rerun_apos_salvar:
        st.rerun()
    return True


def _render_form_execucao_exercicios(usuario, semana, nome_treino, exercicios):
    execucoes = {
        item["exercicio_nome"]: item
        for item in listar_execucao_treino(usuario["id"], semana["semana"], nome_treino)
    }
    prefixo = f"exec_{usuario['id']}_{semana['semana']}_{nome_treino}"

    with st.form(f"form_execucao_{usuario['id']}_{semana['semana']}_{nome_treino}"):
        st.markdown("#### Registrar carga e execucao")
        st.caption("Preencha a execucao real para alimentar a prescricao das proximas sessoes.")
        if semana["semana"] == 2:
            st.markdown("##### Exercicios de avaliacao")
            st.caption("Preencha carga, repeticoes e RPE apenas com uma carga desafiadora e segura.")

        for indice, exercicio in enumerate(exercicios):
            execucao = execucoes.get(exercicio["nome"], {})
            if exercicio.get("modo_carga") == "avaliacao":
                st.markdown(
                    f"""
                    <div class="evaluation-entry">
                        <div class="badge-evaluation">Avaliacao</div>
                        <h4>{exercicio['nome']}</h4>
                        <p>{exercicio['series']} x {exercicio['reps']} | {rotulo_categoria_movimento(exercicio.get('categoria_movimento'))}</p>
                        <p>{exercicio.get('orientacao_carga') or ''}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                col_carga, col_reps, col_rpe = st.columns(3)
                with col_carga:
                    st.number_input(
                        "Carga utilizada (kg)",
                        min_value=0.0,
                        max_value=500.0,
                        step=0.5,
                        value=float(execucao.get("carga_realizada") or 0.0),
                        key=f"{prefixo}_carga_{indice}",
                    )
                with col_reps:
                    st.number_input(
                        "Repeticoes realizadas",
                        min_value=0,
                        max_value=50,
                        value=int(execucao.get("reps_realizadas") or exercicio.get("reps") or 0),
                        key=f"{prefixo}_reps_{indice}",
                    )
                with col_rpe:
                    st.select_slider(
                        "Esforco percebido (RPE)",
                        options=[5, 6, 7, 8, 9, 10],
                        value=int(execucao.get("rpe_real") or 7),
                        key=f"{prefixo}_rpe_{indice}",
                    )
                st.caption("RPE 6 = leve | RPE 7 = moderado | RPE 8 = desafiador | RPE 9 = muito dificil | RPE 10 = esforco maximo")

                col_series, col_dor, col_obs = st.columns([1, 1.2, 1.8])
                with col_series:
                    st.number_input(
                        "Series realizadas",
                        min_value=0,
                        max_value=20,
                        value=int(execucao.get("series_realizadas") or exercicio.get("series") or 0),
                        key=f"{prefixo}_series_{indice}",
                    )
                with col_dor:
                    st.text_input(
                        "Dor/desconforto",
                        value=str(execucao.get("dor") or ""),
                        key=f"{prefixo}_dor_{indice}",
                        placeholder="Ex: joelho esquerdo sensivel",
                    )
                with col_obs:
                    st.text_input(
                        "Observacao",
                        value=str(execucao.get("observacao") or ""),
                        key=f"{prefixo}_obs_{indice}",
                        placeholder="Ex: carga segura e controlada",
                    )
            else:
                st.markdown(f"**{exercicio['nome']}**")
                col_series, col_reps, col_carga, col_rpe = st.columns(4)
                with col_series:
                    st.number_input(
                        "Series realizadas",
                        min_value=0,
                        max_value=20,
                        value=int(execucao.get("series_realizadas") or exercicio.get("series") or 0),
                        key=f"{prefixo}_series_{indice}",
                    )
                with col_reps:
                    st.number_input(
                        "Reps realizadas",
                        min_value=0,
                        max_value=50,
                        value=int(execucao.get("reps_realizadas") or exercicio.get("reps") or 0),
                        key=f"{prefixo}_reps_{indice}",
                    )
                with col_carga:
                    st.number_input(
                        "Carga usada (kg)",
                        min_value=0.0,
                        max_value=500.0,
                        step=0.5,
                        value=float(execucao.get("carga_realizada") or exercicio.get("carga_sugerida") or 0.0),
                        key=f"{prefixo}_carga_{indice}",
                    )
                with col_rpe:
                    st.number_input(
                        "RPE real",
                        min_value=0.0,
                        max_value=10.0,
                        step=0.5,
                        value=float(execucao.get("rpe_real") or 0.0),
                        key=f"{prefixo}_rpe_{indice}",
                    )

                col_dor, col_obs = st.columns(2)
                with col_dor:
                    st.text_input(
                        "Dor/desconforto",
                        value=str(execucao.get("dor") or ""),
                        key=f"{prefixo}_dor_{indice}",
                        placeholder="Ex: joelho esquerdo sensivel",
                    )
                with col_obs:
                    st.text_input(
                        "Observacao",
                        value=str(execucao.get("observacao") or ""),
                        key=f"{prefixo}_obs_{indice}",
                        placeholder="Ex: sobrou carga / muito pesado",
                    )

        salvar = st.form_submit_button("Salvar execucao de carga", use_container_width=True)

    if salvar:
        _salvar_execucao_treino_atleta(usuario, semana, nome_treino, exercicios)


def _anexar_links_exercicios(treino_semana, exercicios_db):
    links_por_nome = {
        item["nome"]: item.get("link_yt")
        for item in exercicios_db
        if item.get("nome")
    }
    treino_com_links = {}

    for nome_treino, exercicios in treino_semana.items():
        treino_com_links[nome_treino] = []
        for exercicio in exercicios:
            item = dict(exercicio)
            item["link_yt"] = item.get("link_yt") or links_por_nome.get(item.get("nome"))
            treino_com_links[nome_treino].append(item)

    return treino_com_links


def _render_video_exercicio():
    exercicio = st.session_state.get("exercicio_video_aberto")
    if not exercicio:
        return

    if _RENDER_DIALOG_VIDEO:
        _RENDER_DIALOG_VIDEO()
        return

    with st.container():
        st.markdown("---")
        st.subheader(f"Vídeo: {exercicio['nome']}")
        if exercicio.get("link_yt"):
            _render_player_video(exercicio["link_yt"])
        else:
            st.info("Nenhum vídeo cadastrado para este exercício.")
        if st.button("Fechar janela", key="btn_fechar_video_inline", use_container_width=True):
            st.session_state.pop("exercicio_video_aberto", None)
            st.rerun()


def _garantir_cronograma(usuario):
    cronograma = st.session_state.get("cronograma")
    if not cronograma:
        cronograma, fases, total = gerar_cronograma(usuario)
        st.session_state["cronograma"] = cronograma
        st.session_state["fases"] = fases
        st.session_state["total_semanas"] = total
    return st.session_state["cronograma"]


def _obter_contexto_semana(usuario):
    cronograma = _garantir_cronograma(usuario)
    semana_atual = obter_semana_atual(cronograma)
    exercicios_db = carregar_exercicios()
    treino_semana = obter_ou_gerar_treino_semana(usuario, exercicios_db, semana_atual["semana"], semana_atual["fase"])
    treino_semana = _anexar_links_exercicios(treino_semana, exercicios_db)
    progresso = buscar_progresso_semana(usuario["id"], semana_atual["semana"])
    total_planejado = len(treino_semana)
    concluidos, percentual = calcular_progresso_semanal(usuario["id"], semana_atual["semana"], total_planejado)
    return cronograma, semana_atual, treino_semana, progresso, concluidos, percentual


def _render_nav_local():
    secao = st.session_state.get("secao_atleta", "visao_geral")
    st.markdown(
        """
        <div class="section-shell">
            <h3>Navega\u00e7\u00e3o do atleta</h3>
            <p>Escolha entre sua vis\u00e3o geral e uma \u00e1rea dedicada apenas aos treinos.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_area, col_treinos = st.columns(2)
    with col_area:
        if st.button(
            "Minha \u00e1rea",
            key="btn_nav_local_area",
            type="primary" if secao == "visao_geral" else "secondary",
            use_container_width=True,
        ):
            st.session_state["secao_atleta"] = "visao_geral"
            st.rerun()
    with col_treinos:
        if st.button(
            "Treinos",
            key="btn_nav_local_treinos",
            type="primary" if secao == "treinos" else "secondary",
            use_container_width=True,
        ):
            st.session_state["secao_atleta"] = "treinos"
            st.rerun()


def _render_resumo_geral(usuario, semana, treino_semana, concluidos, percentual):
    avaliacoes = listar_avaliacoes_forca(usuario["id"])
    st.markdown(
        f"""
        <div class="metric-card">
            <strong>Semana {semana['semana']} | Fase {semana['fase'].capitalize()}</strong>
            <span>Per\u00edodo: {semana['inicio']} at\u00e9 {semana['fim']}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(percentual / 100 if treino_semana else 0)
    st.write(f"Progresso semanal: {percentual}% ({concluidos}/{len(treino_semana)})")
    _render_contexto_carga_semana(semana, avaliacoes)
    _render_resumo_avaliacao_concluida(usuario["id"], semana["semana"])

    st.markdown(
        """
        <div class="section-shell">
            <h3>Resumo da semana</h3>
            <p>Seus treinos est\u00e3o organizados em uma \u00e1rea separada para facilitar a execu\u00e7\u00e3o e o feedback.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for nome_treino, exercicios in treino_semana.items():
        st.markdown(
            f"""
            <div class="history-card">
                <strong>{nome_treino}</strong>
                <span>{len(exercicios)} exerc\u00edcios planejados para este treino.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_historico(usuario, semana, cronograma):
    semanas_anteriores = [item for item in cronograma if item["semana"] < semana["semana"]]
    st.subheader("Hist\u00f3rico")
    if not semanas_anteriores:
        st.caption("Ainda n\u00e3o h\u00e1 semanas anteriores.")
        return

    semana_historica_numero = st.selectbox(
        "Ver semana anterior",
        options=[item["semana"] for item in semanas_anteriores],
        format_func=lambda numero: f"Semana {numero}",
    )
    semana_historica = buscar_semana_por_numero(cronograma, semana_historica_numero)
    treino_historico = buscar_treino_gerado(usuario["id"], semana_historica_numero)
    progresso_historico = buscar_progresso_semana(usuario["id"], semana_historica_numero)

    st.write(f"Semana {semana_historica['semana']} | Fase {semana_historica['fase']}")
    if not treino_historico:
        st.caption("O treino dessa semana ainda n\u00e3o foi gerado.")
        return

    for nome_treino, exercicios in treino_historico["json_treino"].items():
        status = "feito" if progresso_historico.get(nome_treino, {}).get("feito") else "n\u00e3o feito"
        st.markdown(
            f"""
            <div class="history-card">
                <strong>{nome_treino}</strong>
                <span>Status: {status} | {len(exercicios)} exerc\u00edcios</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_grade_treinos(semana, treino_semana, progresso):
    st.markdown(
        f"""
        <div class="section-shell">
            <h3>Treinos da semana</h3>
            <p>Semana {semana['semana']} | Fase {semana['fase'].capitalize()} | Escolha um treino para abrir os detalhes.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nomes_treinos = list(treino_semana.keys())
    if not nomes_treinos:
        st.info("Nenhum treino dispon\u00edvel para esta semana.")
        return

    for inicio in range(0, len(nomes_treinos), 2):
        colunas = st.columns(2)
        for indice, nome_treino in enumerate(nomes_treinos[inicio:inicio + 2]):
            exercicios = treino_semana[nome_treino]
            feito = bool(progresso.get(nome_treino, {}).get("feito"))
            with colunas[indice]:
                st.markdown(
                    f"""
                    <div class="workout-card">
                        <span class="eyebrow">Treino da semana</span>
                        <h4>{nome_treino}</h4>
                        <p>{len(exercicios)} exerc\u00edcios planejados para este bloco.</p>
                        <span class="status-pill {'done' if feito else 'pending'}">{'Conclu\u00eddo' if feito else 'Pendente'}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    f"Abrir {nome_treino}",
                    key=f"abrir_{nome_treino}",
                    type="secondary",
                    use_container_width=True,
                ):
                    st.session_state["treino_aberto"] = nome_treino
                    st.rerun()


def _render_cabecalho_execucao_treino(semana, nome_treino, progresso_item):
    feito_atual = bool(progresso_item.get("feito"))
    st.markdown(
        f"""
        <div class="execution-shell">
            <div class="execution-toolbar">
                <div>
                    <h3>{nome_treino}</h3>
                    <p>Fase {semana['fase'].capitalize()} | Semana {semana['semana']} | Foque apenas na execu\u00e7\u00e3o deste treino.</p>
                </div>
                <div>
                    <span class="status-pill {'done' if feito_atual else 'pending'}">{'Conclu\u00eddo' if feito_atual else 'Pendente'}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _voltar_para_lista_treinos():
    st.session_state["treino_aberto"] = None
    if st.session_state.get("feedback_pendente"):
        st.session_state.pop("feedback_pendente", None)
    st.rerun()


def _render_acoes_execucao_treino(usuario, semana, nome_treino, exercicios, progresso_item):
    feito_atual = bool(progresso_item.get("feito"))
    col_salvar, col_concluir, col_feedback = st.columns(3)
    with col_salvar:
        if st.button(
            "Salvar progresso",
            key=f"salvar_execucao_rapida_{usuario['id']}_{semana['semana']}_{nome_treino}",
            type="secondary",
            use_container_width=True,
        ):
            _salvar_execucao_treino_atleta(usuario, semana, nome_treino, exercicios)
    with col_concluir:
        if st.button(
            "Concluir treino",
            key=f"concluir_treino_{usuario['id']}_{semana['semana']}_{nome_treino}",
            type="primary",
            use_container_width=True,
        ):
            salvou = _salvar_execucao_treino_atleta(
                usuario,
                semana,
                nome_treino,
                exercicios,
                rerun_apos_salvar=False,
            )
            if not salvou:
                return
            marcar_treino_feito(usuario["id"], semana["semana"], nome_treino, True)
            st.session_state[f"feito_{usuario['id']}_{semana['semana']}_{nome_treino}"] = True
            _abrir_feedback_pendente(usuario["id"], semana["semana"], nome_treino, exercicios)
            st.session_state["mensagem_execucao_carga"] = f"Treino {nome_treino} concluido com sucesso."
            st.rerun()
    with col_feedback:
        if st.button(
            "Voltar para treinos",
            key=f"voltar_lista_treinos_{usuario['id']}_{semana['semana']}_{nome_treino}",
            type="secondary",
            use_container_width=True,
        ):
            _voltar_para_lista_treinos()

    if feito_atual:
        if st.button(
            "Dar feedback deste treino",
            key=f"reabrir_feedback_{usuario['id']}_{semana['semana']}_{nome_treino}",
            use_container_width=True,
        ):
            _abrir_feedback_pendente(usuario["id"], semana["semana"], nome_treino, exercicios)
            st.rerun()


def _render_execucao_treino(usuario, semana, nome_treino, exercicios, progresso_item):
    col_voltar, col_video = st.columns([1.2, 5])
    with col_voltar:
        if st.button(
            "\u2190 Voltar para treinos",
            key=f"voltar_topo_treinos_{usuario['id']}_{semana['semana']}_{nome_treino}",
            type="secondary",
            use_container_width=True,
        ):
            _voltar_para_lista_treinos()
    with col_video:
        st.caption("Tela focada na execucao. Registre apenas o que voce precisa durante a sessao.")

    _render_cabecalho_execucao_treino(semana, nome_treino, progresso_item)
    _render_guia_avaliacao_semana(semana, exercicios)
    _render_card_exercicios(exercicios)
    _render_form_execucao_exercicios(usuario, semana, nome_treino, exercicios)
    _render_acoes_execucao_treino(usuario, semana, nome_treino, exercicios, progresso_item)
    _render_feedback_pendente(nome_treino_esperado=nome_treino)


def _render_area_treinos(usuario, semana, treino_semana, progresso):
    treino_aberto = st.session_state.get("treino_aberto")
    if treino_aberto and treino_aberto not in treino_semana:
        st.session_state["treino_aberto"] = None
        treino_aberto = None

    if treino_aberto:
        if not st.session_state.get("feedback_pendente"):
            _render_video_exercicio()
        _render_execucao_treino(
            usuario,
            semana,
            treino_aberto,
            treino_semana[treino_aberto],
            progresso.get(treino_aberto, {}),
        )
        return

    _render_contexto_carga_semana(semana, listar_avaliacoes_forca(usuario["id"]))
    _render_resumo_avaliacao_concluida(usuario["id"], semana["semana"])
    st.markdown(
        """
        <div class="section-shell">
            <h3>Lista de treinos da semana</h3>
            <p>Escolha um treino para abrir uma tela exclusiva de execucao.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_grade_treinos(semana, treino_semana, progresso)


def tela_dashboard(usuario):
    st.title("\u00c1rea do atleta")
    _aplicar_estilo_dashboard()
    tema_app = st.session_state.get("tema_app", {})
    logo_treinador = resolver_logo_treinador(tema_app.get("logo_url"))
    with st.container():
        col_logo, col_banner, col_foto = st.columns([1, 7, 1])
        with col_logo:
            if logo_treinador:
                st.image(logo_treinador, width=80)
        with col_banner:
            nome_exibicao = usuario.get("apelido") or usuario.get("nome", "Atleta")
            st.markdown(
                f"""
                <div class="athlete-banner">
                    <h1>Minha \u00e1rea de treino</h1>
                    <p>{nome_exibicao}, acompanhe seu plano, abra seus treinos separadamente e registre seu feedback com clareza.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_foto:
            foto_bytes = _foto_perfil_bytes(usuario)
            if foto_bytes:
                st.image(foto_bytes, width=68)

    aviso_redefinicao = st.session_state.pop("aviso_redefinicao_objetivo", None)
    if aviso_redefinicao:
        if isinstance(aviso_redefinicao, dict):
            st.warning(
                f"{aviso_redefinicao['mensagem']} "
                f"Nova data da prova: {aviso_redefinicao['data_prova']}. "
                f"Fase atual do novo planejamento: {aviso_redefinicao['fase_atual']}. "
                f"Treinos de muscula\u00e7\u00e3o por semana: {aviso_redefinicao['treinos_semana']}."
            )
        else:
            st.warning(str(aviso_redefinicao))

    mensagem_feedback = st.session_state.pop("mensagem_feedback_treino", None)
    if mensagem_feedback:
        st.success(mensagem_feedback)
    mensagem_execucao = st.session_state.pop("mensagem_execucao_carga", None)
    if mensagem_execucao:
        st.success(mensagem_execucao)

    _render_status_acesso_atleta(usuario)
    _render_convites_pendentes(usuario)

    if st.session_state.get("mostrar_overview"):
        _render_overview_inicial()
        return

    _render_nav_local()
    cronograma, semana_atual, treino_semana, progresso, concluidos, percentual = _obter_contexto_semana(usuario)

    secao = st.session_state.get("secao_atleta", "visao_geral")
    if secao == "treinos":
        _render_area_treinos(usuario, semana_atual, treino_semana, progresso)
    else:
        _render_resumo_geral(usuario, semana_atual, treino_semana, concluidos, percentual)
        _render_historico(usuario, semana_atual, cronograma)

    registros = historico_progresso(usuario["id"])
    if registros:
        st.caption(f"Registros de progresso salvos: {len(registros)}")
