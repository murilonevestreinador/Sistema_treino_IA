import os

import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor


def conectar():
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL nao configurada.")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def _colunas_tabela(cursor, tabela):
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        (tabela,),
    )
    return {linha["column_name"] for linha in cursor.fetchall()}


def _tipo_coluna(cursor, tabela, coluna):
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (tabela, coluna),
    )
    linha = cursor.fetchone()
    if not linha:
        return None
    return linha["data_type"]


def _adicionar_coluna_se_necessario(cursor, tabela, nome_coluna, definicao):
    colunas = _colunas_tabela(cursor, tabela)
    if nome_coluna in colunas:
        return

    try:
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {definicao}")
    except (errors.DuplicateColumn, psycopg2.Error):
        # Em bancos antigos, alguns ALTERs podem falhar; seguimos com o que for possivel.
        pass


def _criar_tabela_usuarios(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            apelido TEXT,
            foto_perfil TEXT,
            email TEXT UNIQUE,
            senha TEXT,
            sexo TEXT,
            tipo_usuario TEXT DEFAULT 'atleta',
            status_conta TEXT DEFAULT 'ativo',
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
        "status_conta": "TEXT DEFAULT 'ativo'",
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
        "asaas_customer_id": "TEXT",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "usuarios", nome, definicao)


def _criar_tabela_treinador_atleta(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS treinador_atleta (
            id SERIAL PRIMARY KEY,
            treinador_id INTEGER NOT NULL,
            atleta_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pendente',
            status_vinculo TEXT DEFAULT 'pendente',
            data_inicio DATE NULL,
            data_fim DATE NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(treinador_id, atleta_id),
            FOREIGN KEY (treinador_id) REFERENCES usuarios(id),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )

    colunas = {
        "status_vinculo": "TEXT DEFAULT 'pendente'",
        "data_inicio": "DATE NULL",
        "data_fim": "DATE NULL",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "treinador_atleta", nome, definicao)


def _criar_tabela_convites_treinador_link(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS convites_treinador_link (
            id SERIAL PRIMARY KEY,
            treinador_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (treinador_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_treinador_tema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS treinador_tema (
            id SERIAL PRIMARY KEY,
            treinador_id INTEGER NOT NULL,
            cor_primaria VARCHAR(20),
            cor_secundaria VARCHAR(20),
            cor_botao VARCHAR(20),
            cor_cards VARCHAR(20),
            cor_header VARCHAR(20),
            logo_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (treinador_id) REFERENCES usuarios(id)
        )
        """
    )

    colunas = {
        "cor_primaria": "VARCHAR(20)",
        "cor_secundaria": "VARCHAR(20)",
        "cor_botao": "VARCHAR(20)",
        "cor_cards": "VARCHAR(20)",
        "cor_header": "VARCHAR(20)",
        "logo_url": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "treinador_tema", nome, definicao)

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_treinador_tema_treinador_unico
        ON treinador_tema (treinador_id)
        """
    )


def _criar_tabela_treinos_gerados(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS treinos_gerados (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER NOT NULL,
            nome_treino TEXT NOT NULL,
            feito INTEGER DEFAULT 0,
            concluido INTEGER DEFAULT 0,
            feito_em TIMESTAMP NULL,
            data_realizada TIMESTAMP NULL,
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
        "data_realizada": "TIMESTAMP NULL",
        "feedback_tipo": "TEXT NULL",
        "feedback_contexto_ruim": "TEXT NULL",
        "exercicio_substituir": "TEXT NULL",
        "motivo_exercicio_ruim": "TEXT NULL",
        "observacao": "TEXT NULL",
        "observacoes": "TEXT NULL",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "treinos_realizados", nome, definicao)


def _migrar_data_realizada_para_timestamp(cursor):
    tipo = _tipo_coluna(cursor, "treinos_realizados", "data_realizada")
    if tipo is None or tipo.startswith("timestamp"):
        return

    if tipo not in {"text", "character varying", "character"}:
        return

    cursor.execute("DROP INDEX IF EXISTS idx_treinos_realizados_atleta_data")
    cursor.execute(
        """
        ALTER TABLE treinos_realizados
        ADD COLUMN IF NOT EXISTS data_realizada_ts TIMESTAMP NULL
        """
    )
    cursor.execute(
        """
        UPDATE treinos_realizados
           SET data_realizada_ts = COALESCE(
               data_realizada_ts,
               feito_em,
               CASE
                   WHEN data_realizada IS NULL OR btrim(data_realizada) = '' THEN NULL
                   WHEN btrim(data_realizada) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?)?([+-][0-9]{2}:?[0-9]{2}|Z)?$'
                        THEN REPLACE(btrim(data_realizada), 'T', ' ')::timestamp
                   ELSE NULL
               END
           )
         WHERE data_realizada_ts IS NULL
        """
    )
    cursor.execute("ALTER TABLE treinos_realizados DROP COLUMN data_realizada")
    cursor.execute(
        """
        ALTER TABLE treinos_realizados
        RENAME COLUMN data_realizada_ts TO data_realizada
        """
    )


def _migrar_feito_em_para_timestamp(cursor):
    tipo = _tipo_coluna(cursor, "treinos_realizados", "feito_em")
    if tipo is None or tipo.startswith("timestamp"):
        return

    if tipo not in {"text", "character varying", "character"}:
        return

    cursor.execute(
        """
        ALTER TABLE treinos_realizados
        ADD COLUMN IF NOT EXISTS feito_em_ts TIMESTAMP NULL
        """
    )
    cursor.execute(
        """
        UPDATE treinos_realizados
           SET feito_em_ts = COALESCE(
               feito_em_ts,
               CASE
                   WHEN feito_em IS NULL OR btrim(feito_em) = '' THEN NULL
                   WHEN btrim(feito_em) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?)?([+-][0-9]{2}:?[0-9]{2}|Z)?$'
                        THEN REPLACE(btrim(feito_em), 'T', ' ')::timestamp
                   ELSE NULL
               END
           )
         WHERE feito_em_ts IS NULL
        """
    )
    cursor.execute("ALTER TABLE treinos_realizados DROP COLUMN feito_em")
    cursor.execute(
        """
        ALTER TABLE treinos_realizados
        RENAME COLUMN feito_em_ts TO feito_em
        """
    )


def _criar_tabela_recuperacao_senha(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recuperacao_senha (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            codigo_hash TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            usado_em TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_sessoes_persistentes(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessoes_persistentes (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            browser_key_hash TEXT NOT NULL UNIQUE,
            user_agent TEXT,
            ultimo_acesso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            revogado_em TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_preferencias_substituicao(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferencias_substituicao_exercicio (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            tipo_plano TEXT,
            periodicidade TEXT DEFAULT 'mensal',
            preco_mensal REAL NOT NULL,
            valor_base NUMERIC(10,2),
            taxa_por_aluno_ativo NUMERIC(10,2) DEFAULT 0,
            limite_atletas INTEGER NULL,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    colunas = {
        "tipo_plano": "TEXT",
        "periodicidade": "TEXT DEFAULT 'mensal'",
        "valor_base": "NUMERIC(10,2)",
        "taxa_por_aluno_ativo": "NUMERIC(10,2) DEFAULT 0",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "planos", nome, definicao)


def _criar_tabela_avaliacao_forca(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS avaliacao_forca (
            id SERIAL PRIMARY KEY,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER NOT NULL,
            fase TEXT,
            categoria_movimento TEXT NOT NULL,
            exercicio_nome TEXT NOT NULL,
            carga_utilizada REAL,
            reps_realizadas INTEGER,
            rpe REAL,
            carga_referencia_estimada REAL,
            carga_sugerida_manual REAL,
            observacao_treinador TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(atleta_id, semana_numero, categoria_movimento),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )

    colunas = {
        "atleta_id": "INTEGER",
        "usuario_id": "INTEGER",
        "fase": "TEXT",
        "carga_utilizada": "REAL",
        "reps_realizadas": "INTEGER",
        "rpe": "REAL",
        "carga_referencia_estimada": "REAL",
        "carga_sugerida_manual": "REAL",
        "observacao_treinador": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "avaliacao_forca", nome, definicao)


def _criar_tabela_execucao_exercicio(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS execucao_exercicio (
            id SERIAL PRIMARY KEY,
            atleta_id INTEGER,
            usuario_id INTEGER,
            semana_numero INTEGER NOT NULL,
            fase TEXT,
            treino_nome TEXT NOT NULL,
            exercicio_nome TEXT NOT NULL,
            categoria_movimento TEXT,
            series_planejadas INTEGER,
            reps_planejadas INTEGER,
            rpe_alvo TEXT,
            carga_planejada REAL,
            orientacao_carga TEXT,
            series_realizadas INTEGER,
            reps_realizadas INTEGER,
            carga_realizada REAL,
            rpe_real REAL,
            dor TEXT,
            observacao TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(atleta_id, semana_numero, treino_nome, exercicio_nome),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )

    colunas = {
        "atleta_id": "INTEGER",
        "usuario_id": "INTEGER",
        "fase": "TEXT",
        "categoria_movimento": "TEXT",
        "series_planejadas": "INTEGER",
        "reps_planejadas": "INTEGER",
        "rpe_alvo": "TEXT",
        "carga_planejada": "REAL",
        "orientacao_carga": "TEXT",
        "series_realizadas": "INTEGER",
        "reps_realizadas": "INTEGER",
        "carga_realizada": "REAL",
        "rpe_real": "REAL",
        "dor": "TEXT",
        "observacao": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "execucao_exercicio", nome, definicao)


def _seed_planos(cursor):
    planos = [
        ("atleta_mensal", "Plano Atleta Mensal", "atleta", "atleta", "mensal", 49.90, 49.90, 0, None, 1),
        ("atleta_anual", "Plano Atleta Anual", "atleta", "atleta", "anual", 499.00, 499.00, 0, None, 1),
        ("treinador_mensal", "Plano Treinador Mensal", "treinador", "treinador", "mensal", 149.90, 149.90, 19.90, None, 1),
        ("treinador_anual", "Plano Treinador Anual", "treinador", "treinador", "anual", 1499.00, 1499.00, 16.90, None, 1),
    ]
    for plano in planos:
        cursor.execute(
            """
            INSERT INTO planos (
                codigo, nome, tipo, tipo_plano, periodicidade, preco_mensal,
                valor_base, taxa_por_aluno_ativo, limite_atletas, ativo, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (codigo) DO UPDATE SET
                nome = EXCLUDED.nome,
                tipo = EXCLUDED.tipo,
                tipo_plano = EXCLUDED.tipo_plano,
                periodicidade = EXCLUDED.periodicidade,
                preco_mensal = EXCLUDED.preco_mensal,
                valor_base = EXCLUDED.valor_base,
                taxa_por_aluno_ativo = EXCLUDED.taxa_por_aluno_ativo,
                limite_atletas = EXCLUDED.limite_atletas,
                ativo = EXCLUDED.ativo
            """,
            plano,
        )


def _criar_tabela_assinaturas(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS assinaturas (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            plano_id INTEGER NOT NULL,
            tipo_plano TEXT,
            status TEXT NOT NULL,
            valor REAL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT,
            data_renovacao DATE NULL,
            valor_base_cobrado NUMERIC(10,2),
            quantidade_alunos_ativos_fechamento INTEGER DEFAULT 0,
            valor_taxa_alunos NUMERIC(10,2) DEFAULT 0,
            valor_total_cobrado NUMERIC(10,2),
            renovacao_automatica INTEGER DEFAULT 1,
            gateway TEXT DEFAULT 'manual',
            gateway_reference TEXT,
            asaas_subscription_id TEXT,
            criado_em TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (plano_id) REFERENCES planos(id)
        )
        """
    )

    colunas = {
        "usuario_id": "INTEGER NOT NULL",
        "plano_id": "INTEGER NOT NULL",
        "tipo_plano": "TEXT",
        "status": "TEXT NOT NULL",
        "valor": "REAL",
        "data_inicio": "TEXT NOT NULL",
        "data_fim": "TEXT",
        "data_renovacao": "DATE NULL",
        "valor_base_cobrado": "NUMERIC(10,2)",
        "quantidade_alunos_ativos_fechamento": "INTEGER DEFAULT 0",
        "valor_taxa_alunos": "NUMERIC(10,2) DEFAULT 0",
        "valor_total_cobrado": "NUMERIC(10,2)",
        "renovacao_automatica": "INTEGER DEFAULT 1",
        "gateway": "TEXT DEFAULT 'manual'",
        "gateway_reference": "TEXT",
        "asaas_subscription_id": "TEXT",
        "criado_em": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "assinaturas", nome, definicao)


def _criar_tabela_pagamentos(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pagamentos (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            assinatura_id INTEGER NULL,
            valor REAL NOT NULL,
            valor_bruto NUMERIC(10,2),
            valor_desconto NUMERIC(10,2) DEFAULT 0,
            valor_final NUMERIC(10,2),
            status TEXT NOT NULL,
            metodo_pagamento TEXT,
            data_pagamento TEXT,
            data_vencimento TEXT,
            referencia_externa TEXT,
            asaas_payment_id TEXT,
            gateway TEXT DEFAULT 'manual',
            gateway_reference TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (assinatura_id) REFERENCES assinaturas(id)
        )
        """
    )

    colunas = {
        "valor_bruto": "NUMERIC(10,2)",
        "valor_desconto": "NUMERIC(10,2) DEFAULT 0",
        "valor_final": "NUMERIC(10,2)",
        "asaas_payment_id": "TEXT",
        "gateway": "TEXT DEFAULT 'manual'",
        "gateway_reference": "TEXT",
    }
    for nome, definicao in colunas.items():
        _adicionar_coluna_se_necessario(cursor, "pagamentos", nome, definicao)


def _criar_tabela_webhook_eventos_asaas(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_eventos_asaas (
            id SERIAL PRIMARY KEY,
            dedupe_key TEXT NOT NULL UNIQUE,
            evento TEXT,
            asaas_event_id TEXT,
            asaas_payment_id TEXT,
            asaas_subscription_id TEXT,
            status_processamento TEXT DEFAULT 'recebido',
            erro TEXT,
            payload TEXT,
            headers TEXT,
            recebido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processado_em TIMESTAMP NULL
        )
        """
    )


def _criar_tabela_cupons_desconto(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cupons_desconto (
            id SERIAL PRIMARY KEY,
            codigo TEXT UNIQUE,
            descricao TEXT,
            tipo_desconto TEXT,
            valor_desconto NUMERIC(10,2) DEFAULT 0,
            percentual_desconto NUMERIC(5,2) DEFAULT 0,
            aplicavel_para TEXT DEFAULT 'todos',
            periodicidade_aplicavel TEXT DEFAULT 'todos',
            quantidade_max_uso INTEGER,
            quantidade_usada INTEGER DEFAULT 0,
            ativo BOOLEAN DEFAULT TRUE,
            data_inicio DATE NULL,
            data_fim DATE NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _criar_tabela_descontos_aplicados(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS descontos_aplicados (
            id SERIAL PRIMARY KEY,
            cupom_id INTEGER NULL,
            usuario_id INTEGER NOT NULL,
            assinatura_id INTEGER NULL,
            pagamento_id INTEGER NULL,
            valor_bruto NUMERIC(10,2),
            valor_desconto NUMERIC(10,2),
            valor_final NUMERIC(10,2),
            aplicado_por TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cupom_id) REFERENCES cupons_desconto(id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (assinatura_id) REFERENCES assinaturas(id),
            FOREIGN KEY (pagamento_id) REFERENCES pagamentos(id)
        )
        """
    )


def _criar_tabela_cobrancas_alunos_treinador(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cobrancas_alunos_treinador (
            id SERIAL PRIMARY KEY,
            treinador_id INTEGER NOT NULL,
            atleta_id INTEGER NOT NULL,
            descricao TEXT,
            valor NUMERIC(10,2) NOT NULL,
            periodicidade TEXT NOT NULL,
            status TEXT DEFAULT 'pendente',
            data_vencimento DATE NULL,
            data_pagamento DATE NULL,
            gateway TEXT DEFAULT 'asaas',
            gateway_reference TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (treinador_id) REFERENCES usuarios(id),
            FOREIGN KEY (atleta_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_admin_logs(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_logs (
            id SERIAL PRIMARY KEY,
            admin_id INTEGER NOT NULL,
            acao TEXT NOT NULL,
            alvo_tipo TEXT NOT NULL,
            alvo_id INTEGER,
            detalhes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_id) REFERENCES usuarios(id)
        )
        """
    )


def _criar_tabela_configuracoes_sistema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _sincronizar_papeis_legados(cursor):
    cursor.execute(
        """
        UPDATE treinador_atleta
        SET status_vinculo = COALESCE(NULLIF(status_vinculo, ''), NULLIF(status, ''), 'pendente'),
            data_inicio = COALESCE(data_inicio, DATE(created_at))
        """
    )
    cursor.execute(
        """
        UPDATE usuarios
        SET tipo_usuario = 'admin'
        WHERE COALESCE(is_admin, 0) = 1
          AND COALESCE(tipo_usuario, '') <> 'admin'
        """
    )
    cursor.execute(
        """
        UPDATE usuarios
        SET status_conta = 'ativo'
        WHERE status_conta IS NULL OR btrim(status_conta) = ''
        """
    )
    cursor.execute(
        """
        UPDATE assinaturas a
        SET tipo_plano = COALESCE(NULLIF(a.tipo_plano, ''), p.tipo),
            valor = COALESCE(a.valor, p.preco_mensal, p.valor_base::float),
            data_renovacao = COALESCE(
                a.data_renovacao,
                CASE
                    WHEN COALESCE(p.periodicidade, 'mensal') = 'anual' THEN CURRENT_DATE + INTERVAL '1 year'
                    ELSE CURRENT_DATE + INTERVAL '1 month'
                END
            ),
            valor_base_cobrado = COALESCE(a.valor_base_cobrado, p.valor_base, p.preco_mensal),
            quantidade_alunos_ativos_fechamento = COALESCE(a.quantidade_alunos_ativos_fechamento, 0),
            valor_taxa_alunos = COALESCE(a.valor_taxa_alunos, 0),
            valor_total_cobrado = COALESCE(a.valor_total_cobrado, a.valor, p.valor_base, p.preco_mensal)
        FROM planos p
        WHERE p.id = a.plano_id
          AND (
              a.tipo_plano IS NULL OR btrim(COALESCE(a.tipo_plano, '')) = ''
              OR a.valor IS NULL
              OR a.valor_total_cobrado IS NULL
          )
        """
    )
    cursor.execute(
        """
        UPDATE planos
        SET tipo_plano = COALESCE(NULLIF(tipo_plano, ''), tipo),
            periodicidade = COALESCE(NULLIF(periodicidade, ''), 'mensal'),
            valor_base = COALESCE(valor_base, preco_mensal),
            taxa_por_aluno_ativo = COALESCE(taxa_por_aluno_ativo, 0)
        """
    )
    cursor.execute(
        """
        UPDATE pagamentos
        SET valor_bruto = COALESCE(valor_bruto, valor),
            valor_desconto = COALESCE(valor_desconto, 0),
            valor_final = COALESCE(valor_final, valor),
            gateway = COALESCE(NULLIF(gateway, ''), 'manual'),
            gateway_reference = COALESCE(gateway_reference, referencia_externa),
            asaas_payment_id = COALESCE(asaas_payment_id, referencia_externa)
        """
    )
    cursor.execute(
        """
        INSERT INTO configuracoes_sistema (chave, valor, updated_at)
        SELECT 'admin_bootstrap_consumed', 'true', CURRENT_TIMESTAMP
        WHERE EXISTS (
            SELECT 1
            FROM usuarios
            WHERE COALESCE(is_admin, 0) = 1
               OR LOWER(COALESCE(tipo_usuario, '')) = 'admin'
        )
        ON CONFLICT (chave) DO UPDATE
        SET valor = EXCLUDED.valor,
            updated_at = CURRENT_TIMESTAMP
        """
    )


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
        ON usuarios (tipo_usuario, status_conta, sexo, objetivo)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pagamentos_usuario_status_vencimento
        ON pagamentos (usuario_id, status, data_vencimento, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_treinador_atleta_snapshot
        ON treinador_atleta (treinador_id, status_vinculo, data_inicio, data_fim)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_assinaturas_renovacao
        ON assinaturas (usuario_id, status, data_renovacao, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_usuarios_asaas_customer
        ON usuarios (asaas_customer_id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_assinaturas_asaas_subscription
        ON assinaturas (asaas_subscription_id, gateway_reference)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pagamentos_asaas_payment
        ON pagamentos (asaas_payment_id, referencia_externa, gateway_reference)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhooks_asaas_recebido
        ON webhook_eventos_asaas (evento, asaas_payment_id, recebido_em DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cupons_codigo_ativo
        ON cupons_desconto (codigo, ativo, data_inicio, data_fim)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_descontos_usuario_assinatura
        ON descontos_aplicados (usuario_id, assinatura_id, pagamento_id, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cobrancas_treinador_status
        ON cobrancas_alunos_treinador (treinador_id, atleta_id, status, data_vencimento, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_data
        ON admin_logs (admin_id, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_avaliacao_forca_atleta_categoria
        ON avaliacao_forca (atleta_id, usuario_id, categoria_movimento, semana_numero DESC, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_execucao_exercicio_atleta_exercicio
        ON execucao_exercicio (atleta_id, usuario_id, exercicio_nome, semana_numero DESC, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_execucao_exercicio_atleta_categoria
        ON execucao_exercicio (atleta_id, usuario_id, categoria_movimento, semana_numero DESC, created_at DESC)
        """
    )


def garantir_colunas_e_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    _criar_tabela_usuarios(cursor)
    _criar_tabela_treinador_atleta(cursor)
    _criar_tabela_convites_treinador_link(cursor)
    _criar_tabela_treinador_tema(cursor)
    _criar_tabela_treinos_gerados(cursor)
    _criar_tabela_treinos_realizados(cursor)
    _migrar_feito_em_para_timestamp(cursor)
    _migrar_data_realizada_para_timestamp(cursor)
    _criar_tabela_recuperacao_senha(cursor)
    _criar_tabela_sessoes_persistentes(cursor)
    _criar_tabela_preferencias_substituicao(cursor)
    _criar_tabela_planos(cursor)
    _seed_planos(cursor)
    _criar_tabela_assinaturas(cursor)
    _criar_tabela_pagamentos(cursor)
    _criar_tabela_webhook_eventos_asaas(cursor)
    _criar_tabela_cupons_desconto(cursor)
    _criar_tabela_descontos_aplicados(cursor)
    _criar_tabela_cobrancas_alunos_treinador(cursor)
    _criar_tabela_admin_logs(cursor)
    _criar_tabela_configuracoes_sistema(cursor)
    _criar_tabela_avaliacao_forca(cursor)
    _criar_tabela_execucao_exercicio(cursor)
    _sincronizar_papeis_legados(cursor)
    _criar_indices_bi(cursor)

    conn.commit()
    conn.close()


def criar_tabelas():
    garantir_colunas_e_tabelas()
