# Lista publica do front; o backend segue aceitando os demais objetivos.
# Para reativar outros objetivos, adicione os slugs aqui e seus rotulos abaixo.
OBJETIVO_PADRAO_FRONT = "performance"
OBJETIVOS_EXPOSTOS_NO_FRONT = (OBJETIVO_PADRAO_FRONT,)

ROTULOS_OBJETIVOS_FRONT = {
    "performance": "Performance",
}


def objetivos_expostos_no_front():
    return list(OBJETIVOS_EXPOSTOS_NO_FRONT)


def objetivo_visivel_no_front(objetivo):
    objetivo_normalizado = str(objetivo or OBJETIVO_PADRAO_FRONT).strip().lower()
    if objetivo_normalizado in OBJETIVOS_EXPOSTOS_NO_FRONT:
        return objetivo_normalizado
    return OBJETIVO_PADRAO_FRONT


def indice_objetivo_exposto_no_front(objetivo):
    objetivos = objetivos_expostos_no_front()
    objetivo_visivel = objetivo_visivel_no_front(objetivo)
    return objetivos.index(objetivo_visivel)


def rotulo_objetivo_front(objetivo):
    return ROTULOS_OBJETIVOS_FRONT.get(objetivo, str(objetivo or "").replace("_", " ").title())
