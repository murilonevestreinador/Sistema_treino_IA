import unicodedata

from core.equipamentos import assinatura_equipamentos, exercicio_compativel_com_equipamentos


CATEGORIAS_COM_DIVERSIDADE_EQUIPAMENTO = {
    "empurrar_membros_inferiores",
    "puxar_membros_inferiores",
    "empurrar_membros_superiores",
    "puxar_membros_superiores",
}


def _normalizar_categoria(valor):
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return texto.strip().lower().replace(" ", "_")


def categoria_exige_diversidade_equipamento(categoria):
    return _normalizar_categoria(categoria) in CATEGORIAS_COM_DIVERSIDADE_EQUIPAMENTO


def normalizar_categoria_funcional(categoria):
    return _normalizar_categoria(categoria)


def assinatura_equipamento_exercicio(exercicio):
    return assinatura_equipamentos(exercicio.get("equipamentos_necessarios") or [])


def _tem_dor_ou_lesao(atleta, chave):
    historico = (atleta.get("historico_lesao") or "").lower()
    dor = (atleta.get("dor_atual") or "").lower()
    return chave in historico or chave in dor


def _impacto_permitido(exercicio, atleta):
    restricoes = {
        "joelho": "impacto_joelho",
        "lombar": "impacto_coluna",
        "coluna": "impacto_coluna",
        "ombro": "impacto_ombro",
    }
    for regiao, campo in restricoes.items():
        if _tem_dor_ou_lesao(atleta, regiao) and exercicio.get(campo) == "alto":
            return False
    return True


def _complexidade_permitida(exercicio, atleta):
    experiencia = (atleta.get("experiencia_musculacao") or "").lower()
    if experiencia in {"", "intermediario", "avancado"}:
        return True
    return exercicio.get("complexidade") != "alto"


def filtrar_exercicios(exercicios, atleta):
    return [
        exercicio
        for exercicio in exercicios
        if _impacto_permitido(exercicio, atleta)
        and _complexidade_permitida(exercicio, atleta)
        and exercicio_compativel_com_equipamentos(exercicio, atleta)
    ]


def listar_exercicios_por_categoria(exercicios, categoria, fase, atleta):
    categoria_normalizada = _normalizar_categoria(categoria)
    chave_prioridade = f"prioridade_{fase}"
    preferencias = atleta.get("preferencias_substituicao", []) or []
    nomes_bloqueados = {item.get("exercicio_nome") for item in preferencias}
    musculos_prioritarios = {
        item.get("principal_musculo")
        for item in preferencias
        if _normalizar_categoria(item.get("categoria")) == categoria_normalizada and item.get("principal_musculo")
    }

    candidatos = [
        exercicio
        for exercicio in filtrar_exercicios(exercicios, atleta)
        if _normalizar_categoria(exercicio.get("categoria")) == categoria_normalizada
        and exercicio.get("nome") not in nomes_bloqueados
    ]

    if musculos_prioritarios:
        candidatos = sorted(
            candidatos,
            key=lambda item: (
                1 if item.get("principal_musculo") in musculos_prioritarios else 0,
                item.get(chave_prioridade, 0),
                1 if item.get("favorito") else 0,
                item.get("nome", ""),
            ),
            reverse=True,
        )
        return candidatos

    return sorted(
        candidatos,
        key=lambda item: (item.get(chave_prioridade, 0), 1 if item.get("favorito") else 0, item.get("nome", "")),
        reverse=True,
    )


def escolher_exercicio_por_categoria(
    exercicios,
    categoria,
    fase,
    atleta,
    nomes_ja_usados=None,
    assinaturas_ja_usadas=None,
):
    nomes_ja_usados = nomes_ja_usados or set()
    assinaturas_ja_usadas = assinaturas_ja_usadas or set()
    candidatos = listar_exercicios_por_categoria(exercicios, categoria, fase, atleta)
    aplicar_diversidade = categoria_exige_diversidade_equipamento(categoria)

    if aplicar_diversidade:
        candidatos_diversos = [
            exercicio
            for exercicio in candidatos
            if assinatura_equipamento_exercicio(exercicio) not in assinaturas_ja_usadas
        ]
    else:
        candidatos_diversos = candidatos

    for exercicio in candidatos_diversos:
        if exercicio["nome"] not in nomes_ja_usados:
            return exercicio

    if candidatos_diversos:
        return candidatos_diversos[0]

    # Fallback controlado: se nao houver opcoes suficientes sem repetir assinatura
    # de equipamento, permite reutilizar a assinatura para completar o treino.
    for exercicio in candidatos:
        if exercicio["nome"] not in nomes_ja_usados:
            return exercicio

    return candidatos[0] if candidatos else None
