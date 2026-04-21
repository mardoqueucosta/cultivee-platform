"""
Cultivee — Conexao com o banco (SQLite) + init + migracoes.

Ponto unico de entrada pra DB. Nenhum outro modulo do pacote models/
deve duplicar a logica de conexao.

Todas as migracoes sao idempotentes (CREATE TABLE IF NOT EXISTS + try/except
em ALTER TABLE) pra permitir rodar init_db() em qualquer ambiente (producao,
dev, testes) sem quebrar o banco existente.
"""

import sqlite3
import os

from config import DB_PATH


# Garante que o diretorio do banco existe (criado 1x na importacao)
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)


# Polling adaptativo — compartilhado entre workers via banco
POLL_FAST = 2000       # 2s quando ha atividade recente
POLL_NORMAL = 10000    # 10s quando idle
ACTIVITY_TIMEOUT = 60  # 60s sem atividade volta ao ritmo normal


def get_db():
    """Abre conexao com foreign_keys + WAL. Caller eh responsavel por conn.close()."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """
    Cria tabelas se nao existirem + aplica migracoes aditivas.
    Chamada 1x no boot do servidor (app.py).

    Qualquer nova migracao deve seguir o padrao:
        try:
            conn.execute("SELECT coluna_nova FROM tabela LIMIT 0")
        except Exception:
            conn.execute("ALTER TABLE tabela ADD COLUMN coluna_nova TIPO DEFAULT ...")
    """
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chip_id TEXT UNIQUE NOT NULL,
            short_id TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'hidro',
            name TEXT DEFAULT '',
            user_id INTEGER,
            ip TEXT DEFAULT '',
            ssid TEXT DEFAULT '',
            rssi INTEGER DEFAULT 0,
            uptime INTEGER DEFAULT 0,
            free_heap INTEGER DEFAULT 0,
            capabilities TEXT DEFAULT '[]',
            ctrl_data TEXT DEFAULT '{}',
            last_seen TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS pending_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chip_id TEXT NOT NULL,
            command TEXT NOT NULL,
            params TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chip_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            admin_email TEXT,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            target_label TEXT,
            details TEXT DEFAULT '{}',
            ip TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # --- Migracoes aditivas (ALTER TABLE IF NOT EXISTS pattern) ---

    # Migracao: adiciona group_id na tabela modules (se nao existir)
    try:
        conn.execute("SELECT group_id FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN group_id INTEGER REFERENCES groups(id)")

    # Migracao: colunas de captura agendada
    for col, ddl in [
        ("capture_interval", "ALTER TABLE modules ADD COLUMN capture_interval INTEGER DEFAULT 600"),
        ("recording", "ALTER TABLE modules ADD COLUMN recording INTEGER DEFAULT 0"),
        ("last_capture_at", "ALTER TABLE modules ADD COLUMN last_capture_at TEXT"),
        ("cam_resolution", "ALTER TABLE modules ADD COLUMN cam_resolution TEXT DEFAULT 'UXGA'"),
        ("cam_quality", "ALTER TABLE modules ADD COLUMN cam_quality INTEGER DEFAULT 10"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM modules LIMIT 0")
        except Exception:
            conn.execute(ddl)

    # Migracao v4.1.10: preferencias de UI do usuario (ordem + selecao de modulos)
    try:
        conn.execute("SELECT module_prefs FROM users LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE users ADD COLUMN module_prefs TEXT DEFAULT '{}'")

    # Migracao v4.1.0: email separado pra notificacoes (diferente do email de login)
    try:
        conn.execute("SELECT notification_email FROM users LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE users ADD COLUMN notification_email TEXT")

    # Migracao v4.1.15: scope do token (full / readonly)
    try:
        conn.execute("SELECT scope FROM tokens LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE tokens ADD COLUMN scope TEXT DEFAULT 'full'")

    # Migracao v4.1.13: role do usuario (admin / support / user)
    try:
        conn.execute("SELECT role FROM users LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        # Bootstrap: user id=1 (primeiro cadastrado) vira admin se nao houver outro
        has_admin = conn.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if not has_admin:
            conn.execute("UPDATE users SET role = 'admin' WHERE id = 1")

    # Migracao v4.1.16: perfil do usuario (telefone, nascimento, endereco completo BR)
    for col, ddl in [
        ("phone", "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''"),
        ("birth_date", "ALTER TABLE users ADD COLUMN birth_date TEXT DEFAULT ''"),
        ("cep", "ALTER TABLE users ADD COLUMN cep TEXT DEFAULT ''"),
        ("street", "ALTER TABLE users ADD COLUMN street TEXT DEFAULT ''"),
        ("number", "ALTER TABLE users ADD COLUMN number TEXT DEFAULT ''"),
        ("complement", "ALTER TABLE users ADD COLUMN complement TEXT DEFAULT ''"),
        ("neighborhood", "ALTER TABLE users ADD COLUMN neighborhood TEXT DEFAULT ''"),
        ("city", "ALTER TABLE users ADD COLUMN city TEXT DEFAULT ''"),
        ("state", "ALTER TABLE users ADD COLUMN state TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM users LIMIT 0")
        except Exception:
            conn.execute(ddl)

    # Migracao v4.1.20: dados fiscais + compliance (LGPD, NF-e, termos, verificacao de email)
    # person_type: 'pf' (Pessoa Fisica, CPF) ou 'pj' (Pessoa Juridica, CNPJ)
    # tax_id: CPF ou CNPJ (so digitos, sem formatacao)
    # company_name: razao social (so PJ)
    # terms_accepted_at: timestamp de quando aceitou os termos (obrigatorio pra novos)
    # email_verified_at: timestamp de verificacao do email (null = nao verificado)
    # email_verification_token: token pra link de verificacao por email
    for col, ddl in [
        ("person_type", "ALTER TABLE users ADD COLUMN person_type TEXT DEFAULT 'pf'"),
        ("tax_id", "ALTER TABLE users ADD COLUMN tax_id TEXT DEFAULT ''"),
        ("company_name", "ALTER TABLE users ADD COLUMN company_name TEXT DEFAULT ''"),
        ("terms_accepted_at", "ALTER TABLE users ADD COLUMN terms_accepted_at TEXT"),
        ("email_verified_at", "ALTER TABLE users ADD COLUMN email_verified_at TEXT"),
        ("email_verification_token", "ALTER TABLE users ADD COLUMN email_verification_token TEXT"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM users LIMIT 0")
        except Exception:
            conn.execute(ddl)

    # Bootstrap: users que ja existiam antes da v4.1.20 sao considerados verificados
    # automaticamente (caso contrario, admin/users existentes perderiam acesso).
    # Tambem marca terms_accepted_at retroativamente (usuarios antigos implicitamente
    # aceitaram ao continuar usando o sistema).
    conn.execute("""
        UPDATE users
        SET email_verified_at = COALESCE(email_verified_at, created_at),
            terms_accepted_at = COALESCE(terms_accepted_at, created_at)
        WHERE email_verified_at IS NULL OR terms_accepted_at IS NULL
    """)

    # Migracao v4.1.22: 2FA TOTP (opcional por usuario)
    # totp_secret armazena o seed base32 (RFC 6238); totp_enabled indica se o user
    # confirmou o primeiro codigo (so ai o segundo fator entra no fluxo de login).
    for col, ddl in [
        ("totp_secret", "ALTER TABLE users ADD COLUMN totp_secret TEXT"),
        ("totp_enabled", "ALTER TABLE users ADD COLUMN totp_enabled INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM users LIMIT 0")
        except Exception:
            conn.execute(ddl)

    # Migracao v4.1.22: metadata de sessao (tokens) — pra session management
    # user_agent + ip + last_used_at dao contexto pro user ver "de onde logou"
    for col, ddl in [
        ("user_agent", "ALTER TABLE tokens ADD COLUMN user_agent TEXT DEFAULT ''"),
        ("ip", "ALTER TABLE tokens ADD COLUMN ip TEXT DEFAULT ''"),
        ("last_used_at", "ALTER TABLE tokens ADD COLUMN last_used_at TEXT"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM tokens LIMIT 0")
        except Exception:
            conn.execute(ddl)

    # Migracao v4.1.28: normaliza modules.type de 'ctrl' (legado, firmware <v4.1.28)
    # para 'hidro' (novo padrao, alinhado com capability). ESP32 em campo continua
    # sendo aceito via normalizacao em register_module() enquanto nao atualizar OTA.
    # Idempotente: so afeta linhas que ainda estao como 'ctrl'.
    conn.execute("UPDATE modules SET type = 'hidro' WHERE type = 'ctrl'")

    conn.commit()
    conn.close()
