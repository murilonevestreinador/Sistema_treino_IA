import os
import sqlite3
from pathlib import Path

import psycopg2


SQLITE_PATH = Path("dados") / "usuarios.db"

TABELAS = [
    {
        "nome": "usuarios",
        "colunas": [
            "id",
            "nome",
            "apelido",
            "foto_perfil",
            "email",
            "senha",
            "sexo",
            "tipo_usuario",
            "onboarding_completo",
            "is_admin",
            "idade",
            "peso",
            "altura",
            "objetivo",
            "distancia_principal",
            "tempo_pratica",
            "treinos_corrida_semana",
            "tem_prova",
            "data_prova",
            "distancia_prova",
            "treinos_musculacao_semana",
            "local_treino",
            "experiencia_musculacao",
            "historico_lesao",
            "dor_atual",
            "aceitou_termos",
            "aceitou_privacidade",
            "data_consentimento",
            "data_criacao",
        ],
        "conflito": "id",
    },
    {
        "nome": "treinador_atleta",
        "colunas": ["id", "treinador_id", "atleta_id", "status", "created_at"],
        "conflito": "id",
    },
    {
        "nome": "convites_treinador_link",
        "colunas": ["id", "treinador_id", "token", "ativo", "created_at"],
        "conflito": "id",
    },
    {
        "nome": "treinos_gerados",
        "colunas": [
            "id",
            "atleta_id",
            "usuario_id",
            "semana_numero",
            "fase",
            "json_treino",
            "editado_por_treinador",
            "criado_em",
            "created_at",
        ],
        "conflito": "id",
    },
    {
        "nome": "treinos_realizados",
        "colunas": [
            "id",
            "atleta_id",
            "usuario_id",
            "semana_numero",
            "nome_treino",
            "feito",
            "concluido",
            "feito_em",
            "data_realizada",
            "feedback_tipo",
            "feedback_contexto_ruim",
            "exercicio_substituir",
            "motivo_exercicio_ruim",
            "observacao",
            "observacoes",
        ],
        "conflito": "id",
    },
    {
        "nome": "recuperacao_senha",
        "colunas": ["id", "usuario_id", "codigo_hash", "expira_em", "usado_em", "created_at"],
        "conflito": "id",
    },
    {
        "nome": "preferencias_substituicao_exercicio",
        "colunas": ["id", "atleta_id", "exercicio_nome", "categoria", "principal_musculo", "motivo", "created_at"],
        "conflito": "id",
    },
    {
        "nome": "planos",
        "colunas": ["id", "codigo", "nome", "tipo", "preco_mensal", "limite_atletas", "ativo"],
        "conflito": "id",
    },
    {
        "nome": "assinaturas",
        "colunas": [
            "id",
            "usuario_id",
            "plano_id",
            "status",
            "data_inicio",
            "data_fim",
            "renovacao_automatica",
            "gateway",
            "gateway_reference",
            "criado_em",
        ],
        "conflito": "id",
    },
]


def _assert_database_url():
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL nao configurada.")
    return database_url


def _colunas_sqlite(conn_sqlite, tabela):
    cursor = conn_sqlite.cursor()
    cursor.execute(f"PRAGMA table_info({tabela})")
    return {linha[1] for linha in cursor.fetchall()}


def _ler_linhas_sqlite(conn_sqlite, tabela, colunas):
    cursor = conn_sqlite.cursor()
    colunas_sql = ", ".join(colunas)
    cursor.execute(f"SELECT {colunas_sql} FROM {tabela}")
    return cursor.fetchall()


def _montar_insert_postgres(tabela, colunas, conflito):
    colunas_sql = ", ".join(colunas)
    placeholders = ", ".join(["%s"] * len(colunas))
    return (
        f"INSERT INTO {tabela} ({colunas_sql}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT ({conflito}) DO NOTHING"
    )


def _ajustar_sequence_id(cursor_pg, tabela):
    cursor_pg.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{tabela}', 'id'),
            COALESCE((SELECT MAX(id) FROM {tabela}), 1),
            true
        )
        """
    )


def migrar():
    if not SQLITE_PATH.exists():
        print(f"SQLite nao encontrado em: {SQLITE_PATH}")
        print("Nada para migrar.")
        return

    database_url = _assert_database_url()

    conn_sqlite = sqlite3.connect(SQLITE_PATH)
    conn_pg = psycopg2.connect(database_url)

    try:
        cursor_pg = conn_pg.cursor()

        for config in TABELAS:
            tabela = config["nome"]
            colunas_desejadas = config["colunas"]
            conflito = config["conflito"]

            colunas_existentes = _colunas_sqlite(conn_sqlite, tabela)
            colunas = [c for c in colunas_desejadas if c in colunas_existentes]
            if not colunas:
                print(f"[SKIP] {tabela}: tabela ausente ou sem colunas compativeis no SQLite.")
                continue

            linhas = _ler_linhas_sqlite(conn_sqlite, tabela, colunas)
            if not linhas:
                print(f"[OK] {tabela}: sem dados para migrar.")
                continue

            sql_insert = _montar_insert_postgres(tabela, colunas, conflito)
            cursor_pg.executemany(sql_insert, linhas)
            print(f"[OK] {tabela}: {len(linhas)} linha(s) processada(s).")

        for config in TABELAS:
            _ajustar_sequence_id(cursor_pg, config["nome"])

        conn_pg.commit()
        print("Migracao concluida com sucesso.")
    except Exception:
        conn_pg.rollback()
        raise
    finally:
        conn_sqlite.close()
        conn_pg.close()


if __name__ == "__main__":
    migrar()
