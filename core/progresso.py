from datetime import datetime

from core.banco import conectar
from core.carga import estimar_carga_referencia


def marcar_treino_feito(atleta_id, semana_numero, nome_treino, feito, observacao=None):
    conn = conectar()
    cursor = conn.cursor()
    feito_flag = int(bool(feito))
    feito_em = datetime.now().replace(microsecond=0) if feito_flag else None
    observacao_final = observacao or None

    cursor.execute(
        """
        SELECT id
        FROM treinos_realizados
        WHERE semana_numero = %s
          AND nome_treino = %s
          AND COALESCE(atleta_id, usuario_id) = %s
        LIMIT 1
        """,
        (semana_numero, nome_treino, atleta_id),
    )
    existente = cursor.fetchone()

    if existente:
        cursor.execute(
            """
            UPDATE treinos_realizados
            SET atleta_id = %s,
                usuario_id = %s,
                feito = %s,
                concluido = %s,
                feito_em = %s,
                data_realizada = %s,
                observacao = %s,
                observacoes = %s
            WHERE id = %s
            """,
            (
                atleta_id,
                atleta_id,
                feito_flag,
                feito_flag,
                feito_em,
                feito_em,
                observacao_final,
                observacao_final,
                existente["id"],
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO treinos_realizados (
                atleta_id, usuario_id, semana_numero, nome_treino, feito, concluido,
                feito_em, data_realizada, observacao, observacoes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                atleta_id,
                atleta_id,
                semana_numero,
                nome_treino,
                feito_flag,
                feito_flag,
                feito_em,
                feito_em,
                observacao_final,
                observacao_final,
            ),
        )

    conn.commit()
    conn.close()


def salvar_feedback_treino(
    atleta_id,
    semana_numero,
    nome_treino,
    feedback_tipo,
    feedback_contexto_ruim=None,
    exercicio_substituir=None,
    motivo_exercicio_ruim=None,
):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE treinos_realizados
        SET feedback_tipo = %s,
            feedback_contexto_ruim = %s,
            exercicio_substituir = %s,
            motivo_exercicio_ruim = %s
        WHERE semana_numero = %s
          AND nome_treino = %s
          AND COALESCE(atleta_id, usuario_id) = %s
        """,
        (
            feedback_tipo,
            feedback_contexto_ruim,
            exercicio_substituir,
            motivo_exercicio_ruim,
            semana_numero,
            nome_treino,
            atleta_id,
        ),
    )
    conn.commit()
    conn.close()


def salvar_feedback_exercicio(
    atleta_id,
    semana_numero,
    fase,
    treino_nome,
    exercicio_nome,
    categoria_feedback,
    observacao=None,
    exercicio_original_nome=None,
):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO feedback_exercicio (
            atleta_id, usuario_id, semana_numero, fase, treino_nome, exercicio_nome,
            exercicio_original_nome, categoria_feedback, observacao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            atleta_id,
            atleta_id,
            semana_numero,
            fase,
            treino_nome,
            exercicio_nome,
            exercicio_original_nome,
            categoria_feedback,
            observacao,
        ),
    )
    linha = dict(cursor.fetchone())
    conn.commit()
    conn.close()
    return linha


def registrar_preferencia_substituicao(atleta_id, exercicio):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO preferencias_substituicao_exercicio (
            atleta_id, exercicio_nome, categoria, principal_musculo, motivo
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(atleta_id, exercicio_nome)
        DO UPDATE SET
            categoria = excluded.categoria,
            principal_musculo = excluded.principal_musculo,
            motivo = excluded.motivo
        """,
        (
            atleta_id,
            exercicio.get("nome"),
            exercicio.get("categoria"),
            exercicio.get("principal_musculo"),
            exercicio.get("motivo"),
        ),
    )
    conn.commit()
    conn.close()


def listar_preferencias_substituicao(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT atleta_id, exercicio_nome, categoria, principal_musculo, motivo
        FROM preferencias_substituicao_exercicio
        WHERE atleta_id = %s
        ORDER BY created_at DESC
        """,
        (atleta_id,),
    )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return linhas


def buscar_progresso_semana(atleta_id, semana_numero):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT nome_treino,
               COALESCE(feito, concluido, 0) AS feito,
               COALESCE(CAST(feito_em AS text), CAST(data_realizada AS text)) AS feito_em,
               COALESCE(observacao, observacoes) AS observacao,
               feedback_tipo,
               feedback_contexto_ruim,
               exercicio_substituir,
               motivo_exercicio_ruim
        FROM treinos_realizados
        WHERE semana_numero = %s
          AND COALESCE(atleta_id, usuario_id) = %s
        ORDER BY nome_treino
        """,
        (semana_numero, atleta_id),
    )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return {linha["nome_treino"]: linha for linha in linhas}


def historico_progresso(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT semana_numero,
               nome_treino,
               COALESCE(feito, concluido, 0) AS feito,
               COALESCE(CAST(feito_em AS text), CAST(data_realizada AS text)) AS feito_em,
               COALESCE(observacao, observacoes) AS observacao,
               feedback_tipo
        FROM treinos_realizados
        WHERE COALESCE(atleta_id, usuario_id) = %s
        ORDER BY semana_numero, nome_treino
        """,
        (atleta_id,),
    )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return linhas


def calcular_progresso_semanal(atleta_id, semana_numero, total_planejado):
    progresso = buscar_progresso_semana(atleta_id, semana_numero)
    concluidos = sum(1 for item in progresso.values() if item.get("feito"))
    percentual = int((concluidos / total_planejado) * 100) if total_planejado else 0
    return concluidos, percentual


def salvar_avaliacao_forca(
    atleta_id,
    semana_numero,
    fase,
    categoria_movimento,
    exercicio_nome,
    carga_utilizada,
    reps_realizadas,
    rpe,
):
    if not categoria_movimento:
        return None

    carga = float(carga_utilizada or 0)
    reps = int(reps_realizadas or 0)
    rpe_real = float(rpe or 0)
    if carga <= 0 or reps <= 0 or rpe_real <= 0:
        return None

    carga_referencia = estimar_carga_referencia(carga, reps, rpe_real)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO avaliacao_forca (
            atleta_id, usuario_id, semana_numero, fase, categoria_movimento,
            exercicio_nome, carga_utilizada, reps_realizadas, rpe, carga_referencia_estimada, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (atleta_id, semana_numero, categoria_movimento)
        DO UPDATE SET
            usuario_id = excluded.usuario_id,
            fase = excluded.fase,
            exercicio_nome = excluded.exercicio_nome,
            carga_utilizada = excluded.carga_utilizada,
            reps_realizadas = excluded.reps_realizadas,
            rpe = excluded.rpe,
            carga_referencia_estimada = excluded.carga_referencia_estimada,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            atleta_id,
            atleta_id,
            semana_numero,
            fase,
            categoria_movimento,
            exercicio_nome,
            carga,
            reps,
            rpe_real,
            carga_referencia,
        ),
    )
    linha = dict(cursor.fetchone())
    conn.commit()
    conn.close()
    return linha


def listar_avaliacoes_forca(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM avaliacao_forca
        WHERE COALESCE(atleta_id, usuario_id) = %s
        ORDER BY semana_numero DESC, created_at DESC
        """,
        (atleta_id,),
    )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return linhas


def listar_feedback_exercicio(atleta_id, semana_numero=None, treino_nome=None):
    conn = conectar()
    cursor = conn.cursor()
    filtros = ["COALESCE(atleta_id, usuario_id) = %s"]
    params = [atleta_id]

    if semana_numero is not None:
        filtros.append("semana_numero = %s")
        params.append(semana_numero)
    if treino_nome:
        filtros.append("treino_nome = %s")
        params.append(treino_nome)

    cursor.execute(
        f"""
        SELECT *
        FROM feedback_exercicio
        WHERE {" AND ".join(filtros)}
        ORDER BY created_at DESC
        """,
        tuple(params),
    )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return linhas


def registrar_substituicao_exercicio(
    atleta_id,
    semana_numero,
    fase,
    treino_nome,
    exercicio_original_nome,
    exercicio_substituto_nome,
    motivo,
    regiao_dor=None,
    detalhe_sugestao=None,
):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO substituicoes_exercicio (
            atleta_id, usuario_id, semana_numero, fase, treino_nome,
            exercicio_original_nome, exercicio_substituto_nome, motivo, regiao_dor, detalhe_sugestao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            atleta_id,
            atleta_id,
            semana_numero,
            fase,
            treino_nome,
            exercicio_original_nome,
            exercicio_substituto_nome,
            motivo,
            regiao_dor,
            detalhe_sugestao,
        ),
    )
    linha = dict(cursor.fetchone())
    conn.commit()
    conn.close()
    return linha


def buscar_avaliacao_referencia(atleta_id, categoria_movimento):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM avaliacao_forca
        WHERE COALESCE(atleta_id, usuario_id) = %s
          AND categoria_movimento = %s
        ORDER BY semana_numero DESC, created_at DESC
        LIMIT 1
        """,
        (atleta_id, categoria_movimento),
    )
    linha = cursor.fetchone()
    conn.close()
    return dict(linha) if linha else None


def salvar_ajuste_manual_avaliacao(avaliacao_id, carga_sugerida_manual=None, observacao_treinador=None):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE avaliacao_forca
        SET carga_sugerida_manual = %s,
            observacao_treinador = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING *
        """,
        (carga_sugerida_manual, observacao_treinador, avaliacao_id),
    )
    linha = cursor.fetchone()
    conn.commit()
    conn.close()
    return dict(linha) if linha else None


def salvar_execucao_exercicio(atleta_id, semana_numero, fase, treino_nome, exercicios):
    conn = conectar()
    cursor = conn.cursor()
    registros_salvos = []

    for exercicio in exercicios:
        cursor.execute(
            """
            INSERT INTO execucao_exercicio (
                atleta_id, usuario_id, semana_numero, fase, treino_nome, exercicio_nome,
                categoria_movimento, series_planejadas, reps_planejadas, rpe_alvo, carga_planejada,
                orientacao_carga, series_realizadas, reps_realizadas, carga_realizada, rpe_real,
                dor, observacao, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, CURRENT_TIMESTAMP
            )
            ON CONFLICT (atleta_id, semana_numero, treino_nome, exercicio_nome)
            DO UPDATE SET
                usuario_id = excluded.usuario_id,
                fase = excluded.fase,
                categoria_movimento = excluded.categoria_movimento,
                series_planejadas = excluded.series_planejadas,
                reps_planejadas = excluded.reps_planejadas,
                rpe_alvo = excluded.rpe_alvo,
                carga_planejada = excluded.carga_planejada,
                orientacao_carga = excluded.orientacao_carga,
                series_realizadas = excluded.series_realizadas,
                reps_realizadas = excluded.reps_realizadas,
                carga_realizada = excluded.carga_realizada,
                rpe_real = excluded.rpe_real,
                dor = excluded.dor,
                observacao = excluded.observacao,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (
                atleta_id,
                atleta_id,
                semana_numero,
                fase,
                treino_nome,
                exercicio.get("nome"),
                exercicio.get("categoria_movimento"),
                exercicio.get("series"),
                exercicio.get("reps"),
                exercicio.get("rpe"),
                exercicio.get("carga_sugerida"),
                exercicio.get("orientacao_carga"),
                exercicio.get("series_realizadas"),
                exercicio.get("reps_realizadas"),
                exercicio.get("carga_realizada"),
                exercicio.get("rpe_real"),
                exercicio.get("dor"),
                exercicio.get("observacao"),
            ),
        )
        registros_salvos.append(dict(cursor.fetchone()))

    conn.commit()
    conn.close()
    return registros_salvos


def listar_execucao_treino(atleta_id, semana_numero, treino_nome):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM execucao_exercicio
        WHERE COALESCE(atleta_id, usuario_id) = %s
          AND semana_numero = %s
          AND treino_nome = %s
        ORDER BY created_at, exercicio_nome
        """,
        (atleta_id, semana_numero, treino_nome),
    )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return linhas


def listar_historico_cargas(atleta_id, exercicio_nome=None):
    conn = conectar()
    cursor = conn.cursor()
    if exercicio_nome:
        cursor.execute(
            """
            SELECT *
            FROM execucao_exercicio
            WHERE COALESCE(atleta_id, usuario_id) = %s
              AND exercicio_nome = %s
            ORDER BY semana_numero DESC, created_at DESC
            """,
            (atleta_id, exercicio_nome),
        )
    else:
        cursor.execute(
            """
            SELECT *
            FROM execucao_exercicio
            WHERE COALESCE(atleta_id, usuario_id) = %s
            ORDER BY semana_numero DESC, created_at DESC
            LIMIT 100
            """,
            (atleta_id,),
        )
    linhas = [dict(linha) for linha in cursor.fetchall()]
    conn.close()
    return linhas


def buscar_ultima_execucao(atleta_id, exercicio_nome=None, categoria_movimento=None):
    if not exercicio_nome and not categoria_movimento:
        return None

    conn = conectar()
    cursor = conn.cursor()
    if exercicio_nome:
        cursor.execute(
            """
            SELECT *
            FROM execucao_exercicio
            WHERE COALESCE(atleta_id, usuario_id) = %s
              AND exercicio_nome = %s
            ORDER BY semana_numero DESC, created_at DESC
            LIMIT 1
            """,
            (atleta_id, exercicio_nome),
        )
    else:
        cursor.execute(
            """
            SELECT *
            FROM execucao_exercicio
            WHERE COALESCE(atleta_id, usuario_id) = %s
              AND categoria_movimento = %s
            ORDER BY semana_numero DESC, created_at DESC
            LIMIT 1
            """,
            (atleta_id, categoria_movimento),
        )
    linha = cursor.fetchone()
    conn.close()
    return dict(linha) if linha else None
