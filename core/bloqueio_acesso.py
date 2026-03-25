import streamlit as st

from core.financeiro import obter_status_interface_atleta


def _aplicar_estilo_bloqueio():
    st.markdown(
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
            color:var(--tri-text-soft);
            line-height:1.65;
            font-size:.95rem;
        }
        @media (max-width: 860px){
            .trial-lock-body{grid-template-columns:1fr}
            .trial-lock-head h2{font-size:1.6rem}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _abrir_pagina(destino):
    try:
        st.switch_page(destino)
    except Exception:
        st.info("Use o menu lateral para abrir esta pagina.")


def _conteudo_bloqueio_atleta(contexto, usuario):
    status = contexto.get("status")
    if status == "vinculo_pendente":
        return {
            "badge": "Atleta • vinculo pendente",
            "titulo": contexto.get("titulo") or "Seu vinculo com o treinador esta pendente",
            "texto": contexto.get("texto") or "Assim que o treinador aprovar seu vinculo, seu acesso sera liberado normalmente pela plataforma.",
            "painel_titulo": "Enquanto isso",
            "painel_html": "<p class='trial-lock-note'>Se o seu teste gratis ja terminou, o acesso completo depende da aprovacao do treinador ou da contratacao de um plano proprio.</p>",
            "acao_titulo": "Proximo passo recomendado",
            "acao_texto": "Acompanhe a aprovacao do seu treinador. Se preferir, voce tambem pode assinar um plano para continuar agora.",
        }
    if status == "vinculo_encerrado":
        return {
            "badge": "Atleta • vinculo encerrado",
            "titulo": contexto.get("titulo") or "Seu vinculo com o treinador foi encerrado",
            "texto": contexto.get("texto") or "Para continuar usando o TriLab, escolha um plano ou vincule-se novamente a um treinador.",
            "painel_titulo": "Como retomar o acesso",
            "painel_html": "<p class='trial-lock-note'>Voce pode seguir com um plano individual ou solicitar um novo vinculo com treinador pela plataforma.</p>",
            "acao_titulo": "Proximo passo recomendado",
            "acao_texto": f"{usuario.get('nome', 'Atleta')}, escolha um plano ou vincule sua conta novamente para voltar a usar a plataforma sem interrupcao.",
        }
    return {
        "badge": "Atleta • acesso premium",
        "titulo": contexto.get("titulo") or "Seu periodo de teste terminou",
        "texto": contexto.get("texto") or "Para continuar usando o TriLab, escolha um plano ou treine com um treinador parceiro.",
        "painel_titulo": "O que voce desbloqueia ao continuar",
        "painel_html": """
            <div class="trial-lock-benefit">
                <div class="trial-lock-icon">1</div>
                <div><strong>Treinos e historico completos</strong><br><span class="trial-lock-note">Acompanhe seu plano, progresso e consistencia sem perder o que ja construiu.</span></div>
            </div>
            <div class="trial-lock-benefit">
                <div class="trial-lock-icon">2</div>
                <div><strong>Periodizacao e ajustes inteligentes</strong><br><span class="trial-lock-note">Continue recebendo evolucao do treino com base no seu momento e nas suas respostas.</span></div>
            </div>
            <div class="trial-lock-benefit">
                <div class="trial-lock-icon">3</div>
                <div><strong>Fluxo com treinador parceiro</strong><br><span class="trial-lock-note">Se voce ja tem treinador, vincule sua conta para manter o acesso pela operacao dele.</span></div>
            </div>
        """,
        "acao_titulo": "Proximo passo recomendado",
        "acao_texto": f"{usuario.get('nome', 'Atleta')}, voce pode retomar o acesso agora escolhendo um plano ou vinculando sua conta a um treinador ativo.",
    }


def render_bloqueio_atleta(usuario, on_logout, contexto=None):
    contexto = contexto or obter_status_interface_atleta(usuario["id"])
    conteudo = _conteudo_bloqueio_atleta(contexto, usuario)
    _aplicar_estilo_bloqueio()
    st.markdown(
        f"""
        <div class="trial-lock-shell">
            <div class="trial-lock-card">
                <div class="trial-lock-head">
                    <div class="trial-lock-badge">{conteudo['badge']}</div>
                    <h2>{conteudo['titulo']}</h2>
                    <p>{conteudo['texto']}</p>
                </div>
                <div class="trial-lock-body">
                    <div class="trial-lock-panel">
                        <h3>{conteudo['painel_titulo']}</h3>
                        {conteudo['painel_html']}
                    </div>
                    <div class="trial-lock-panel">
                        <h3>{conteudo['acao_titulo']}</h3>
                        <p class="trial-lock-note">{conteudo['acao_texto']}</p>
                        <p class="trial-lock-note">Se recebeu um convite, use a opcao de perfil para adicionar o treinador ou aceitar o vinculo.</p>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Ver planos", type="primary", use_container_width=True):
            _abrir_pagina("pages/planos.py")
    with col2:
        if st.button("Ja tenho treinador", use_container_width=True):
            st.session_state["secao_app"] = "perfil"
            st.rerun()
    with col3:
        if st.button("Sair", use_container_width=True):
            on_logout()


def render_bloqueio_treinador(on_logout):
    _aplicar_estilo_bloqueio()
    st.markdown(
        """
        <div class="trial-lock-shell">
            <div class="trial-lock-card">
                <div class="trial-lock-head">
                    <div class="trial-lock-badge">Treinador • assinatura da plataforma</div>
                    <h2>Seu periodo de teste terminou</h2>
                    <p>Assine um plano para continuar prescrevendo treinos e acompanhando seus atletas.</p>
                </div>
                <div class="trial-lock-body">
                    <div class="trial-lock-panel">
                        <h3>Beneficios do plano treinador</h3>
                        <div class="trial-lock-benefit">
                            <div class="trial-lock-icon">A</div>
                            <div><strong>Gestao dos seus atletas</strong><br><span class="trial-lock-note">Continue acompanhando vinculos, evolucao e operacao da sua carteira dentro da plataforma.</span></div>
                        </div>
                        <div class="trial-lock-benefit">
                            <div class="trial-lock-icon">B</div>
                            <div><strong>Prescricao e acompanhamento</strong><br><span class="trial-lock-note">Mantenha o fluxo de prescricao, BI, ajustes e suporte para seus alunos.</span></div>
                        </div>
                        <div class="trial-lock-benefit">
                            <div class="trial-lock-icon">C</div>
                            <div><strong>Escala com modelo SaaS</strong><br><span class="trial-lock-note">Ative o plano base e siga operando com taxa fixa por aluno ativo vinculado.</span></div>
                        </div>
                    </div>
                    <div class="trial-lock-panel">
                        <h3>Recupere o acesso</h3>
                        <p class="trial-lock-note">Assine um plano para voltar a prescrever treinos, acompanhar sua base e manter sua operacao rodando com clareza.</p>
                        <p class="trial-lock-note">Se precisar falar com o time, o suporte segue disponivel.</p>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Ver planos", type="primary", use_container_width=True):
            _abrir_pagina("pages/planos.py")
    with col2:
        if st.button("Falar com suporte", use_container_width=True):
            _abrir_pagina("pages/contato.py")
    with col3:
        if st.button("Sair", use_container_width=True):
            on_logout()
