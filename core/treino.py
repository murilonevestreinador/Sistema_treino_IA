import json

from config.estrutura import estrutura_treinos
from core.banco import conectar
from core.carga import categoria_movimento, descrever_prescricao_carga
from core.periodizacao import definir_parametros_semana
from core.progresso import (
    buscar_avaliacao_referencia,
    buscar_ultima_execucao,
    listar_preferencias_substituicao,
)
from core.selecao import (
    assinatura_equipamento_exercicio,
    categoria_exige_diversidade_equipamento,
    normalizar_categoria_funcional,
    escolher_exercicio_por_categoria,
)


def gerar_treino_semana(atleta, exercicios_db, semana_numero, fase):
    atleta_contexto = dict(atleta)
    atleta_contexto["preferencias_substituicao"] = listar_preferencias_substituicao(atleta["id"])
    frequencia = max(1, min(5, int(atleta.get("treinos_musculacao_semana", 1))))
    estrutura = estrutura_treinos[fase][frequencia]
    series, reps, carga, rpe, execucao, intencao = definir_parametros_semana(fase, semana_numero)

    treinos = {}
    categorias_avaliadas = set()
    for nome_treino, categorias in estrutura.items():
        nomes_usados = set()
        assinaturas_por_categoria = {}
        bloco = []

        for categoria in categorias:
            categoria_normalizada = normalizar_categoria_funcional(categoria)
            assinaturas_ja_usadas = assinaturas_por_categoria.setdefault(categoria_normalizada, set())
            exercicio = escolher_exercicio_por_categoria(
                exercicios_db,
                categoria,
                fase,
                atleta_contexto,
                nomes_ja_usados=nomes_usados,
                assinaturas_ja_usadas=assinaturas_ja_usadas,
            )
            if not exercicio:
                continue

            nomes_usados.add(exercicio["nome"])
            if categoria_exige_diversidade_equipamento(categoria):
                assinaturas_ja_usadas.add(assinatura_equipamento_exercicio(exercicio))
            categoria_mov = categoria_movimento(categoria)
            avaliacao = buscar_avaliacao_referencia(atleta["id"], categoria_mov) if semana_numero >= 3 and categoria_mov else None
            ultima_execucao = buscar_ultima_execucao(
                atleta["id"],
                exercicio_nome=exercicio["nome"],
            ) or (
                buscar_ultima_execucao(atleta["id"], categoria_movimento=categoria_mov)
                if categoria_mov
                else None
            )
            prescricao_carga = descrever_prescricao_carga(
                semana_numero,
                fase,
                {"categoria": categoria, "nome": exercicio["nome"]},
                rpe,
                avaliacao=avaliacao,
                ultima_execucao=ultima_execucao,
            )
            if semana_numero == 2 and categoria_mov:
                if categoria_mov in categorias_avaliadas:
                    prescricao_carga["modo_carga"] = "qualitativa"
                    prescricao_carga["orientacao_carga"] = (
                        "Use a referencia do exercicio principal avaliado nesta categoria e mantenha tecnica perfeita."
                    )
                else:
                    categorias_avaliadas.add(categoria_mov)

            bloco.append(
                {
                    "nome": exercicio["nome"],
                    "categoria": categoria,
                    "principal_musculo": exercicio.get("principal_musculo"),
                    "series": series,
                    "reps": reps,
                    "descanso": "60-90s",
                    "carga": carga,
                    "carga_sugerida": prescricao_carga.get("carga_sugerida"),
                    "modo_carga": prescricao_carga.get("modo_carga"),
                    "categoria_movimento": prescricao_carga.get("categoria_movimento"),
                    "orientacao_carga": prescricao_carga.get("orientacao_carga"),
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


def invalidar_treinos_gerados_desde_semana(atleta_id, semana_inicial):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM treinos_gerados
        WHERE COALESCE(atleta_id, usuario_id) = %s
          AND semana_numero >= %s
        """,
        (atleta_id, semana_inicial),
    )
    conn.commit()
    conn.close()


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
    cursor.execute(
        """
        DELETE FROM execucao_exercicio
        WHERE COALESCE(atleta_id, usuario_id) = %s
        """,
        (atleta_id,),
    )
    cursor.execute(
        """
        DELETE FROM avaliacao_forca
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
    cursor.execute(
        """
        DELETE FROM execucao_exercicio
        WHERE COALESCE(atleta_id, usuario_id) = %s
          AND semana_numero > %s
        """,
        (atleta_id, semana_atual),
    )
    conn.commit()
    conn.close()
