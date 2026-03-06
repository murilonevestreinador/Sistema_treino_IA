import base64
import os

import streamlit as st

from core.cronograma import buscar_semana_por_numero, gerar_cronograma, obter_semana_atual
from core.exercicios import carregar_exercicios
from core.progresso import buscar_progresso_semana, calcular_progresso_semanal
from core.treinador import gerar_link_convite, listar_atletas_do_treinador, listar_vinculos
from core.treino import buscar_treino_gerado, obter_ou_gerar_treino_semana, salvar_treino_gerado
from core.usuarios import buscar_usuario_por_id

DEFAULT_PUBLIC_APP_URL = "https://trilab-treinamento.onrender.com"


def _foto_perfil_bytes(foto_perfil):
    if not foto_perfil:
        return None
    try:
        return base64.b64decode(foto_perfil)
    except Exception:
        return None


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
        st.caption("Envie este link para o atleta. Se ele criar conta por aqui, o v\u00ednculo ser\u00e1 autom\u00e1tico.")
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
            st.write(f"{nome_exibicao}")
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
        options=[item["atleta_id"] for item in atletas_ativos],
        index=opcoes_ids.index(atleta_padrao),
        format_func=lambda valor: next(
            (item.get("atleta_apelido") or item["atleta_nome"])
            for item in atletas_ativos
            if item["atleta_id"] == valor
        ),
    )
    st.session_state["atleta_treinador_selecionado"] = atleta_id
    atleta = buscar_usuario_por_id(atleta_id)
    if not atleta:
        st.error("Atleta n\u00e3o encontrado.")
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
        status = "feito" if progresso.get(nome_treino, {}).get("feito") else "n\u00e3o feito"
        st.markdown(f"**Treino {nome_treino}** ({status})")
        for exercicio in exercicios:
            st.markdown(
                f"- {exercicio['nome']} ({exercicio['series']} x {exercicio['reps']}) | descanso {exercicio['descanso']}"
            )

    if semana_escolhida["semana"] < semana_atual["semana"]:
        st.info("Edi\u00e7\u00e3o dispon\u00edvel apenas para a semana atual ou futuras.")
        return

    st.subheader("Editar treino da semana")
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
    musculo_por_nome = {item["nome"]: next(
        (ex["principal_musculo"] for ex in exercicios_db if ex["nome"] == item["nome"]),
        "",
    ) for item in opcoes_exercicios}

    with st.form(f"editar_treino_{atleta_id}_{semana_escolhida['semana']}"):
        treino_editado = {}

        for nome_treino, exercicios in treino.items():
            st.markdown(f"**Treino {nome_treino}**")
            treino_editado[nome_treino] = []

            for indice, exercicio in enumerate(exercicios):
                label_atual = label_por_nome.get(
                    exercicio["nome"],
                    f"{exercicio['nome']} ({exercicio.get('categoria', '').replace('_', ' ')})",
                )
                opcoes = labels_exercicios if labels_exercicios else [label_atual]
                indice_padrao = opcoes.index(label_atual) if label_atual in opcoes else 0

                label_escolhido = st.selectbox(
                    f"{nome_treino} | Exercicio {indice + 1}",
                    options=opcoes,
                    index=indice_padrao,
                    key=f"edit_nome_{atleta_id}_{semana_escolhida['semana']}_{nome_treino}_{indice}",
                )
                nome_escolhido = next(
                    (item["nome"] for item in opcoes_exercicios if item["label"] == label_escolhido),
                    exercicio["nome"],
                )
                col_series, col_reps = st.columns(2)
                with col_series:
                    series = st.number_input(
                        "S\u00e9ries",
                        min_value=1,
                        max_value=8,
                        value=int(exercicio["series"]),
                        key=f"edit_series_{atleta_id}_{semana_escolhida['semana']}_{nome_treino}_{indice}",
                    )
                with col_reps:
                    reps = st.number_input(
                        "Reps",
                        min_value=1,
                        max_value=30,
                        value=int(exercicio["reps"]),
                        key=f"edit_reps_{atleta_id}_{semana_escolhida['semana']}_{nome_treino}_{indice}",
                    )

                treino_editado[nome_treino].append(
                    {
                        **exercicio,
                        "nome": nome_escolhido,
                        "categoria": categoria_por_nome.get(nome_escolhido, exercicio.get("categoria", "")),
                        "principal_musculo": musculo_por_nome.get(
                            nome_escolhido,
                            exercicio.get("principal_musculo", ""),
                        ),
                        "series": int(series),
                        "reps": int(reps),
                    }
                )

        salvar = st.form_submit_button("Salvar edi\u00e7\u00e3o")

    if salvar:
        salvar_treino_gerado(
            atleta["id"],
            semana_escolhida["semana"],
            semana_escolhida["fase"],
            treino_editado,
            editado_por_treinador=1,
        )
        st.success("Treino atualizado pelo treinador.")
        st.rerun()


def tela_area_treinador(treinador):
    st.title("\u00c1rea do treinador")
    _render_convite(treinador)
    _render_vinculos(treinador)
    _render_visualizacao_atleta(treinador)
