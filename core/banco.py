import sqlite3
from pathlib import Path


DB_PATH = Path("dados") / "usuarios.db"


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _colunas_tabela(cursor, tabela):
    cursor.execute(f"PRAGMA table_info({tabela})")
    return {linha["name"] for linha in cursor.fetchall()}


def _adicionar_coluna_se_necessario(cursor, tabela, nome_coluna, definicao):
    colunas = _colunas_tabela(cursor, tabela)
    if nome_coluna in colunas:
        return

    try:
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {definicao}")
    except sqlite3.OperationalError:
        # Em bancos antigos, alguns ALTERs podem falhar; seguimos com o que for possivel.
        pass


def _criar_tabela_usuarios(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            apelido TEXT,
            foto_perfil TEXT,
            email TEXT UNIQUE,
            senha TEXT,
            sexo TEXT,
            tipo_usuario TEXT DEFAULT 'atleta',
            onboarding_completo INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            idade INTEGER,
            peso REAL,
            altura REAL,
            objetivo TEXT,
            distancia_principal TEXT,
            tempo_pratica TEXT,
            treinos_corrida_semana INTEGER,
            tem_prova INTEGER DEFAULT 0,
            data_prova TEXT,
            distancia_prova TEXT,
            treinos_musculacao_semana INTEGER,
            local_treino TEXT,
            experiencia_musculacao TEXT,
            historico_lesao TEXT,
            dor_atual TEXT,
            aceitou_termos INTEGER DEFAULT 0,
            aceitou_privacidade INTEGER DEFAULT 0,
            data_consentimento TEXT,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    colunas = {
        "apelido": "TEXT",
        "foto_perfil": "TEXT",
        "tipo_usuario": "TEXT DEFAULT 'atleta'",
        "onboarding_completo": "INTEGER DEFAULT 0",
        "is_admin": "INTEGER DEFAULT 0",
        "idade": "INTEGER",
        "peso": "REAL",
        "altura": "REAL",
        "objetivo": "TEXT",
        "distancia_principal": "TEXT",
        "tempo_pratica": "TEXT",
        "treinos_corrida_semana": "INTEGER",
        "tem_prova": "INTEGER DEFAULT 0",
        "data_prova": "TEXT",
        "distancia_prova": "TEXT",
        "treinos_musculacao_semana": "INTEGER",
        "local_treino": "TEXT",
        "experiencia_musculacao": "TEXT",
        "historico_lesao": "TEXT",
        "dor_atual": "TEXT",
        "aceitou_termos": "INTEGER DEFAULT 0",
        "aceitou_privacidade": "INTEGER DEFAULT 0",
        "data_consentimento": "TEXT",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "usuarios", nome, definicao)


def _criar_tabela_treinador_atleta(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS treinador_atleta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treinador_id INTEGER NOT NULL,
            atleta_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pendente',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(treinador_id, atleta_id),
            FOREIGN KEY (treinador_id) REFERENCES usuarios(id),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_convites_treinador_link(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS convites_treinador_link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treinador_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (treinador_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_treinos_gerados(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS treinos_gerados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER NOT NULL,
            fase TEXT,
            json_treino TEXT NOT NULL,
            editado_por_treinador INTEGER DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(atleta_id, semana_numero),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )

    colunas = {
        "atleta_id": "INTEGER",
        "usuario_id": "INTEGER",
        "fase": "TEXT",
        "editado_por_treinador": "INTEGER DEFAULT 0",
        "criado_em": "TIMESTAMP",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "treinos_gerados", nome, definicao)


def _criar_tabela_treinos_realizados(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS treinos_realizados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER NOT NULL,
            nome_treino TEXT NOT NULL,
            feito INTEGER DEFAULT 0,
            concluido INTEGER DEFAULT 0,
            feito_em TIMESTAMP NULL,
            data_realizada TEXT NULL,
            feedback_tipo TEXT NULL,
            feedback_contexto_ruim TEXT NULL,
            exercicio_substituir TEXT NULL,
            motivo_exercicio_ruim TEXT NULL,
            observacao TEXT NULL,
            observacoes TEXT NULL,
            UNIQUE(atleta_id, semana_numero, nome_treino),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )

    colunas = {
        "atleta_id": "INTEGER",
        "usuario_id": "INTEGER",
        "feito": "INTEGER DEFAULT 0",
        "concluido": "INTEGER DEFAULT 0",
        "feito_em": "TIMESTAMP NULL",
        "data_realizada": "TEXT NULL",
        "feedback_tipo": "TEXT NULL",
        "feedback_contexto_ruim": "TEXT NULL",
        "exercicio_substituir": "TEXT NULL",
        "motivo_exercicio_ruim": "TEXT NULL",
        "observacao": "TEXT NULL",
        "observacoes": "TEXT NULL",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "treinos_realizados", nome, definicao)


def _criar_tabela_recuperacao_senha(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recuperacao_senha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            codigo_hash TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            usado_em TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_preferencias_substituicao(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferencias_substituicao_exercicio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atleta_id INTEGER NOT NULL,
            exercicio_nome TEXT NOT NULL,
            categoria TEXT,
            principal_musculo TEXT,
            motivo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(atleta_id, exercicio_nome),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_planos(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS planos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            preco_mensal REAL NOT NULL,
            limite_atletas INTEGER NULL,
            ativo INTEGER DEFAULT 1
        )
        """
    )


def _seed_planos(cursor):
    planos = [
        ("atleta_mensal", "Plano Atleta Mensal", "atleta", 49.90, None, 1),
        ("treinador_mensal", "Plano Treinador Mensal", "treinador", 149.90, 30, 1),
    ]
    for plano in planos:
        cursor.execute(
            """
            INSERT OR IGNORE INTO planos (codigo, nome, tipo, preco_mensal, limite_atletas, ativo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            plano,
        )


def _criar_tabela_assinaturas(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS assinaturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            plano_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT,
            renovacao_automatica INTEGER DEFAULT 1,
            gateway TEXT DEFAULT 'manual',
            gateway_reference TEXT,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (plano_id) REFERENCES planos(id)
        )
        """
    )

    colunas = {
        "usuario_id": "INTEGER NOT NULL",
        "plano_id": "INTEGER NOT NULL",
        "status": "TEXT NOT NULL",
        "data_inicio": "TEXT NOT NULL",
        "data_fim": "TEXT",
        "renovacao_automatica": "INTEGER DEFAULT 1",
        "gateway": "TEXT DEFAULT 'manual'",
        "gateway_reference": "TEXT",
        "criado_em": "TEXT",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "assinaturas", nome, definicao)


def _criar_indices_bi(cursor):
    colunas_treinos_gerados = _colunas_tabela(cursor, "treinos_gerados")
    colunas_assinaturas = _colunas_tabela(cursor, "assinaturas")

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_treinador_atleta_treinador_status
        ON treinador_atleta (treinador_id, status, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_treinos_realizados_atleta_data
        ON treinos_realizados (atleta_id, usuario_id, feito_em, data_realizada)
        """
    )
    if "criado_em" in colunas_treinos_gerados and "created_at" in colunas_treinos_gerados:
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_treinos_gerados_atleta_criado
            ON treinos_gerados (atleta_id, usuario_id, criado_em, created_at)
            """
        )
    elif "created_at" in colunas_treinos_gerados:
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_treinos_gerados_atleta_created_only
            ON treinos_gerados (atleta_id, usuario_id, created_at)
            """
        )

    if "criado_em" in colunas_assinaturas:
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assinaturas_usuario_data
            ON assinaturas (usuario_id, status, data_inicio, criado_em)
            """
        )
    else:
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assinaturas_usuario_data_no_criado
            ON assinaturas (usuario_id, status, data_inicio)
            """
        )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_usuarios_tipo_segmento
        ON usuarios (tipo_usuario, sexo, objetivo)
        """
    )


def garantir_colunas_e_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    _criar_tabela_usuarios(cursor)
    _criar_tabela_treinador_atleta(cursor)
    _criar_tabela_convites_treinador_link(cursor)
    _criar_tabela_treinos_gerados(cursor)
    _criar_tabela_treinos_realizados(cursor)
    _criar_tabela_recuperacao_senha(cursor)
    _criar_tabela_preferencias_substituicao(cursor)
    _criar_tabela_planos(cursor)
    _seed_planos(cursor)
    _criar_tabela_assinaturas(cursor)
    _criar_indices_bi(cursor)

    conn.commit()
    conn.close()


def criar_tabelas():
    garantir_colunas_e_tabelas()
