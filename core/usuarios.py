import bcrypt
import hashlib
import secrets
from datetime import datetime, timedelta

from core.banco import conectar


def _linha_para_dict(linha):
    return dict(linha) if linha else None


def _normalizar_sexo(sexo):
    sexo_normalizado = (sexo or "outro").strip().lower()
    if sexo_normalizado in {"masculino", "feminino"}:
        return sexo_normalizado
    return "outro"


def _normalizar_tipo_usuario(tipo_usuario):
    tipo = (tipo_usuario or "atleta").strip().lower()
    if tipo == "treinador":
        return "treinador"
    return "atleta"


def _usuario_sem_senha(usuario):
    if not usuario:
        return None
    usuario_limpo = dict(usuario)
    usuario_limpo.pop("senha", None)
    usuario_limpo["sexo"] = _normalizar_sexo(usuario_limpo.get("sexo"))
    usuario_limpo["tipo_usuario"] = _normalizar_tipo_usuario(usuario_limpo.get("tipo_usuario"))
    usuario_limpo["onboarding_completo"] = int(usuario_limpo.get("onboarding_completo") or 0)
    usuario_limpo["is_admin"] = int(usuario_limpo.get("is_admin") or 0)
    usuario_limpo["aceitou_termos"] = int(usuario_limpo.get("aceitou_termos") or 0)
    usuario_limpo["aceitou_privacidade"] = int(usuario_limpo.get("aceitou_privacidade") or 0)
    return usuario_limpo


def _buscar_usuario_por_coluna(coluna, valor, incluir_senha=False):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM usuarios WHERE {coluna} = %s", (valor,))
    usuario = _linha_para_dict(cursor.fetchone())
    conn.close()
    if incluir_senha:
        return usuario
    return _usuario_sem_senha(usuario)


def hash_senha(senha):
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha, senha_hash):
    if not senha_hash:
        return False
    senha_hash_bytes = senha_hash if isinstance(senha_hash, bytes) else senha_hash.encode("utf-8")
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash_bytes)


def buscar_usuario_por_email(email):
    return _buscar_usuario_por_coluna("email", (email or "").strip().lower())


def buscar_usuario_por_id(usuario_id):
    return _buscar_usuario_por_coluna("id", usuario_id)


def criar_usuario(dados):
    data_consentimento = dados.get("data_consentimento")
    if not data_consentimento and (dados.get("aceitou_termos") or dados.get("aceitou_privacidade")):
        data_consentimento = datetime.now().isoformat(timespec="seconds")

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (
            nome, apelido, foto_perfil, email, senha, sexo, tipo_usuario, onboarding_completo, is_admin,
            idade, peso, altura, objetivo, distancia_principal, tempo_pratica,
            treinos_corrida_semana, tem_prova, data_prova, distancia_prova,
            treinos_musculacao_semana, local_treino, experiencia_musculacao,
            historico_lesao, dor_atual, aceitou_termos, aceitou_privacidade, data_consentimento
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            (dados.get("nome") or "").strip(),
            (dados.get("apelido") or "").strip() or None,
            dados.get("foto_perfil"),
            (dados.get("email") or "").strip().lower(),
            hash_senha(dados.get("senha") or ""),
            _normalizar_sexo(dados.get("sexo")),
            _normalizar_tipo_usuario(dados.get("tipo_usuario")),
            int(dados.get("onboarding_completo", 0)),
            int(dados.get("is_admin", 0)),
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
            dados.get("local_treino", ""),
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
    return _usuario_sem_senha(usuario)


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
            dados_onboarding.get("local_treino", ""),
            dados_onboarding.get("experiencia_musculacao", ""),
            dados_onboarding.get("historico_lesao", ""),
            dados_onboarding.get("dor_atual", ""),
            usuario_id,
        ),
    )
    conn.commit()
    conn.close()
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
            treinos_musculacao_semana = %s
        WHERE id = %s
        """,
        (
            dados_objetivo.get("objetivo", "performance"),
            int(bool(dados_objetivo.get("tem_prova", 0))),
            dados_objetivo.get("data_prova"),
            dados_objetivo.get("distancia_prova", ""),
            dados_objetivo.get("distancia_principal", ""),
            int(dados_objetivo.get("treinos_musculacao_semana", 1)),
            usuario_id,
        ),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def atualizar_perfil_usuario(usuario_id, dados_perfil):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET nome = %s,
            apelido = %s,
            foto_perfil = %s
        WHERE id = %s
        """,
        (
            (dados_perfil.get("nome") or "").strip(),
            (dados_perfil.get("apelido") or "").strip() or None,
            dados_perfil.get("foto_perfil"),
            usuario_id,
        ),
    )
    conn.commit()
    conn.close()
    return buscar_usuario_por_id(usuario_id)


def excluir_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM recuperacao_senha WHERE usuario_id = %s", (usuario_id,))
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
