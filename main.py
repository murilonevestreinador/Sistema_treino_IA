from core.exercicios import carregar_exercicios
from core.treino import gerar_treino
from core.cronograma import gerar_cronograma, gerar_mensagem_usuario


# =========================
# ATLETA EXEMPLO
# =========================

atleta = {
    "nome": "João",
    "tem_prova": True,
    "data_prova": "2025-09-20",
    "treinos_semana": 3,
    "experiencia_musculacao": "intermediario",
    "dor": "joelho",
    "semana_ciclo": 1
}


# =========================
# CRONOGRAMA
# =========================

cronograma, fases, total_semanas = gerar_cronograma(atleta)

mensagem = gerar_mensagem_usuario(atleta, fases, total_semanas)

print("\n===== MENSAGEM USUÁRIO =====\n")
print(mensagem)


# =========================
# EXERCÍCIOS
# =========================

exercicios_db = carregar_exercicios()


# =========================
# GERAR TREINO
# =========================

treinos = gerar_treino(atleta, exercicios_db)


# =========================
# PRINT TREINOS
# =========================

for nome_treino, lista in treinos.items():

    print(f"\n===== TREINO {nome_treino} =====\n")

    for ex in lista:
        print(f"{ex['categoria'].upper()} -> {ex['nome']}")
        print(f"Séries: {ex['series']} | Reps: {ex['reps']}")
        print("----------------------------")

from core.banco import criar_tabelas
from core.usuarios import criar_usuario

# cria banco e tabela
criar_tabelas()

usuario = {
    "nome": "João",
    "email": "joao@email.com",
    "senha": "123456",
    "sexo": "masculino",
    "idade": 35,
    "peso": 75,
    "altura": 175,

    "objetivo": "performance",
    "distancia_principal": "10km",
    "tempo_pratica": "2 anos",
    "treinos_corrida_semana": 4,

    "tem_prova": 1,
    "data_prova": "2025-09-20",
    "distancia_prova": "10km",

    "treinos_musculacao_semana": 3,
    "local_treino": "academia",
    "experiencia_musculacao": "intermediario",

    "historico_lesao": "joelho",
    "dor_atual": "leve"
}

criar_usuario(usuario)

print("Usuário criado com sucesso!")   