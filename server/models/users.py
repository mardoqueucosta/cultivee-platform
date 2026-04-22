"""
Cultivee — Usuarios, autenticacao, tokens, roles, preferencias.

Tudo relacionado ao usuario em si (identidade, sessao, permissao).
Nao inclui modulos do hardware — isso vive em models.modules.
"""

import os
import shutil
import pathlib
import sqlite3
import hashlib
import secrets
import json
import logging
from datetime import datetime, timedelta

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback defensivo
    bcrypt = None
    _BCRYPT_AVAILABLE = False

from .db import get_db

log = logging.getLogger(__name__)


# =====================================================================
# Password hashing (v4.1.26 — bcrypt com migracao transparente de SHA-256)
# =====================================================================
#
# Formato:
#   - Novos hashes: "bcrypt$<bcrypt_hash>" (bcrypt rounds=12 por padrao)
#   - Legados SHA-256: "<salt_hex>:<sha256_hex>" (sem prefixo) — validos para login,
#     migrados automaticamente para bcrypt no primeiro login bem-sucedido via
#     check_password_and_upgrade().
#
# Objetivo: hashes legados continuam funcionando; novos usuarios e resets ja usam
# bcrypt; senhas em uso migram sozinhas ao longo do tempo, sem exigir reset forcado.

_BCRYPT_PREFIX = "bcrypt$"
_BCRYPT_ROUNDS = 12


def _hash_bcrypt(password: str) -> str:
    if not _BCRYPT_AVAILABLE:
        # Fallback extremo se bcrypt nao estiver instalado — mantem login funcionando
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}:{h}"
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return _BCRYPT_PREFIX + digest.decode("utf-8")


def _check_bcrypt(password: str, stored: str) -> bool:
    if not _BCRYPT_AVAILABLE:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored[len(_BCRYPT_PREFIX):].encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _check_sha256_legacy(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":", 1)
    except ValueError:
        return False
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def hash_password(password):
    """Hash novo sempre em bcrypt (se disponivel). Legado SHA-256 so aparece
    em hashes antigos no banco — nunca criado a partir daqui."""
    return _hash_bcrypt(password)


def check_password(password, password_hash):
    """Valida senha contra hash armazenado (bcrypt ou SHA-256 legado)."""
    if not password_hash:
        return False
    if password_hash.startswith(_BCRYPT_PREFIX):
        return _check_bcrypt(password, password_hash)
    return _check_sha256_legacy(password, password_hash)


def needs_rehash(password_hash):
    """True se o hash atual nao esta no algoritmo preferido (bcrypt)."""
    if not password_hash:
        return False
    return not password_hash.startswith(_BCRYPT_PREFIX)


def check_password_and_upgrade(user_id, password, password_hash):
    """
    Verifica a senha e, se valida E o hash esta em formato legado, faz rehash
    em bcrypt e persiste. Chamado pelo login para migracao transparente.
    Retorna True se a senha bater, False caso contrario.
    """
    if not check_password(password, password_hash):
        return False
    if _BCRYPT_AVAILABLE and needs_rehash(password_hash):
        try:
            update_user_password(user_id, password)
            log.info(f"Hash de senha migrado para bcrypt: user_id={user_id}")
        except Exception as e:  # pragma: no cover
            log.warning(f"Falha ao migrar hash bcrypt user_id={user_id}: {e}")
    return True


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
      - Arquivos fisicos (v4.1.26 — LGPD direito ao esquecimento):
        captures/<chip_id>/, thumbs/<chip_id>/ dos modulos do usuario sao apagados.
        Firmware pendente tambem. Modulo vira "livre" mas sem historico de imagens
        do dono anterior.
    """
    conn = get_db()
    # Captura chip_ids ANTES de despareciar, senao perdemos a ligacao
    chip_rows = conn.execute(
        "SELECT chip_id FROM modules WHERE user_id = ?", (user_id,)
    ).fetchall()
    chip_ids = [r["chip_id"] for r in chip_rows]

    conn.execute("DELETE FROM tokens WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("UPDATE modules SET user_id = NULL, name = '' WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    _purge_user_files(chip_ids)


def _purge_user_files(chip_ids):
    """Remove pastas de capturas, thumbs e firmware pendente dos chips informados.
    Silencia erros individuais para nao bloquear o delete — loga para auditoria."""
    if not chip_ids:
        return
    data_dir = pathlib.Path(os.environ.get("DATA_DIR", "data"))
    targets = [
        data_dir / "captures",
        data_dir / "thumbs",
        data_dir / "live",
    ]
    for chip_id in chip_ids:
        for base in targets:
            chip_folder = base / chip_id
            if chip_folder.exists() and chip_folder.is_dir():
                try:
                    shutil.rmtree(chip_folder)
                    log.info(f"LGPD purge: removido {chip_folder}")
                except OSError as e:
                    log.warning(f"LGPD purge: falha removendo {chip_folder}: {e}")
        fw_file = data_dir / "firmware" / f"{chip_id}.bin"
        if fw_file.exists():
            try:
                fw_file.unlink()
                log.info(f"LGPD purge: removido firmware pendente {fw_file}")
            except OSError as e:
                log.warning(f"LGPD purge: falha removendo {fw_file}: {e}")


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


# --- 2FA TOTP (v4.1.22) ---

def set_totp_secret(user_id, secret):
    """Armazena o secret TOTP (ainda nao habilitado ate o user confirmar o 1o codigo)."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET totp_secret = ?, totp_enabled = 0 WHERE id = ?",
        (secret, user_id)
    )
    conn.commit()
    conn.close()


def enable_totp(user_id):
    """Confirma 2FA (depois do 1o codigo OK)."""
    conn = get_db()
    conn.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def disable_totp(user_id):
    """Remove 2FA e apaga o secret."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


# --- 2FA Email OTP (v4.1.29) ---
# Alternativa ao TOTP pra usuarios que nao querem instalar app authenticator.
# Codigo de 6 digitos enviado por email a cada login, valido 10min, single-use.

def _generate_email_2fa_code():
    """6 digitos zero-padded. secrets.randbelow garante distribuicao uniforme."""
    return f"{secrets.randbelow(1000000):06d}"


def create_email_2fa_code(user_id, expires_minutes=10):
    """
    Gera novo codigo OTP por email. Invalida codigos anteriores nao-usados do
    mesmo user (so 1 codigo valido por vez evita confusao no login).
    Retorna o codigo plain (chamador envia por email).
    """
    code = _generate_email_2fa_code()
    expires = (datetime.now() + timedelta(minutes=expires_minutes)).isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE email_2fa_codes SET used = 1 WHERE user_id = ? AND used = 0",
        (user_id,)
    )
    conn.execute(
        "INSERT INTO email_2fa_codes (user_id, code, expires_at) VALUES (?, ?, ?)",
        (user_id, code, expires)
    )
    conn.commit()
    conn.close()
    return code


def verify_email_2fa_code(user_id, code):
    """Valida codigo + marca como usado. Retorna True se OK."""
    if not code or len(code) != 6:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT id, expires_at, used FROM email_2fa_codes "
        "WHERE user_id = ? AND code = ? ORDER BY id DESC LIMIT 1",
        (user_id, code)
    ).fetchone()
    if not row:
        conn.close()
        return False
    if row["used"]:
        conn.close()
        return False
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            conn.close()
            return False
    except (ValueError, TypeError):
        conn.close()
        return False
    conn.execute("UPDATE email_2fa_codes SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return True


def enable_email_2fa(user_id):
    """Ativa 2FA por email. UI deve garantir que TOTP esteja desativado."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET email_2fa_enabled = 1 WHERE id = ?", (user_id,)
    )
    conn.commit()
    conn.close()


def disable_email_2fa(user_id):
    """Desativa 2FA por email + invalida codigos pendentes."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET email_2fa_enabled = 0 WHERE id = ?", (user_id,)
    )
    conn.execute(
        "UPDATE email_2fa_codes SET used = 1 WHERE user_id = ? AND used = 0",
        (user_id,)
    )
    conn.commit()
    conn.close()


# --- Sessions / Tokens com metadata (v4.1.22) ---

def create_token_with_metadata(user_id, days=30, user_agent="", ip=""):
    """
    Versao extendida de create_token que captura metadata pra session management.
    create_token() original continua funcionando (backward compat).
    """
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=days)).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO tokens (user_id, token, expires_at, user_agent, ip) VALUES (?, ?, ?, ?, ?)",
        (user_id, token, expires, user_agent[:500] if user_agent else "", ip[:100] if ip else "")
    )
    conn.commit()
    conn.close()
    return token


def touch_token(token):
    """Atualiza last_used_at na ultima vez que o token foi usado (pra UI)."""
    if not token:
        return
    conn = get_db()
    conn.execute(
        "UPDATE tokens SET last_used_at = ? WHERE token = ?",
        (datetime.now().isoformat(), token)
    )
    conn.commit()
    conn.close()


def list_user_sessions(user_id):
    """Lista tokens ativos do user com metadata. Usado em 'Meus dispositivos'."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, substr(token, 1, 8) as token_prefix, expires_at, created_at,
               last_used_at, user_agent, ip, COALESCE(scope, 'full') as scope
        FROM tokens
        WHERE user_id = ? AND datetime(expires_at) > datetime('now')
        ORDER BY COALESCE(last_used_at, created_at) DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_token_by_id(token_id, user_id):
    """Revoga um token especifico (valida que pertence ao user pra nao vazar)."""
    conn = get_db()
    result = conn.execute(
        "DELETE FROM tokens WHERE id = ? AND user_id = ?",
        (token_id, user_id)
    )
    conn.commit()
    revoked = result.rowcount > 0
    conn.close()
    return revoked


def revoke_all_other_tokens(user_id, current_token):
    """Revoga todos os tokens do user EXCETO o atual."""
    conn = get_db()
    conn.execute(
        "DELETE FROM tokens WHERE user_id = ? AND token != ?",
        (user_id, current_token)
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
