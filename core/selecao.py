import unicodedata


def _normalizar_categoria(valor):
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return texto.strip().lower().replace(" ", "_")


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
        if _impacto_permitido(exercicio, atleta) and _complexidade_permitida(exercicio, atleta)
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


def escolher_exercicio_por_categoria(exercicios, categoria, fase, atleta, nomes_ja_usados=None):
    nomes_ja_usados = nomes_ja_usados or set()
    candidatos = listar_exercicios_por_categoria(exercicios, categoria, fase, atleta)

    for exercicio in candidatos:
        if exercicio["nome"] not in nomes_ja_usados:
            return exercicio

    return candidatos[0] if candidatos else None
