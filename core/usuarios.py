import bcrypt
import hashlib
import os
import secrets
from datetime import datetime, timedelta

from core.banco import conectar
from core.permissoes import eh_admin, normalizar_status_conta, normalizar_tipo_usuario


def _linha_para_dict(linha):
    return dict(linha) if linha else None


def _normalizar_sexo(sexo):
    sexo_normalizado = (sexo or "outro").strip().lower()
    if sexo_normalizado in {"masculino", "feminino"}:
        return sexo_normalizado
    return "outro"


def _usuario_sem_senha(usuario):
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
            nome, apelido, foto_perfil, email, senha, sexo, tipo_usuario, status_conta, onboarding_completo, is_admin,
            idade, peso, altura, objetivo, distancia_principal, tempo_pratica,
            treinos_corrida_semana, tem_prova, data_prova, distancia_prova,
            treinos_musculacao_semana, local_treino, experiencia_musculacao,
            historico_lesao, dor_atual, aceitou_termos, aceitou_privacidade, data_consentimento
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            (dados.get("nome") or "").strip(),
            (dados.get("apelido") or "").strip() or None,
            dados.get("foto_perfil"),
            (dados.get("email") or "").strip().lower(),
            hash_senha(dados.get("senha") or ""),
            _normalizar_sexo(dados.get("sexo")),
            normalizar_tipo_usuario(dados.get("tipo_usuario"), dados.get("is_admin")),
            normalizar_status_conta(dados.get("status_conta")),
            int(dados.get("onboarding_completo", 0)),
            int(normalizar_tipo_usuario(dados.get("tipo_usuario"), dados.get("is_admin")) == "admin"),
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
