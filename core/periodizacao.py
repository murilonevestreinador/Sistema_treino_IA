def semana_do_ciclo(semana_global, tamanho_ciclo=4):
    if not semana_global:
        return 1
    return ((semana_global - 1) % tamanho_ciclo) + 1


def definir_parametros_semana(fase, semana_global):
    semana = semana_do_ciclo(semana_global)

    if fase == "base":
        opcoes = {
            1: (3, 12, "leve", "5-6", "controlada", "2s subir / 2s descer"),
            2: (3, 10, "moderada", "6-7", "controlada", "2s subir / 2s descer"),
            3: (4, 8, "moderada-alta", "7", "controlada", "2s subir / 2s descer"),
            4: (3, 10, "moderada", "6", "controlada", "2s subir / 2s descer"),
        }
        return opcoes[semana]

    if fase == "especifico":
        opcoes = {
            1: (3, 8, "moderada", "6-7", "explosiva", "movimento rapido"),
            2: (4, 6, "moderada-alta", "7-8", "explosiva", "movimento rapido"),
            3: (4, 5, "alta", "8", "explosiva", "movimento rapido"),
            4: (3, 6, "moderada", "6-7", "explosiva", "movimento rapido"),
        }
        return opcoes[semana]

    if fase == "polimento":
        return 2, 4, "leve", "5", "explosiva", "movimento rapido"

    if fase == "retorno":
        opcoes = {
            1: (2, 12, "leve", "5", "controlada", "lento"),
            2: (3, 10, "leve", "5-6", "controlada", "lento"),
            3: (3, 8, "moderada", "6", "controlada", "normal"),
            4: (3, 8, "moderada", "6-7", "controlada", "normal"),
        }
        return opcoes[semana]

    return 3, 10, "moderada", "6", "controlada", "normal"
