import bcrypt
import hashlib
import os
import secrets
from datetime import datetime, timedelta

from core.banco import conectar
from core.calendario import inicio_semana_local
from core.equipamentos import normalizar_ambiente_treino_forca, normalizar_lista_equipamentos
from core.permissoes import eh_admin, normalizar_status_conta, normalizar_tipo_usuario


def _linha_para_dict(linha):
    return dict(linha) if linha else None


def _normalizar_sexo(sexo):
    sexo_normalizado = (sexo or "outro").strip().lower()
    if sexo_normalizado in {"masculino", "feminino"}:
        return sexo_normalizado
    return "outro"


def _somente_digitos(valor):
    return "".join(char for char in str(valor or "") if char.isdigit())


def normalizar_cpf(cpf):
    return _somente_digitos(cpf)


def formatar_cpf(cpf):
    cpf_normalizado = normalizar_cpf(cpf)
    if len(cpf_normalizado) != 11:
        return cpf_normalizado
    return f"{cpf_normalizado[:3]}.{cpf_normalizado[3:6]}.{cpf_normalizado[6:9]}-{cpf_normalizado[9:]}"


def validar_cpf(cpf):
    cpf_normalizado = normalizar_cpf(cpf)
    if not cpf_normalizado:
        return False, "Informe o CPF."
    if len(cpf_normalizado) != 11:
        return False, "Informe um CPF com 11 digitos."
    if cpf_normalizado == cpf_normalizado[0] * 11:
        return False, "Informe um CPF valido."

    soma = sum(int(digito) * peso for digito, peso in zip(cpf_normalizado[:9], range(10, 1, -1)))
    digito_1 = ((soma * 10) % 11) % 10
    soma = sum(int(digito) * peso for digito, peso in zip(cpf_normalizado[:10], range(11, 1, -1)))
    digito_2 = ((soma * 10) % 11) % 10
    if cpf_normalizado[-2:] != f"{digito_1}{digito_2}":
        return False, "Informe um CPF valido."
    return True, cpf_normalizado


def normalizar_telefone(telefone):
    telefone_normalizado = _somente_digitos(telefone)
    if telefone_normalizado.startswith("55") and len(telefone_normalizado) in {12, 13}:
        telefone_normalizado = telefone_normalizado[2:]
    return telefone_normalizado


def formatar_telefone(telefone):
    telefone_normalizado = normalizar_telefone(telefone)
    if len(telefone_normalizado) == 11:
        return f"({telefone_normalizado[:2]}) {telefone_normalizado[2:7]}-{telefone_normalizado[7:]}"
    if len(telefone_normalizado) == 10:
        return f"({telefone_normalizado[:2]}) {telefone_normalizado[2:6]}-{telefone_normalizado[6:]}"
    return telefone_normalizado


def validar_telefone(telefone):
    telefone_normalizado = normalizar_telefone(telefone)
    if not telefone_normalizado:
        return False, "Informe o telefone."
    if len(telefone_normalizado) not in {10, 11}:
        return False, "Informe um telefone valido com DDD."
    return True, telefone_normalizado


def normalizar_cref(cref):
    return (cref or "").strip().upper()


def validar_cref(cref, obrigatorio=False):
    cref_normalizado = normalizar_cref(cref)
    if obrigatorio and not cref_normalizado:
        return False, "Informe o CREF."
    if cref and len(cref_normalizado) < 4:
        return False, "Informe um CREF valido."
    return True, cref_normalizado or None


def diagnosticar_dados_checkout(usuario):
    usuario = usuario or {}
    faltantes = []
    cpf_ok, _ = validar_cpf(usuario.get("cpf") or usuario.get("cpf_cnpj"))
    telefone_ok, _ = validar_telefone(usuario.get("telefone") or usuario.get("mobilePhone"))
    if not cpf_ok:
        faltantes.append("CPF")
    if not telefone_ok:
        faltantes.append("telefone")

    if not faltantes:
        return {"ok": True, "faltantes": [], "mensagem": None}

    campos = " e ".join(faltantes) if len(faltantes) == 2 else faltantes[0]
    return {
        "ok": False,
        "faltantes": faltantes,
        "mensagem": f"Complete {campos} no seu perfil antes de seguir para o pagamento.",
    }


def _validar_dados_contato_usuario(dados, exigir_preenchimento=False, usuario_id=None, tipo_usuario=None):
    cpf_informado = dados.get("cpf") if "cpf" in dados else dados.get("cpf_cnpj")
    telefone_informado = dados.get("telefone") if "telefone" in dados else dados.get("mobilePhone")
    tipo_normalizado = normalizar_tipo_usuario(tipo_usuario or dados.get("tipo_usuario"), dados.get("is_admin"))

    cpf_normalizado = normalizar_cpf(cpf_informado)
    telefone_normalizado = normalizar_telefone(telefone_informado)

    if exigir_preenchimento and not cpf_normalizado:
        raise ValueError("Informe o CPF.")
    if exigir_preenchimento and not telefone_normalizado:
        raise ValueError("Informe o telefone.")

    if cpf_normalizado:
        cpf_ok, cpf_msg = validar_cpf(cpf_normalizado)
        if not cpf_ok:
            raise ValueError(cpf_msg)
        cpf_normalizado = cpf_msg
    elif cpf_informado not in (None, ""):
        raise ValueError("Informe um CPF valido.")

    if telefone_normalizado:
        telefone_ok, telefone_msg = validar_telefone(telefone_normalizado)
        if not telefone_ok:
            raise ValueError(telefone_msg)
        telefone_normalizado = telefone_msg
    elif telefone_informado not in (None, ""):
        raise ValueError("Informe um telefone valido com DDD.")

    if cpf_normalizado:
        usuario_existente = buscar_usuario_por_cpf(cpf_normalizado, tipo_usuario=tipo_normalizado)
        if usuario_existente and int(usuario_existente["id"]) != int(usuario_id or 0):
            raise ValueError(f"Ja existe uma conta {tipo_normalizado} com este CPF.")

    return {
        "cpf": cpf_normalizado or None,
        "telefone": telefone_normalizado or None,
    }


def listar_equipamentos_atleta(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT equipamento
        FROM atleta_equipamentos
        WHERE atleta_id = %s
        ORDER BY equipamento
        """,
        (usuario_id,),
    )
    equipamentos = [linha["equipamento"] for linha in cursor.fetchall()]
    conn.close()
    return normalizar_lista_equipamentos(equipamentos)


def salvar_equipamentos_atleta(usuario_id, equipamentos, origem="manual"):
    equipamentos_normalizados = normalizar_lista_equipamentos(equipamentos)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM atleta_equipamentos WHERE atleta_id = %s", (usuario_id,))
    for equipamento in equipamentos_normalizados:
        cursor.execute(
            """
            INSERT INTO atleta_equipamentos (atleta_id, equipamento, origem, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (usuario_id, equipamento, (origem or "manual").strip().lower()),
        )
    conn.commit()
    conn.close()
    return equipamentos_normalizados


def _anexar_contexto_treino_atleta(usuario_limpo):
    if not usuario_limpo or usuario_limpo.get("tipo_usuario") != "atleta":
        return usuario_limpo
    usuario_limpo["ambiente_treino_forca"] = normalizar_ambiente_treino_forca(
        usuario_limpo.get("ambiente_treino_forca"),
        usuario_limpo.get("local_treino"),
    )
    usuario_limpo["equipamentos_disponiveis"] = listar_equipamentos_atleta(usuario_limpo["id"])
    return usuario_limpo


def _usuario_sem_senha(usuario, incluir_contexto_treino=False):
    if not usuario:
        return None
    usuario_limpo = dict(usuario)
    usuario_limpo.pop("senha", None)
    usuario_limpo["sexo"] = _normalizar_sexo(usuario_limpo.get("sexo"))
    usuario_limpo["tipo_usuario"] = normalizar_tipo_usuario(
        usuario_limpo.get("tipo_usuario"),
        usuario_limpo.get("is_admin"),
    )
    usuario_limpo["status_conta"] = normalizar_status_conta(usuario_limpo.get("status_conta"))
    usuario_limpo["onboarding_completo"] = int(usuario_limpo.get("onboarding_completo") or 0)
    usuario_limpo["is_admin"] = int(usuario_limpo.get("is_admin") or 0)
    usuario_limpo["aceitou_termos"] = int(usuario_limpo.get("aceitou_termos") or 0)
    usuario_limpo["aceitou_privacidade"] = int(usuario_limpo.get("aceitou_privacidade") or 0)
    usuario_limpo["cpf"] = normalizar_cpf(usuario_limpo.get("cpf") or usuario_limpo.get("cpf_cnpj")) or None
    usuario_limpo["telefone"] = normalizar_telefone(usuario_limpo.get("telefone") or usuario_limpo.get("mobilePhone")) or None
    usuario_limpo["cpf_cnpj"] = usuario_limpo["cpf"]
    usuario_limpo["mobilePhone"] = usuario_limpo["telefone"]
    usuario_limpo["cpf_formatado"] = formatar_cpf(usuario_limpo["cpf"])
    usuario_limpo["telefone_formatado"] = formatar_telefone(usuario_limpo["telefone"])
    usuario_limpo["cref"] = normalizar_cref(usuario_limpo.get("cref")) or None
    usuario_limpo["ambiente_treino_forca"] = normalizar_ambiente_treino_forca(
        usuario_limpo.get("ambiente_treino_forca"),
        usuario_limpo.get("local_treino"),
    )
    if incluir_contexto_treino:
        return _anexar_contexto_treino_atleta(usuario_limpo)
    return usuario_limpo


def _buscar_usuario_por_coluna(coluna, valor, incluir_senha=False, incluir_contexto_treino=False):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM usuarios WHERE {coluna} = %s", (valor,))
    usuario = _linha_para_dict(cursor.fetchone())
    conn.close()
    if incluir_senha:
        return usuario
    return _usuario_sem_senha(usuario, incluir_contexto_treino=incluir_contexto_treino)


def hash_senha(senha):
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha, senha_hash):
    if not senha_hash:
        return False
    senha_hash_bytes = senha_hash if isinstance(senha_hash, bytes) else senha_hash.encode("utf-8")
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash_bytes)


def buscar_usuario_por_email(email):
    return _buscar_usuario_por_coluna("email", (email or "").strip().lower(), incluir_contexto_treino=True)


def buscar_usuario_por_cpf(cpf, tipo_usuario=None):
    cpf_normalizado = normalizar_cpf(cpf)
    if not cpf_normalizado:
        return None
    conn = conectar()
    cursor = conn.cursor()
    if tipo_usuario:
        cursor.execute(
            "SELECT * FROM usuarios WHERE cpf = %s AND tipo_usuario = %s ORDER BY id ASC LIMIT 1",
            (cpf_normalizado, normalizar_tipo_usuario(tipo_usuario)),
        )
    else:
        cursor.execute("SELECT * FROM usuarios WHERE cpf = %s ORDER BY id ASC LIMIT 1", (cpf_normalizado,))
    usuario = _linha_para_dict(cursor.fetchone())
    conn.close()
    return _usuario_sem_senha(usuario, incluir_contexto_treino=True)


def buscar_usuario_por_id(usuario_id):
    return _buscar_usuario_por_coluna("id", usuario_id, incluir_contexto_treino=True)


def criar_usuario(dados):
    data_consentimento = dados.get("data_consentimento")
    if not data_consentimento and (dados.get("aceitou_termos") or dados.get("aceitou_privacidade")):
        data_consentimento = datetime.now().isoformat(timespec="seconds")
    tipo_usuario = normalizar_tipo_usuario(dados.get("tipo_usuario"), dados.get("is_admin"))
    contato = _validar_dados_contato_usuario(dados, exigir_preenchimento=True, tipo_usuario=tipo_usuario)
    cref_obrigatorio = tipo_usuario == "treinador"
    cref_ok, cref_msg = validar_cref(dados.get("cref"), obrigatorio=cref_obrigatorio)
    if not cref_ok:
        raise ValueError(cref_msg)

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (
            nome, apelido, foto_perfil, email, cpf, telefone, cref, senha, sexo, tipo_usuario, status_conta, onboarding_completo, is_admin,
            idade, peso, altura, objetivo, distancia_principal, tempo_pratica,
            treinos_corrida_semana, tem_prova, data_prova, distancia_prova,
            treinos_musculacao_semana, local_treino, ambiente_treino_forca, experiencia_musculacao,
            historico_lesao, dor_atual, aceitou_termos, aceitou_privacidade, data_consentimento
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            (dados.get("nome") or "").strip(),
            (dados.get("apelido") or "").strip() or None,
            dados.get("foto_perfil"),
            (dados.get("email") or "").strip().lower(),
            contato["cpf"],
            contato["telefone"],
            cref_msg,
            hash_senha(dados.get("senha") or ""),
            _normalizar_sexo(dados.get("sexo")),
            tipo_usuario,
            normalizar_status_conta(dados.get("status_conta")),
            int(dados.get("onboarding_completo", 0)),
            int(tipo_usuario == "admin"),
            dados.get("idade"),
            dados.get("peso"),
            dados.get("altura"),
            dados.get("objetivo", "performance"),
            dados.get("distancia_principal", ""),
            dados.get("tempo_pratica", ""),
            dados.get("treinos_corrida_semana", 0),
            int(bool(dados.get("tem_prova", 0))),
            dados.get("data_prova"),
            dados.get("distancia_prova", ""),
            dados.get("treinos_musculacao_semana", 0),
            dados.get("local_treino", "") if tipo_usuario == "atleta" else None,
            normalizar_ambiente_treino_forca(dados.get("ambiente_treino_forca"), dados.get("local_treino"))
            if tipo_usuario == "atleta"
            else None,
            dados.get("experiencia_musculacao", ""),
            dados.get("historico_lesao", ""),
            dados.get("dor_atual", ""),
            int(bool(dados.get("aceitou_termos", 0))),
            int(bool(dados.get("aceitou_privacidade", 0))),
            data_consentimento,
        ),
    )
    usuario_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    return usuario_id


def autenticar_usuario(email, senha):
    usuario = _buscar_usuario_por_coluna("email", (email or "").strip().lower(), incluir_senha=True)
    if not usuario:
        return None
    if not verificar_senha(senha or "", usuario.get("senha")):
        return None
    return _usuario_sem_senha(usuario, incluir_contexto_treino=True)


def atualizar_senha_por_email(email, nova_senha):
    email_normalizado = (email or "").strip().lower()
    usuario = _buscar_usuario_por_coluna("email", email_normalizado, incluir_senha=True)
    if not usuario:
        return False

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET senha = %s
        WHERE email = %s
        """,
        (hash_senha(nova_senha or ""), email_normalizado),
    )
    conn.commit()
    conn.close()
    return True


def _hash_codigo_recuperacao(codigo):
    return hashlib.sha256((codigo or "").encode("utf-8")).hexdigest()


def solicitar_codigo_recuperacao(email, minutos_validade=15):
    usuario = _buscar_usuario_por_coluna("email", (email or "").strip().lower(), incluir_senha=True)
    if not usuario:
        return None

    codigo = f"{secrets.randbelow(1000000):06d}"
    expira_em = (datetime.now() + timedelta(minutes=minutos_validade)).isoformat(timespec="seconds")

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE recuperacao_senha
        SET usado_em = %s
        WHERE usuario_id = %s AND usado_em IS NULL
        """,
        (datetime.now().isoformat(timespec="seconds"), usuario["id"]),
    )
    cursor.execute(
        """
        INSERT INTO recuperacao_senha (usuario_id, codigo_hash, expira_em)
        VALUES (%s, %s, %s)
        """,
        (usuario["id"], _hash_codigo_recuperacao(codigo), expira_em),
    )
    conn.commit()
    conn.close()

    return {
        "codigo": codigo,
        "expira_em": expira_em,
        "usuario_id": usuario["id"],
    }


def redefinir_senha_com_codigo(email, codigo, nova_senha):
    usuario = _buscar_usuario_por_coluna("email", (email or "").strip().lower(), incluir_senha=True)
    if not usuario:
        return False, "Codigo invalido ou expirado."

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, codigo_hash, expira_em
        FROM recuperacao_senha
        WHERE usuario_id = %s
          AND usado_em IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (usuario["id"],),
    )
    token = cursor.fetchone()

    if not token:
        conn.close()
        return False, "Codigo invalido ou expirado."

    if datetime.fromisoformat(token["expira_em"]) < datetime.now():
        cursor.execute(
            "UPDATE recuperacao_senha SET usado_em = %s WHERE id = %s",
            (datetime.now().isoformat(timespec="seconds"), token["id"]),
        )
        conn.commit()
        conn.close()
        return False, "Codigo expirado. Solicite um novo codigo."

    if token["codigo_hash"] != _hash_codigo_recuperacao(codigo):
        conn.close()
        return False, "Codigo invalido ou expirado."

    cursor.execute(
        """
        UPDATE usuarios
        SET senha = %s
        WHERE id = %s
        """,
        (hash_senha(nova_senha or ""), usuario["id"]),
    )
    cursor.execute(
        "UPDATE recuperacao_senha SET usado_em = %s WHERE id = %s",
        (datetime.now().isoformat(timespec="seconds"), token["id"]),
    )
    conn.commit()
    conn.close()
    return True, "Senha atualizada com sucesso."


def atualizar_usuario_onboarding(usuario_id, dados_onboarding):
    ambiente_treino_forca = normalizar_ambiente_treino_forca(
        dados_onboarding.get("ambiente_treino_forca"),
        dados_onboarding.get("local_treino"),
    )
    plano_inicio_em = inicio_semana_local().isoformat()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET objetivo = %s,
            distancia_principal = %s,
            tempo_pratica = %s,
            treinos_corrida_semana = %s,
            tem_prova = %s,
            data_prova = %s,
            distancia_prova = %s,
            treinos_musculacao_semana = %s,
            local_treino = %s,
            ambiente_treino_forca = %s,
            plano_inicio_em = COALESCE(plano_inicio_em, %s),
            experiencia_musculacao = %s,
            historico_lesao = %s,
            dor_atual = %s,
            onboarding_completo = 1
        WHERE id = %s
        """,
        (
            dados_onboarding.get("objetivo", "performance"),
            dados_onboarding.get("distancia_principal", ""),
            dados_onboarding.get("tempo_pratica", ""),
            int(dados_onboarding.get("treinos_corrida_semana", 0)),
            int(bool(dados_onboarding.get("tem_prova", 0))),
            dados_onboarding.get("data_prova"),
            dados_onboarding.get("distancia_prova", ""),
            int(dados_onboarding.get("treinos_musculacao_semana", 1)),
            ambiente_treino_forca,
            ambiente_treino_forca,
            plano_inicio_em,
            dados_onboarding.get("experiencia_musculacao", ""),
            dados_onboarding.get("historico_lesao", ""),
            dados_onboarding.get("dor_atual", ""),
            usuario_id,
        ),
    )
    conn.commit()
    conn.close()
    if "equipamentos_disponiveis" in dados_onboarding:
        salvar_equipamentos_atleta(usuario_id, dados_onboarding.get("equipamentos_disponiveis"), origem="manual")
    return buscar_usuario_por_id(usuario_id)


def marcar_onboarding(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET onboarding_completo = 1 WHERE id = %s", (usuario_id,))
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def redefinir_objetivo_atleta(usuario_id, dados_objetivo):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET objetivo = %s,
            tem_prova = %s,
            data_prova = %s,
            distancia_prova = %s,
            distancia_principal = %s,
            treinos_musculacao_semana = %s,
            plano_inicio_em = %s
        WHERE id = %s
        """,
        (
            dados_objetivo.get("objetivo", "performance"),
            int(bool(dados_objetivo.get("tem_prova", 0))),
            dados_objetivo.get("data_prova"),
            dados_objetivo.get("distancia_prova", ""),
            dados_objetivo.get("distancia_principal", ""),
            int(dados_objetivo.get("treinos_musculacao_semana", 1)),
            inicio_semana_local().isoformat(),
            usuario_id,
        ),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def atualizar_perfil_usuario(usuario_id, dados_perfil):
    usuario_atual = buscar_usuario_por_id(usuario_id)
    tipo_usuario = normalizar_tipo_usuario(
        dados_perfil.get("tipo_usuario") or (usuario_atual or {}).get("tipo_usuario"),
        dados_perfil.get("is_admin") or (usuario_atual or {}).get("is_admin"),
    )
    contato = _validar_dados_contato_usuario(
        dados_perfil,
        exigir_preenchimento=False,
        usuario_id=usuario_id,
        tipo_usuario=tipo_usuario,
    )
    cref_valor = (usuario_atual or {}).get("cref")
    if "cref" in dados_perfil:
        cref_ok, cref_msg = validar_cref(dados_perfil.get("cref"), obrigatorio=False)
        if not cref_ok:
            raise ValueError(cref_msg)
        cref_valor = cref_msg
    ambiente_treino_forca = normalizar_ambiente_treino_forca(
        dados_perfil.get("ambiente_treino_forca") if "ambiente_treino_forca" in dados_perfil else usuario_atual.get("ambiente_treino_forca"),
        dados_perfil.get("local_treino") if "local_treino" in dados_perfil else usuario_atual.get("local_treino"),
    )
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET nome = %s,
            apelido = %s,
            foto_perfil = %s,
            cpf = %s,
            telefone = %s,
            cref = %s,
            local_treino = %s,
            ambiente_treino_forca = %s
        WHERE id = %s
        """,
        (
            (dados_perfil.get("nome") or "").strip(),
            (dados_perfil.get("apelido") or "").strip() or None,
            dados_perfil.get("foto_perfil"),
            contato["cpf"],
            contato["telefone"],
            cref_valor,
            ambiente_treino_forca if usuario_atual.get("tipo_usuario") == "atleta" else None,
            ambiente_treino_forca if usuario_atual.get("tipo_usuario") == "atleta" else None,
            usuario_id,
        ),
    )
    conn.commit()
    conn.close()
    if usuario_atual.get("tipo_usuario") == "atleta" and "equipamentos_disponiveis" in dados_perfil:
        salvar_equipamentos_atleta(usuario_id, dados_perfil.get("equipamentos_disponiveis"), origem="manual")
    return buscar_usuario_por_id(usuario_id)


def atualizar_tipo_usuario(usuario_id, tipo_usuario):
    tipo_normalizado = normalizar_tipo_usuario(tipo_usuario)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET tipo_usuario = %s,
            is_admin = %s
        WHERE id = %s
        """,
        (tipo_normalizado, int(tipo_normalizado == "admin"), usuario_id),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def alterar_papel_usuario_por_admin(admin_id, usuario_id, tipo_usuario):
    tipo_normalizado = normalizar_tipo_usuario(tipo_usuario)
    conn = conectar()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM usuarios WHERE id = %s FOR UPDATE", (admin_id,))
        admin = _linha_para_dict(cursor.fetchone())
        if not eh_admin(admin):
            raise PermissionError("Apenas administradores podem alterar papeis.")

        cursor.execute("SELECT * FROM usuarios WHERE id = %s FOR UPDATE", (usuario_id,))
        usuario = _linha_para_dict(cursor.fetchone())
        if not usuario:
            conn.rollback()
            return False, "Usuario nao encontrado.", None

        tipo_atual = normalizar_tipo_usuario(usuario.get("tipo_usuario"), usuario.get("is_admin"))
        if tipo_atual == tipo_normalizado:
            conn.rollback()
            return True, "Nenhuma alteracao foi necessaria.", _usuario_sem_senha(usuario)

        if tipo_atual == "admin" and tipo_normalizado != "admin":
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM usuarios
                WHERE COALESCE(is_admin, 0) = 1
                   OR LOWER(COALESCE(tipo_usuario, '')) = 'admin'
                """
            )
            total_admins = int((cursor.fetchone() or {}).get("total") or 0)
            if total_admins <= 1:
                conn.rollback()
                return False, "Nao e possivel remover o privilegio do ultimo admin do sistema.", _usuario_sem_senha(usuario)

        cursor.execute(
            """
            UPDATE usuarios
            SET tipo_usuario = %s,
                is_admin = %s
            WHERE id = %s
            """,
            (tipo_normalizado, int(tipo_normalizado == "admin"), usuario_id),
        )
        conn.commit()
    finally:
        conn.close()

    usuario_atualizado = buscar_usuario_por_id(usuario_id)
    if tipo_atual != "admin" and tipo_normalizado == "admin":
        return True, "Usuario promovido para admin com sucesso.", usuario_atualizado
    if tipo_atual == "admin" and tipo_normalizado != "admin":
        return True, "Privilegio de admin removido com sucesso.", usuario_atualizado
    return True, "Papel atualizado com sucesso.", usuario_atualizado


def _bootstrap_admin_habilitado():
    return (os.getenv("ALLOW_ADMIN_BOOTSTRAP") or "").strip().lower() == "true"


def _bootstrap_admin_email():
    return (os.getenv("ADMIN_BOOTSTRAP_EMAIL") or "").strip().lower()


def tentar_bootstrap_primeiro_admin(usuario_id, email):
    email_normalizado = (email or "").strip().lower()
    email_autorizado = _bootstrap_admin_email()

    if not _bootstrap_admin_habilitado() or not email_autorizado or email_normalizado != email_autorizado:
        return buscar_usuario_por_id(usuario_id)

    conn = conectar()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT valor
            FROM configuracoes_sistema
            WHERE chave = 'admin_bootstrap_consumed'
            FOR UPDATE
            """
        )
        flag = _linha_para_dict(cursor.fetchone())
        if flag and (flag.get("valor") or "").strip().lower() == "true":
            conn.commit()
            return buscar_usuario_por_id(usuario_id)

        cursor.execute(
            """
            SELECT id
            FROM usuarios
            WHERE COALESCE(is_admin, 0) = 1
               OR LOWER(COALESCE(tipo_usuario, '')) = 'admin'
            LIMIT 1
            FOR UPDATE
            """
        )
        admin_existente = _linha_para_dict(cursor.fetchone())
        if admin_existente:
            cursor.execute(
                """
                INSERT INTO configuracoes_sistema (chave, valor, updated_at)
                VALUES ('admin_bootstrap_consumed', 'true', CURRENT_TIMESTAMP)
                ON CONFLICT (chave) DO UPDATE
                SET valor = EXCLUDED.valor,
                    updated_at = CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return buscar_usuario_por_id(usuario_id)

        cursor.execute(
            """
            UPDATE usuarios
            SET tipo_usuario = 'admin',
                is_admin = 1
            WHERE id = %s
              AND LOWER(COALESCE(email, '')) = %s
            """,
            (usuario_id, email_autorizado),
        )
        if cursor.rowcount:
            cursor.execute(
                """
                INSERT INTO configuracoes_sistema (chave, valor, updated_at)
                VALUES ('admin_bootstrap_consumed', 'true', CURRENT_TIMESTAMP)
                ON CONFLICT (chave) DO UPDATE
                SET valor = EXCLUDED.valor,
                    updated_at = CURRENT_TIMESTAMP
                """
            )

        conn.commit()
    finally:
        conn.close()

    return buscar_usuario_por_id(usuario_id)


def atualizar_status_conta(usuario_id, status_conta):
    status_normalizado = normalizar_status_conta(status_conta)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET status_conta = %s
        WHERE id = %s
        """,
        (status_normalizado, usuario_id),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def redefinir_senha_usuario(usuario_id, nova_senha):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET senha = %s
        WHERE id = %s
        """,
        (hash_senha(nova_senha or ""), usuario_id),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def alterar_senha_usuario_autenticado(usuario_id, senha_atual, nova_senha, confirmacao_nova_senha):
    senha_atual = senha_atual or ""
    nova_senha = nova_senha or ""
    confirmacao_nova_senha = confirmacao_nova_senha or ""

    if not senha_atual.strip():
        return False, "Informe sua senha atual."
    if not nova_senha:
        return False, "Informe a nova senha."
    if not confirmacao_nova_senha:
        return False, "Confirme a nova senha."
    if nova_senha != confirmacao_nova_senha:
        return False, "A confirmacao da nova senha nao confere."
    if len(nova_senha) < 8:
        return False, "A nova senha deve ter pelo menos 8 caracteres."

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, senha FROM usuarios WHERE id = %s", (usuario_id,))
    usuario = _linha_para_dict(cursor.fetchone())

    if not usuario:
        conn.close()
        return False, "Usuario nao encontrado."
    if not verificar_senha(senha_atual, usuario.get("senha")):
        conn.close()
        return False, "A senha atual informada esta incorreta."
    if verificar_senha(nova_senha, usuario.get("senha")):
        conn.close()
        return False, "A nova senha deve ser diferente da senha atual."

    cursor.execute(
        """
        UPDATE usuarios
        SET senha = %s
        WHERE id = %s
        """,
        (hash_senha(nova_senha), usuario_id),
    )
    conn.commit()
    conn.close()
    return True, "Senha alterada com sucesso."


def listar_usuarios(
    busca=None,
    tipo_usuario=None,
    status_conta=None,
):
    filtros = []
    params = []

    busca_normalizada = (busca or "").strip().lower()
    if busca_normalizada:
        filtros.append("(LOWER(COALESCE(u.nome, '')) LIKE %s OR LOWER(COALESCE(u.email, '')) LIKE %s)")
        termo = f"%{busca_normalizada}%"
        params.extend([termo, termo])

    tipo_normalizado = (tipo_usuario or "").strip().lower()
    if tipo_normalizado:
        filtros.append("LOWER(COALESCE(u.tipo_usuario, '')) = %s")
        params.append(tipo_normalizado)

    status_normalizado = (status_conta or "").strip().lower()
    if status_normalizado:
        filtros.append("LOWER(COALESCE(u.status_conta, 'ativo')) = %s")
        params.append(status_normalizado)

    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT
            u.*,
            a.status AS assinatura_status,
            a.data_inicio AS assinatura_data_inicio,
            a.data_fim AS assinatura_data_fim,
            COALESCE(a.valor_total_cobrado, a.valor) AS assinatura_valor,
            p.nome AS plano_nome,
            p.codigo AS plano_codigo
        FROM usuarios u
        LEFT JOIN LATERAL (
            SELECT *
            FROM assinaturas ax
            WHERE ax.usuario_id = u.id
            ORDER BY
                CASE ax.status
                    WHEN 'ativa' THEN 0
                    WHEN 'trial' THEN 1
                    WHEN 'inadimplente' THEN 2
                    WHEN 'cancelada' THEN 3
                    ELSE 4
                END,
                COALESCE(ax.created_at, CURRENT_TIMESTAMP) DESC,
                ax.id DESC
            LIMIT 1
        ) a ON TRUE
        LEFT JOIN planos p ON p.id = a.plano_id
        {where_sql}
        ORDER BY COALESCE(u.data_criacao, CURRENT_TIMESTAMP) DESC, u.id DESC
        """,
        tuple(params),
    )
    usuarios = [_usuario_sem_senha(item) | {
        "assinatura_status": item.get("assinatura_status"),
        "assinatura_data_inicio": item.get("assinatura_data_inicio"),
        "assinatura_data_fim": item.get("assinatura_data_fim"),
        "assinatura_valor": item.get("assinatura_valor"),
        "plano_nome": item.get("plano_nome"),
        "plano_codigo": item.get("plano_codigo"),
    } for item in cursor.fetchall()]
    conn.close()
    return usuarios


def excluir_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM recuperacao_senha WHERE usuario_id = %s", (usuario_id,))
    cursor.execute("DELETE FROM atleta_equipamentos WHERE atleta_id = %s", (usuario_id,))
    cursor.execute("DELETE FROM preferencias_substituicao_exercicio WHERE atleta_id = %s", (usuario_id,))
    cursor.execute(
        "DELETE FROM treinos_realizados WHERE COALESCE(atleta_id, usuario_id) = %s",
        (usuario_id,),
    )
    cursor.execute(
        "DELETE FROM treinos_gerados WHERE COALESCE(atleta_id, usuario_id) = %s",
        (usuario_id,),
    )
    cursor.execute("DELETE FROM convites_treinador_link WHERE treinador_id = %s", (usuario_id,))
    cursor.execute("DELETE FROM treinador_tema WHERE treinador_id = %s", (usuario_id,))
    cursor.execute(
        """
        DELETE FROM treinador_atleta
        WHERE treinador_id = %s OR atleta_id = %s
        """,
        (usuario_id, usuario_id),
    )
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))

    conn.commit()
    conn.close()
    return True


def saudacao_usuario(sexo):
    sexo_normalizado = _normalizar_sexo(sexo)
    if sexo_normalizado == "masculino":
        return "Bem-vindo"
    if sexo_normalizado == "feminino":
        return "Bem-vinda"
    return "Bem-vindo(a)"
