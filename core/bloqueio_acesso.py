import logging
from html import escape
from textwrap import dedent

import streamlit as st

from core.financeiro import obter_status_interface_atleta


LOGGER = logging.getLogger("trilab.access_lock")


def _aplicar_estilo_bloqueio():
    st.markdown(
        dedent(
            """
            <style>
            .trial-lock-shell{
                min-height:62vh;
                display:flex;
                align-items:center;
                justify-content:center;
                padding:1.5rem 0 1rem;
            }
            .trial-lock-card{
                width:min(860px, 100%);
                border-radius:32px;
                border:1px solid var(--tri-border);
                background:
                    radial-gradient(circle at top right, color-mix(in srgb, var(--tri-primary) 16%, transparent), transparent 28%),
                    linear-gradient(180deg, color-mix(in srgb, var(--tri-surface) 98%, white) 0%, color-mix(in srgb, var(--tri-surface) 92%, var(--tri-card-bg, white)) 100%);
                box-shadow:var(--tri-shadow-strong);
                overflow:hidden;
            }
            .trial-lock-head{
                padding:1.35rem 1.45rem 1rem;
                background:linear-gradient(135deg, var(--tri-header-start) 0%, var(--tri-header-end) 100%);
                color:var(--tri-text-on-header);
            }
            .trial-lock-badge{
                display:inline-flex;
                align-items:center;
                gap:.4rem;
                padding:.35rem .7rem;
                border-radius:999px;
                background:color-mix(in srgb, var(--tri-text-on-header) 14%, transparent);
                border:1px solid color-mix(in srgb, var(--tri-text-on-header) 16%, transparent);
                font-size:.74rem;
                font-weight:800;
                letter-spacing:.08em;
                text-transform:uppercase;
            }
            .trial-lock-head h2{
                margin:.8rem 0 .35rem;
                color:var(--tri-text-on-header);
                font-size:2rem;
            }
            .trial-lock-head p{
                margin:0;
                color:color-mix(in srgb, var(--tri-text-on-header) 82%, transparent);
                font-size:1rem;
                line-height:1.6;
            }
            .trial-lock-body{
                display:grid;
                grid-template-columns:1.1fr .9fr;
                gap:1rem;
                padding:1.2rem 1.35rem 1.35rem;
            }
            .trial-lock-panel{
                border-radius:24px;
                border:1px solid var(--tri-border);
                background:color-mix(in srgb, var(--tri-surface) 96%, transparent);
                padding:1rem 1.05rem;
            }
            .trial-lock-panel h3{
                margin:0 0 .65rem;
                font-size:1rem;
                color:var(--tri-text-strong);
            }
            .trial-lock-benefit{
                display:flex;
                gap:.7rem;
                align-items:flex-start;
                padding:.65rem 0;
                border-bottom:1px solid color-mix(in srgb, var(--tri-border) 80%, transparent);
            }
            .trial-lock-benefit:last-child{border-bottom:none}
            .trial-lock-icon{
                width:2.4rem;
                height:2.4rem;
                border-radius:16px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:color-mix(in srgb, var(--tri-primary) 12%, transparent);
                color:var(--tri-primary);
                font-weight:900;
            }
            .trial-lock-note{
                margin:0 0 .75rem;
                color:var(--tri-text-soft);
                line-height:1.65;
                font-size:.95rem;
            }
            .trial-lock-note:last-child{margin-bottom:0}
            @media (max-width: 860px){
                .trial-lock-body{grid-template-columns:1fr}
                .trial-lock-head h2{font-size:1.6rem}
            }
            </style>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _abrir_pagina(destino):
    try:
        st.switch_page(destino)
    except Exception:
        st.info("Use o menu lateral para abrir esta pagina.")


def _executar_acao_bloqueio(acao):
    if not acao:
        return
    if acao.get("destino"):
        _abrir_pagina(acao["destino"])
        return
    if acao.get("secao_app"):
        st.session_state["secao_app"] = acao["secao_app"]
        st.rerun()


def _render_beneficios_html(beneficios):
    blocos = []
    for beneficio in beneficios or []:
        blocos.append(
            (
                f'<div class="trial-lock-benefit">'
                f'<div class="trial-lock-icon">{escape(str(beneficio.get("icone") or ""))}</div>'
                f"<div>"
                f"<strong>{escape(beneficio.get('titulo') or '')}</strong><br>"
                f'<span class="trial-lock-note">{escape(beneficio.get("texto") or "")}</span>'
                f"</div>"
                f"</div>"
            )
        )
    return "".join(blocos)


def _render_textos_html(textos):
    return "".join(
        f'<p class="trial-lock-note">{escape(texto)}</p>'
        for texto in (textos or [])
        if texto
    )


def _montar_html_painel(titulo, beneficios=None, textos=None):
    return (
        f'<div class="trial-lock-panel">'
        f"<h3>{escape(titulo or '')}</h3>"
        f"{_render_beneficios_html(beneficios)}"
        f"{_render_textos_html(textos)}"
        f"</div>"
    )


def _montar_html_bloqueio(conteudo):
    painel_principal_html = _montar_html_painel(
        conteudo.get("painel_titulo"),
        beneficios=conteudo.get("beneficios"),
        textos=conteudo.get("painel_textos"),
    )
    painel_acao_html = _montar_html_painel(
        conteudo.get("acao_titulo"),
        textos=conteudo.get("acao_textos"),
    )
    return dedent(
        f"""
        <div class="trial-lock-shell">
            <div class="trial-lock-card">
                <div class="trial-lock-head">
                    <div class="trial-lock-badge">{escape(conteudo.get("badge") or "")}</div>
                    <h2>{escape(conteudo.get("titulo") or "")}</h2>
                    <p>{escape(conteudo.get("texto") or "")}</p>
                </div>
                <div class="trial-lock-body">
{painel_principal_html}
{painel_acao_html}
                </div>
            </div>
        </div>
        """
    ).strip()


def _conteudo_bloqueio_atleta(contexto, usuario):
    nome_base = (usuario.get("nome") or "").strip()
    primeiro_nome = nome_base.split()[0] if nome_base else "Atleta"
    status = contexto.get("status")

    if status == "vinculo_pendente":
        return {
            "badge": "Atleta | aprovacao pendente",
            "titulo": contexto.get("titulo") or "Seu vinculo com o treinador esta pendente",
            "texto": contexto.get("texto") or "Assim que o treinador aprovar seu vinculo, seu acesso sera liberado normalmente pela plataforma.",
            "painel_titulo": "Enquanto voce aguarda",
            "beneficios": [],
            "painel_textos": [
                "Se o seu teste gratis ja terminou, voce pode concluir um plano individual para liberar o acesso sem depender dessa aprovacao.",
            ],
            "acao_titulo": "Proximo passo recomendado",
            "acao_textos": [
                f"{primeiro_nome}, acompanhe o status do convite pelo seu perfil.",
                "Se preferir voltar agora, escolha um plano e continue usando o app sem interrupcao.",
            ],
            "cta_primaria": {"label": "Escolher plano", "destino": "pages/planos.py"},
            "cta_secundaria": {"label": "Abrir meu perfil", "secao_app": "perfil"},
        }

    if status == "vinculo_encerrado":
        return {
            "badge": "Atleta | acesso pausado",
            "titulo": contexto.get("titulo") or "Seu vinculo com o treinador foi encerrado",
            "texto": contexto.get("texto") or "Continue usando o TriLab escolhendo um plano para liberar seu acesso novamente.",
            "painel_titulo": "Como retomar o acesso",
            "beneficios": [],
            "painel_textos": [
                "Seu historico continua associado a esta conta. Assim que voce escolher um plano, o acesso volta ao normal.",
            ],
            "acao_titulo": "Proximo passo recomendado",
            "acao_textos": [
                f"{primeiro_nome}, escolha um plano para seguir com seus treinos e manter a continuidade do que voce ja construiu.",
            ],
            "cta_primaria": {"label": "Escolher plano", "destino": "pages/planos.py"},
            "cta_secundaria": {"label": "Ver minha assinatura", "destino": "pages/minha_assinatura.py"},
        }

    return {
        "badge": "Atleta | assinatura necessaria",
        "titulo": contexto.get("titulo") or "Seu periodo de teste terminou",
        "texto": "Continue usando o TriLab escolhendo um plano para liberar seu acesso novamente.",
        "painel_titulo": "O que voce libera ao continuar",
        "beneficios": [
            {
                "icone": "1",
                "titulo": "Treinos e historico",
                "texto": "Acesse novamente seus treinos, registros e a evolucao do que voce ja vem construindo.",
            },
            {
                "icone": "2",
                "titulo": "Acompanhamento da evolucao",
                "texto": "Mantenha sua consistencia com a visao do que funcionou melhor em cada etapa do plano.",
            },
            {
                "icone": "3",
                "titulo": "Periodizacao do plano",
                "texto": "Continue seguindo uma estrutura pensada para o seu momento, sem perder a sequencia.",
            },
            {
                "icone": "4",
                "titulo": "Continuidade do ciclo",
                "texto": "Volte a usar o app com tudo pronto para seguir do ponto em que voce parou.",
            },
        ],
        "painel_textos": [],
        "acao_titulo": "Pronto para voltar?",
        "acao_textos": [
            "Seu acesso pode ser liberado assim que a assinatura for concluida.",
        ],
        "cta_primaria": {"label": "Escolher plano", "destino": "pages/planos.py"},
        "cta_secundaria": {"label": "Ver minha assinatura", "destino": "pages/minha_assinatura.py"},
    }


def render_bloqueio_atleta(usuario, on_logout, contexto=None):
    contexto = contexto or obter_status_interface_atleta(usuario["id"])
    conteudo = _conteudo_bloqueio_atleta(contexto, usuario)
    LOGGER.info(
        "[TRIAL_LOCK] Renderizando bloqueio do atleta usuario_id=%s status=%s renderer=structured_card_v2",
        usuario["id"],
        contexto.get("status") or "sem_acesso",
    )
    _aplicar_estilo_bloqueio()
    st.markdown(_montar_html_bloqueio(conteudo), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            conteudo["cta_primaria"]["label"],
            key=f"trial_lock_primary_{contexto.get('status') or 'sem_acesso'}",
            type="primary",
            use_container_width=True,
        ):
            _executar_acao_bloqueio(conteudo["cta_primaria"])
    with col2:
        if st.button(
            conteudo["cta_secundaria"]["label"],
            key=f"trial_lock_secondary_{contexto.get('status') or 'sem_acesso'}",
            use_container_width=True,
        ):
            _executar_acao_bloqueio(conteudo["cta_secundaria"])
    if st.button("Sair", key=f"trial_lock_logout_{contexto.get('status') or 'sem_acesso'}", use_container_width=True):
        on_logout()


def render_bloqueio_treinador(on_logout):
    LOGGER.info("[TRIAL_LOCK] Renderizando bloqueio do treinador renderer=structured_card_v2")
    _aplicar_estilo_bloqueio()
    st.markdown(
        _montar_html_bloqueio(
            {
                "badge": "Treinador | assinatura da plataforma",
                "titulo": "Seu periodo de teste terminou",
                "texto": "Assine um plano para continuar prescrevendo treinos e acompanhando seus atletas.",
                "painel_titulo": "Beneficios do plano treinador",
                "beneficios": [
                    {
                        "icone": "A",
                        "titulo": "Gestao dos seus atletas",
                        "texto": "Continue acompanhando vinculos, evolucao e operacao da sua carteira dentro da plataforma.",
                    },
                    {
                        "icone": "B",
                        "titulo": "Prescricao e acompanhamento",
                        "texto": "Mantenha o fluxo de prescricao, BI, ajustes e suporte para seus alunos.",
                    },
                    {
                        "icone": "C",
                        "titulo": "Escala com modelo SaaS",
                        "texto": "Ative o plano base e siga operando com taxa fixa por aluno ativo vinculado.",
                    },
                ],
                "painel_textos": [],
                "acao_titulo": "Recupere o acesso",
                "acao_textos": [
                    "Assine um plano para voltar a prescrever treinos, acompanhar sua base e manter sua operacao rodando com clareza.",
                    "Se precisar falar com o time, o suporte segue disponivel.",
                ],
            }
        ),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Ver planos", key="trainer_trial_lock_primary", type="primary", use_container_width=True):
            _abrir_pagina("pages/planos.py")
    with col2:
        if st.button("Falar com suporte", key="trainer_trial_lock_secondary", use_container_width=True):
            _abrir_pagina("pages/contato.py")
    if st.button("Sair", key="trainer_trial_lock_logout", use_container_width=True):
        on_logout()
