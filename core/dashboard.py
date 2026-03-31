import base64
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import streamlit as st
import streamlit.components.v1 as components

from core.cronograma import buscar_semana_por_numero, gerar_cronograma, obter_semana_atual
from core.exercicios import carregar_exercicios
from core.equipamentos import exercicio_compativel_com_equipamentos, normalizar_lista_equipamentos
from core.financeiro import obter_status_interface_atleta
from core.progresso import (
    buscar_progresso_semana,
    calcular_progresso_semanal,
    historico_progresso,
    listar_avaliacoes_forca,
    listar_execucao_treino,
    marcar_treino_feito,
    registrar_preferencia_substituicao,
    registrar_substituicao_exercicio,
    salvar_avaliacao_forca,
    salvar_execucao_exercicio,
    salvar_feedback_exercicio,
    salvar_feedback_treino,
)
from core.selecao import normalizar_categoria_funcional
from core.treinador import listar_convites_pendentes_do_atleta, resolver_logo_treinador
from core.treino import (
    buscar_treino_gerado,
    obter_ou_gerar_treino_semana,
    resetar_treinos_futuros,
    salvar_treino_gerado,
)


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


FEEDBACK_EXERCICIO_OPCOES = [
    ("muito_facil", "Muito fácil"),
    ("dentro_esperado", "Dentro do esperado"),
    ("muito_dificil", "Muito difícil"),
    ("desconforto", "Senti desconforto"),
    ("dor", "Senti dor"),
    ("nao_executei_bem", "Não consegui executar bem"),
]
MOTIVOS_SUBSTITUICAO = {
    "dor": "Estou com dor",
    "equipamento": "Não tenho o equipamento necessário",
}
REGIOES_DOR = {
    "joelho": "Joelho",
    "coluna": "Coluna",
    "ombro": "Ombro",
}
IMPACTO_PESO = {"baixo": 0, "medio": 1, "médio": 1, "alto": 2}
COMPLEXIDADE_PESO = {"baixo": 0, "basico": 0, "médio": 1, "medio": 1, "alto": 2, "avancado": 2}


def _rotulo_feedback_exercicio(valor):
    mapa = dict(FEEDBACK_EXERCICIO_OPCOES)
    return mapa.get(valor, (valor or "").replace("_", " ").title())


def _rotulo_motivo_substituicao(valor):
    return MOTIVOS_SUBSTITUICAO.get(valor, valor or "")


def _rotulo_regiao_dor(valor):
    return REGIOES_DOR.get(valor, valor or "")


def _chave_fase_prioridade(fase):
    fase_normalizada = (fase or "").strip().lower()
    if fase_normalizada == "específico":
        fase_normalizada = "especifico"
    return {
        "base": "prioridade_base",
        "especifico": "prioridade_especifico",
        "polimento": "prioridade_polimento",
        "retorno": "prioridade_retorno",
    }.get(fase_normalizada, "prioridade_base")


def _peso_impacto(valor):
    return IMPACTO_PESO.get((valor or "").strip().lower(), 1)


def _peso_complexidade(valor):
    return COMPLEXIDADE_PESO.get((valor or "").strip().lower(), 1)


def _exercicio_original_nome(exercicio):
    return exercicio.get("exercicio_original_nome") or exercicio.get("nome")


def _fechar_acao_exercicio():
    st.session_state.pop("acao_exercicio", None)


def _abrir_acao_exercicio(usuario, semana, nome_treino, exercicio):
    st.session_state.pop("exercicio_video_aberto", None)
    st.session_state["acao_exercicio"] = {
        "atleta_id": usuario["id"],
        "semana_numero": semana["semana"],
        "fase": semana["fase"],
        "nome_treino": nome_treino,
        "exercicio": dict(exercicio),
        "etapa": "menu",
    }


def _obter_execucao_por_exercicio(usuario_id, semana_numero, treino_nome):
    return {
        item["exercicio_nome"]: item
        for item in listar_execucao_treino(usuario_id, semana_numero, treino_nome)
    }


def _salvar_execucao_exercicio_individual(contexto, exercicio, valores):
    carga_realizada = float(valores.get("carga_realizada") or 0)
    reps_realizadas = int(valores.get("reps_realizadas") or exercicio.get("reps") or 0)
    series_realizadas = int(valores.get("series_realizadas") or exercicio.get("series") or 0)
    rpe_real = float(valores.get("rpe_real") or 0)
    observacao = (valores.get("observacao") or "").strip() or None

    if exercicio.get("modo_carga") == "avaliacao":
        if carga_realizada <= 0:
            st.error("Informe uma carga utilizada maior que zero.")
            return False
        if reps_realizadas <= 0:
            st.error("Informe repetições realizadas acima de zero.")
            return False
        if not 5 <= rpe_real <= 10:
            st.error("Selecione uma percepção de esforço entre 5 e 10.")
            return False

    payload = {
        **exercicio,
        "series_realizadas": series_realizadas,
        "reps_realizadas": reps_realizadas,
        "carga_realizada": carga_realizada if carga_realizada > 0 else None,
        "rpe_real": rpe_real if rpe_real > 0 else None,
        "observacao": observacao,
    }
    salvar_execucao_exercicio(
        contexto["atleta_id"],
        contexto["semana_numero"],
        contexto["fase"],
        contexto["nome_treino"],
        [payload],
    )

    if exercicio.get("modo_carga") == "avaliacao" and payload.get("carga_realizada") and payload.get("rpe_real"):
        avaliacao = salvar_avaliacao_forca(
            contexto["atleta_id"],
            contexto["semana_numero"],
            contexto["fase"],
            exercicio.get("categoria_movimento"),
            exercicio.get("nome"),
            payload.get("carga_realizada"),
            payload.get("reps_realizadas"),
            payload.get("rpe_real"),
        )
        if avaliacao:
            resetar_treinos_futuros(contexto["atleta_id"], contexto["semana_numero"])
            chave_resumo = f"resumo_avaliacao_{contexto['atleta_id']}_{contexto['semana_numero']}"
            resumo_existente = st.session_state.get(chave_resumo, [])
            resumo_existente = [item for item in resumo_existente if item.get("exercicio") != exercicio.get("nome")]
            resumo_existente.append(
                {
                    "exercicio": exercicio.get("nome"),
                    "carga": round(payload.get("carga_realizada") or 0, 1),
                    "reps": int(payload.get("reps_realizadas") or 0),
                    "rpe": round(payload.get("rpe_real") or 0, 1),
                }
            )
            st.session_state[chave_resumo] = resumo_existente

    st.session_state["mensagem_execucao_carga"] = f"Carga de {exercicio['nome']} salva."
    return True


def _justificativa_substituicao(candidato, motivo, regiao):
    equipamento = candidato.get("equipamento_bruto") or "sem equipamento"
    if motivo == "dor" and regiao:
        impacto = candidato.get(f"impacto_{regiao}") or "baixo"
        return f"Menor impacto em {REGIOES_DOR.get(regiao, regiao).lower()} ({impacto})."
    return f"Mesma função com equipamento diferente: {equipamento}."


def _gerar_sugestoes_substituicao(exercicio_atual, exercicios_db, usuario, fase, motivo, regiao=None, limite=3):
    categoria_alvo = normalizar_categoria_funcional(exercicio_atual.get("categoria"))
    prioridade_fase = _chave_fase_prioridade(fase)
    equipamento_original = set(normalizar_lista_equipamentos(exercicio_atual.get("equipamentos_necessarios") or []))
    nomes_bloqueados = {
        exercicio_atual.get("nome"),
        exercicio_atual.get("exercicio_original_nome"),
    }

    candidatos = []
    for item in exercicios_db:
        if item.get("nome") in nomes_bloqueados:
            continue
        if normalizar_categoria_funcional(item.get("categoria")) != categoria_alvo:
            continue
        if not exercicio_compativel_com_equipamentos(item, usuario):
            continue

        equipamento_candidato = set(normalizar_lista_equipamentos(item.get("equipamentos_necessarios") or []))
        if motivo == "equipamento" and equipamento_original and equipamento_candidato == equipamento_original:
            continue

        score = 0
        detalhe_extra = []
        score += int(item.get(prioridade_fase) or 0) * 100

        if item.get("principal_musculo") == exercicio_atual.get("principal_musculo"):
            score += 40
            detalhe_extra.append("mesmo foco muscular")

        if motivo == "dor" and regiao:
            impacto = _peso_impacto(item.get(f"impacto_{regiao}"))
            score += max(0, 30 - (impacto * 15))
            detalhe_extra.append(f"impacto {item.get(f'impacto_{regiao}') or 'medio'}")
        elif motivo == "equipamento":
            if equipamento_candidato != equipamento_original:
                score += 25
                detalhe_extra.append("equipamento diferente")

        complexidade_atual = _peso_complexidade(exercicio_atual.get("complexidade"))
        complexidade_candidato = _peso_complexidade(item.get("complexidade"))
        if complexidade_candidato <= complexidade_atual:
            score += 15
        else:
            score -= 10

        if item.get("favorito"):
            score += 5

        candidatos.append(
            {
                **item,
                "score": score,
                "detalhe_sugestao": _justificativa_substituicao(item, motivo, regiao),
                "criterios": detalhe_extra,
            }
        )

    candidatos.sort(
        key=lambda item: (
            item.get("score", 0),
            int(item.get(prioridade_fase) or 0),
            -_peso_impacto(item.get(f"impacto_{regiao}")) if motivo == "dor" and regiao else 0,
            -_peso_complexidade(item.get("complexidade")),
            item.get("nome", ""),
        ),
        reverse=True,
    )

    sugestoes = candidatos[:limite]
    nomes_prioritarios = {
        nome.strip()
        for nome in exercicio_atual.get("substituicoes_dor", []) or []
        if nome and nome.strip()
    }
    if nomes_prioritarios:
        sugestoes.sort(
            key=lambda item: (
                1 if item.get("nome") in nomes_prioritarios else 0,
                item.get("score", 0),
            ),
            reverse=True,
        )
    return sugestoes[:limite]


def _aplicar_substituicao_exercicio(contexto, exercicio_atual, sugestao):
    treino_salvo = buscar_treino_gerado(contexto["atleta_id"], contexto["semana_numero"])
    if not treino_salvo:
        st.error("Não foi possível localizar o treino salvo desta semana.")
        return False

    treino_json = treino_salvo["json_treino"]
    exercicios_treino = treino_json.get(contexto["nome_treino"], [])
    indice_alvo = next(
        (
            indice
            for indice, item in enumerate(exercicios_treino)
            if item.get("nome") == exercicio_atual.get("nome")
        ),
        None,
    )
    if indice_alvo is None:
        st.error("Não encontrei o exercício selecionado no treino atual.")
        return False

    exercicio_base = dict(exercicios_treino[indice_alvo])
    exercicio_original_nome = _exercicio_original_nome(exercicio_base)
    substituido = {
        **exercicio_base,
        **{chave: valor for chave, valor in sugestao.items() if chave not in {"score", "criterios", "detalhe_sugestao"}},
        "series": exercicio_base.get("series"),
        "reps": exercicio_base.get("reps"),
        "descanso": exercicio_base.get("descanso"),
        "rpe": exercicio_base.get("rpe"),
        "carga": exercicio_base.get("carga"),
        "carga_sugerida": exercicio_base.get("carga_sugerida"),
        "modo_carga": exercicio_base.get("modo_carga"),
        "categoria_movimento": exercicio_base.get("categoria_movimento"),
        "orientacao_carga": exercicio_base.get("orientacao_carga"),
        "execucao": exercicio_base.get("execucao"),
        "intencao": exercicio_base.get("intencao"),
        "substituido": True,
        "exercicio_original_nome": exercicio_original_nome,
        "substituicao_motivo": contexto.get("motivo"),
        "substituicao_regiao": contexto.get("regiao"),
        "substituicao_resumo": sugestao.get("detalhe_sugestao"),
        "substituido_em": datetime.now().replace(microsecond=0).isoformat(),
    }
    exercicios_treino[indice_alvo] = substituido

    salvar_treino_gerado(
        contexto["atleta_id"],
        contexto["semana_numero"],
        contexto["fase"],
        treino_json,
        editado_por_treinador=int(treino_salvo.get("editado_por_treinador") or 0),
    )
    registrar_substituicao_exercicio(
        contexto["atleta_id"],
        contexto["semana_numero"],
        contexto["fase"],
        contexto["nome_treino"],
        exercicio_original_nome,
        substituido["nome"],
        contexto.get("motivo"),
        regiao_dor=contexto.get("regiao"),
        detalhe_sugestao=sugestao.get("detalhe_sugestao"),
    )

    if contexto.get("motivo") == "dor":
        registrar_preferencia_substituicao(
            contexto["atleta_id"],
            {
                "nome": exercicio_original_nome,
                "categoria": exercicio_base.get("categoria"),
                "principal_musculo": exercicio_base.get("principal_musculo"),
                "motivo": contexto.get("regiao") or contexto.get("motivo"),
            },
        )
        resetar_treinos_futuros(contexto["atleta_id"], contexto["semana_numero"])

    st.session_state["mensagem_execucao_carga"] = f"{exercicio_original_nome} foi substituído por {substituido['nome']}."
    return True


def _render_dialog_acoes_exercicio():
    contexto = st.session_state.get("acao_exercicio")
    if not contexto:
        return

    exercicio = contexto["exercicio"]
    base_key = (
        f"{contexto['atleta_id']}_{contexto['semana_numero']}_{contexto['nome_treino']}_{_exercicio_original_nome(exercicio)}"
        .replace(" ", "_")
    )

    etapa = contexto.get("etapa", "menu")
    st.caption(f"Treino {contexto['nome_treino']}")
    st.markdown(f"**{exercicio['nome']}**")

    if etapa == "menu":
        if st.button("Registrar feedback", key=f"acao_feedback_{base_key}", use_container_width=True):
            contexto["etapa"] = "feedback"
            st.rerun()
        if st.button("Ajustar carga", key=f"acao_carga_{base_key}", use_container_width=True):
            contexto["etapa"] = "carga"
            st.rerun()
        if st.button("Substituir exercício", key=f"acao_substituir_{base_key}", use_container_width=True):
            contexto["etapa"] = "substituir"
            st.rerun()
        if st.button("Cancelar", key=f"acao_cancelar_{base_key}", use_container_width=True):
            _fechar_acao_exercicio()
            st.rerun()
        return

    if etapa == "feedback":
        categoria = st.radio(
            "Como foi este exercício?",
            [item[0] for item in FEEDBACK_EXERCICIO_OPCOES],
            format_func=_rotulo_feedback_exercicio,
            key=f"feedback_categoria_{base_key}",
        )
        observacao = st.text_area(
            "Observação opcional",
            key=f"feedback_obs_{base_key}",
            placeholder="Ex: senti desconforto no joelho nas últimas repetições.",
            max_chars=220,
        )
        col_salvar, col_voltar = st.columns(2)
        with col_salvar:
            if st.button("Salvar feedback", key=f"feedback_salvar_{base_key}", use_container_width=True):
                salvar_feedback_exercicio(
                    contexto["atleta_id"],
                    contexto["semana_numero"],
                    contexto["fase"],
                    contexto["nome_treino"],
                    exercicio["nome"],
                    categoria,
                    observacao=observacao,
                    exercicio_original_nome=_exercicio_original_nome(exercicio),
                )
                if categoria in {"dor", "desconforto", "nao_executei_bem", "muito_dificil"}:
                    salvar_feedback_treino(
                        contexto["atleta_id"],
                        contexto["semana_numero"],
                        contexto["nome_treino"],
                        "muito ruim",
                        feedback_contexto_ruim="feedback_exercicio",
                        exercicio_substituir=exercicio["nome"],
                        motivo_exercicio_ruim=categoria,
                    )
                st.session_state["mensagem_feedback_treino"] = f"Feedback de {exercicio['nome']} salvo."
                _fechar_acao_exercicio()
                st.rerun()
        with col_voltar:
            if st.button("Voltar", key=f"feedback_voltar_{base_key}", use_container_width=True):
                contexto["etapa"] = "menu"
                st.rerun()
        return

    if etapa == "carga":
        execucoes = _obter_execucao_por_exercicio(contexto["atleta_id"], contexto["semana_numero"], contexto["nome_treino"])
        execucao_atual = execucoes.get(exercicio["nome"], {})
        carga = st.number_input(
            "Carga utilizada (kg)",
            min_value=0.0,
            max_value=500.0,
            step=0.5,
            value=float(execucao_atual.get("carga_realizada") or exercicio.get("carga_sugerida") or 0.0),
            key=f"carga_valor_{base_key}",
        )
        reps = st.number_input(
            "Repetições realizadas",
            min_value=0,
            max_value=50,
            value=int(execucao_atual.get("reps_realizadas") or exercicio.get("reps") or 0),
            key=f"carga_reps_{base_key}",
        )
        series = st.number_input(
            "Séries realizadas",
            min_value=0,
            max_value=20,
            value=int(execucao_atual.get("series_realizadas") or exercicio.get("series") or 0),
            key=f"carga_series_{base_key}",
        )
        rpe_default = execucao_atual.get("rpe_real") or (7 if exercicio.get("modo_carga") == "avaliacao" else 0)
        rpe = st.number_input(
            "Percepção de esforço real",
            min_value=0.0,
            max_value=10.0,
            step=0.5,
            value=float(rpe_default),
            key=f"carga_rpe_{base_key}",
        )
        observacao = st.text_input(
            "Observação opcional",
            value=str(execucao_atual.get("observacao") or ""),
            key=f"carga_obs_{base_key}",
            placeholder="Ex: carga segura e controlada",
        )
        col_salvar, col_voltar = st.columns(2)
        with col_salvar:
            if st.button("Salvar carga", key=f"carga_salvar_{base_key}", use_container_width=True):
                if _salvar_execucao_exercicio_individual(
                    contexto,
                    exercicio,
                    {
                        "carga_realizada": carga,
                        "reps_realizadas": reps,
                        "series_realizadas": series,
                        "rpe_real": rpe,
                        "observacao": observacao,
                    },
                ):
                    _fechar_acao_exercicio()
                    st.rerun()
        with col_voltar:
            if st.button("Voltar", key=f"carga_voltar_{base_key}", use_container_width=True):
                contexto["etapa"] = "menu"
                st.rerun()
        return

    if etapa == "substituir":
        motivo = st.radio(
            "Por que você quer substituir este exercício?",
            list(MOTIVOS_SUBSTITUICAO.keys()),
            format_func=_rotulo_motivo_substituicao,
            key=f"substituir_motivo_{base_key}",
        )
        contexto["motivo"] = motivo
        if motivo == "dor":
            regiao = st.selectbox(
                "Onde está a dor?",
                list(REGIOES_DOR.keys()),
                format_func=_rotulo_regiao_dor,
                key=f"substituir_regiao_{base_key}",
            )
            contexto["regiao"] = regiao
        else:
            contexto["regiao"] = None

        exercicios_db = carregar_exercicios()
        usuario_contexto = st.session_state.get("usuario") or {"id": contexto["atleta_id"]}
        sugestoes = _gerar_sugestoes_substituicao(
            exercicio,
            exercicios_db,
            usuario_contexto,
            contexto["fase"],
            motivo,
            regiao=contexto.get("regiao"),
        )

        if not sugestoes:
            st.warning("Nenhuma alternativa compatível foi encontrada para este contexto.")
        else:
            opcoes = [item["nome"] for item in sugestoes]
            for item in sugestoes:
                equipamento = item.get("equipamento_bruto") or "Sem equipamento"
                st.markdown(
                    f"**{item['nome']}**  \nEquipamento: {equipamento}  \n{item['detalhe_sugestao']}"
                )

            escolhida = st.radio(
                "Escolha uma alternativa",
                opcoes,
                key=f"substituir_opcao_{base_key}",
            )
            sugestao_escolhida = next(item for item in sugestoes if item["nome"] == escolhida)
            if st.button("Confirmar substituição", key=f"substituir_confirmar_{base_key}", use_container_width=True):
                if _aplicar_substituicao_exercicio(contexto, exercicio, sugestao_escolhida):
                    _fechar_acao_exercicio()
                    st.rerun()

        col_voltar, col_cancelar = st.columns(2)
        with col_voltar:
            if st.button("Voltar", key=f"substituir_voltar_{base_key}", use_container_width=True):
                contexto["etapa"] = "menu"
                st.rerun()
        with col_cancelar:
            if st.button("Cancelar", key=f"substituir_cancelar_{base_key}", use_container_width=True):
                _fechar_acao_exercicio()
                st.rerun()


def _registrar_dialog_acoes_exercicio():
    if not hasattr(st, "dialog"):
        return None

    @st.dialog("Ações do exercício")
    def _render_dialog():
        _render_dialog_acoes_exercicio()

    return _render_dialog


_RENDER_DIALOG_ACOES_EXERCICIO = _registrar_dialog_acoes_exercicio()


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
        .exercise-header-title {
            display: block;
            color: var(--tri-text-strong);
            font-size: 1rem;
            line-height: 1.35;
            margin: 0;
        }
        div[class*="st-key-acoes_exercicio_"] {
            display: flex;
            justify-content: flex-end;
        }
        div[class*="st-key-acoes_exercicio_"] button {
            width: 2.4rem !important;
            min-width: 2.4rem !important;
            max-width: 2.4rem !important;
            min-height: 2.4rem !important;
            padding: 0 !important;
            border-radius: 0.8rem !important;
        }
        div[class*="st-key-acoes_exercicio_"] button p {
            font-size: 1rem;
            line-height: 1;
        }
        .exercise-card {
            padding-top: 0.1rem;
        }
        .exercise-card .exercise-meta-line {
            color: var(--tri-text-soft);
            font-size: 0.92rem;
            display: block;
        }
        .exercise-card .exercise-guidance {
            margin-top: 0.4rem;
            color: var(--tri-text);
            font-size: 0.9rem;
            line-height: 1.4;
            display: block;
        }
        .exercise-meta-badge {
            display: inline-block;
            margin: 0.1rem 0.35rem 0 0;
            padding: 0.18rem 0.55rem;
            border-radius: 999px;
            background: var(--tri-info-bg);
            color: var(--tri-info-text);
            border: 1px solid var(--tri-info-border);
            font-size: 0.74rem;
            font-weight: 700;
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
            margin: 0.1rem 0.35rem 0 0;
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
                padding-top: 0.05rem;
            }
            div[class*="st-key-acoes_exercicio_"] button {
                width: 2.55rem !important;
                min-width: 2.55rem !important;
                max-width: 2.55rem !important;
                min-height: 2.55rem !important;
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


def _render_card_exercicios(usuario, semana, nome_treino, exercicios):
    for indice, exercicio in enumerate(exercicios):
        col_info, col_video, col_acoes = st.columns([6, 1.2, 1.2])
        with col_info:
            orientacao_carga = exercicio.get("orientacao_carga")
            instrucoes = exercicio.get("observacao_curta") or exercicio.get("execucao") or ""
            complemento_carga = f'<span class="exercise-guidance">{orientacao_carga}</span>' if orientacao_carga else ""
            bloco_instrucoes = f'<span class="exercise-guidance">{instrucoes}</span>' if instrucoes else ""
            badge_avaliacao = (
                '<div class="badge-evaluation">Avaliacao</div>'
                if exercicio.get("modo_carga") == "avaliacao"
                else ""
            )
            badge_substituicao = (
                '<div class="exercise-meta-badge">Exercício alternativo</div>'
                if exercicio.get("substituido")
                else ""
            )
            origem_substituicao = (
                f'<span class="exercise-guidance">Origem: {exercicio.get("exercicio_original_nome")}</span>'
                if exercicio.get("substituido")
                else ""
            )
            classe_avaliacao = "evaluation" if exercicio.get("modo_carga") == "avaliacao" else ""
            st.markdown(
                (
                    f'<div class="exercise-card {classe_avaliacao}">'
                    f"{badge_avaliacao}"
                    f"{badge_substituicao}"
                    f"<strong>{exercicio['nome']}</strong>"
                    f"<span>Séries {exercicio['series']} | Reps {exercicio['reps']} | "
                    f"Descanso {exercicio['descanso']} | Percepção de esforço alvo {exercicio.get('rpe', '-')}</span>"
                    f"{bloco_instrucoes}"
                    f"{complemento_carga}"
                    f"{origem_substituicao}"
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
        with col_acoes:
            if st.button(
                "⋯",
                key=f"acoes_exercicio_{nome_treino}_{indice}_{_exercicio_original_nome(exercicio)}",
                use_container_width=True,
            ):
                _abrir_acao_exercicio(usuario, semana, nome_treino, exercicio)
                st.rerun()


def _render_card_exercicios_integrado(usuario, semana, nome_treino, exercicios):
    for indice, exercicio in enumerate(exercicios):
        orientacao_carga = exercicio.get("orientacao_carga")
        instrucoes = exercicio.get("observacao_curta") or exercicio.get("execucao") or ""
        complemento_carga = f'<span class="exercise-guidance">{orientacao_carga}</span>' if orientacao_carga else ""
        bloco_instrucoes = f'<span class="exercise-guidance">{instrucoes}</span>' if instrucoes else ""
        badge_avaliacao = (
            '<div class="badge-evaluation">Avaliacao</div>'
            if exercicio.get("modo_carga") == "avaliacao"
            else ""
        )
        badge_substituicao = (
            '<div class="exercise-meta-badge">Exerc\u00edcio alternativo</div>'
            if exercicio.get("substituido")
            else ""
        )
        origem_substituicao = (
            f'<span class="exercise-guidance">Origem: {exercicio.get("exercicio_original_nome")}</span>'
            if exercicio.get("substituido")
            else ""
        )
        classe_avaliacao = "evaluation" if exercicio.get("modo_carga") == "avaliacao" else ""

        with st.container(border=True):
            col_titulo, col_acoes = st.columns([6.6, 0.7], vertical_alignment="top")
            with col_titulo:
                st.markdown(
                    f'<div class="exercise-header-title"><strong>{exercicio["nome"]}</strong></div>',
                    unsafe_allow_html=True,
                )
            with col_acoes:
                if st.button(
                    "\u22ef",
                    key=f"acoes_exercicio_{nome_treino}_{indice}_{_exercicio_original_nome(exercicio)}",
                    help="Acoes do exercicio",
                ):
                    _abrir_acao_exercicio(usuario, semana, nome_treino, exercicio)
                    st.rerun()

            st.markdown(
                (
                    f'<div class="exercise-card {classe_avaliacao}">'
                    f"{badge_avaliacao}"
                    f"{badge_substituicao}"
                    f"<span class=\"exercise-meta-line\">S\u00e9ries {exercicio['series']} | Reps {exercicio['reps']} | "
                    f"Descanso {exercicio['descanso']} | Percep\u00e7\u00e3o de esfor\u00e7o alvo {exercicio.get('rpe', '-')}</span>"
                    f"{bloco_instrucoes}"
                    f"{complemento_carga}"
                    f"{origem_substituicao}"
                    f"</div>"
                ),
                unsafe_allow_html=True,
            )

        if st.button(
            "V\u00eddeo",
            key=f"video_exercicio_{indice}_{exercicio['nome']}",
            disabled=not exercicio.get("link_yt"),
            use_container_width=True,
        ):
            st.session_state["exercicio_video_aberto"] = exercicio
            st.rerun()
        st.markdown("")


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
            f"{item['exercicio']} | carga {item['carga']} kg | reps {item['reps']} | Percepcao de esforco {item['rpe']}"
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
        st.warning("Semana 2: os exercicios-base marcados como avaliacao de carga devem registrar peso usado, repeticoes e percepcao de esforco.")
        return

    total_avaliacoes = len(avaliacoes or [])
    if total_avaliacoes:
        st.success(
            f"Semana {semana['semana']}: as cargas sugeridas usam a avaliacao da semana 2, a fase {semana['fase']} e os registros de percepcao de esforco/dor."
        )
    else:
        st.info("Ainda nao ha avaliacao de carga salva. As orientacoes seguem qualitativas ate existir referencia.")


def _anexar_links_exercicios(treino_semana, exercicios_db):
    metadados_por_nome = {
        item["nome"]: item
        for item in exercicios_db
        if item.get("nome")
    }
    treino_com_links = {}

    for nome_treino, exercicios in treino_semana.items():
        treino_com_links[nome_treino] = []
        for exercicio in exercicios:
            item = dict(exercicio)
            metadados = metadados_por_nome.get(item.get("nome"), {})
            for chave in (
                "link_yt",
                "equipamento",
                "equipamento_bruto",
                "equipamentos_necessarios",
                "complexidade",
                "impacto_joelho",
                "impacto_coluna",
                "impacto_ombro",
                "substituicoes_dor",
                "favorito",
            ):
                item[chave] = item.get(chave) or metadados.get(chave)
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
    _fechar_acao_exercicio()
    st.rerun()


def _render_acoes_execucao_treino(usuario, semana, nome_treino, exercicios, progresso_item):
    feito_atual = bool(progresso_item.get("feito"))
    col_status, col_concluir, col_voltar = st.columns([2.2, 1.2, 1.2])
    with col_status:
        st.caption("Use o menu de ações em cada exercício para registrar feedback, carga e substituições.")
    with col_concluir:
        if st.button(
            "Concluir treino",
            key=f"concluir_treino_{usuario['id']}_{semana['semana']}_{nome_treino}",
            type="primary",
            use_container_width=True,
        ):
            marcar_treino_feito(usuario["id"], semana["semana"], nome_treino, True)
            st.session_state[f"feito_{usuario['id']}_{semana['semana']}_{nome_treino}"] = True
            st.session_state["mensagem_execucao_carga"] = f"Treino {nome_treino} concluído com sucesso."
            st.rerun()
    with col_voltar:
        if st.button(
            "Voltar para treinos",
            key=f"voltar_lista_treinos_{usuario['id']}_{semana['semana']}_{nome_treino}",
            type="secondary",
            use_container_width=True,
        ):
            _voltar_para_lista_treinos()

    if feito_atual:
        st.caption("Treino concluído. Você ainda pode ajustar qualquer exercício pelo botão de ações.")


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
    _render_card_exercicios_integrado(usuario, semana, nome_treino, exercicios)
    _render_acoes_execucao_treino(usuario, semana, nome_treino, exercicios, progresso_item)
    if _RENDER_DIALOG_ACOES_EXERCICIO and st.session_state.get("acao_exercicio", {}).get("nome_treino") == nome_treino:
        _RENDER_DIALOG_ACOES_EXERCICIO()
    elif st.session_state.get("acao_exercicio", {}).get("nome_treino") == nome_treino:
        st.markdown("---")
        _render_dialog_acoes_exercicio()


def _render_area_treinos(usuario, semana, treino_semana, progresso):
    treino_aberto = st.session_state.get("treino_aberto")
    if treino_aberto and treino_aberto not in treino_semana:
        st.session_state["treino_aberto"] = None
        treino_aberto = None

    if treino_aberto:
        if not st.session_state.get("acao_exercicio"):
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
