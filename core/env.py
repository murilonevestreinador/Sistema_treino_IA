import logging
import os


LOGGER = logging.getLogger("trilab.env")
TRUE_VALUES = {"1", "true", "yes", "on", "sim", "s"}
FALSE_VALUES = {"", "0", "false", "no", "off", "nao", "não", "n", "none", "null"}


def raw_env(nome):
    return os.getenv(nome)


def _logger_destino(logger=None):
    return logger or LOGGER


def _valor_para_log(valor, sensivel=False):
    if valor is None:
        return "<unset>"
    if str(valor) == "":
        return "<empty>"
    if sensivel:
        return "<set>"
    texto = str(valor)
    if len(texto) > 200:
        texto = f"{texto[:197]}..."
    return texto


def _contexto_log(contexto=None):
    return contexto or "-"


def parse_bool(valor, padrao=False):
    if valor is None:
        return bool(padrao)

    normalizado = str(valor).strip().lower()
    if normalizado in TRUE_VALUES:
        return True
    if normalizado in FALSE_VALUES:
        return False
    return bool(padrao)


def get_env_str(nome, padrao=None, logger=None, contexto=None, sensivel=False, strip=True):
    valor_bruto = os.getenv(nome)
    if valor_bruto is None:
        valor_final = padrao
    else:
        valor_final = valor_bruto.strip() if strip else valor_bruto

    _logger_destino(logger).info(
        "[AUTH_ENV] String env lida nome=%s bruto=%s interpretado=%s padrao=%s contexto=%s",
        nome,
        _valor_para_log(valor_bruto, sensivel=sensivel),
        _valor_para_log(valor_final, sensivel=sensivel),
        _valor_para_log(padrao, sensivel=sensivel),
        _contexto_log(contexto),
    )
    return valor_final


def get_env_bool(nome, padrao=False, logger=None, contexto=None):
    valor_bruto = os.getenv(nome)
    valor_normalizado = str(valor_bruto or "").strip().lower()
    valor_booleano = parse_bool(valor_bruto, padrao=padrao)
    destino_log = _logger_destino(logger)
    campos_log = (
        nome,
        _valor_para_log(valor_bruto),
        valor_booleano,
        bool(padrao),
        _contexto_log(contexto),
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


def get_env_int(nome, padrao=0, logger=None, contexto=None):
    valor_bruto = os.getenv(nome)
    destino_log = _logger_destino(logger)

    if valor_bruto is None or str(valor_bruto).strip() == "":
        valor_inteiro = int(padrao)
        destino_log.info(
            "[AUTH_ENV] Integer env lida nome=%s bruto=%s interpretado=%s padrao=%s contexto=%s",
            nome,
            _valor_para_log(valor_bruto),
            valor_inteiro,
            int(padrao),
            _contexto_log(contexto),
        )
        return valor_inteiro

    try:
        valor_inteiro = int(str(valor_bruto).strip())
    except (TypeError, ValueError):
        valor_inteiro = int(padrao)
        destino_log.warning(
            "[AUTH_ENV] Integer env com valor invalido nome=%s bruto=%s interpretado=%s padrao=%s contexto=%s",
            nome,
            _valor_para_log(valor_bruto),
            valor_inteiro,
            int(padrao),
            _contexto_log(contexto),
        )
        return valor_inteiro

    destino_log.info(
        "[AUTH_ENV] Integer env lida nome=%s bruto=%s interpretado=%s padrao=%s contexto=%s",
        nome,
        _valor_para_log(valor_bruto),
        valor_inteiro,
        int(padrao),
        _contexto_log(contexto),
    )
    return valor_inteiro


def str_env(nome, padrao=None, logger=None, contexto=None, sensivel=False, strip=True):
    return get_env_str(
        nome,
        padrao=padrao,
        logger=logger,
        contexto=contexto,
        sensivel=sensivel,
        strip=strip,
    )


def bool_env(nome, padrao=False, logger=None, contexto=None):
    return get_env_bool(nome, padrao=padrao, logger=logger, contexto=contexto)


def int_env(nome, padrao=0, logger=None, contexto=None):
    return get_env_int(nome, padrao=padrao, logger=logger, contexto=contexto)
