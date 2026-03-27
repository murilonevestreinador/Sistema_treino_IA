from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


TIMEZONE_PADRAO = "America/Sao_Paulo"


def hoje_local():
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(TIMEZONE_PADRAO)).date()


def inicio_semana_local(referencia=None):
    dia = referencia or hoje_local()
    return dia - timedelta(days=dia.weekday())
