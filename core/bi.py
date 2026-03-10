import csv
import io
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from core.banco import conectar


PAID_SUBSCRIPTION_STATUSES = {"ativa", "cancelada", "inadimplente"}
VALID_RETENTION_PERIODS = {"mensal", "trimestral"}

OBJECTIVE_MAP = {
    "performance": "desempenho",
    "desempenho": "desempenho",
    "completar prova": "desempenho",
    "perda de peso": "perda_peso",
    "perda_peso": "perda_peso",
    "emagrecimento": "perda_peso",
    "hipertrofia": "hipertrofia",
    "saude": "saude",
    "saude geral": "saude",
    "saude cardiovascular": "saude",
}

SEX_ALLOWED = {"masculino", "feminino", "outro"}


class BIValidationError(ValueError):
    pass


@dataclass(frozen=True)
class BIFilters:
    data_inicio: date | None = None
    data_fim: date | None = None
    sexo: str | None = None
    objetivo: str | None = None
    granularidade_retencao: str = "mensal"
    top_percentual_receita: float = 0.2
    incluir_vinculos_encerrados: bool = True

    @classmethod
    def from_dict(cls, dados: dict[str, Any] | None):
        dados = dados or {}
        granularidade = str(dados.get("granularidade_retencao", "mensal")).strip().lower()
        if granularidade not in VALID_RETENTION_PERIODS:
            raise BIValidationError("granularidade_retencao deve ser 'mensal' ou 'trimestral'.")

        top_percentual = float(dados.get("top_percentual_receita", 0.2))
        if top_percentual <= 0 or top_percentual > 1:
            raise BIValidationError("top_percentual_receita deve estar entre 0 e 1.")

        sexo = _normalizar_sexo(dados.get("sexo"))
        objetivo = _normalizar_objetivo(dados.get("objetivo"))
        data_inicio = _coagir_data(dados.get("data_inicio"))
        data_fim = _coagir_data(dados.get("data_fim"))
        if data_inicio and data_fim and data_inicio > data_fim:
            raise BIValidationError("data_inicio nao pode ser maior que data_fim.")

        return cls(
            data_inicio=data_inicio,
            data_fim=data_fim,
            sexo=sexo,
            objetivo=objetivo,
            granularidade_retencao=granularidade,
            top_percentual_receita=top_percentual,
            incluir_vinculos_encerrados=bool(dados.get("incluir_vinculos_encerrados", True)),
        )


def _coagir_data(valor: Any) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto[:19], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        return None


def _coagir_datetime(valor: Any) -> datetime | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    texto = str(valor).strip()
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(texto[:19], fmt)
            except ValueError:
                continue
    return None


def _normalizar_objetivo(objetivo: Any) -> str | None:
    if objetivo is None:
        return None
    valor = str(objetivo).strip().lower()
    if not valor:
        return None
    return OBJECTIVE_MAP.get(valor, valor)


def _normalizar_sexo(sexo: Any) -> str | None:
    if sexo is None:
        return None
    valor = str(sexo).strip().lower()
    if not valor:
        return None
    if valor in SEX_ALLOWED:
        return valor
    return "outro"


def _periodo_padrao(hoje: date | None = None) -> tuple[date, date]:
    hoje = hoje or date.today()
    primeiro_dia_mes = hoje.replace(day=1)
    data_inicio = (primeiro_dia_mes - timedelta(days=365)).replace(day=1)
    return data_inicio, hoje


def _primeiro_dia_trimestre(data_ref: date) -> date:
    inicio_mes = ((data_ref.month - 1) // 3) * 3 + 1
    return date(data_ref.year, inicio_mes, 1)


def _proximo_periodo(inicio: date, granularidade: str) -> date:
    if granularidade == "trimestral":
        mes = inicio.month + 3
    else:
        mes = inicio.month + 1
    ano = inicio.year + (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    return date(ano, mes, 1)


def _listar_periodos(data_inicio: date, data_fim: date, granularidade: str) -> list[dict[str, Any]]:
    if granularidade == "trimestral":
        cursor = _primeiro_dia_trimestre(data_inicio)
        chave_fmt = lambda dt: f"{dt.year}-Q{((dt.month - 1) // 3) + 1}"
        rotulo_fmt = chave_fmt
    else:
        cursor = data_inicio.replace(day=1)
        chave_fmt = lambda dt: f"{dt.year:04d}-{dt.month:02d}"
        rotulo_fmt = chave_fmt

    periodos = []
    while cursor <= data_fim:
        proximo = _proximo_periodo(cursor, granularidade)
        fim_periodo = min(proximo - timedelta(days=1), data_fim)
        periodos.append(
            {
                "chave": chave_fmt(cursor),
                "rotulo": rotulo_fmt(cursor),
                "inicio": cursor,
                "fim": fim_periodo,
            }
        )
        cursor = proximo
    return periodos


def _datetime_no_periodo(data_ref: datetime, periodo: dict[str, Any]) -> bool:
    return periodo["inicio"] <= data_ref.date() <= periodo["fim"]


class TrainerBIService:
    """
    Servico de BI para a area administrativa do treinador.

    Metricas principais:
    - Retencao de alunos (global, segmentada e tendencia temporal)
    - Receitas (mensal, anual, por segmento sexo+objetivo)
    - KPIs de negocio (aquisicao, churn, RMA, LTV, frequencia, conclusao, concentracao e demanda)
    """

    def __init__(self, conn_factory=conectar, cache_ttl_seconds: int = 120, param_placeholder: str = "%s"):
        self._conn_factory = conn_factory
        self._cache_ttl = max(0, int(cache_ttl_seconds))
        self._param_placeholder = param_placeholder
        self._cache: dict[str, tuple[datetime, Any]] = {}

    def get_dashboard_data(self, treinador_id: int, filtros: BIFilters | dict[str, Any] | None = None) -> dict[str, Any]:
        filtros_resolvidos = filtros if isinstance(filtros, BIFilters) else BIFilters.from_dict(filtros)
        cache_key = self._cache_key("dashboard", treinador_id, filtros_resolvidos)
        cache_hit = self._cache_get(cache_key)
        if cache_hit is not None:
            return cache_hit

        escopo = self._carregar_escopo(treinador_id, filtros_resolvidos)
        payload = {
            "filtros_aplicados": self._serializar_filtros(filtros_resolvidos, escopo["data_inicio"], escopo["data_fim"]),
            "retencao": self._calcular_retencao(escopo, filtros_resolvidos),
            "financeiro": self._calcular_financeiro(escopo, filtros_resolvidos),
            "kpis": self._calcular_kpis(escopo, filtros_resolvidos),
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
        }
        self._cache_set(cache_key, payload)
        return payload

    def get_retention_analysis(self, treinador_id: int, filtros: BIFilters | dict[str, Any] | None = None) -> dict[str, Any]:
        filtros_resolvidos = filtros if isinstance(filtros, BIFilters) else BIFilters.from_dict(filtros)
        escopo = self._carregar_escopo(treinador_id, filtros_resolvidos)
        return self._calcular_retencao(escopo, filtros_resolvidos)

    def get_financial_report(self, treinador_id: int, filtros: BIFilters | dict[str, Any] | None = None) -> dict[str, Any]:
        filtros_resolvidos = filtros if isinstance(filtros, BIFilters) else BIFilters.from_dict(filtros)
        escopo = self._carregar_escopo(treinador_id, filtros_resolvidos)
        return self._calcular_financeiro(escopo, filtros_resolvidos)

    def get_additional_kpis(self, treinador_id: int, filtros: BIFilters | dict[str, Any] | None = None) -> dict[str, Any]:
        filtros_resolvidos = filtros if isinstance(filtros, BIFilters) else BIFilters.from_dict(filtros)
        escopo = self._carregar_escopo(treinador_id, filtros_resolvidos)
        return self._calcular_kpis(escopo, filtros_resolvidos)

    def get_student_engagement_report(
        self,
        treinador_id: int,
        filtros: BIFilters | dict[str, Any] | None = None,
        referencia: date | None = None,
    ) -> dict[str, Any]:
        filtros_resolvidos = filtros if isinstance(filtros, BIFilters) else BIFilters.from_dict(filtros)
        escopo = self._carregar_escopo(treinador_id, filtros_resolvidos)
        return self._calcular_engajamento_alunos(escopo, referencia=referencia)

    def export_dashboard_json(self, treinador_id: int, filtros: BIFilters | dict[str, Any] | None = None) -> str:
        dados = self.get_dashboard_data(treinador_id, filtros=filtros)
        return json.dumps(dados, ensure_ascii=False, indent=2)

    @staticmethod
    def export_rows_to_csv(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        campos = sorted({campo for row in rows for campo in row.keys()})
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=campos)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buffer.getvalue()

    def _cache_key(self, nome: str, treinador_id: int, filtros: BIFilters) -> str:
        payload = {
            "nome": nome,
            "treinador_id": int(treinador_id),
            "filtros": {
                "data_inicio": filtros.data_inicio.isoformat() if filtros.data_inicio else None,
                "data_fim": filtros.data_fim.isoformat() if filtros.data_fim else None,
                "sexo": filtros.sexo,
                "objetivo": filtros.objetivo,
                "granularidade_retencao": filtros.granularidade_retencao,
                "top_percentual_receita": filtros.top_percentual_receita,
                "incluir_vinculos_encerrados": filtros.incluir_vinculos_encerrados,
            },
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _cache_get(self, key: str):
        if self._cache_ttl <= 0:
            return None
        registro = self._cache.get(key)
        if not registro:
            return None
        expira_em, valor = registro
        if expira_em < datetime.now():
            self._cache.pop(key, None)
            return None
        return valor

    def _cache_set(self, key: str, valor: Any):
        if self._cache_ttl <= 0:
            return
        self._cache[key] = (datetime.now() + timedelta(seconds=self._cache_ttl), valor)

    def _placeholder_list(self, total: int) -> str:
        return ",".join(self._param_placeholder for _ in range(total))

    def _carregar_escopo(self, treinador_id: int, filtros: BIFilters) -> dict[str, Any]:
        if int(treinador_id) <= 0:
            raise BIValidationError("treinador_id invalido.")

        data_inicio, data_fim = filtros.data_inicio, filtros.data_fim
        if not data_inicio or not data_fim:
            inicio_padrao, fim_padrao = _periodo_padrao()
            data_inicio = data_inicio or inicio_padrao
            data_fim = data_fim or fim_padrao

        atletas = self._buscar_atletas_treinador(int(treinador_id), filtros)
        atleta_ids = [row["atleta_id"] for row in atletas]

        treinos_realizados = self._buscar_treinos_realizados(atleta_ids, data_inicio, data_fim)
        treinos_gerados = self._buscar_treinos_gerados(atleta_ids, data_inicio, data_fim)
        assinaturas = self._buscar_assinaturas(atleta_ids, data_inicio, data_fim)
        return {
            "treinador_id": int(treinador_id),
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "atletas": atletas,
            "atleta_ids": atleta_ids,
            "treinos_realizados": treinos_realizados,
            "treinos_gerados": treinos_gerados,
            "assinaturas": assinaturas,
        }

    def _buscar_atletas_treinador(self, treinador_id: int, filtros: BIFilters) -> list[dict[str, Any]]:
        conn = self._conn_factory()
        cursor = conn.cursor()
        status_sql = "('ativo', 'encerrado')" if filtros.incluir_vinculos_encerrados else "('ativo')"
        cursor.execute(
            f"""
            SELECT ta.atleta_id,
                   ta.status AS vinculo_status,
                   ta.created_at AS vinculo_created_at,
                   u.nome,
                   u.apelido,
                   u.email,
                   u.sexo,
                   u.objetivo,
                   u.data_criacao
            FROM treinador_atleta ta
            JOIN usuarios u ON u.id = ta.atleta_id
            WHERE ta.treinador_id = {self._param_placeholder}
              AND ta.status IN {status_sql}
              AND u.tipo_usuario = 'atleta'
            """,
            (treinador_id,),
        )
        linhas = [dict(item) for item in cursor.fetchall()]
        conn.close()

        filtradas = []
        for linha in linhas:
            sexo = _normalizar_sexo(linha.get("sexo"))
            objetivo = _normalizar_objetivo(linha.get("objetivo")) or "outros"
            if filtros.sexo and sexo != filtros.sexo:
                continue
            if filtros.objetivo and objetivo != filtros.objetivo:
                continue
            linha["sexo"] = sexo or "outro"
            linha["objetivo"] = objetivo
            filtradas.append(linha)
        return filtradas

    def _buscar_treinos_realizados(
        self,
        atleta_ids: list[int],
        data_inicio: date,
        data_fim: date,
    ) -> list[dict[str, Any]]:
        if not atleta_ids:
            return []
        conn = self._conn_factory()
        cursor = conn.cursor()
        placeholders = self._placeholder_list(len(atleta_ids))
        cursor.execute(
            f"""
            SELECT COALESCE(atleta_id, usuario_id) AS atleta_id,
                   semana_numero,
                   nome_treino,
                   COALESCE(feito, concluido, 0) AS feito,
                   COALESCE(CAST(feito_em AS TEXT), CAST(data_realizada AS TEXT)) AS realizado_em,
                   feedback_tipo,
                   feedback_contexto_ruim,
                   exercicio_substituir,
                   motivo_exercicio_ruim
            FROM treinos_realizados
            WHERE COALESCE(atleta_id, usuario_id) IN ({placeholders})
            """,
            atleta_ids,
        )
        linhas = []
        for item in cursor.fetchall():
            linha = dict(item)
            dt = _coagir_datetime(linha.get("realizado_em"))
            if not dt:
                continue
            if not (data_inicio <= dt.date() <= data_fim):
                continue
            linha["realizado_em_dt"] = dt
            linha["feito"] = int(linha.get("feito") or 0)
            linhas.append(linha)
        conn.close()
        return linhas

    def _buscar_treinos_gerados(
        self,
        atleta_ids: list[int],
        data_inicio: date,
        data_fim: date,
    ) -> list[dict[str, Any]]:
        if not atleta_ids:
            return []
        conn = self._conn_factory()
        cursor = conn.cursor()
        placeholders = self._placeholder_list(len(atleta_ids))
        cursor.execute(
            f"""
            SELECT COALESCE(atleta_id, usuario_id) AS atleta_id,
                   semana_numero,
                   fase,
                   json_treino,
                   COALESCE(criado_em, created_at) AS criado_em
            FROM treinos_gerados
            WHERE COALESCE(atleta_id, usuario_id) IN ({placeholders})
            """,
            atleta_ids,
        )
        linhas = []
        for item in cursor.fetchall():
            linha = dict(item)
            dt = _coagir_datetime(linha.get("criado_em"))
            if not dt:
                continue
            if not (data_inicio <= dt.date() <= data_fim):
                continue
            linha["criado_em_dt"] = dt
            linha["qtde_treinos_planejados"] = _contar_treinos_planejados(linha.get("json_treino"))
            linhas.append(linha)
        conn.close()
        return linhas

    def _buscar_assinaturas(
        self,
        atleta_ids: list[int],
        data_inicio: date,
        data_fim: date,
    ) -> list[dict[str, Any]]:
        if not atleta_ids:
            return []
        conn = self._conn_factory()
        cursor = conn.cursor()
        placeholders = self._placeholder_list(len(atleta_ids))
        cursor.execute(
            f"""
            SELECT a.usuario_id AS atleta_id,
                   a.status,
                   a.data_inicio,
                   a.data_fim,
                   a.criado_em,
                   p.preco_mensal
            FROM assinaturas a
            JOIN planos p ON p.id = a.plano_id
            WHERE a.usuario_id IN ({placeholders})
              AND p.tipo = 'atleta'
            """,
            atleta_ids,
        )
        linhas = []
        for item in cursor.fetchall():
            linha = dict(item)
            dt = _coagir_datetime(linha.get("data_inicio")) or _coagir_datetime(linha.get("criado_em"))
            if not dt:
                continue
            if not (data_inicio <= dt.date() <= data_fim):
                continue
            linha["evento_dt"] = dt
            linha["receita"] = float(linha.get("preco_mensal") or 0) if linha.get("status") in PAID_SUBSCRIPTION_STATUSES else 0.0
            linhas.append(linha)
        conn.close()
        return linhas

    def _serializar_filtros(self, filtros: BIFilters, data_inicio: date, data_fim: date) -> dict[str, Any]:
        return {
            "data_inicio": data_inicio.isoformat(),
            "data_fim": data_fim.isoformat(),
            "sexo": filtros.sexo,
            "objetivo": filtros.objetivo,
            "granularidade_retencao": filtros.granularidade_retencao,
            "top_percentual_receita": filtros.top_percentual_receita,
            "incluir_vinculos_encerrados": filtros.incluir_vinculos_encerrados,
        }

    def _calcular_retencao(self, escopo: dict[str, Any], filtros: BIFilters) -> dict[str, Any]:
        periodos = _listar_periodos(escopo["data_inicio"], escopo["data_fim"], filtros.granularidade_retencao)
        atletas = escopo["atletas"]
        workouts_done = [item for item in escopo["treinos_realizados"] if item["feito"] == 1]
        ativos_periodo = {periodo["chave"]: set() for periodo in periodos}

        for evento in workouts_done:
            atleta_id = int(evento["atleta_id"])
            dt = evento["realizado_em_dt"]
            for periodo in periodos:
                if _datetime_no_periodo(dt, periodo):
                    ativos_periodo[periodo["chave"]].add(atleta_id)
                    break

        tendencia = []
        taxas_validas = []
        for indice, periodo in enumerate(periodos):
            atual = ativos_periodo[periodo["chave"]]
            anteriores = ativos_periodo[periodos[indice - 1]["chave"]] if indice > 0 else set()
            retidos = len(anteriores.intersection(atual))
            taxa = (retidos / len(anteriores)) if anteriores else None
            if taxa is not None:
                taxas_validas.append(taxa)
            tendencia.append(
                {
                    "periodo": periodo["rotulo"],
                    "ativos": len(atual),
                    "retidos": retidos,
                    "base_periodo_anterior": len(anteriores),
                    "taxa_retencao": round(taxa * 100, 2) if taxa is not None else None,
                }
            )

        media_global = round((sum(taxas_validas) / len(taxas_validas)) * 100, 2) if taxas_validas else 0.0
        por_sexo = self._retencao_por_segmento(atletas, periodos, ativos_periodo, chave_segmento="sexo")
        por_objetivo = self._retencao_por_segmento(atletas, periodos, ativos_periodo, chave_segmento="objetivo")

        return {
            "taxa_media_retencao_percentual": media_global,
            "segmentacao_por_sexo": por_sexo,
            "segmentacao_por_objetivo": por_objetivo,
            "tendencia": tendencia,
            "metodologia": (
                "Retencao por periodo = atletas com treino concluido no periodo anterior "
                "que tambem concluirem treino no periodo atual."
            ),
        }

    def _retencao_por_segmento(
        self,
        atletas: list[dict[str, Any]],
        periodos: list[dict[str, Any]],
        ativos_periodo: dict[str, set[int]],
        chave_segmento: str,
    ) -> list[dict[str, Any]]:
        ids_por_segmento: dict[str, set[int]] = {}
        for atleta in atletas:
            segmento = str(atleta.get(chave_segmento) or "outros")
            ids_por_segmento.setdefault(segmento, set()).add(int(atleta["atleta_id"]))

        saida = []
        for segmento, ids_segmento in sorted(ids_por_segmento.items()):
            taxas = []
            for indice in range(1, len(periodos)):
                atual = ativos_periodo[periodos[indice]["chave"]].intersection(ids_segmento)
                anterior = ativos_periodo[periodos[indice - 1]["chave"]].intersection(ids_segmento)
                if not anterior:
                    continue
                taxas.append(len(atual.intersection(anterior)) / len(anterior))
            media = round((sum(taxas) / len(taxas)) * 100, 2) if taxas else 0.0
            saida.append(
                {
                    "segmento": segmento,
                    "total_alunos_segmento": len(ids_segmento),
                    "taxa_media_retencao_percentual": media,
                }
            )
        return saida

    def _calcular_financeiro(self, escopo: dict[str, Any], filtros: BIFilters) -> dict[str, Any]:
        periodos_mensais = _listar_periodos(escopo["data_inicio"], escopo["data_fim"], "mensal")
        atletas = {int(item["atleta_id"]): item for item in escopo["atletas"]}
        assinaturas = escopo["assinaturas"]

        historico_mensal = []
        for periodo in periodos_mensais:
            eventos = [
                ev for ev in assinaturas
                if _datetime_no_periodo(ev["evento_dt"], periodo)
            ]
            receita_total = round(sum(ev["receita"] for ev in eventos), 2)
            historico_mensal.append(
                {
                    "periodo": periodo["rotulo"],
                    "receita_total": receita_total,
                    "numero_transacoes": len(eventos),
                }
            )

        anual: dict[int, dict[str, Any]] = {}
        for ev in assinaturas:
            ano = ev["evento_dt"].year
            anual.setdefault(ano, {"ano": ano, "receita_total": 0.0, "numero_transacoes": 0})
            anual[ano]["receita_total"] += ev["receita"]
            anual[ano]["numero_transacoes"] += 1
        anual_ordenado = []
        for ano in sorted(anual):
            item = anual[ano]
            item["receita_total"] = round(item["receita_total"], 2)
            anual_ordenado.append(item)
        for i, item in enumerate(anual_ordenado):
            if i == 0:
                item["variacao_percentual_vs_ano_anterior"] = None
                continue
            anterior = anual_ordenado[i - 1]["receita_total"]
            if anterior <= 0:
                item["variacao_percentual_vs_ano_anterior"] = None
            else:
                item["variacao_percentual_vs_ano_anterior"] = round(((item["receita_total"] - anterior) / anterior) * 100, 2)

        por_segmento: dict[str, dict[str, Any]] = {}
        for ev in assinaturas:
            atleta = atletas.get(int(ev["atleta_id"]), {})
            sexo = atleta.get("sexo", "outro")
            objetivo = atleta.get("objetivo", "outros")
            segmento = f"{sexo}|{objetivo}"
            por_segmento.setdefault(segmento, {"segmento": segmento, "receita_total": 0.0, "numero_transacoes": 0})
            por_segmento[segmento]["receita_total"] += ev["receita"]
            por_segmento[segmento]["numero_transacoes"] += 1
        segmentos = sorted(por_segmento.values(), key=lambda row: row["receita_total"], reverse=True)
        for seg in segmentos:
            seg["receita_total"] = round(seg["receita_total"], 2)

        return {
            "historico_mensal": historico_mensal,
            "resumo_anual": anual_ordenado,
            "receita_por_segmento": segmentos,
            "receita_total_periodo": round(sum(ev["receita"] for ev in assinaturas), 2),
            "metodologia": (
                "Receita considera assinaturas de atletas vinculados com status financeiro "
                f"{sorted(PAID_SUBSCRIPTION_STATUSES)} no periodo."
            ),
        }

    def _calcular_kpis(self, escopo: dict[str, Any], filtros: BIFilters) -> dict[str, Any]:
        atletas = {int(item["atleta_id"]): item for item in escopo["atletas"]}
        treinos_done = [item for item in escopo["treinos_realizados"] if int(item.get("feito") or 0) == 1]
        treinos_gerados = escopo["treinos_gerados"]
        assinaturas = escopo["assinaturas"]
        periodos_mensais = _listar_periodos(escopo["data_inicio"], escopo["data_fim"], "mensal")

        aquisicao = self._kpi_aquisicao(atletas, periodos_mensais)
        churn = self._kpi_churn(atletas, treinos_done, periodos_mensais)
        receita_total = sum(item["receita"] for item in assinaturas)
        alunos_ativos = {int(item["atleta_id"]) for item in treinos_done} | {int(item["atleta_id"]) for item in assinaturas if item["receita"] > 0}
        rma = round(receita_total / len(alunos_ativos), 2) if alunos_ativos else 0.0

        planejado_total = sum(int(item.get("qtde_treinos_planejados") or 0) for item in treinos_gerados)
        feito_unicos = {
            (int(item["atleta_id"]), int(item["semana_numero"]), str(item["nome_treino"]))
            for item in treinos_done
        }
        conclusao_programa = round((len(feito_unicos) / planejado_total) * 100, 2) if planejado_total else 0.0
        frequencia_por_objetivo = self._kpi_frequencia_objetivo(atletas, treinos_done, treinos_gerados)
        concentracao_receita = self._kpi_concentracao_receita(assinaturas, filtros.top_percentual_receita)
        ltv = round((rma / churn["taxa_media_churn"]), 2) if churn["taxa_media_churn"] > 0 else None
        pico_demanda = self._kpi_picos_demanda(treinos_done)

        return {
            "taxa_aquisicao_alunos_mensal": aquisicao,
            "receita_media_por_aluno_rma": rma,
            "taxa_evasao": churn,
            "taxa_frequencia_por_objetivo": frequencia_por_objetivo,
            "concentracao_receita": concentracao_receita,
            "valor_medio_ciclo_vida_ltv_estimado": ltv,
            "taxa_conclusao_programa_percentual": conclusao_programa,
            "picos_demanda": pico_demanda,
            "metodologia": {
                "rma": "Receita total do periodo / alunos ativos no periodo.",
                "ltv": "RMA / taxa media de churn mensal (estimativa).",
                "frequencia": "Treinos concluidos / treinos planejados por objetivo.",
                "conclusao_programa": "Treinos concluidos unicos / total de treinos planejados.",
            },
        }

    def _calcular_engajamento_alunos(self, escopo: dict[str, Any], referencia: date | None = None) -> dict[str, Any]:
        referencia = referencia or date.today()
        inicio_semana = referencia - timedelta(days=referencia.weekday())
        inicio_mes = referencia.replace(day=1)
        inicio_ano = date(referencia.year, 1, 1)

        atletas = {int(item["atleta_id"]): item for item in escopo["atletas"]}
        treinos_done = [item for item in escopo["treinos_realizados"] if int(item.get("feito") or 0) == 1]

        por_atleta: dict[int, dict[str, Any]] = {}
        for atleta_id, atleta in atletas.items():
            nome_exibicao = atleta.get("apelido") or atleta.get("nome") or f"Atleta {atleta_id}"
            por_atleta[atleta_id] = {
                "atleta_id": atleta_id,
                "nome": nome_exibicao,
                "email": atleta.get("email"),
                "status_vinculo": atleta.get("vinculo_status"),
                "treinos_semana": 0,
                "treinos_mes": 0,
                "treinos_ano": 0,
                "total_treinos_periodo": 0,
                "meses_ativos_periodo": 0,
                "ultima_atividade": None,
                "dias_desde_ultima_atividade": None,
            }

        meses_ativos_por_atleta: dict[int, set[str]] = {atleta_id: set() for atleta_id in atletas}
        for treino in treinos_done:
            atleta_id = int(treino["atleta_id"])
            if atleta_id not in por_atleta:
                continue
            dt = treino["realizado_em_dt"]
            item = por_atleta[atleta_id]
            item["total_treinos_periodo"] += 1
            meses_ativos_por_atleta[atleta_id].add(f"{dt.year:04d}-{dt.month:02d}")
            if dt.date() >= inicio_ano:
                item["treinos_ano"] += 1
            if dt.date() >= inicio_mes:
                item["treinos_mes"] += 1
            if dt.date() >= inicio_semana:
                item["treinos_semana"] += 1
            if item["ultima_atividade"] is None or dt > item["ultima_atividade"]:
                item["ultima_atividade"] = dt

        linhas = []
        for atleta_id, item in por_atleta.items():
            item["meses_ativos_periodo"] = len(meses_ativos_por_atleta[atleta_id])
            ultima = item["ultima_atividade"]
            if ultima:
                item["dias_desde_ultima_atividade"] = (referencia - ultima.date()).days
                item["ultima_atividade"] = ultima.isoformat(timespec="seconds")
            linhas.append(item)

        linhas.sort(
            key=lambda row: (
                -(row["treinos_mes"] or 0),
                -(row["treinos_semana"] or 0),
                row["nome"].lower(),
            )
        )

        total_alunos = len(linhas)
        ativos_semana = sum(1 for row in linhas if row["treinos_semana"] > 0)
        ativos_mes = sum(1 for row in linhas if row["treinos_mes"] > 0)
        ativos_ano = sum(1 for row in linhas if row["treinos_ano"] > 0)

        return {
            "referencia": referencia.isoformat(),
            "resumo": {
                "total_alunos": total_alunos,
                "alunos_ativos_semana": ativos_semana,
                "alunos_ativos_mes": ativos_mes,
                "alunos_ativos_ano": ativos_ano,
                "media_treinos_semana": round(sum(row["treinos_semana"] for row in linhas) / total_alunos, 2) if total_alunos else 0.0,
                "media_treinos_mes": round(sum(row["treinos_mes"] for row in linhas) / total_alunos, 2) if total_alunos else 0.0,
                "media_treinos_ano": round(sum(row["treinos_ano"] for row in linhas) / total_alunos, 2) if total_alunos else 0.0,
                "media_meses_ativos_periodo": round(
                    sum(row["meses_ativos_periodo"] for row in linhas) / total_alunos, 2
                ) if total_alunos else 0.0,
            },
            "alunos": linhas,
        }

    def _kpi_aquisicao(self, atletas: dict[int, dict[str, Any]], periodos_mensais: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resultado = []
        for periodo in periodos_mensais:
            ids = []
            for atleta_id, atleta in atletas.items():
                dt = _coagir_datetime(atleta.get("vinculo_created_at"))
                if dt and _datetime_no_periodo(dt, periodo):
                    ids.append(atleta_id)
            resultado.append(
                {
                    "periodo": periodo["rotulo"],
                    "novos_alunos": len(ids),
                }
            )
        return resultado

    def _kpi_churn(
        self,
        atletas: dict[int, dict[str, Any]],
        treinos_done: list[dict[str, Any]],
        periodos_mensais: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ativos_por_periodo = {p["chave"]: set() for p in periodos_mensais}
        motivos_por_atleta = {}
        for item in treinos_done:
            atleta_id = int(item["atleta_id"])
            dt = item["realizado_em_dt"]
            for periodo in periodos_mensais:
                if _datetime_no_periodo(dt, periodo):
                    ativos_por_periodo[periodo["chave"]].add(atleta_id)
                    break
            if item.get("feedback_tipo") == "muito ruim" and item.get("motivo_exercicio_ruim"):
                atual = motivos_por_atleta.get(atleta_id)
                if not atual or dt > atual["dt"]:
                    motivos_por_atleta[atleta_id] = {"dt": dt, "motivo": item["motivo_exercicio_ruim"]}

        linha_churn = []
        total_prev = 0
        total_churned = 0
        contagem_motivos: dict[str, int] = {}

        for i in range(1, len(periodos_mensais)):
            anterior = ativos_por_periodo[periodos_mensais[i - 1]["chave"]]
            atual = ativos_por_periodo[periodos_mensais[i]["chave"]]
            churned = anterior - atual
            taxa = (len(churned) / len(anterior)) if anterior else 0.0
            linha_churn.append(
                {
                    "periodo": periodos_mensais[i]["rotulo"],
                    "base_anterior": len(anterior),
                    "alunos_evadidos": len(churned),
                    "taxa_churn": round(taxa, 4),
                }
            )
            total_prev += len(anterior)
            total_churned += len(churned)
            for atleta_id in churned:
                motivo = motivos_por_atleta.get(atleta_id, {}).get("motivo") or "sem_motivo_reportado"
                contagem_motivos[motivo] = contagem_motivos.get(motivo, 0) + 1

        taxa_media = (total_churned / total_prev) if total_prev else 0.0
        motivos = [
            {"motivo": motivo, "quantidade": qtd}
            for motivo, qtd in sorted(contagem_motivos.items(), key=lambda item: item[1], reverse=True)
        ]
        return {
            "serie_mensal": linha_churn,
            "taxa_media_churn": round(taxa_media, 4),
            "motivos_evasao": motivos,
        }

    def _kpi_frequencia_objetivo(
        self,
        atletas: dict[int, dict[str, Any]],
        treinos_done: list[dict[str, Any]],
        treinos_gerados: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        feito_por_objetivo: dict[str, int] = {}
        planejado_por_objetivo: dict[str, int] = {}

        for item in treinos_done:
            objetivo = atletas.get(int(item["atleta_id"]), {}).get("objetivo", "outros")
            feito_por_objetivo[objetivo] = feito_por_objetivo.get(objetivo, 0) + 1

        for item in treinos_gerados:
            objetivo = atletas.get(int(item["atleta_id"]), {}).get("objetivo", "outros")
            planejado_por_objetivo[objetivo] = planejado_por_objetivo.get(objetivo, 0) + int(item.get("qtde_treinos_planejados") or 0)

        objetivos = sorted(set(feito_por_objetivo.keys()) | set(planejado_por_objetivo.keys()))
        saida = []
        for objetivo in objetivos:
            feitos = feito_por_objetivo.get(objetivo, 0)
            planejados = planejado_por_objetivo.get(objetivo, 0)
            taxa = round((feitos / planejados) * 100, 2) if planejados else 0.0
            saida.append(
                {
                    "objetivo": objetivo,
                    "treinos_planejados": planejados,
                    "treinos_concluidos": feitos,
                    "taxa_frequencia_percentual": taxa,
                }
            )
        return saida

    def _kpi_concentracao_receita(self, assinaturas: list[dict[str, Any]], top_percentual: float) -> dict[str, Any]:
        receita_por_atleta: dict[int, float] = {}
        for item in assinaturas:
            atleta_id = int(item["atleta_id"])
            receita_por_atleta[atleta_id] = receita_por_atleta.get(atleta_id, 0.0) + float(item["receita"] or 0.0)

        if not receita_por_atleta:
            return {
                "top_percentual": top_percentual,
                "participacao_receita_top_percentual": 0.0,
                "total_alunos_com_receita": 0,
            }

        valores = sorted(receita_por_atleta.values(), reverse=True)
        top_n = max(1, int(math.ceil(len(valores) * top_percentual)))
        total = sum(valores)
        top = sum(valores[:top_n])
        participacao = round((top / total) * 100, 2) if total > 0 else 0.0
        return {
            "top_percentual": top_percentual,
            "participacao_receita_top_percentual": participacao,
            "total_alunos_com_receita": len(valores),
            "top_n_alunos": top_n,
        }

    def _kpi_picos_demanda(self, treinos_done: list[dict[str, Any]]) -> dict[str, Any]:
        por_mes: dict[str, int] = {}
        por_trimestre: dict[str, int] = {}
        por_dia_semana: dict[str, int] = {}
        dias = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

        for item in treinos_done:
            dt = item["realizado_em_dt"]
            mes = f"{dt.year:04d}-{dt.month:02d}"
            tri = f"{dt.year}-Q{((dt.month - 1) // 3) + 1}"
            dia = dias[dt.weekday()]
            por_mes[mes] = por_mes.get(mes, 0) + 1
            por_trimestre[tri] = por_trimestre.get(tri, 0) + 1
            por_dia_semana[dia] = por_dia_semana.get(dia, 0) + 1

        top_mes = max(por_mes.items(), key=lambda item: item[1])[0] if por_mes else None
        top_trimestre = max(por_trimestre.items(), key=lambda item: item[1])[0] if por_trimestre else None
        top_dia_semana = max(por_dia_semana.items(), key=lambda item: item[1])[0] if por_dia_semana else None
        return {
            "volume_por_mes": [{"periodo": k, "sessoes_concluidas": v} for k, v in sorted(por_mes.items())],
            "volume_por_trimestre": [{"periodo": k, "sessoes_concluidas": v} for k, v in sorted(por_trimestre.items())],
            "volume_por_dia_semana": [{"dia": k, "sessoes_concluidas": v} for k, v in sorted(por_dia_semana.items())],
            "mes_pico": top_mes,
            "trimestre_pico": top_trimestre,
            "dia_semana_pico": top_dia_semana,
        }


def _contar_treinos_planejados(json_treino: Any) -> int:
    if not json_treino:
        return 0
    dados = json_treino
    if isinstance(json_treino, str):
        try:
            dados = json.loads(json_treino)
        except json.JSONDecodeError:
            return 0
    if isinstance(dados, dict):
        return len(dados)
    return 0


def construir_dashboard_bi_treinador(
    treinador_id: int,
    filtros: dict[str, Any] | None = None,
    cache_ttl_seconds: int = 120,
) -> dict[str, Any]:
    """
    Funcao de alto nivel para ser chamada pela area do treinador.
    """
    service = TrainerBIService(cache_ttl_seconds=cache_ttl_seconds)
    return service.get_dashboard_data(treinador_id, filtros)


def demo_bi_em_memoria() -> dict[str, Any]:
    """
    Exemplo auto contido com dados de teste para validar o motor de BI.
    Nao altera o banco real da aplicacao.
    """
    uri = "file:bi_demo_mem?mode=memory&cache=shared"
    keeper = sqlite3.connect(uri, uri=True)
    keeper.row_factory = sqlite3.Row
    cur = keeper.cursor()

    cur.executescript(
        """
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            nome TEXT,
            apelido TEXT,
            email TEXT,
            sexo TEXT,
            objetivo TEXT,
            tipo_usuario TEXT,
            data_criacao TEXT
        );
        CREATE TABLE treinador_atleta (
            id INTEGER PRIMARY KEY,
            treinador_id INTEGER,
            atleta_id INTEGER,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE treinos_realizados (
            id INTEGER PRIMARY KEY,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER,
            nome_treino TEXT,
            feito INTEGER,
            concluido INTEGER,
            feito_em TEXT,
            data_realizada TEXT,
            feedback_tipo TEXT,
            feedback_contexto_ruim TEXT,
            exercicio_substituir TEXT,
            motivo_exercicio_ruim TEXT
        );
        CREATE TABLE planos (
            id INTEGER PRIMARY KEY,
            codigo TEXT,
            nome TEXT,
            tipo TEXT,
            preco_mensal REAL
        );
        CREATE TABLE assinaturas (
            id INTEGER PRIMARY KEY,
            usuario_id INTEGER,
            plano_id INTEGER,
            status TEXT,
            data_inicio TEXT,
            data_fim TEXT,
            criado_em TEXT
        );
        CREATE TABLE treinos_gerados (
            id INTEGER PRIMARY KEY,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER,
            fase TEXT,
            json_treino TEXT,
            criado_em TEXT,
            created_at TEXT
        );
        """
    )

    cur.executemany(
        "INSERT INTO usuarios (id, nome, apelido, email, sexo, objetivo, tipo_usuario, data_criacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "Treinador", None, "treinador@demo.com", "masculino", "desempenho", "treinador", "2025-01-05T09:00:00"),
            (101, "Ana", "Aninha", "ana@demo.com", "feminino", "hipertrofia", "atleta", "2025-01-10T09:00:00"),
            (102, "Bruno", None, "bruno@demo.com", "masculino", "performance", "atleta", "2025-01-15T09:00:00"),
            (103, "Carla", None, "carla@demo.com", "feminino", "perda de peso", "atleta", "2025-02-10T09:00:00"),
        ],
    )
    cur.executemany(
        "INSERT INTO treinador_atleta (treinador_id, atleta_id, status, created_at) VALUES (?, ?, ?, ?)",
        [
            (1, 101, "ativo", "2025-01-12T10:00:00"),
            (1, 102, "ativo", "2025-01-16T11:00:00"),
            (1, 103, "ativo", "2025-02-11T11:00:00"),
        ],
    )
    cur.executemany(
        "INSERT INTO planos (id, codigo, nome, tipo, preco_mensal) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "atleta_mensal", "Plano Atleta", "atleta", 49.90),
        ],
    )
    cur.executemany(
        "INSERT INTO assinaturas (usuario_id, plano_id, status, data_inicio, criado_em) VALUES (?, ?, ?, ?, ?)",
        [
            (101, 1, "ativa", "2025-02-01T08:00:00", "2025-02-01T08:00:00"),
            (102, 1, "ativa", "2025-02-05T08:00:00", "2025-02-05T08:00:00"),
            (103, 1, "trial", "2025-02-20T08:00:00", "2025-02-20T08:00:00"),
        ],
    )
    cur.executemany(
        """
        INSERT INTO treinos_gerados (atleta_id, usuario_id, semana_numero, fase, json_treino, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (101, 101, 1, "base", '{"A":[{}],"B":[{}]}', "2025-02-01T08:00:00"),
            (102, 102, 1, "base", '{"A":[{}],"B":[{}],"C":[{}]}', "2025-02-02T08:00:00"),
            (103, 103, 1, "base", '{"A":[{}]}', "2025-02-20T08:00:00"),
        ],
    )
    cur.executemany(
        """
        INSERT INTO treinos_realizados (
            atleta_id, usuario_id, semana_numero, nome_treino, feito, concluido, feito_em, data_realizada,
            feedback_tipo, motivo_exercicio_ruim
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (101, 101, 1, "Treino A", 1, 1, "2025-02-03T07:30:00", "2025-02-03T07:30:00", "muito bom", None),
            (102, 102, 1, "Treino A", 1, 1, "2025-02-04T07:30:00", "2025-02-04T07:30:00", "muito ruim", "dor em um exercicio"),
            (101, 101, 5, "Treino A", 1, 1, "2025-03-05T07:30:00", "2025-03-05T07:30:00", "muito bom", None),
        ],
    )
    keeper.commit()

    def demo_conn():
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    service = TrainerBIService(conn_factory=demo_conn, cache_ttl_seconds=0, param_placeholder="?")
    resultado = service.get_dashboard_data(
        treinador_id=1,
        filtros={
            "data_inicio": "2025-02-01",
            "data_fim": "2025-03-31",
            "granularidade_retencao": "mensal",
        },
    )
    keeper.close()
    return resultado
