from pathlib import Path
import unicodedata

import pandas as pd

from core.equipamentos import parsear_equipamentos_exercicio


PASTA_DADOS = Path("dados")
NOME_PLANILHA_PADRAO = "Planilha exercícios e infos.xlsx"


def _normalizar_texto(valor):
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return texto.strip().lower().replace(" ", "_")


def _normalizar_colunas(df):
    df = df.copy()
    df.columns = [_normalizar_texto(coluna) for coluna in df.columns]
    return df


def _resolver_caminho_excel(caminho_excel):
    if caminho_excel:
        return Path(caminho_excel)

    caminho_padrao = PASTA_DADOS / NOME_PLANILHA_PADRAO
    if caminho_padrao.exists():
        return caminho_padrao

    candidatos = sorted(PASTA_DADOS.glob("Planilha*infos.xlsx"))
    if candidatos:
        return candidatos[0]

    raise FileNotFoundError("Planilha de exercicios nao encontrada na pasta dados.")


def _valor_numerico(valor):
    if pd.isna(valor):
        return 0
    texto = str(valor).strip()
    try:
        return int(float(texto))
    except (TypeError, ValueError):
        return 0


def _valor_texto(valor):
    if pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def carregar_exercicios(caminho="dados/Planilha exercícios e infos.xlsx"):
    caminho_resolvido = _resolver_caminho_excel(caminho)
    df = pd.read_excel(caminho_resolvido)
    df = _normalizar_colunas(df)

    coluna_nome = "exercicio" if "exercicio" in df.columns else None
    if not coluna_nome:
        raise ValueError("A planilha precisa conter a coluna exercicio.")

    exercicios = []
    for _, row in df.iterrows():
        nome = row.get(coluna_nome)
        if pd.isna(nome):
            continue

        exercicios.append(
            {
                "nome": str(nome).strip(),
                "categoria": _normalizar_texto(row.get("categoria_funcional")),
                "principal_musculo": _normalizar_texto(row.get("principal_musculo")),
                "complexidade": _normalizar_texto(row.get("complexidade")),
                "equipamento": _normalizar_texto(row.get("equipamento_utilizado")),
                "equipamento_bruto": _valor_texto(row.get("equipamento_utilizado")),
                "equipamentos_necessarios": parsear_equipamentos_exercicio(row.get("equipamento_utilizado")),
                "impacto_joelho": _normalizar_texto(row.get("impacto_joelho")),
                "impacto_coluna": _normalizar_texto(row.get("impacto_coluna")),
                "impacto_ombro": _normalizar_texto(row.get("impacto_ombro")),
                "prioridade_base": _valor_numerico(row.get("prioridade_base")),
                "prioridade_especifico": _valor_numerico(row.get("prioridade_especifico")),
                "prioridade_polimento": _valor_numerico(row.get("prioridade_polimento")),
                "prioridade_retorno": _valor_numerico(row.get("prioridade_retorno")),
                "favorito": _normalizar_texto(row.get("favorito")) == "sim",
                "link_yt": _valor_texto(row.get("link_yt")),
            }
        )

    return exercicios
