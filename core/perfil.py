import base64

import streamlit as st

from core.treinador import (
    listar_treinadores_do_atleta,
    remover_vinculo_treinador_atleta,
    vincular_atleta_ao_treinador_por_email,
)
from core.usuarios import atualizar_perfil_usuario, excluir_usuario


def _foto_perfil_bytes(usuario):
    foto_perfil = usuario.get("foto_perfil")
    if not foto_perfil:
        return None

    try:
        return base64.b64decode(foto_perfil)
    except Exception:
        return None


def _render_foto_atual(usuario):
    foto_bytes = _foto_perfil_bytes(usuario)
    if foto_bytes:
        st.image(foto_bytes, width=160)
        return

    st.caption("Nenhuma foto de perfil cadastrada.")


def _render_form_perfil(usuario):
    st.subheader("Dados pessoais")
    col_form, col_preview = st.columns([2, 1])

    with col_preview:
        _render_foto_atual(usuario)

    with col_form:
        with st.form(f"form_perfil_{usuario['id']}"):
            nome = st.text_input("Nome", value=usuario.get("nome", ""))
            apelido = st.text_input("Apelido", value=usuario.get("apelido") or "")
            foto_upload = st.file_uploader(
                "Foto de perfil",
                type=["png", "jpg", "jpeg", "webp"],
                help="Selecione uma imagem do dispositivo para trocar a foto atual.",
                key=f"upload_foto_perfil_{usuario['id']}",
            )
            remover_foto = st.checkbox(
                "Remover foto atual",
                value=False,
                disabled=not usuario.get("foto_perfil"),
                key=f"remover_foto_perfil_{usuario['id']}",
            )
            salvar = st.form_submit_button("Salvar perfil", use_container_width=True)

        if not salvar:
            return

        foto_perfil = usuario.get("foto_perfil")
        if remover_foto:
            foto_perfil = None
        elif foto_upload is not None:
            foto_perfil = base64.b64encode(foto_upload.getvalue()).decode("ascii")

        usuario_atualizado = atualizar_perfil_usuario(
            usuario["id"],
            {
                "nome": nome,
                "apelido": apelido,
                "foto_perfil": foto_perfil,
            },
        )
        st.session_state["usuario"] = usuario_atualizado
        st.session_state["mensagem_perfil"] = "Perfil atualizado com sucesso."
        st.rerun()


def _render_vinculo_atleta(usuario):
    if usuario.get("tipo_usuario") != "atleta":
        return

    st.subheader("Treinador")
    vinculos = listar_treinadores_do_atleta(usuario["id"])
    ativos = [item for item in vinculos if item["status"] == "ativo"]

    if ativos:
        for vinculo in ativos:
            nome_treinador = vinculo.get("treinador_apelido") or vinculo["treinador_nome"]
            col_info, col_acao = st.columns([4, 1])
            with col_info:
                st.write(f"{nome_treinador} ({vinculo['treinador_email']})")
            with col_acao:
                if st.button(
                    "Remover",
                    key=f"remover_vinculo_{usuario['id']}_{vinculo['treinador_id']}",
                    use_container_width=True,
                ):
                    remover_vinculo_treinador_atleta(vinculo["treinador_id"], usuario["id"])
                    usuario_atualizado = dict(st.session_state.get("usuario", usuario))
                    st.session_state["usuario"] = usuario_atualizado
                    st.session_state["mensagem_perfil"] = "Vinculo com treinador removido."
                    st.rerun()
    else:
        st.caption("Nenhum treinador ativo vinculado.")

    with st.form(f"form_vinculo_treinador_{usuario['id']}"):
        email_treinador = st.text_input("E-mail do treinador", value="")
        salvar_vinculo = st.form_submit_button("Adicionar treinador", use_container_width=True)

    if not salvar_vinculo:
        return

    ok, mensagem = vincular_atleta_ao_treinador_por_email(usuario["id"], email_treinador)
    if ok:
        st.session_state["mensagem_perfil"] = mensagem
        st.rerun()
    st.error(mensagem)


def _render_exclusao_conta(usuario):
    st.subheader("Excluir conta")
    st.caption("Essa acao remove seu usuario e os dados relacionados.")
    with st.form(f"form_excluir_conta_{usuario['id']}"):
        confirmar = st.checkbox("Confirmo que desejo excluir minha conta permanentemente.")
        excluir = st.form_submit_button("Excluir conta", use_container_width=True)

    if not excluir:
        return False
    if not confirmar:
        st.error("Confirme a exclusao para continuar.")
        return False

    excluir_usuario(usuario["id"])
    return True


def tela_meu_perfil(usuario):
    st.title("Meu perfil")

    mensagem = st.session_state.pop("mensagem_perfil", None)
    if mensagem:
        st.success(mensagem)

    _render_form_perfil(usuario)
    _render_vinculo_atleta(usuario)
    return _render_exclusao_conta(usuario)
