import base64
import logging
import uuid
from pathlib import Path

import streamlit as st

from core.cronograma import gerar_cronograma, obter_semana_atual
from core.email_service import email_envio_habilitado
from core.email_tokens import atualizar_email_pendente_verificacao, solicitar_verificacao_email
from core.equipamentos import (
    AMBIENTES_TREINO_FORCA,
    EQUIPAMENTO_OPCOES,
    ambiente_requer_inventario,
    normalizar_ambiente_treino_forca,
    rotulo_ambiente_treino,
    rotulo_equipamento,
)
from core.permissoes import email_verificado
from core.treinador import (
    buscar_tema_treinador,
    listar_treinadores_do_atleta,
    remover_vinculo_treinador_atleta,
    resolver_logo_treinador,
    salvar_tema_treinador,
    vincular_atleta_ao_treinador_por_email,
)
from core.treino import invalidar_treinos_gerados_desde_semana
from core.usuarios import (
    ExclusaoContaBloqueadaError,
    ExclusaoContaError,
    alterar_senha_usuario_autenticado,
    atualizar_perfil_usuario,
    buscar_usuario_por_id,
    diagnosticar_dados_checkout,
    excluir_usuario,
    formatar_cpf,
    formatar_telefone,
    validar_cpf,
    validar_cref,
    validar_telefone,
)


LOGGER = logging.getLogger("trilab.profile")


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
    diagnostico_checkout = diagnosticar_dados_checkout(usuario)
    if not diagnostico_checkout["ok"]:
        st.warning("Complete CPF e telefone para liberar o checkout e o pagamento.")
    col_form, col_preview = st.columns([2, 1])

    with col_preview:
        _render_foto_atual(usuario)

    with col_form:
        with st.form(f"form_perfil_{usuario['id']}"):
            nome = st.text_input("Nome", value=usuario.get("nome", ""))
            apelido = st.text_input("Apelido", value=usuario.get("apelido") or "")
            cpf = st.text_input("CPF", value=formatar_cpf(usuario.get("cpf")), placeholder="123.456.789-09")
            telefone = st.text_input("Telefone", value=formatar_telefone(usuario.get("telefone")), placeholder="(16) 99999-9999")
            cref = None
            if usuario.get("tipo_usuario") == "treinador":
                cref = st.text_input("CREF", value=usuario.get("cref") or "", placeholder="Ex.: 123456-G/SP")
            ambiente_treino_forca = None
            equipamentos_disponiveis = None
            if usuario.get("tipo_usuario") == "atleta":
                st.markdown("### Contexto de treino de forca")
                ambiente_atual = normalizar_ambiente_treino_forca(
                    usuario.get("ambiente_treino_forca"),
                    usuario.get("local_treino"),
                )
                ambiente_treino_forca = st.selectbox(
                    "Ambiente de treino de forca",
                    AMBIENTES_TREINO_FORCA,
                    index=AMBIENTES_TREINO_FORCA.index(ambiente_atual),
                    format_func=rotulo_ambiente_treino,
                )
                if ambiente_requer_inventario(ambiente_treino_forca):
                    equipamentos_disponiveis = st.multiselect(
                        "Equipamentos disponiveis",
                        EQUIPAMENTO_OPCOES,
                        default=usuario.get("equipamentos_disponiveis") or [],
                        format_func=rotulo_equipamento,
                        help="A barra `/` na planilha e tratada como `e`: o exercicio so entra se todos os equipamentos exigidos estiverem disponiveis.",
                    )
                elif usuario.get("equipamentos_disponiveis"):
                    st.caption("Seu inventario anterior foi preservado, mas sera ignorado enquanto o ambiente estiver como academia completa.")
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

        if cpf.strip():
            cpf_ok, cpf_msg = validar_cpf(cpf)
            if not cpf_ok:
                st.error(cpf_msg)
                return
        else:
            cpf_msg = None

        if telefone.strip():
            telefone_ok, telefone_msg = validar_telefone(telefone)
            if not telefone_ok:
                st.error(telefone_msg)
                return
        else:
            telefone_msg = None

        cref_msg = None
        if usuario.get("tipo_usuario") == "treinador":
            cref_ok, cref_msg = validar_cref(cref, obrigatorio=False)
            if not cref_ok:
                st.error(cref_msg)
                return

        try:
            ambiente_anterior = normalizar_ambiente_treino_forca(
                usuario.get("ambiente_treino_forca"),
                usuario.get("local_treino"),
            )
            usuario_atualizado = atualizar_perfil_usuario(
                usuario["id"],
                {
                    "nome": nome,
                    "apelido": apelido,
                    "foto_perfil": foto_perfil,
                    "cpf": cpf_msg,
                    "telefone": telefone_msg,
                    "cref": cref_msg,
                    "ambiente_treino_forca": ambiente_treino_forca,
                    **(
                        {"equipamentos_disponiveis": equipamentos_disponiveis}
                        if usuario.get("tipo_usuario") == "atleta" and equipamentos_disponiveis is not None
                        else {}
                    ),
                },
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        if usuario.get("tipo_usuario") == "atleta":
            ambiente_novo = normalizar_ambiente_treino_forca(
                usuario_atualizado.get("ambiente_treino_forca"),
                usuario_atualizado.get("local_treino"),
            )
            inventario_anterior = usuario.get("equipamentos_disponiveis") or []
            inventario_novo = usuario_atualizado.get("equipamentos_disponiveis") or []
            if ambiente_anterior != ambiente_novo or inventario_anterior != inventario_novo:
                cronograma, _, _ = gerar_cronograma(usuario_atualizado)
                semana_atual = obter_semana_atual(cronograma)
                invalidar_treinos_gerados_desde_semana(usuario["id"], semana_atual["semana"])
                st.session_state["cronograma"] = cronograma
        st.session_state["usuario"] = usuario_atualizado
        st.session_state["mensagem_perfil"] = "Perfil atualizado com sucesso."
        st.rerun()


def _render_status_email(usuario):
    st.subheader("E-mail da conta")

    notice = st.session_state.pop("perfil_email_notice", None)
    if notice and notice.get("mensagem"):
        status = notice.get("status")
        mensagem = notice.get("mensagem")
        if status in {"envio_falhou", "rate_limited", "erro"}:
            st.warning(mensagem)
        elif status in {"confirmado", "ja_verificado"}:
            st.success(mensagem)
        else:
            st.info(mensagem)

    st.write(f"E-mail cadastrado: {usuario.get('email') or '-'}")
    if email_verificado(usuario):
        st.success("Seu e-mail ja esta confirmado.")
        if usuario.get("email_verificado_em"):
            st.caption(f"Confirmado em: {usuario.get('email_verificado_em')}")
        return

    st.info("Seu e-mail ainda nao foi confirmado. Esta conta continua com acesso normal neste momento.")
    if not email_envio_habilitado():
        st.warning("O envio de e-mail esta indisponivel no momento. Voce ainda pode usar a plataforma normalmente.")
        return

    col_reenviar, col_status = st.columns([1.4, 1])
    with col_reenviar:
        if st.button("Reenviar e-mail de verificacao", use_container_width=True, key=f"perfil_reenviar_email_{usuario['id']}"):
            try:
                resultado = solicitar_verificacao_email(usuario["id"], origem="perfil_reenvio")
            except Exception:
                LOGGER.exception("[EMAIL_VERIFY] Falha ao reenviar verificacao no perfil usuario_id=%s", usuario["id"])
                resultado = {
                    "status": "erro",
                    "mensagem": "Nao foi possivel reenviar o e-mail agora. Tente novamente em alguns instantes.",
                }
            usuario_refresh = resultado.get("usuario") or st.session_state.get("usuario") or usuario
            st.session_state["usuario"] = usuario_refresh
            st.session_state["perfil_email_notice"] = {
                "status": resultado.get("status"),
                "mensagem": resultado.get("mensagem"),
            }
            st.session_state["email_pending_notice"] = {
                "status": resultado.get("status"),
                "mensagem": resultado.get("mensagem"),
            }
            st.rerun()
    with col_status:
        if usuario.get("ultimo_envio_verificacao_em"):
            st.caption(f"Ultimo envio: {usuario.get('ultimo_envio_verificacao_em')}")

    with st.form(f"form_email_verificacao_{usuario['id']}"):
        novo_email = st.text_input(
            "Corrigir e-mail e reenviar",
            value=usuario.get("email") or "",
            placeholder="voce@exemplo.com",
        )
        salvar_email = st.form_submit_button("Salvar e reenviar link", use_container_width=True)

    if not salvar_email:
        return

    try:
        resultado = atualizar_email_pendente_verificacao(usuario["id"], novo_email)
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        LOGGER.exception("[EMAIL_VERIFY] Falha ao atualizar e-mail pendente no perfil usuario_id=%s", usuario["id"])
        st.error("Nao foi possivel atualizar o e-mail agora. Tente novamente em alguns instantes.")
        return

    usuario_refresh = resultado.get("usuario") or st.session_state.get("usuario") or usuario
    st.session_state["usuario"] = usuario_refresh
    st.session_state["perfil_email_notice"] = {
        "status": resultado.get("status"),
        "mensagem": resultado.get("mensagem") or "Enviamos um novo link para o e-mail atualizado.",
    }
    st.session_state["email_pending_notice"] = {
        "status": resultado.get("status"),
        "mensagem": resultado.get("mensagem") or "Enviamos um novo link para o e-mail atualizado.",
    }
    st.rerun()


def _salvar_logo_treinador(arquivo_upload):
    if arquivo_upload is None:
        return None

    extensao = Path(arquivo_upload.name or "").suffix.lower()
    if extensao not in {".png", ".jpg", ".jpeg", ".webp"}:
        extensao = ".png"

    diretorio = Path.cwd() / "uploads" / "logos"
    diretorio.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"treinador_logo_{uuid.uuid4().hex}{extensao}"
    destino = diretorio / nome_arquivo
    with open(destino, "wb") as arquivo_destino:
        arquivo_destino.write(arquivo_upload.getbuffer())

    return f"/uploads/logos/{nome_arquivo}"


def _render_personalizacao_treinador(usuario):
    if usuario.get("tipo_usuario") != "treinador":
        return

    st.subheader("Personalizacao do aplicativo")
    st.caption("As cores e a logo definidas aqui tambem serao exibidas para os atletas vinculados.")

    tema_atual = buscar_tema_treinador(usuario["id"])
    logo_atual = resolver_logo_treinador(tema_atual.get("logo_url"))

    if logo_atual:
        st.image(logo_atual, width=120)

    with st.form(f"form_tema_treinador_perfil_{usuario['id']}"):
        cor_primaria = st.color_picker("Cor primaria", value=tema_atual.get("cor_primaria", "#023363"))
        cor_secundaria = st.color_picker("Cor secundaria", value=tema_atual.get("cor_secundaria", "#0c4a85"))
        cor_botao = st.color_picker("Cor do botao", value=tema_atual.get("cor_botao", "#E73529"))
        cor_cards = st.color_picker("Cor de fundo dos cards", value=tema_atual.get("cor_cards", "#f4f8fc"))
        cor_header = st.color_picker("Cor do header", value=tema_atual.get("cor_header", "#02284e"))
        logo_upload = st.file_uploader(
            "Logo ou foto do treinador",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"logo_treinador_perfil_{usuario['id']}",
        )
        remover_logo = st.checkbox(
            "Remover logo atual",
            value=False,
            disabled=not bool(tema_atual.get("logo_url")),
            key=f"remover_logo_treinador_perfil_{usuario['id']}",
        )
        salvar = st.form_submit_button("Salvar personalizacao", use_container_width=True)

    if not salvar:
        return

    logo_url = tema_atual.get("logo_url")
    if remover_logo:
        logo_url = None
    elif logo_upload is not None:
        logo_url = _salvar_logo_treinador(logo_upload)

    salvar_tema_treinador(
        usuario["id"],
        cor_primaria,
        cor_secundaria,
        logo_url,
        cor_botao=cor_botao,
        cor_cards=cor_cards,
        cor_header=cor_header,
    )
    st.session_state["tema_app"] = buscar_tema_treinador(usuario["id"])
    st.session_state["mensagem_perfil"] = "Personalizacao atualizada com sucesso."
    st.rerun()


def _render_vinculo_atleta(usuario):
    if usuario.get("tipo_usuario") != "atleta":
        return

    st.subheader("Treinador")
    vinculos = listar_treinadores_do_atleta(usuario["id"])
    ativos = [item for item in vinculos if item["status"] == "ativo"]
    pendentes = [item for item in vinculos if item["status"] == "pendente"]

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

    if pendentes:
        st.caption("Solicitacoes pendentes de aprovacao pelo treinador")
        for vinculo in pendentes:
            nome_treinador = vinculo.get("treinador_apelido") or vinculo["treinador_nome"]
            st.write(f"{nome_treinador} ({vinculo['treinador_email']})")

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
    st.caption("Essa acao remove permanentemente sua conta e os dados permitidos para exclusao automatica.")
    with st.form(f"form_excluir_conta_{usuario['id']}"):
        confirmar = st.checkbox("Confirmo que desejo excluir minha conta permanentemente.")
        excluir = st.form_submit_button("Excluir conta", use_container_width=True)

    if not excluir:
        return False
    if not confirmar:
        st.error("Confirme a exclusao para continuar.")
        return False

    try:
        excluir_usuario(usuario["id"])
    except ExclusaoContaBloqueadaError as exc:
        st.error(str(exc))
        return False
    except ExclusaoContaError:
        st.error("Nao foi possivel excluir sua conta agora. Tente novamente em alguns instantes ou entre em contato com o suporte.")
        return False
    except Exception:
        LOGGER.exception("[ACCOUNT_DELETE_ERROR] Falha inesperada na tela de perfil usuario_id=%s", usuario["id"])
        st.error("Nao foi possivel excluir sua conta agora. Tente novamente em alguns instantes ou entre em contato com o suporte.")
        return False

    return True


def _render_alterar_senha(usuario):
    st.subheader("Alterar senha")
    st.caption("Confirme sua senha atual e defina uma nova senha para esta conta.")

    with st.form(f"form_alterar_senha_{usuario['id']}"):
        senha_atual = st.text_input("Senha atual", type="password")
        nova_senha = st.text_input("Nova senha", type="password")
        confirmar_nova_senha = st.text_input("Confirmar nova senha", type="password")
        salvar_senha = st.form_submit_button("Salvar nova senha", use_container_width=True)

    if not salvar_senha:
        return

    ok, mensagem = alterar_senha_usuario_autenticado(
        usuario["id"],
        senha_atual,
        nova_senha,
        confirmar_nova_senha,
    )
    if ok:
        st.session_state["mensagem_perfil"] = mensagem
        st.rerun()
    st.error(mensagem)


def tela_meu_perfil(usuario):
    usuario = buscar_usuario_por_id(usuario["id"]) or usuario
    st.session_state["usuario"] = usuario
    st.title("Meu perfil")

    mensagem = st.session_state.pop("mensagem_perfil", None)
    if mensagem:
        st.success(mensagem)

    _render_form_perfil(usuario)
    _render_status_email(st.session_state.get("usuario") or usuario)
    _render_alterar_senha(usuario)
    _render_personalizacao_treinador(usuario)
    _render_vinculo_atleta(usuario)
    return _render_exclusao_conta(usuario)
