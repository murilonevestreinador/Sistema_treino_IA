from datetime import date, datetime, timedelta
import math

from core.calendario import hoje_local, inicio_semana_local
from core.usuarios import saudacao_usuario


FASES_PADRAO = ("base", "especifico", "polimento", "retorno")
SEMANAS_RETORNO = 2


def _normalizar_data(data_texto):
    if not data_texto:
        return None
    if isinstance(data_texto, date):
        return data_texto
    texto = str(data_texto).strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(texto).date()
        except ValueError:
            return None


def _inicio_plano_atleta(atleta):
    return inicio_semana_local(
        _normalizar_data(atleta.get("plano_inicio_em"))
        or _normalizar_data(atleta.get("data_criacao"))
        or hoje_local()
    )


def calcular_semanas_ate_prova(atleta, inicio_plano=None):
    if not atleta.get("tem_prova") or not atleta.get("data_prova"):
        return 12

    data_prova = _normalizar_data(atleta["data_prova"])
    referencia_inicial = inicio_plano or _inicio_plano_atleta(atleta)
    dias = (data_prova - referencia_inicial).days
    return max(1, math.ceil(max(dias, 1) / 7))


def distribuir_fases(total_semanas_pre_prova, tem_dor=False):
    if total_semanas_pre_prova <= 2:
        base = 1
        especifico = 0
        polimento = max(1, total_semanas_pre_prova - base)
    else:
        polimento = 2 if total_semanas_pre_prova >= 6 else 1
        semanas_desenvolvimento = max(1, total_semanas_pre_prova - polimento)
        proporcao_base = 0.6 if tem_dor else 0.55
        base = max(1, round(semanas_desenvolvimento * proporcao_base))
        especifico = max(0, semanas_desenvolvimento - base)

    return {
        "base": base,
        "especifico": especifico,
        "polimento": polimento,
        "retorno": SEMANAS_RETORNO,
    }


def gerar_cronograma(atleta):
    inicio_base = _inicio_plano_atleta(atleta)
    total_pre_prova = calcular_semanas_ate_prova(atleta, inicio_plano=inicio_base)
    historico = (atleta.get("historico_lesao") or "").lower()
    dor = (atleta.get("dor_atual") or "").lower()
    tem_dor = any(valor and valor != "nenhuma" for valor in (historico, dor))
    fases = distribuir_fases(total_pre_prova, tem_dor=tem_dor)
    cronograma = []
    semana_numero = 1

    for fase in FASES_PADRAO:
        for _ in range(fases.get(fase, 0)):
            inicio = inicio_base + timedelta(days=(semana_numero - 1) * 7)
            fim = inicio + timedelta(days=6)
            cronograma.append(
                {
                    "semana": semana_numero,
                    "fase": fase,
                    "inicio": inicio.isoformat(),
                    "fim": fim.isoformat(),
                }
            )
            semana_numero += 1

    return cronograma, fases, total_pre_prova


def obter_semana_atual(cronograma, referencia=None):
    if not cronograma:
        return None

    hoje = referencia or hoje_local()

    for semana in cronograma:
        inicio = _normalizar_data(semana["inicio"])
        fim = _normalizar_data(semana["fim"])
        if inicio <= hoje <= fim:
            return semana

    if hoje < _normalizar_data(cronograma[0]["inicio"]):
        return cronograma[0]

    return cronograma[-1]


def buscar_semana_por_numero(cronograma, semana_numero):
    for semana in cronograma:
        if semana["semana"] == semana_numero:
            return semana
    return None


def gerar_mensagem_usuario(atleta, fases, total_semanas):
    saudacao = saudacao_usuario(atleta.get("sexo"))
    nome = atleta.get("nome", "Atleta")

    return (
        f"{saudacao}, {nome}! "
        f"Seu planejamento tem {total_semanas} semanas ate a prova, com "
        f"{fases.get('base', 0)} semanas de base, "
        f"{fases.get('especifico', 0)} semanas de especifico, "
        f"{fases.get('polimento', 0)} semanas de polimento "
        f"e {fases.get('retorno', 0)} semanas de retorno."
    )
