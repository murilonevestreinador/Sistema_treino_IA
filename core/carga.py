from core.periodizacao import semana_do_ciclo


CATEGORIAS_AVALIACAO = {
    "empurrar membros inferiores": "empurrar_membros_inferiores",
    "puxar membros inferiores": "puxar_membros_inferiores",
    "empurrar membros superiores": "empurrar_membros_superiores",
    "puxar membros superiores": "puxar_membros_superiores",
    "panturrilha": "panturrilha",
}

ROTULOS_CATEGORIA = {
    "empurrar_membros_inferiores": "Empurrar membros inferiores",
    "puxar_membros_inferiores": "Puxar membros inferiores",
    "empurrar_membros_superiores": "Empurrar membros superiores",
    "puxar_membros_superiores": "Puxar membros superiores",
    "panturrilha": "Panturrilha",
}

MULTIPLICADORES_FASE = {
    "base": {1: 0.68, 2: 0.72, 3: 0.76, 4: 0.7},
    "especifico": {1: 0.78, 2: 0.83, 3: 0.87, 4: 0.8},
    "polimento": {1: 0.64, 2: 0.66, 3: 0.68, 4: 0.66},
    "retorno": {1: 0.55, 2: 0.6, 3: 0.65, 4: 0.62},
}


def categoria_movimento(categoria):
    return CATEGORIAS_AVALIACAO.get((categoria or "").strip().lower())


def rotulo_categoria_movimento(categoria_mov):
    return ROTULOS_CATEGORIA.get(categoria_mov, categoria_mov or "")


def exercicio_elegivel_avaliacao(exercicio):
    return bool(categoria_movimento(exercicio.get("categoria")))


def estimar_carga_referencia(carga_utilizada, reps_realizadas, rpe):
    carga = float(carga_utilizada or 0)
    reps = int(reps_realizadas or 0)
    rpe_real = float(rpe or 0)
    if carga <= 0 or reps <= 0 or rpe_real <= 0:
        return None

    reps_reserva = max(0.0, 10.0 - rpe_real)
    reps_ate_falha = reps + reps_reserva
    return round(carga * (1 + (reps_ate_falha / 30.0)), 2)


def parse_rpe_alvo(rpe_alvo):
    if rpe_alvo is None:
        return None
    texto = str(rpe_alvo).strip().replace(",", ".")
    if not texto:
        return None
    if "-" in texto:
        partes = [parte.strip() for parte in texto.split("-") if parte.strip()]
        if len(partes) == 2:
            try:
                return (float(partes[0]) + float(partes[1])) / 2
            except ValueError:
                return None
    try:
        return float(texto)
    except ValueError:
        return None


def ajuste_percentual_por_feedback(rpe_alvo, rpe_real=None, dor=None, feedback_ruim=False):
    if dor or feedback_ruim:
        return -0.1

    alvo = parse_rpe_alvo(rpe_alvo)
    real = float(rpe_real) if rpe_real is not None else None
    if alvo is None or real is None:
        return 0.0

    diferenca = real - alvo
    if diferenca <= -1.5:
        return 0.05
    if diferenca <= -0.5:
        return 0.025
    if diferenca >= 1.5:
        return -0.06
    if diferenca >= 0.5:
        return -0.03
    return 0.01


def orientacao_carga_semana_1(fase):
    orientacoes = {
        "base": "Carga sugerida: leve, priorizando tecnica, amplitude e controle.",
        "especifico": "Carga sugerida: leve a moderada, com execucao perfeita antes de acelerar.",
        "polimento": "Carga sugerida: leve, poupando fadiga e preservando qualidade do movimento.",
        "retorno": "Carga sugerida: leve, com cautela extra e foco em readaptacao.",
    }
    return orientacoes.get(fase, "Carga sugerida: leve, priorizando tecnica perfeita.")


def multiplicador_por_periodizacao(fase, semana_global):
    semana_ciclo = semana_do_ciclo(semana_global)
    tabela = MULTIPLICADORES_FASE.get(fase, MULTIPLICADORES_FASE["base"])
    return tabela.get(semana_ciclo, 0.7)


def calcular_carga_sugerida(
    fase,
    semana_numero,
    rpe_alvo,
    avaliacao=None,
    ultima_execucao=None,
    feedback_ruim=False,
):
    if semana_numero <= 1:
        return None

    if not avaliacao:
        return None

    referencia_base = avaliacao.get("carga_sugerida_manual") or avaliacao.get("carga_referencia_estimada")
    if not referencia_base:
        return None

    carga = float(referencia_base) * multiplicador_por_periodizacao(fase, semana_numero)
    if ultima_execucao:
        carga *= 1 + ajuste_percentual_por_feedback(
            rpe_alvo,
            rpe_real=ultima_execucao.get("rpe_real"),
            dor=ultima_execucao.get("dor"),
            feedback_ruim=feedback_ruim,
        )

    return round(max(carga, 0), 1)


def descrever_prescricao_carga(semana_numero, fase, exercicio, rpe_alvo, avaliacao=None, ultima_execucao=None, feedback_ruim=False):
    categoria = categoria_movimento(exercicio.get("categoria"))

    if semana_numero == 1:
        return {
            "modo_carga": "tecnica",
            "categoria_movimento": categoria,
            "carga_sugerida": None,
            "orientacao_carga": orientacao_carga_semana_1(fase),
        }

    if semana_numero == 2 and categoria:
        return {
            "modo_carga": "avaliacao",
            "categoria_movimento": categoria,
            "carga_sugerida": None,
            "orientacao_carga": "Avaliacao de carga: registre peso usado, repeticoes realizadas e percepcao de esforco.",
        }

    carga_sugerida = calcular_carga_sugerida(
        fase,
        semana_numero,
        rpe_alvo,
        avaliacao=avaliacao,
        ultima_execucao=ultima_execucao,
        feedback_ruim=feedback_ruim,
    )
    if carga_sugerida is not None:
        return {
            "modo_carga": "prescrita",
            "categoria_movimento": categoria,
            "carga_sugerida": carga_sugerida,
            "orientacao_carga": (
                f"Carga sugerida: {carga_sugerida} kg | Percepcao de esforco alvo {rpe_alvo}. "
                "Carga sugerida com base na sua avaliacao anterior."
            ),
        }

    return {
        "modo_carga": "qualitativa",
        "categoria_movimento": categoria,
        "carga_sugerida": None,
        "orientacao_carga": "Use uma carga moderada que mantenha tecnica consistente e percepcao de esforco dentro da meta.",
    }
