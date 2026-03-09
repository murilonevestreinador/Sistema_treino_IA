import json

from config.estrutura import estrutura_treinos
from core.banco import conectar
from core.periodizacao import definir_parametros_semana
from core.progresso import listar_preferencias_substituicao
from core.selecao import escolher_exercicio_por_categoria


def gerar_treino_semana(atleta, exercicios_db, semana_numero, fase):
    atleta_contexto = dict(atleta)
    atleta_contexto["preferencias_substituicao"] = listar_preferencias_substituicao(atleta["id"])
    frequencia = max(1, min(5, int(atleta.get("treinos_musculacao_semana", 1))))
    estrutura = estrutura_treinos[fase][frequencia]
    series, reps, carga, rpe, execucao, intencao = definir_parametros_semana(fase, semana_numero)

    treinos = {}
    for nome_treino, categorias in estrutura.items():
        nomes_usados = set()
        bloco = []

        for categoria in categorias:
            exercicio = escolher_exercicio_por_categoria(
                exercicios_db,
                categoria,
                fase,
                atleta_contexto,
                nomes_ja_usados=nomes_usados,
            )
            if not exercicio:
                continue

            nomes_usados.add(exercicio["nome"])
            bloco.append(
                {
                    "nome": exercicio["nome"],
                    "categoria": categoria,
                    "principal_musculo": exercicio.get("principal_musculo"),
                    "series": series,
                    "reps": reps,
                    "descanso": "60-90s",
                    "carga": carga,
                    "rpe": rpe,
                    "execucao": execucao,
                    "intencao": intencao,
                }
            )

        treinos[nome_treino] = bloco

    return treinos


def buscar_treino_gerado(atleta_id, semana_numero):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *,
               COALESCE(atleta_id, usuario_id) AS atleta_ref
        FROM treinos_gerados
        WHERE semana_numero = %s
          AND COALESCE(atleta_id, usuario_id) = %s
        LIMIT 1
        """,
        (semana_numero, atleta_id),
    )
    linha = cursor.fetchone()
    conn.close()

    if not linha:
        return None

    treino = dict(linha)
    treino["json_treino"] = json.loads(treino["json_treino"])
    return treino


def salvar_treino_gerado(atleta_id, semana_numero, fase, treinos_json, editado_por_treinador=0):
    treino_existente = buscar_treino_gerado(atleta_id, semana_numero)
    conn = conectar()
    cursor = conn.cursor()
    json_treino = json.dumps(treinos_json, ensure_ascii=False)

    if treino_existente:
        cursor.execute(
            """
            UPDATE treinos_gerados
            SET atleta_id = %s,
                usuario_id = %s,
                fase = %s,
                json_treino = %s,
                editado_por_treinador = %s
            WHERE id = %s
            """,
            (
                atleta_id,
                atleta_id,
                fase,
                json_treino,
                int(editado_por_treinador),
                treino_existente["id"],
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO treinos_gerados (
                atleta_id, usuario_id, semana_numero, fase, json_treino, editado_por_treinador
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                atleta_id,
                atleta_id,
                semana_numero,
                fase,
                json_treino,
                int(editado_por_treinador),
            ),
        )

    conn.commit()
    conn.close()
    return buscar_treino_gerado(atleta_id, semana_numero)


def obter_ou_gerar_treino_semana(atleta, exercicios_db, semana_numero, fase, forcar=False):
    if not forcar:
        treino_existente = buscar_treino_gerado(atleta["id"], semana_numero)
        if treino_existente:
            return treino_existente["json_treino"]

    treino = gerar_treino_semana(atleta, exercicios_db, semana_numero, fase)
    salvo = salvar_treino_gerado(atleta["id"], semana_numero, fase, treino)
    return salvo["json_treino"]


def resetar_planejamento_atleta(atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM treinos_gerados
        WHERE COALESCE(atleta_id, usuario_id) = %s
        """,
        (atleta_id,),
    )
    cursor.execute(
        """
        DELETE FROM treinos_realizados
        WHERE COALESCE(atleta_id, usuario_id) = %s
        """,
        (atleta_id,),
    )
    conn.commit()
    conn.close()


def resetar_treinos_futuros(atleta_id, semana_atual):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM treinos_gerados
        WHERE COALESCE(atleta_id, usuario_id) = %s
          AND semana_numero > %s
        """,
        (atleta_id, semana_atual),
    )
    cursor.execute(
        """
        DELETE FROM treinos_realizados
        WHERE COALESCE(atleta_id, usuario_id) = %s
          AND semana_numero > %s
        """,
        (atleta_id, semana_atual),
    )
    conn.commit()
    conn.close()
