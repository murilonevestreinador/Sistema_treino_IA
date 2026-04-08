import logging
import os


LOGGER = logging.getLogger("trilab.env")
TRUE_VALUES = {"1", "true", "yes", "on", "sim", "s"}
FALSE_VALUES = {"", "0", "false", "no", "off", "nao", "não", "n", "none", "null"}


def raw_env(nome):
    return os.getenv(nome)


def _valor_para_log(valor):
    if valor is None:
        return "<unset>"
    if str(valor) == "":
        return "<empty>"
    return str(valor)


def parse_bool(valor, padrao=False):
    if valor is None:
        return bool(padrao)

    normalizado = str(valor).strip().lower()
    if normalizado in TRUE_VALUES:
        return True
    if normalizado in FALSE_VALUES:
        return False
    return bool(padrao)


def bool_env(nome, padrao=False, logger=None, contexto=None):
    valor_bruto = os.getenv(nome)
    valor_normalizado = str(valor_bruto or "").strip().lower()
    valor_booleano = parse_bool(valor_bruto, padrao=padrao)
    destino_log = logger or LOGGER
    campos_log = (
        nome,
        _valor_para_log(valor_bruto),
        valor_booleano,
        bool(padrao),
        contexto or "-",
    )

    if valor_bruto is not None and valor_normalizado not in TRUE_VALUES and valor_normalizado not in FALSE_VALUES:
        destino_log.warning(
            "[AUTH_ENV] Boolean env com valor desconhecido nome=%s bruto=%s interpretado=%s padrao=%s contexto=%s",
            *campos_log,
        )
        return valor_booleano

    destino_log.info(
        "[AUTH_ENV] Boolean env lida nome=%s bruto=%s interpretado=%s padrao=%s contexto=%s",
        *campos_log,
    )
    return valor_booleano
