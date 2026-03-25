from core.banco import conectar


TIPOS_USUARIO_VALIDOS = {"atleta", "treinador", "admin"}
STATUS_CONTA_VALIDOS = {"ativo", "inativo", "suspenso", "cancelado"}
STATUS_CONTA_COM_ACESSO = {"ativo"}


def normalizar_tipo_usuario(tipo_usuario, is_admin=0):
    tipo = (tipo_usuario or "").strip().lower()
    if int(is_admin or 0) == 1:
        return "admin"
    if tipo in TIPOS_USUARIO_VALIDOS:
        return tipo
    return "atleta"


def normalizar_status_conta(status_conta):
    status = (status_conta or "").strip().lower()
    if status in STATUS_CONTA_VALIDOS:
        return status
    return "ativo"


def eh_admin(usuario):
    return bool(usuario and normalizar_tipo_usuario(usuario.get("tipo_usuario"), usuario.get("is_admin")) == "admin")


def eh_treinador(usuario):
    return bool(usuario and normalizar_tipo_usuario(usuario.get("tipo_usuario"), usuario.get("is_admin")) == "treinador")


def eh_atleta(usuario):
    return bool(usuario and normalizar_tipo_usuario(usuario.get("tipo_usuario"), usuario.get("is_admin")) == "atleta")


def conta_ativa(usuario):
    return bool(usuario and normalizar_status_conta(usuario.get("status_conta")) in STATUS_CONTA_COM_ACESSO)


def validar_admin(usuario):
    if not eh_admin(usuario):
        raise PermissionError("Apenas administradores podem acessar esta area.")


def validar_conta_ativa(usuario):
    if not conta_ativa(usuario):
        raise PermissionError("Sua conta nao possui permissao para acessar o sistema no momento.")


def treinador_pode_acessar_atleta(treinador_id, atleta_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM treinador_atleta
        WHERE treinador_id = %s
          AND atleta_id = %s
          AND COALESCE(status_vinculo, status, 'pendente') = 'ativo'
        LIMIT 1
        """,
        (treinador_id, atleta_id),
    )
    permitido = cursor.fetchone() is not None
    conn.close()
    return permitido


def validar_acesso_atleta(usuario, atleta_id):
    if eh_admin(usuario):
        return True
    if eh_atleta(usuario) and int(usuario.get("id") or 0) == int(atleta_id):
        return True
    if eh_treinador(usuario) and treinador_pode_acessar_atleta(usuario["id"], atleta_id):
        return True
    raise PermissionError("Voce nao tem permissao para acessar os dados deste atleta.")
