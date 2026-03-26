LANCAMENTO_SOMENTE_ATLETAS = True


def cadastro_publico_permite_treinador():
    return not LANCAMENTO_SOMENTE_ATLETAS


def planos_publicos_permitem_treinador():
    return not LANCAMENTO_SOMENTE_ATLETAS


def pode_exibir_planos_treinador_publicamente(usuario=None):
    if planos_publicos_permitem_treinador():
        return True
    return bool(usuario and (usuario.get("tipo_usuario") or "").strip().lower() == "treinador")
