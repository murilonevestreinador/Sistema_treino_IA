from datetime import datetime

from core.banco import conectar


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
