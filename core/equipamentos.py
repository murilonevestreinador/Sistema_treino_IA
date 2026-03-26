import re
import unicodedata


AMBIENTES_TREINO_FORCA = [
    "academia_completa",
    "casa",
    "academia_limitada",
]

AMBIENTE_LABELS = {
    "academia_completa": "Academia completa",
    "casa": "Em casa",
    "academia_limitada": "Academia de condominio / academia limitada",
}

EQUIPAMENTOS_CATALOGO = [
    ("banco", "Banco"),
    ("banco_romano", "Banco romano"),
    ("banco_scott", "Banco scott"),
    ("barra", "Barra"),
    ("barra_hexagonal", "Barra hexagonal"),
    ("barra_fixa", "Barra fixa"),
    ("barras_paralelas", "Barras paralelas"),
    ("bola_suica", "Bola suica"),
    ("cadeira_adutora", "Cadeira adutora"),
    ("cadeira_extensora", "Cadeira extensora"),
    ("cadeira_flexora", "Cadeira flexora"),
    ("caixa", "Caixa"),
    ("cama_elastica", "Cama elastica"),
    ("caneleira", "Caneleira"),
    ("crossover", "Crossover"),
    ("elevacao_pelvica", "Elevacao pelvica"),
    ("elastico", "Elastico"),
    ("halter", "Halter"),
    ("kettlebell", "Kettlebell"),
    ("leg_press_45o", "Leg press 45o"),
    ("leg_press_horizontal", "Leg press horizontal"),
    ("mesa_flexora", "Mesa flexora"),
    ("maquina_abdominal", "Maquina abdominal"),
    ("maquina_paralelas", "Maquina paralelas"),
    ("panturrilha_sentado", "Panturrilha sentado"),
    ("polia", "Polia"),
    ("puxador", "Puxador"),
    ("remada_cavalinho", "Remada cavalinho"),
    ("roda_abdominal", "Roda abdominal"),
    ("sissy_squat", "Sissy squat"),
    ("smith", "Smith"),
    ("supino_declinado", "Supino declinado"),
    ("supino_inclinado", "Supino inclinado"),
    ("supino_reto", "Supino reto"),
    ("trx", "TRX"),
    ("medicine_ball", "Medicine ball"),
    ("peck_deck", "Peck deck"),
]

EQUIPAMENTO_LABELS = {chave: rotulo for chave, rotulo in EQUIPAMENTOS_CATALOGO}
EQUIPAMENTO_OPCOES = [chave for chave, _ in EQUIPAMENTOS_CATALOGO]
EQUIPAMENTOS_LIVRES = {"", "peso_corporal", "livre", "sem_equipamento", "nenhum", "na"}


def _slugificar(valor):
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    return texto.strip("_")


EQUIPAMENTO_ALIASES = {
    _slugificar(referencia): chave
    for chave, rotulo in EQUIPAMENTOS_CATALOGO
    for referencia in {chave, rotulo}
}


def rotulo_ambiente_treino(valor):
    return AMBIENTE_LABELS.get(valor, AMBIENTE_LABELS["academia_completa"])


def rotulo_equipamento(chave):
    return EQUIPAMENTO_LABELS.get(chave, (chave or "").replace("_", " ").title())


def ambiente_requer_inventario(valor):
    return normalizar_ambiente_treino_forca(valor) in {"casa", "academia_limitada"}


def normalizar_ambiente_treino_forca(valor, valor_legado=None):
    ambiente = _slugificar(valor)
    if ambiente in {"academia_completa", "casa", "academia_limitada"}:
        return ambiente
    if ambiente == "academia":
        return "academia_completa"
    if ambiente == "condominio":
        return "academia_limitada"
    if ambiente == "hibrido":
        return "academia_completa"

    legado = _slugificar(valor_legado)
    if legado in {"academia", "hibrido", ""}:
        return "academia_completa"
    if legado == "casa":
        return "academia_completa"
    return "academia_completa"


def normalizar_equipamento(valor):
    chave = _slugificar(valor)
    if chave in EQUIPAMENTOS_LIVRES:
        return None
    return EQUIPAMENTO_ALIASES.get(chave, chave or None)


def normalizar_lista_equipamentos(valores):
    equipamentos = []
    vistos = set()
    for valor in valores or []:
        chave = normalizar_equipamento(valor)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        equipamentos.append(chave)
    return equipamentos


def parsear_equipamentos_exercicio(valor):
    if valor is None:
        return []

    texto = str(valor).strip()
    if not texto:
        return []

    equipamentos = []
    vistos = set()
    for parte in texto.split("/"):
        chave = normalizar_equipamento(parte)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        equipamentos.append(chave)
    return equipamentos


def exercicio_compativel_com_equipamentos(exercicio, atleta):
    ambiente = normalizar_ambiente_treino_forca(
        atleta.get("ambiente_treino_forca"),
        atleta.get("local_treino"),
    )
    if not ambiente_requer_inventario(ambiente):
        return True

    equipamentos_necessarios = normalizar_lista_equipamentos(exercicio.get("equipamentos_necessarios") or [])
    if not equipamentos_necessarios:
        return True

    equipamentos_atleta = set(normalizar_lista_equipamentos(atleta.get("equipamentos_disponiveis") or []))
    return all(item in equipamentos_atleta for item in equipamentos_necessarios)
