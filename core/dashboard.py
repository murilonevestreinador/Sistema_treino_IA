import base64
from urllib.parse import parse_qs, urlparse

import streamlit as st
import streamlit.components.v1 as components

from core.cronograma import buscar_semana_por_numero, gerar_cronograma, obter_semana_atual
from core.exercicios import carregar_exercicios
from core.progresso import (
    buscar_progresso_semana,
    calcular_progresso_semanal,
    historico_progresso,
    marcar_treino_feito,
    registrar_preferencia_substituicao,
    salvar_feedback_treino,
)
from core.treinador import listar_convites_pendentes_do_atleta, responder_convite
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
                radial-gradient(circle at top left, rgba(27, 110, 104, 0.08), transparent 26%),
                linear-gradient(180deg, #f6f8f6 0%, #edf3ef 100%);
        }
        .athlete-banner {
            padding: 1.1rem 1.3rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #102f2b 0%, #1f5c53 58%, #2f7d71 100%);
            color: #f5fbf8;
            box-shadow: 0 18px 42px rgba(16, 47, 43, 0.14);
            margin-bottom: 1rem;
        }
        .athlete-banner h1 {
            margin: 0;
            font-size: 1.85rem;
        }
        .athlete-banner p {
            margin: 0.35rem 0 0;
            color: rgba(245, 251, 248, 0.82);
        }
        .metric-card, .workout-detail, .history-card {
            border-radius: 18px;
            border: 1px solid rgba(16, 47, 43, 0.08);
            background: rgba(255, 255, 255, 0.92);
            padding: 1rem 1.05rem;
            box-shadow: 0 12px 30px rgba(31, 92, 83, 0.08);
            margin-bottom: 0.9rem;
        }
        .metric-card strong,
        .history-card strong {
            display: block;
            color: #14342f;
            margin-bottom: 0.2rem;
        }
        .section-shell {
            border-radius: 22px;
            border: 1px solid rgba(16, 47, 43, 0.08);
            background:
                radial-gradient(circle at top right, rgba(47, 125, 113, 0.10), transparent 32%),
                rgba(255, 255, 255, 0.78);
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .section-shell h3 {
            margin: 0 0 0.35rem;
            color: #102f2b;
        }
        .section-shell p {
            margin: 0;
            color: #40615b;
        }
        .workout-card {
            border-radius: 18px;
            border: 1px solid rgba(16, 47, 43, 0.08);
            background:
                linear-gradient(160deg, rgba(255, 255, 255, 0.96) 0%, rgba(236, 245, 241, 0.96) 100%);
            padding: 1rem;
            min-height: 150px;
            box-shadow: 0 12px 28px rgba(31, 92, 83, 0.08);
            margin-bottom: 0.7rem;
        }
        .workout-card.active {
            border-color: rgba(31, 92, 83, 0.28);
            box-shadow: 0 16px 34px rgba(31, 92, 83, 0.14);
            background:
                linear-gradient(155deg, rgba(244, 251, 249, 1) 0%, rgba(220, 241, 233, 0.95) 100%);
        }
        .workout-card .eyebrow {
            display: inline-block;
            font-size: 0.72rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #2f7d71;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .workout-card h4 {
            margin: 0 0 0.35rem;
            color: #102f2b;
            font-size: 1.15rem;
        }
        .workout-card p {
            margin: 0;
            color: #4a6761;
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
            background: rgba(33, 128, 92, 0.12);
            color: #1e6e51;
        }
        .status-pill.pending {
            background: rgba(16, 47, 43, 0.08);
            color: #36534d;
        }
        .exercise-card {
            border-radius: 16px;
            border: 1px solid rgba(16, 47, 43, 0.07);
            background: rgba(247, 251, 249, 0.92);
            padding: 0.85rem 0.95rem;
            margin-bottom: 0.55rem;
        }
        .exercise-card strong {
            display: block;
            color: #123a34;
            margin-bottom: 0.18rem;
        }
        .exercise-card span {
            color: #4f6863;
            font-size: 0.92rem;
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
            color: #102f2b;
        }
        .detail-header p {
            margin: 0.15rem 0 0;
            color: #4f6863;
        }
        .nav-chip-row .stButton > button {
            width: 100%;
        }
        .stButton > button, .stFormSubmitButton > button {
            border-radius: 999px;
            border: none;
            background: linear-gradient(135deg, #1f5c53 0%, #2f7d71 100%);
            color: white;
            font-weight: 700;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover {
            background: linear-gradient(135deg, #184942 0%, #276a60 100%);
            color: white;
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

    st.info("Voc\u00ea possui convites pendentes de treinadores.")
    for convite in convites:
        col_info, col_aceitar, col_recusar = st.columns([4, 1, 1])
        with col_info:
            st.write(f"{convite['treinador_nome']} ({convite['treinador_email']})")
        with col_aceitar:
            if st.button("Aceitar", key=f"aceitar_{convite['treinador_id']}"):
                responder_convite(usuario["id"], convite["treinador_id"], aceitar=True)
                st.rerun()
        with col_recusar:
            if st.button("Recusar", key=f"recusar_{convite['treinador_id']}"):
                responder_convite(usuario["id"], convite["treinador_id"], aceitar=False)
                st.rerun()


def _render_overview_inicial():
    mensagem = st.session_state.get("mensagem_onboarding")
    st.subheader("Bem-vindo ao seu planejamento")
    if mensagem:
        st.success(mensagem)
    if st.button("Ir para minha \u00e1rea", key="btn_ir_area"):
        st.session_state["mostrar_overview"] = False
        st.rerun()


def _abrir_feedback_pendente(usuario_id, semana_numero, nome_treino, exercicios):
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

    st.markdown("---")
    with st.container():
        st.subheader(f"Feedback do treino {feedback['nome_treino']}")
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
                    "dor em um exerc\u00edcio",
                    "n\u00e3o gostou do exerc\u00edcio",
                    "exerc\u00edcio ficou desconfort\u00e1vel",
                    "n\u00e3o tem o equipamento na academia",
                ],
                key=f"motivo_ruim_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
            )
            nomes_exercicios = [item["nome"] for item in feedback["exercicios"]]
            exercicio_escolhido = st.selectbox(
                "Qual exerc\u00edcio do treino gerou esse desconforto?",
                nomes_exercicios,
                key=f"exercicio_ruim_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
            )

        if not st.button(
            "Enviar feedback",
            key=f"enviar_feedback_{feedback['atleta_id']}_{feedback['semana_numero']}_{feedback['nome_treino']}",
        ):
            return

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
                    "Obrigado pelo feedback. Vamos substituir esse exerc\u00edcio nos pr\u00f3ximos treinos."
                )
            else:
                st.session_state["mensagem_feedback_treino"] = "Obrigado pelo feedback."
        else:
            st.session_state["mensagem_feedback_treino"] = "Obrigado e at\u00e9 o pr\u00f3ximo treino."

        st.session_state.pop("feedback_pendente", None)
        st.rerun()


def _render_card_exercicios(exercicios):
    for indice, exercicio in enumerate(exercicios):
        col_info, col_video = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"""
                <div class="exercise-card">
                    <strong>{exercicio['nome']}</strong>
                    <span>{exercicio['series']} x {exercicio['reps']} | Descanso {exercicio['descanso']}</span>
                </div>
                """,
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


def _render_resumo_geral(semana, treino_semana, concluidos, percentual):
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
        return None

    treino_aberto = st.session_state.get("treino_aberto_nome")
    if treino_aberto not in treino_semana:
        treino_aberto = nomes_treinos[0]
        st.session_state["treino_aberto_nome"] = treino_aberto

    for inicio in range(0, len(nomes_treinos), 2):
        colunas = st.columns(2)
        for indice, nome_treino in enumerate(nomes_treinos[inicio:inicio + 2]):
            exercicios = treino_semana[nome_treino]
            feito = bool(progresso.get(nome_treino, {}).get("feito"))
            ativo = nome_treino == treino_aberto
            with colunas[indice]:
                st.markdown(
                    f"""
                    <div class="workout-card {'active' if ativo else ''}">
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
                    type="primary" if ativo else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["treino_aberto_nome"] = nome_treino
                    st.rerun()
    return st.session_state.get("treino_aberto_nome")


def _render_detalhe_treino(usuario, semana, nome_treino, exercicios, progresso_item):
    feito_atual = bool(progresso_item.get("feito"))
    st.markdown(
        f"""
        <div class="workout-detail">
            <div class="detail-header">
                <div>
                    <h3>{nome_treino}</h3>
                    <p>Execute o treino, marque como conclu\u00eddo e registre seu feedback ao final.</p>
                </div>
                <div>
                    <span class="status-pill {'done' if feito_atual else 'pending'}">{'Conclu\u00eddo' if feito_atual else 'Pendente'}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_card_exercicios(exercicios)

    chave_checkbox = f"feito_{usuario['id']}_{semana['semana']}_{nome_treino}"
    if chave_checkbox not in st.session_state:
        st.session_state[chave_checkbox] = feito_atual

    novo_valor = st.checkbox("Marcar treino como conclu\u00eddo", key=chave_checkbox)
    if novo_valor != feito_atual:
        marcar_treino_feito(usuario["id"], semana["semana"], nome_treino, novo_valor)
        if novo_valor:
            _abrir_feedback_pendente(usuario["id"], semana["semana"], nome_treino, exercicios)
        elif st.session_state.get("feedback_pendente", {}).get("nome_treino") == nome_treino:
            st.session_state.pop("feedback_pendente", None)
        st.rerun()

    if bool(buscar_progresso_semana(usuario["id"], semana["semana"]).get(nome_treino, {}).get("feito")):
        if st.button(
            "Dar feedback deste treino",
            key=f"reabrir_feedback_{usuario['id']}_{semana['semana']}_{nome_treino}",
            use_container_width=True,
        ):
            _abrir_feedback_pendente(usuario["id"], semana["semana"], nome_treino, exercicios)
            st.rerun()

    _render_feedback_pendente(nome_treino_esperado=nome_treino)


def _render_area_treinos(usuario, semana, treino_semana, progresso):
    _render_video_exercicio()
    treino_aberto = _render_grade_treinos(semana, treino_semana, progresso)
    if not treino_aberto:
        return
    st.markdown("")
    _render_detalhe_treino(
        usuario,
        semana,
        treino_aberto,
        treino_semana[treino_aberto],
        progresso.get(treino_aberto, {}),
    )


def tela_dashboard(usuario):
    st.title("\u00c1rea do atleta")
    _aplicar_estilo_dashboard()
    with st.container():
        col_banner, col_foto = st.columns([8, 1])
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
        _render_resumo_geral(semana_atual, treino_semana, concluidos, percentual)
        _render_historico(usuario, semana_atual, cronograma)

    registros = historico_progresso(usuario["id"])
    if registros:
        st.caption(f"Registros de progresso salvos: {len(registros)}")
