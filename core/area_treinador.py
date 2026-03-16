import base64
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from core.carga import rotulo_categoria_movimento
from core.bi import BIValidationError, TrainerBIService
from core.cronograma import buscar_semana_por_numero, gerar_cronograma, obter_semana_atual
from core.exercicios import carregar_exercicios
from core.progresso import (
    buscar_progresso_semana,
    calcular_progresso_semanal,
    listar_avaliacoes_forca,
    listar_historico_cargas,
    salvar_ajuste_manual_avaliacao,
)
from core.treinador import (
    buscar_atleta_vinculado,
    gerar_link_convite,
    listar_atletas_do_treinador,
    listar_vinculos,
)
from core.treino import (
    buscar_treino_gerado,
    obter_ou_gerar_treino_semana,
    resetar_treinos_futuros,
    salvar_treino_gerado,
)
from core.usuarios import buscar_usuario_por_id

try:
    from streamlit_sortables import sort_items
except ImportError:
    sort_items = None

DEFAULT_PUBLIC_APP_URL = "https://trilab-treinamento.onrender.com"

SEXO_FILTROS = {
    "Todos": None,
    "Feminino": "feminino",
    "Masculino": "masculino",
    "Outro": "outro",
}
OBJETIVO_FILTROS = {
    "Todos": None,
    "Desempenho": "desempenho",
    "Hipertrofia": "hipertrofia",
    "Saude": "saude",
    "Perda de peso": "perda_peso",
}


def _foto_perfil_bytes(foto_perfil):
    if not foto_perfil:
        return None
    try:
        return base64.b64decode(foto_perfil)
    except Exception:
        return None


def _formatar_percentual(valor):
    if valor is None:
        return "-"
    return f"{float(valor):.2f}%"


def _formatar_data_hora(valor):
    if not valor:
        return "-"
    return str(valor).replace("T", " ")


def _assinatura_editor_treino(treino):
    return tuple(
        (
            nome_treino,
            tuple(
                (
                    exercicio.get("nome"),
                    exercicio.get("series"),
                    exercicio.get("reps"),
                    exercicio.get("descanso"),
                )
                for exercicio in exercicios
            ),
        )
        for nome_treino, exercicios in treino.items()
    )


def _chave_editor_treino(atleta_id, semana_numero):
    return f"editor_treino_{atleta_id}_{semana_numero}"


def _construir_estado_editor_treino(treino):
    return {
        nome_treino: [
            {
                "uid": uuid.uuid4().hex,
                "dados": {
                    **dict(exercicio),
                    "nome": exercicio.get("nome", ""),
                    "series": int(exercicio.get("series") or 3),
                    "reps": int(exercicio.get("reps") or 10),
                    "descanso": str(exercicio.get("descanso") or ""),
                },
            }
            for exercicio in exercicios
        ]
        for nome_treino, exercicios in treino.items()
    }


def _garantir_editor_treino(atleta_id, semana_numero, treino):
    chave = _chave_editor_treino(atleta_id, semana_numero)
    assinatura = _assinatura_editor_treino(treino)
    estado = st.session_state.get(chave)
    if not estado or estado.get("assinatura_origem") != assinatura:
        st.session_state[chave] = {
            "assinatura_origem": assinatura,
            "treinos": _construir_estado_editor_treino(treino),
        }
    return st.session_state[chave]["treinos"]


def _garantir_ordem_editor(atleta_id, semana_numero, treino):
    return {
        nome_treino: [f"{nome_treino}::{indice}" for indice, _ in enumerate(exercicios)]
        for nome_treino, exercicios in treino.items()
    }


def _exercicios_ordenados(treino, ordem_salva):
    treino_ordenado = {}
    for nome_treino, exercicios in treino.items():
        mapa_exercicios = {
            f"{nome_treino}::{indice}": exercicio
            for indice, exercicio in enumerate(exercicios)
        }
        ordem_atual = [item_id for item_id in ordem_salva.get(nome_treino, []) if item_id in mapa_exercicios]
        faltantes = [item_id for item_id in mapa_exercicios if item_id not in ordem_atual]
        treino_ordenado[nome_treino] = [mapa_exercicios[item_id] for item_id in ordem_atual + faltantes]
    return treino_ordenado


def _widget_key_editor(campo, atleta_id, semana_numero, nome_treino, exercicio_uid):
    return f"editor_{campo}_{atleta_id}_{semana_numero}_{nome_treino}_{exercicio_uid}"


def _rotulo_bloco_exercicio(exercicio, indice_base):
    return (
        f":: {indice_base + 1:02d} | {exercicio.get('nome') or 'Novo exercicio'} | "
        f"{exercicio.get('series', '-')}x{exercicio.get('reps', '-')} | "
        f"descanso {exercicio.get('descanso') or '-'}"
    )


def _sort_component_habilitado():
    if not sort_items:
        return False
    if os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        return False
    return True


def _render_ordenacao_exercicios(atleta_id, semana_numero, treino):
    ordem_salva = _garantir_ordem_editor(atleta_id, semana_numero, treino)

    for nome_treino, exercicios in treino.items():
        st.markdown(f"**Ordenar {nome_treino}**")
        st.caption("Arraste os blocos para cima ou para baixo antes de salvar a edicao.")

        ids_exercicios = [f"{nome_treino}::{indice}" for indice, _ in enumerate(exercicios)]
        rotulo_por_id = {
            item_id: _rotulo_bloco_exercicio(exercicio, indice)
            for indice, (item_id, exercicio) in enumerate(zip(ids_exercicios, exercicios))
        }
        ordem_atual = [item_id for item_id in ordem_salva.get(nome_treino, []) if item_id in rotulo_por_id]
        ordem_atual += [item_id for item_id in ids_exercicios if item_id not in ordem_atual]

        if _sort_component_habilitado():
            itens_exibidos = [rotulo_por_id[item_id] for item_id in ordem_atual]
            custom_style = """
            .sortable-component {
                border: 1px solid var(--tri-border);
                border-radius: 16px;
                padding: 0.35rem;
                margin-bottom: 0.75rem;
                background: var(--tri-bg-soft);
            }
            .sortable-container {
                background: transparent;
            }
            .sortable-item, .sortable-item:hover {
                background: var(--tri-surface);
                border: 1px solid var(--tri-border);
                border-radius: 12px;
                color: var(--tri-text-strong);
                font-weight: 600;
                padding: 0.7rem 0.85rem;
                margin-bottom: 0.45rem;
                box-shadow: var(--tri-shadow-soft);
            }
            """
            itens_ordenados = sort_items(
                itens_exibidos,
                direction="vertical",
                key=f"sort_{atleta_id}_{semana_numero}_{nome_treino}",
                custom_style=custom_style,
            )
            id_por_rotulo = {rotulo_por_id[item_id]: item_id for item_id in ordem_atual}
            ordem_salva[nome_treino] = [id_por_rotulo[rotulo] for rotulo in itens_ordenados if rotulo in id_por_rotulo]
        else:
            st.info("Reordenacao por arrastar sera habilitada quando a dependencia visual estiver instalada. Use os botoes abaixo por enquanto.")
            nova_ordem = list(ordem_atual)
            for posicao, item_id in enumerate(ordem_atual):
                col_rotulo, col_cima, col_baixo = st.columns([8, 1, 1])
                with col_rotulo:
                    st.markdown(
                        f"""
                        <div style="padding:0.7rem 0.85rem; border:1px solid var(--tri-border); border-radius:12px; background:var(--tri-surface); margin-bottom:0.45rem; color:var(--tri-text-strong);">
                            {rotulo_por_id[item_id]}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_cima:
                    if st.button("↑", key=f"subir_{atleta_id}_{semana_numero}_{nome_treino}_{posicao}", use_container_width=True):
                        if posicao > 0:
                            nova_ordem[posicao - 1], nova_ordem[posicao] = nova_ordem[posicao], nova_ordem[posicao - 1]
                            ordem_salva[nome_treino] = nova_ordem
                            st.rerun()
                with col_baixo:
                    if st.button("↓", key=f"descer_{atleta_id}_{semana_numero}_{nome_treino}_{posicao}", use_container_width=True):
                        if posicao < len(nova_ordem) - 1:
                            nova_ordem[posicao + 1], nova_ordem[posicao] = nova_ordem[posicao], nova_ordem[posicao + 1]
                            ordem_salva[nome_treino] = nova_ordem
                            st.rerun()

    return _exercicios_ordenados(treino, ordem_salva)


def _sincronizar_widgets_editor(atleta_id, semana_numero, nome_treino, exercicios, nome_por_label):
    for item in exercicios:
        dados = item["dados"]
        uid = item["uid"]
        chave_nome = _widget_key_editor("nome", atleta_id, semana_numero, nome_treino, uid)
        chave_series = _widget_key_editor("series", atleta_id, semana_numero, nome_treino, uid)
        chave_reps = _widget_key_editor("reps", atleta_id, semana_numero, nome_treino, uid)
        chave_descanso = _widget_key_editor("descanso", atleta_id, semana_numero, nome_treino, uid)

        if chave_nome in st.session_state:
            dados["nome"] = nome_por_label.get(st.session_state[chave_nome], "")
        if chave_series in st.session_state:
            dados["series"] = int(st.session_state[chave_series] or 0)
        if chave_reps in st.session_state:
            dados["reps"] = int(st.session_state[chave_reps] or 0)
        if chave_descanso in st.session_state:
            dados["descanso"] = str(st.session_state[chave_descanso] or "")


def _reordenar_exercicios_editor(atleta_id, semana_numero, nome_treino, exercicios):
    if not exercicios:
        return

    rotulo_por_uid = {
        item["uid"]: _rotulo_bloco_exercicio(item["dados"], indice)
        for indice, item in enumerate(exercicios)
    }
    ordem_atual = [item["uid"] for item in exercicios]
    st.caption("Arraste para reorganizar a ordem real dos exercicios deste treino.")

    if _sort_component_habilitado():
        custom_style = """
        .sortable-component {
            border: 1px dashed var(--tri-border-strong);
            border-radius: 16px;
            padding: 0.35rem;
            margin-bottom: 0.8rem;
            background: color-mix(in srgb, var(--tri-bg-soft) 88%, transparent);
        }
        .sortable-container {
            background: transparent;
        }
        .sortable-item, .sortable-item:hover {
            background: var(--tri-surface);
            border: 1px solid var(--tri-border);
            border-radius: 12px;
            color: var(--tri-text-strong);
            font-weight: 600;
            padding: 0.8rem 0.9rem;
            margin-bottom: 0.45rem;
            box-shadow: var(--tri-shadow-soft);
        }
        """
        itens_ordenados = sort_items(
            [rotulo_por_uid[uid] for uid in ordem_atual],
            direction="vertical",
            key=f"sort_editor_unificado_{atleta_id}_{semana_numero}_{nome_treino}",
            custom_style=custom_style,
        )
        uid_por_rotulo = {rotulo: uid for uid, rotulo in rotulo_por_uid.items()}
        mapa_exercicios = {item["uid"]: item for item in exercicios}
        exercicios[:] = [mapa_exercicios[uid_por_rotulo[rotulo]] for rotulo in itens_ordenados if rotulo in uid_por_rotulo]
        return

    st.info("Drag and drop nao esta disponivel. Use mover para cima ou para baixo neste ambiente.")
    for posicao, item in enumerate(list(exercicios)):
        col_rotulo, col_cima, col_baixo = st.columns([8, 1, 1])
        with col_rotulo:
            st.markdown(
                f"""
                <div style="padding:0.7rem 0.85rem; border:1px solid var(--tri-border); border-radius:12px; background:var(--tri-surface); margin-bottom:0.45rem; color:var(--tri-text-strong);">
                    {_rotulo_bloco_exercicio(item['dados'], posicao)}
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_cima:
            if st.button("Subir", key=f"subir_{atleta_id}_{semana_numero}_{nome_treino}_{item['uid']}", use_container_width=True):
                if posicao > 0:
                    exercicios[posicao - 1], exercicios[posicao] = exercicios[posicao], exercicios[posicao - 1]
                    st.rerun()
        with col_baixo:
            if st.button("Descer", key=f"descer_{atleta_id}_{semana_numero}_{nome_treino}_{item['uid']}", use_container_width=True):
                if posicao < len(exercicios) - 1:
                    exercicios[posicao + 1], exercicios[posicao] = exercicios[posicao], exercicios[posicao + 1]
                    st.rerun()


def _adicionar_exercicio_editor(exercicios, exercicio_padrao=None):
    dados_padrao = dict(exercicio_padrao or {})
    exercicios.append(
        {
            "uid": uuid.uuid4().hex,
            "dados": {
                **dados_padrao,
                "nome": dados_padrao.get("nome", ""),
                "series": int(dados_padrao.get("series") or 3),
                "reps": int(dados_padrao.get("reps") or 10),
                "descanso": str(dados_padrao.get("descanso") or ""),
            },
        }
    )


def _duplicar_exercicio_editor(exercicios, indice):
    exercicios.insert(
        indice + 1,
        {
            "uid": uuid.uuid4().hex,
            "dados": dict(exercicios[indice]["dados"]),
        },
    )


def _coletar_treino_editado(
    atleta_id,
    semana_numero,
    treinos_editor,
    nome_por_label,
    categoria_por_nome,
    musculo_por_nome,
):
    treino_editado = {}
    erros = []

    for nome_treino, exercicios in treinos_editor.items():
        _sincronizar_widgets_editor(atleta_id, semana_numero, nome_treino, exercicios, nome_por_label)
        treino_editado[nome_treino] = []

        for indice, item in enumerate(exercicios):
            dados = dict(item["dados"])
            nome_exercicio = (dados.get("nome") or "").strip()
            if not nome_exercicio:
                erros.append(f"{nome_treino}: selecione um exercicio no bloco {indice + 1}.")
                continue

            treino_editado[nome_treino].append(
                {
                    **dados,
                    "nome": nome_exercicio,
                    "categoria": categoria_por_nome.get(nome_exercicio, dados.get("categoria", "")),
                    "principal_musculo": musculo_por_nome.get(
                        nome_exercicio,
                        dados.get("principal_musculo", ""),
                    ),
                    "series": int(dados.get("series") or 0),
                    "reps": int(dados.get("reps") or 0),
                    "descanso": str(dados.get("descanso") or ""),
                }
            )

        if not treino_editado[nome_treino]:
            erros.append(f"{nome_treino}: adicione pelo menos um exercicio antes de salvar.")

    return treino_editado, erros


def _aplicar_estilo_editor_treino():
    st.markdown(
        """
        <style>
        .trainer-banner {
            padding: 1.15rem 1.25rem;
            border-radius: 24px;
            background: linear-gradient(135deg, var(--tri-header-start) 0%, var(--tri-primary) 62%, var(--tri-header-end) 100%);
            color: var(--tri-text-on-header);
            margin-bottom: 1rem;
            box-shadow: var(--tri-shadow-strong);
        }
        .trainer-banner h2 {
            margin: 0;
            color: var(--tri-text-on-header);
        }
        .trainer-banner p {
            margin: 0.35rem 0 0;
            color: color-mix(in srgb, var(--tri-text-on-header) 78%, transparent);
        }
        .trainer-editor-shell {
            border: 1px solid var(--tri-border);
            border-radius: 24px;
            padding: 1rem;
            background: color-mix(in srgb, var(--tri-surface) 94%, transparent);
            box-shadow: var(--tri-shadow-card);
            margin-bottom: 1rem;
        }
        .trainer-editor-card {
            border: 1px solid var(--tri-border);
            border-radius: 18px;
            padding: 0.9rem 0.95rem;
            background: var(--tri-surface);
            box-shadow: var(--tri-shadow-soft);
            margin-bottom: 0.75rem;
        }
        .trainer-editor-card h4 {
            margin: 0;
            color: var(--tri-text-strong);
            font-size: 1rem;
        }
        .trainer-editor-card p {
            margin: 0.2rem 0 0;
            color: var(--tri-text-soft);
            font-size: 0.88rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_linha_atleta(nome, email, foto_perfil=None):
    col_foto, col_info = st.columns([1, 8])
    with col_foto:
        foto_bytes = _foto_perfil_bytes(foto_perfil)
        if foto_bytes:
            st.image(foto_bytes, width=44)
        else:
            st.caption(" ")
    with col_info:
        st.write(f"{nome} ({email})")


def _render_painel_cargas_atleta(atleta):
    avaliacoes = listar_avaliacoes_forca(atleta["id"])
    historico = listar_historico_cargas(atleta["id"])

    st.subheader("Forca, carga e historico")
    if not avaliacoes:
        st.caption("Nenhuma avaliacao de carga registrada ainda.")
    else:
        linhas_avaliacao = []
        for avaliacao in avaliacoes:
            referencia = avaliacao.get("carga_sugerida_manual") or avaliacao.get("carga_referencia_estimada")
            linhas_avaliacao.append(
                {
                    "Semana": avaliacao["semana_numero"],
                    "Exercicio": avaliacao.get("exercicio_nome"),
                    "Categoria": rotulo_categoria_movimento(avaliacao.get("categoria_movimento")),
                    "Carga": avaliacao.get("carga_utilizada"),
                    "Reps": avaliacao.get("reps_realizadas"),
                    "RPE": avaliacao.get("rpe"),
                    "Referencia estimada": referencia,
                }
            )

        st.dataframe(linhas_avaliacao, use_container_width=True, hide_index=True)

        st.markdown("#### Ajuste manual da carga futura")
        st.caption("Use os cards abaixo para confirmar ou ajustar a referencia que sera usada nas proximas semanas.")
        for avaliacao in avaliacoes:
            referencia = avaliacao.get("carga_sugerida_manual") or avaliacao.get("carga_referencia_estimada")
            with st.container(border=True):
                st.markdown(
                    f"**Semana {avaliacao['semana_numero']} | {rotulo_categoria_movimento(avaliacao.get('categoria_movimento'))}**"
                )
                st.caption(
                    f"{avaliacao.get('exercicio_nome')} | carga usada {avaliacao.get('carga_utilizada') or '-'} kg | "
                    f"reps {avaliacao.get('reps_realizadas') or '-'} | RPE {avaliacao.get('rpe') or '-'} | "
                    f"referencia {referencia or '-'} kg"
                )
                with st.form(f"form_override_carga_{avaliacao['id']}"):
                    carga_manual = st.number_input(
                        "Carga sugerida manual (kg)",
                        min_value=0.0,
                        max_value=500.0,
                        step=0.5,
                        value=float(avaliacao.get("carga_sugerida_manual") or 0.0),
                        key=f"manual_carga_{avaliacao['id']}",
                    )
                    observacao = st.text_input(
                        "Observacao do treinador",
                        value=str(avaliacao.get("observacao_treinador") or ""),
                        key=f"obs_carga_{avaliacao['id']}",
                    )
                    salvar = st.form_submit_button("Salvar ajuste manual", use_container_width=True)
                if salvar:
                    salvar_ajuste_manual_avaliacao(
                        avaliacao["id"],
                        carga_sugerida_manual=carga_manual if carga_manual > 0 else None,
                        observacao_treinador=observacao or None,
                    )
                    resetar_treinos_futuros(atleta["id"], avaliacao["semana_numero"])
                    st.success("Ajuste manual salvo.")
                    st.rerun()

    if historico:
        linhas = [
            {
                "Semana": item["semana_numero"],
                "Treino": item["treino_nome"],
                "Exercicio": item["exercicio_nome"],
                "Categoria": rotulo_categoria_movimento(item.get("categoria_movimento")),
                "Carga sugerida": item.get("carga_planejada"),
                "Carga realizada": item.get("carga_realizada"),
                "RPE alvo": item.get("rpe_alvo"),
                "RPE real": item.get("rpe_real"),
                "Dor": item.get("dor") or "-",
            }
            for item in historico
        ]
        st.dataframe(linhas, use_container_width=True, hide_index=True)


def _render_menu_local_treinador():
    secao = st.session_state.get("secao_treinador", "visao_geral")
    st.caption("Use o menu abaixo para alternar entre gestão dos atletas e BI.")
    col_geral, col_atletas, col_bi = st.columns(3)
    with col_geral:
        if st.button(
            "Visao geral",
            key="btn_secao_treinador_geral",
            type="primary" if secao == "visao_geral" else "secondary",
            use_container_width=True,
        ):
            st.session_state["secao_treinador"] = "visao_geral"
            st.rerun()
    with col_atletas:
        if st.button(
            "Atletas",
            key="btn_secao_treinador_atletas",
            type="primary" if secao == "atletas" else "secondary",
            use_container_width=True,
        ):
            st.session_state["secao_treinador"] = "atletas"
            st.rerun()
    with col_bi:
        if st.button(
            "BI",
            key="btn_secao_treinador_bi",
            type="primary" if secao == "bi" else "secondary",
            use_container_width=True,
        ):
            st.session_state["secao_treinador"] = "bi"
            st.rerun()
def _render_convite(treinador):
    st.subheader("Convidar atleta")
    base_url = (
        st.session_state.get("convite_base_url")
        or os.getenv("APP_BASE_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("PUBLIC_APP_URL")
        or (
            f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME').strip('/')}"
            if os.getenv("RENDER_EXTERNAL_HOSTNAME")
            else DEFAULT_PUBLIC_APP_URL
        )
    ).strip().rstrip("/")

    st.caption(f"URL base do app: {base_url}")
    st.session_state["convite_base_url"] = base_url

    if st.button("Convidar atleta", key="btn_gerar_link_convite"):
        st.session_state["link_convite_gerado"] = gerar_link_convite(treinador["id"], base_url)

    link_gerado = st.session_state.get("link_convite_gerado")
    if link_gerado:
        st.caption("Envie este link para o atleta. Se ele criar conta por aqui, o vinculo sera automatico.")
        st.code(link_gerado)


def _render_vinculos(treinador):
    vinculos = listar_vinculos(treinador["id"])
    pendentes = [v for v in vinculos if v["status"] == "pendente"]
    ativos = [v for v in vinculos if v["status"] == "ativo"]

    col_pendentes, col_ativos = st.columns(2)
    with col_pendentes:
        st.subheader("Pendentes")
        if not pendentes:
            st.caption("Nenhum convite pendente.")
        for vinculo in pendentes:
            nome_exibicao = vinculo.get("atleta_apelido") or vinculo["atleta_nome"]
            _render_linha_atleta(
                nome_exibicao,
                vinculo["atleta_email"],
                vinculo.get("atleta_foto_perfil"),
            )

    with col_ativos:
        st.subheader("Ativos")
        if not ativos:
            st.caption("Nenhum atleta vinculado.")
        for vinculo in ativos:
            nome_exibicao = vinculo.get("atleta_apelido") or vinculo["atleta_nome"]
            _render_linha_atleta(
                nome_exibicao,
                vinculo["atleta_email"],
                vinculo.get("atleta_foto_perfil"),
            )


def _render_visualizacao_atleta(treinador):
    atletas_ativos = listar_atletas_do_treinador(treinador["id"])
    if not atletas_ativos:
        st.info("Nenhum atleta ativo para visualizar.")
        return

    st.subheader("Selecionar atleta")
    for item in atletas_ativos:
        nome_exibicao = item.get("atleta_apelido") or item["atleta_nome"]
        col_foto, col_info, col_acao = st.columns([1, 6, 2])
        with col_foto:
            foto_bytes = _foto_perfil_bytes(item.get("atleta_foto_perfil"))
            if foto_bytes:
                st.image(foto_bytes, width=40)
            else:
                st.caption(" ")
        with col_info:
            st.write(nome_exibicao)
            st.caption(item["atleta_email"])
        with col_acao:
            if st.button(
                "Abrir",
                key=f"abrir_atleta_{item['atleta_id']}",
                use_container_width=True,
            ):
                st.session_state["atleta_treinador_selecionado"] = item["atleta_id"]
                st.rerun()

    opcoes_ids = [item["atleta_id"] for item in atletas_ativos]
    atleta_padrao = st.session_state.get("atleta_treinador_selecionado")
    if atleta_padrao not in opcoes_ids:
        atleta_padrao = opcoes_ids[0]
        st.session_state["atleta_treinador_selecionado"] = atleta_padrao

    atleta_id = st.selectbox(
        "Ou selecione pela lista",
        options=opcoes_ids,
        index=opcoes_ids.index(atleta_padrao),
        format_func=lambda valor: next(
            (item.get("atleta_apelido") or item["atleta_nome"])
            for item in atletas_ativos
            if item["atleta_id"] == valor
        ),
    )
    st.session_state["atleta_treinador_selecionado"] = atleta_id
    atleta = buscar_atleta_vinculado(treinador["id"], atleta_id)
    if not atleta:
        st.error("Atleta nao encontrado ou sem permissao de acesso.")
        return

    cronograma, _, _ = gerar_cronograma(atleta)
    semana_atual = obter_semana_atual(cronograma)
    semana_escolhida_numero = st.selectbox(
        "Semana para visualizar/editar",
        options=[item["semana"] for item in cronograma],
        index=max(semana_atual["semana"] - 1, 0),
        format_func=lambda numero: f"Semana {numero}",
        key=f"semana_atleta_{atleta_id}",
    )
    semana_escolhida = buscar_semana_por_numero(cronograma, semana_escolhida_numero)

    exercicios_db = carregar_exercicios()
    treino = obter_ou_gerar_treino_semana(atleta, exercicios_db, semana_escolhida["semana"], semana_escolhida["fase"])
    treino_salvo = buscar_treino_gerado(atleta["id"], semana_escolhida["semana"])
    progresso = buscar_progresso_semana(atleta["id"], semana_escolhida["semana"])
    concluidos, percentual = calcular_progresso_semanal(atleta["id"], semana_escolhida["semana"], len(treino))

    col_foto, col_titulo = st.columns([1, 8])
    with col_foto:
        foto_bytes = _foto_perfil_bytes(atleta.get("foto_perfil"))
        if foto_bytes:
            st.image(foto_bytes, width=52)
    with col_titulo:
        nome_exibicao = atleta.get("apelido") or atleta["nome"]
        st.subheader(f"{nome_exibicao} | Semana {semana_escolhida['semana']} | Fase {semana_escolhida['fase']}")
    st.write(f"Progresso do atleta: {percentual}% ({concluidos}/{len(treino)})")
    if treino_salvo and int(treino_salvo.get("editado_por_treinador", 0)) == 1:
        st.caption("Treino desta semana foi editado por treinador.")

    for nome_treino, exercicios in treino.items():
        status = "feito" if progresso.get(nome_treino, {}).get("feito") else "nao feito"
        st.markdown(f"**Treino {nome_treino}** ({status})")
        for exercicio in exercicios:
            st.markdown(
                f"- {exercicio['nome']} ({exercicio['series']} x {exercicio['reps']}) | "
                f"descanso {exercicio['descanso']} | {exercicio.get('orientacao_carga') or 'sem orientacao de carga'}"
            )

    _render_painel_cargas_atleta(atleta)

    if semana_escolhida["semana"] < semana_atual["semana"]:
        st.info("Edicao disponivel apenas para a semana atual ou futuras.")
        return

    st.subheader("Editar treino da semana")
    _aplicar_estilo_editor_treino()
    opcoes_exercicios = sorted(
        [
            {
                "nome": item["nome"],
                "categoria": item.get("categoria", ""),
                "label": f"{item['nome']} ({item.get('categoria', '').replace('_', ' ')})",
            }
            for item in exercicios_db
        ],
        key=lambda item: item["label"],
    )
    labels_exercicios = [item["label"] for item in opcoes_exercicios]
    label_por_nome = {item["nome"]: item["label"] for item in opcoes_exercicios}
    categoria_por_nome = {item["nome"]: item["categoria"] for item in opcoes_exercicios}
    musculo_por_nome = {
        item["nome"]: next(
            (ex["principal_musculo"] for ex in exercicios_db if ex["nome"] == item["nome"]),
            "",
        )
        for item in opcoes_exercicios
    }
    label_vazio = "Selecione um exercicio"
    opcoes_dropdown = [label_vazio] + labels_exercicios
    nome_por_label = {item["label"]: item["nome"] for item in opcoes_exercicios}
    treinos_editor = _garantir_editor_treino(atleta["id"], semana_escolhida["semana"], treino)

    for nome_treino, exercicios in treinos_editor.items():
        _sincronizar_widgets_editor(
            atleta["id"],
            semana_escolhida["semana"],
            nome_treino,
            exercicios,
            nome_por_label,
        )

        with st.container(border=True):
            st.markdown(f"#### Treino {nome_treino}")
            st.caption("Reordene e edite os blocos no mesmo fluxo. Duplicar, excluir e adicionar so afetam este treino.")
        _reordenar_exercicios_editor(atleta["id"], semana_escolhida["semana"], nome_treino, exercicios)

        for indice, item_editor in enumerate(list(exercicios)):
            dados = item_editor["dados"]
            uid = item_editor["uid"]
            label_atual = label_por_nome.get(
                dados.get("nome"),
                label_vazio if not dados.get("nome") else f"{dados.get('nome')} ({dados.get('categoria', '').replace('_', ' ')})",
            )
            opcoes_item = opcoes_dropdown if label_atual in opcoes_dropdown else opcoes_dropdown + [label_atual]

            chave_nome = _widget_key_editor("nome", atleta["id"], semana_escolhida["semana"], nome_treino, uid)
            chave_series = _widget_key_editor("series", atleta["id"], semana_escolhida["semana"], nome_treino, uid)
            chave_reps = _widget_key_editor("reps", atleta["id"], semana_escolhida["semana"], nome_treino, uid)
            chave_descanso = _widget_key_editor("descanso", atleta["id"], semana_escolhida["semana"], nome_treino, uid)

            with st.container(border=True):
                col_titulo, col_dup, col_exc = st.columns([6, 1.5, 1.5])
                with col_titulo:
                    st.markdown(f"#### Exercicio {indice + 1}")
                    st.caption(dados.get("nome") or "Selecione um exercicio para este bloco.")
                with col_dup:
                    if st.button("Duplicar", key=f"duplicar_{nome_treino}_{uid}", use_container_width=True):
                        _sincronizar_widgets_editor(
                            atleta["id"],
                            semana_escolhida["semana"],
                            nome_treino,
                            exercicios,
                            nome_por_label,
                        )
                        _duplicar_exercicio_editor(exercicios, indice)
                        st.rerun()
                with col_exc:
                    if st.button("Excluir", key=f"excluir_{nome_treino}_{uid}", use_container_width=True):
                        _sincronizar_widgets_editor(
                            atleta["id"],
                            semana_escolhida["semana"],
                            nome_treino,
                            exercicios,
                            nome_por_label,
                        )
                        exercicios.pop(indice)
                        st.rerun()

                st.selectbox(
                    f"Exercicio {indice + 1}",
                    options=opcoes_item,
                    index=opcoes_item.index(label_atual),
                    key=chave_nome,
                    label_visibility="collapsed",
                )

                col_series, col_reps, col_descanso = st.columns([1, 1, 1.4])
                with col_series:
                    st.number_input(
                        "Series",
                        min_value=1,
                        max_value=12,
                        value=int(dados.get("series") or 3),
                        key=chave_series,
                    )
                with col_reps:
                    st.number_input(
                        "Reps",
                        min_value=1,
                        max_value=50,
                        value=int(dados.get("reps") or 10),
                        key=chave_reps,
                    )
                with col_descanso:
                    st.text_input(
                        "Descanso",
                        value=str(dados.get("descanso") or ""),
                        key=chave_descanso,
                        placeholder="ex: 60s",
                    )

        if st.button(
            "Adicionar exercicio",
            key=f"adicionar_exercicio_{atleta['id']}_{semana_escolhida['semana']}_{nome_treino}",
            use_container_width=True,
        ):
            _sincronizar_widgets_editor(
                atleta["id"],
                semana_escolhida["semana"],
                nome_treino,
                exercicios,
                nome_por_label,
            )
            _adicionar_exercicio_editor(exercicios)
            st.rerun()

    if st.button("Salvar edicao", key=f"salvar_treino_unificado_{atleta_id}_{semana_escolhida['semana']}", use_container_width=True):
        treino_editado, erros = _coletar_treino_editado(
            atleta["id"],
            semana_escolhida["semana"],
            treinos_editor,
            nome_por_label,
            categoria_por_nome,
            musculo_por_nome,
        )
        if erros:
            for erro in erros:
                st.error(erro)
            return
        salvar_treino_gerado(
            atleta["id"],
            semana_escolhida["semana"],
            semana_escolhida["fase"],
            treino_editado,
            editado_por_treinador=1,
        )
        st.success("Treino atualizado pelo treinador.")
        st.rerun()


def _filtros_bi_padrao():
    hoje = date.today()
    inicio = (hoje.replace(day=1) - timedelta(days=365)).replace(day=1)
    return {
        "data_inicio": inicio,
        "data_fim": hoje,
        "sexo": None,
        "objetivo": None,
        "granularidade_retencao": "mensal",
        "top_percentual_receita": 0.2,
        "incluir_vinculos_encerrados": True,
    }


def _render_filtros_bi():
    if "treinador_bi_filtros" not in st.session_state:
        st.session_state["treinador_bi_filtros"] = _filtros_bi_padrao()

    filtros = st.session_state["treinador_bi_filtros"]
    with st.form("form_filtros_bi_treinador"):
        col_data_inicio, col_data_fim, col_gran = st.columns(3)
        with col_data_inicio:
            data_inicio = st.date_input("Data inicial", value=filtros["data_inicio"])
        with col_data_fim:
            data_fim = st.date_input("Data final", value=filtros["data_fim"])
        with col_gran:
            granularidade = st.selectbox(
                "Retencao",
                options=["mensal", "trimestral"],
                index=["mensal", "trimestral"].index(filtros["granularidade_retencao"]),
            )

        col_sexo, col_objetivo, col_top = st.columns(3)
        sexo_labels = list(SEXO_FILTROS.keys())
        sexo_inicial = next((label for label, valor in SEXO_FILTROS.items() if valor == filtros["sexo"]), "Todos")
        objetivo_labels = list(OBJETIVO_FILTROS.keys())
        objetivo_inicial = next(
            (label for label, valor in OBJETIVO_FILTROS.items() if valor == filtros["objetivo"]),
            "Todos",
        )

        with col_sexo:
            sexo_label = st.selectbox("Sexo", options=sexo_labels, index=sexo_labels.index(sexo_inicial))
        with col_objetivo:
            objetivo_label = st.selectbox(
                "Objetivo",
                options=objetivo_labels,
                index=objetivo_labels.index(objetivo_inicial),
            )
        with col_top:
            top_percentual = st.slider(
                "Top receita",
                min_value=10,
                max_value=50,
                value=int(round(float(filtros["top_percentual_receita"]) * 100)),
                step=5,
                format="%d%%",
            )

        incluir_encerrados = st.checkbox(
            "Incluir vinculos encerrados",
            value=bool(filtros["incluir_vinculos_encerrados"]),
        )
        aplicar = st.form_submit_button("Atualizar BI")

    if aplicar:
        st.session_state["treinador_bi_filtros"] = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "sexo": SEXO_FILTROS[sexo_label],
            "objetivo": OBJETIVO_FILTROS[objetivo_label],
            "granularidade_retencao": granularidade,
            "top_percentual_receita": top_percentual / 100,
            "incluir_vinculos_encerrados": incluir_encerrados,
        }
        st.rerun()

    filtros = st.session_state["treinador_bi_filtros"]
    return {
        "data_inicio": filtros["data_inicio"].isoformat(),
        "data_fim": filtros["data_fim"].isoformat(),
        "sexo": filtros["sexo"],
        "objetivo": filtros["objetivo"],
        "granularidade_retencao": filtros["granularidade_retencao"],
        "top_percentual_receita": filtros["top_percentual_receita"],
        "incluir_vinculos_encerrados": filtros["incluir_vinculos_encerrados"],
    }


def _render_bi_treinador(treinador):
    st.subheader("Business Intelligence")
    st.caption("Acompanhe retencao, receita e engajamento por aluno com recortes de semana, mes e ano.")

    filtros = _render_filtros_bi()
    service = TrainerBIService()

    try:
        dashboard = service.get_dashboard_data(treinador["id"], filtros=filtros)
        engajamento = service.get_student_engagement_report(treinador["id"], filtros=filtros)
    except BIValidationError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Nao foi possivel carregar o BI: {exc}")
        return

    resumo = engajamento["resumo"]
    retencao = dashboard["retencao"]
    financeiro = dashboard["financeiro"]
    kpis = dashboard["kpis"]

    col_1, col_2, col_3, col_4 = st.columns(4)
    with col_1:
        st.metric("Alunos ativos na semana", resumo["alunos_ativos_semana"])
    with col_2:
        st.metric("Media treinos no mes", resumo["media_treinos_mes"])
    with col_3:
        st.metric("Meses ativos medio", resumo["media_meses_ativos_periodo"])
    with col_4:
        st.metric("Retencao media", _formatar_percentual(retencao["taxa_media_retencao_percentual"]))

    col_5, col_6, col_7, col_8 = st.columns(4)
    with col_5:
        st.metric("Receita no periodo", f"R$ {financeiro['receita_total_periodo']:.2f}")
    with col_6:
        st.metric("RMA", f"R$ {float(kpis['receita_media_por_aluno_rma']):.2f}")
    with col_7:
        st.metric("Conclusao do programa", _formatar_percentual(kpis["taxa_conclusao_programa_percentual"]))
    with col_8:
        ltv = kpis["valor_medio_ciclo_vida_ltv_estimado"]
        st.metric("LTV estimado", f"R$ {ltv:.2f}" if ltv is not None else "-")

    st.markdown("### Engajamento por aluno")
    linhas_engajamento = []
    for item in engajamento["alunos"]:
        linhas_engajamento.append(
            {
                "Aluno": item["nome"],
                "Email": item["email"] or "-",
                "Status": item["status_vinculo"] or "-",
                "Treinos semana": item["treinos_semana"],
                "Treinos mes": item["treinos_mes"],
                "Treinos ano": item["treinos_ano"],
                "Meses ativos": item["meses_ativos_periodo"],
                "Ultima atividade": _formatar_data_hora(item["ultima_atividade"]),
                "Dias sem atividade": item["dias_desde_ultima_atividade"] if item["dias_desde_ultima_atividade"] is not None else "-",
            }
        )

    if linhas_engajamento:
        st.dataframe(linhas_engajamento, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum dado de treino encontrado para os filtros escolhidos.")

    csv_engajamento = TrainerBIService.export_rows_to_csv(engajamento["alunos"])
    json_dashboard = service.export_dashboard_json(treinador["id"], filtros=filtros)
    col_export_csv, col_export_json = st.columns(2)
    with col_export_csv:
        st.download_button(
            "Baixar CSV de engajamento",
            data=csv_engajamento,
            file_name="bi_engajamento_alunos.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not bool(csv_engajamento),
        )
    with col_export_json:
        st.download_button(
            "Baixar JSON completo",
            data=json_dashboard,
            file_name="bi_treinador_dashboard.json",
            mime="application/json",
            use_container_width=True,
        )

    st.markdown("### Tendencia de retencao")
    if retencao["tendencia"]:
        st.dataframe(retencao["tendencia"], use_container_width=True, hide_index=True)
    else:
        st.caption("Sem base suficiente para tendencia de retencao.")

    col_freq, col_receita = st.columns(2)
    with col_freq:
        st.markdown("### Frequencia por objetivo")
        if kpis["taxa_frequencia_por_objetivo"]:
            st.dataframe(kpis["taxa_frequencia_por_objetivo"], use_container_width=True, hide_index=True)
        else:
            st.caption("Sem dados de frequencia no periodo.")
    with col_receita:
        st.markdown("### Receita mensal")
        if financeiro["historico_mensal"]:
            st.dataframe(financeiro["historico_mensal"], use_container_width=True, hide_index=True)
        else:
            st.caption("Sem eventos financeiros no periodo.")

    col_anual, col_picos = st.columns(2)
    with col_anual:
        st.markdown("### Receita anual")
        if financeiro["resumo_anual"]:
            st.dataframe(financeiro["resumo_anual"], use_container_width=True, hide_index=True)
        else:
            st.caption("Sem base anual para exibir.")
    with col_picos:
        picos = kpis["picos_demanda"]
        st.markdown("### Picos de demanda")
        st.write(f"Mes pico: {picos['mes_pico'] or '-'}")
        st.write(f"Trimestre pico: {picos['trimestre_pico'] or '-'}")
        st.write(f"Dia da semana pico: {picos['dia_semana_pico'] or '-'}")


def tela_area_treinador(treinador):
    if "secao_treinador" not in st.session_state:
        st.session_state["secao_treinador"] = "visao_geral"

    st.title("Area do treinador")
    _aplicar_estilo_editor_treino()
    st.markdown(
        """
        <div class="trainer-banner">
            <h2>Painel do treinador</h2>
            <p>Gerencie atletas, acompanhe desempenho e ajuste os treinos com uma interface mais limpa e profissional.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_menu_local_treinador()

    secao = st.session_state.get("secao_treinador", "visao_geral")
    if secao == "atletas":
        _render_visualizacao_atleta(treinador)
        return
    if secao == "bi":
        _render_bi_treinador(treinador)
        return

    _render_convite(treinador)
    _render_vinculos(treinador)
