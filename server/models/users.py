"""
Cultivee — Usuarios, autenticacao, tokens, roles, preferencias.

Tudo relacionado ao usuario em si (identidade, sessao, permissao).
Nao inclui modulos do hardware — isso vive em models.modules.
"""

import sqlite3
import hashlib
import secrets
import json
from datetime import datetime, timedelta

from .db import get_db


# =====================================================================
# Password hashing
# =====================================================================

def hash_password(password):
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def check_password(password, password_hash):
    salt, h = password_hash.split(":")
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


# =====================================================================
# Users CRUD
# =====================================================================

def create_user(email, password, name):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
            (email.lower().strip(), hash_password(password), name.strip())
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def update_user_password(user_id, new_password):
    """Atualiza hash de senha do usuario."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id)
    )
    conn.commit()
    conn.close()


# --- LGPD + compliance (v4.1.20) ---

def delete_user_cascade(user_id):
    """
    Hard delete do usuario + todas as suas dependencias.
    Usado pelo direito de exclusao (LGPD).

    Cascade:
      - tokens (sessoes + impersonation)
      - password_reset_tokens
      - push_subscriptions
      - module_prefs (fica em users.module_prefs, sumira com o DELETE)
      - Modulos pareados: user_id setado pra NULL (modulo fica "livre", pode ser repareado)
      - audit_log: MANTIDO (registros historicos — admin_email preservado)
      - alert_log: MANTIDO (historico)
    """
    conn = get_db()
    conn.execute("DELETE FROM tokens WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("UPDATE modules SET user_id = NULL, name = '' WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def export_user_data(user_id):
    """
    Exporta TODOS os dados do usuario em um dict serializavel (LGPD/portabilidade).
    Nao inclui password_hash ou tokens (dados sensiveis que nao devem ser exportados).
    """
    conn = get_db()
    # Dados do usuario (sem hash de senha)
    user = conn.execute(
        "SELECT id, email, name, notification_email, role, phone, birth_date, "
        "person_type, tax_id, company_name, "
        "cep, street, number, complement, neighborhood, city, state, "
        "created_at, email_verified_at, terms_accepted_at "
        "FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    if not user:
        conn.close()
        return None
    # Modulos pareados
    modules = conn.execute(
        "SELECT chip_id, short_id, type, name, created_at FROM modules WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    # Push subscriptions (so endpoints, sem keys)
    subs = conn.execute(
        "SELECT substr(endpoint, 1, 80) as endpoint, created_at FROM push_subscriptions WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    # Alertas enviados ao usuario
    alerts = conn.execute(
        "SELECT chip_id, alert_type, sent_at FROM alert_log WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    conn.close()
    return {
        "exported_at": datetime.now().isoformat(),
        "user": dict(user),
        "modules": [dict(m) for m in modules],
        "push_devices_count": len(subs),
        "alerts_received": [dict(a) for a in alerts],
    }


# --- Email verification (v4.1.20) ---

def generate_email_verification_token(user_id):
    """Cria e armazena token de verificacao no proprio user (1 token por user, substitui)."""
    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute(
        "UPDATE users SET email_verification_token = ? WHERE id = ?",
        (token, user_id)
    )
    conn.commit()
    conn.close()
    return token


def verify_email_with_token(token):
    """Consome token e marca email como verificado. Retorna user_id se sucesso."""
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE email_verification_token = ?",
        (token,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    user_id = row["id"]
    conn.execute(
        "UPDATE users SET email_verified_at = ?, email_verification_token = NULL WHERE id = ?",
        (datetime.now().isoformat(), user_id)
    )
    conn.commit()
    conn.close()
    return user_id


def mark_terms_accepted(user_id):
    """Registra aceite dos termos com timestamp."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET terms_accepted_at = ? WHERE id = ?",
        (datetime.now().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


# =====================================================================
# User profile (v4.1.16) — dados editaveis via /api/profile
# =====================================================================

# Campos do perfil que o usuario pode editar. notification_email fica separado porque
# e gerenciado em outra area (notificacoes) e name/email tem fluxo especifico.
# v4.1.20: adiciona dados fiscais (PF/PJ, CPF/CNPJ, razao social)
PROFILE_EDITABLE_FIELDS = (
    "name", "phone", "birth_date", "notification_email",
    "cep", "street", "number", "complement", "neighborhood", "city", "state",
    "person_type", "tax_id", "company_name",
)


def update_user_profile(user_id, updates):
    """
    Atualiza campos do perfil do usuario (whitelist PROFILE_EDITABLE_FIELDS).
    Ignora silenciosamente qualquer chave fora da whitelist (seguranca).
    Retorna dict com os campos efetivamente atualizados.
    """
    clean = {}
    for k in PROFILE_EDITABLE_FIELDS:
        if k in updates:
            v = updates[k]
            if v is None:
                v = ""
            clean[k] = str(v).strip()

    if not clean:
        return {}

    sets = ", ".join(f"{k} = ?" for k in clean.keys())
    values = list(clean.values()) + [user_id]
    conn = get_db()
    conn.execute(f"UPDATE users SET {sets} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return clean


# =====================================================================
# Tokens de sessao (login) + impersonation
# =====================================================================

def create_token(user_id, days=30):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=days)).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires)
    )
    conn.commit()
    conn.close()
    return token


def create_impersonation_token(target_user_id, minutes=30, scope="full"):
    """
    Token temporario pro fluxo de impersonation (admin agindo como outro user).

    Args:
        target_user_id: id do usuario-alvo
        minutes: tempo de expiracao (default 30, clampado entre 5 e 240 pelo endpoint)
        scope: 'full' (padrao) ou 'readonly' (bloqueia POST/PUT/DELETE)
    """
    if scope not in ("full", "readonly"):
        scope = "full"
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO tokens (user_id, token, expires_at, scope) VALUES (?, ?, ?, ?)",
        (target_user_id, token, expires, scope)
    )
    conn.commit()
    conn.close()
    return token


def validate_token(token):
    """Backward-compat: retorna user_id ou None."""
    result = validate_token_full(token)
    return result[0] if result else None


def validate_token_full(token):
    """
    Versao nova (v4.1.15): retorna (user_id, scope) ou None.
    scope: 'full' (permite tudo) ou 'readonly' (bloqueia mutacoes).
    """
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, expires_at, COALESCE(scope, 'full') AS scope FROM tokens WHERE token = ?",
        (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            return None
    except (ValueError, TypeError):
        return None
    return (row["user_id"], row["scope"] or "full")


def delete_token(token):
    conn = get_db()
    conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


# =====================================================================
# Password Reset (v4.1.12) — fluxo "esqueci minha senha"
# =====================================================================

def create_password_reset_token(user_id, expires_minutes=60):
    """Cria token de reset, invalida tokens anteriores do mesmo usuario. Retorna o token."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(minutes=expires_minutes)).isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0",
        (user_id,)
    )
    conn.execute(
        "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires)
    )
    conn.commit()
    conn.close()
    return token


def validate_password_reset_token(token):
    """Retorna user_id se token valido (nao expirado, nao usado), senao None."""
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token = ?",
        (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    if row["used"]:
        return None
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            return None
    except (ValueError, TypeError):
        return None
    return row["user_id"]


def consume_password_reset_token(token):
    """Marca token como usado."""
    conn = get_db()
    conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()


# =====================================================================
# Roles / Admin (v4.1.13)
# =====================================================================

def get_all_users():
    """Lista todos os usuarios com contagem de modulos + ultimo login estimado."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            u.id, u.email, u.notification_email, u.name, u.role, u.created_at,
            (SELECT COUNT(*) FROM modules m WHERE m.user_id = u.id) AS module_count,
            (SELECT MAX(t.created_at) FROM tokens t WHERE t.user_id = u.id) AS last_token_at
        FROM users u
        ORDER BY u.id ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_user_role(user_id, new_role):
    """Altera role. Retorna True se ok, False se role invalida."""
    if new_role not in ("user", "support", "admin"):
        return False
    conn = get_db()
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    return True


def count_admins():
    """Protege contra remover o ultimo admin (sistema sem admin = ruim)."""
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    conn.close()
    return n


def get_admin_stats():
    """Contadores agregados pro dashboard admin."""
    conn = get_db()
    n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    n_modules = conn.execute("SELECT COUNT(*) FROM modules WHERE chip_id != 'test'").fetchone()[0]
    n_paired = conn.execute(
        "SELECT COUNT(*) FROM modules WHERE user_id IS NOT NULL AND chip_id != 'test'"
    ).fetchone()[0]
    n_online = conn.execute("""
        SELECT COUNT(*) FROM modules
        WHERE chip_id != 'test'
          AND last_seen IS NOT NULL
          AND datetime(last_seen) > datetime('now', '-2 minutes')
    """).fetchone()[0]
    by_type_rows = conn.execute("""
        SELECT type, COUNT(*) AS c FROM modules
        WHERE chip_id != 'test' GROUP BY type
    """).fetchall()
    by_type = {r["type"]: r["c"] for r in by_type_rows}
    n_alerts_24h = conn.execute(
        "SELECT COUNT(*) FROM alert_log WHERE datetime(sent_at) > datetime('now', '-24 hours')"
    ).fetchone()[0]
    n_push = conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0]
    conn.close()
    return {
        "users": {"total": n_users, "admins": n_admins},
        "modules": {
            "total": n_modules,
            "paired": n_paired,
            "online_now": n_online,
            "by_type": by_type,
        },
        "alerts_24h": n_alerts_24h,
        "push_subscriptions": n_push,
    }


# =====================================================================
# User Module Prefs (v4.1.10) — ordem + selecao de modulos, persistida no servidor
# =====================================================================

def get_user_module_prefs(user_id):
    """Retorna {selected: [...], order: [...]} ou {} se nao ha."""
    conn = get_db()
    row = conn.execute("SELECT module_prefs FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not row or not row["module_prefs"]:
        return {}
    try:
        return json.loads(row["module_prefs"])
    except (json.JSONDecodeError, TypeError):
        return {}


def save_user_module_prefs(user_id, prefs):
    """Salva dict {selected: [chipIds], order: [chipIds]} no banco."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET module_prefs = ? WHERE id = ?",
        (json.dumps(prefs or {}), user_id)
    )
    conn.commit()
    conn.close()
