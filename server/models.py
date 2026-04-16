"""
Cultivee — Modelos do banco de dados (SQLite)
Compartilhado por todos os modulos. Identico ao original.
"""

import sqlite3
import hashlib
import secrets
import os
import json
from datetime import datetime, timedelta

from config import DB_PATH

# Garante que o diretorio do banco existe
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
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
            type TEXT NOT NULL DEFAULT 'ctrl',
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
    """)

    # Migracao: adiciona group_id na tabela modules (se nao existir)
    try:
        conn.execute("SELECT group_id FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN group_id INTEGER REFERENCES groups(id)")

    # Migracao: colunas de captura agendada
    try:
        conn.execute("SELECT capture_interval FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN capture_interval INTEGER DEFAULT 600")
    try:
        conn.execute("SELECT recording FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN recording INTEGER DEFAULT 0")
    try:
        conn.execute("SELECT last_capture_at FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN last_capture_at TEXT")
    try:
        conn.execute("SELECT cam_resolution FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN cam_resolution TEXT DEFAULT 'UXGA'")
    try:
        conn.execute("SELECT cam_quality FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN cam_quality INTEGER DEFAULT 10")

    conn.commit()
    conn.close()


# --- Password hashing ---

def hash_password(password):
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def check_password(password, password_hash):
    salt, h = password_hash.split(":")
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


# --- Users ---

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


# --- Tokens ---

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


def validate_token(token):
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, expires_at FROM tokens WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        return None
    return row["user_id"]


def delete_token(token):
    conn = get_db()
    conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


# --- Modules ---

def register_module(chip_id, short_id, module_type="ctrl", ip="", ssid="", rssi=0, uptime=0, free_heap=0, ctrl_data="{}", capabilities="[]"):
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()

    now = datetime.now().isoformat()

    # Auto-migrate: adiciona coluna capabilities se nao existir
    try:
        conn.execute("SELECT capabilities FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN capabilities TEXT DEFAULT '[]'")

    if existing:
        # Merge ctrl_data para nao sobrescrever config salva pelo app
        try:
            existing_data = json.loads(existing["ctrl_data"] or "{}")
        except (json.JSONDecodeError, TypeError):
            existing_data = {}
        try:
            new_data = json.loads(ctrl_data or "{}")
        except (json.JSONDecodeError, TypeError):
            new_data = {}
        # Campos de config da CAMERA — servidor e fonte da verdade.
        # Para camera: o PWA configura resolution/quality/interval e o ESP32 apenas ecoa.
        # Para hidro/hidro-farm: o ESP32 e a fonte de verdade (NVS) — phases, start_date
        # e num_phases NAO sao protegidos aqui. Se o ESP32 reboota com NVS intacto,
        # manda os dados corretos; se NVS foi apagado, manda defaults e o usuario
        # reconfigura. Isso garante consistencia entre start_date e cycle_day.
        server_keys = ("recording", "capture_interval", "cam_resolution",
                       "cam_quality", "last_capture_at", "capture_folder",
                       "cam_wb_mode", "cam_brightness", "cam_contrast",
                       "cam_saturation", "cam_ae_level", "cam_gainceiling",
                       "cam_special_effect", "cam_hmirror", "cam_vflip",
                       "cam_exposure_ctrl", "cam_whitebal")
        for k in server_keys:
            if k in existing_data:
                new_data[k] = existing_data[k]
        merged_ctrl = json.dumps(new_data)
        conn.execute(
            "UPDATE modules SET type = ?, ip = ?, last_seen = ?, ssid = ?, rssi = ?, uptime = ?, free_heap = ?, ctrl_data = ?, capabilities = ? WHERE chip_id = ?",
            (module_type, ip, now, ssid, rssi, uptime, free_heap, merged_ctrl, capabilities, chip_id)
        )
    else:
        conn.execute(
            "INSERT INTO modules (chip_id, short_id, type, ip, last_seen, ssid, rssi, uptime, free_heap, ctrl_data, capabilities) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chip_id, short_id, module_type, ip, now, ssid, rssi, uptime, free_heap, ctrl_data, capabilities)
        )
    conn.commit()
    conn.close()


def pair_module(chip_id, user_id, name=""):
    conn = get_db()
    module = conn.execute(
        "SELECT * FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()

    if not module:
        conn.close()
        return False, "Modulo nao encontrado. Ligue o modulo primeiro."

    if module["user_id"] and module["user_id"] != user_id:
        conn.close()
        return False, "Modulo ja vinculado a outro usuario."

    conn.execute(
        "UPDATE modules SET user_id = ?, name = ? WHERE chip_id = ?",
        (user_id, name, chip_id)
    )
    conn.commit()
    conn.close()
    return True, "Modulo vinculado com sucesso."


def unpair_module(chip_id, user_id):
    conn = get_db()
    conn.execute(
        "UPDATE modules SET user_id = NULL, name = '' WHERE chip_id = ? AND user_id = ?",
        (chip_id, user_id)
    )
    conn.commit()
    conn.close()


def get_user_modules(user_id):
    conn = get_db()
    modules = conn.execute(
        "SELECT * FROM modules WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(m) for m in modules]


def get_module_by_short_id(short_id):
    conn = get_db()
    module = conn.execute(
        "SELECT * FROM modules WHERE short_id = ?", (short_id.upper(),)
    ).fetchone()
    conn.close()
    return dict(module) if module else None


# Polling adaptativo via banco (compativel com multi-worker)
POLL_FAST = 2000      # 2s quando ha atividade
POLL_NORMAL = 10000   # 10s quando idle
ACTIVITY_TIMEOUT = 60  # 60s sem atividade volta ao normal


def mark_activity(chip_id):
    """Marca atividade no banco (compartilhado entre workers)."""
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE modules SET ctrl_data = json_set(COALESCE(ctrl_data,'{}'), '$.last_activity', ?) WHERE chip_id = ?",
        (now, chip_id)
    )
    conn.commit()
    conn.close()


def get_poll_interval(chip_id):
    """Retorna intervalo baseado na ultima atividade (do banco)."""
    conn = get_db()
    row = conn.execute(
        "SELECT json_extract(ctrl_data, '$.last_activity') as la FROM modules WHERE chip_id = ?",
        (chip_id,)
    ).fetchone()
    conn.close()
    if row and row["la"]:
        try:
            last = datetime.fromisoformat(row["la"])
            if (datetime.now() - last).total_seconds() < ACTIVITY_TIMEOUT:
                return POLL_FAST
        except (ValueError, TypeError):
            pass
    return POLL_NORMAL


def update_ctrl_data(chip_id, updates):
    """Atualiza campos especificos no ctrl_data do modulo (merge parcial)."""
    conn = get_db()
    row = conn.execute("SELECT ctrl_data FROM modules WHERE chip_id = ?", (chip_id,)).fetchone()
    if not row:
        conn.close()
        return
    try:
        data = json.loads(row["ctrl_data"] or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    data.update(updates)
    conn.execute(
        "UPDATE modules SET ctrl_data = ? WHERE chip_id = ?",
        (json.dumps(data), chip_id)
    )
    conn.commit()
    conn.close()


def add_pending_command(chip_id, command, params="{}"):
    mark_activity(chip_id)
    conn = get_db()
    conn.execute(
        "INSERT INTO pending_commands (chip_id, command, params) VALUES (?, ?, ?)",
        (chip_id, command, params)
    )
    conn.commit()
    conn.close()


def get_pending_commands(chip_id):
    conn = get_db()
    cmds = conn.execute(
        "SELECT * FROM pending_commands WHERE chip_id = ? ORDER BY id",
        (chip_id,)
    ).fetchall()
    # Deleta apos ler
    conn.execute("DELETE FROM pending_commands WHERE chip_id = ?", (chip_id,))
    conn.commit()
    conn.close()
    return [dict(c) for c in cmds]


def get_module_by_chip_id(chip_id):
    conn = get_db()
    module = conn.execute(
        "SELECT * FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()
    conn.close()
    return dict(module) if module else None


# --- Groups ---

def create_group(user_id, name):
    conn = get_db()
    conn.execute(
        "INSERT INTO groups (user_id, name) VALUES (?, ?)",
        (user_id, name)
    )
    conn.commit()
    group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return group_id


def get_user_groups(user_id):
    conn = get_db()
    groups = conn.execute(
        "SELECT * FROM groups WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(g) for g in groups]


def rename_group(group_id, user_id, name):
    conn = get_db()
    result = conn.execute(
        "UPDATE groups SET name = ? WHERE id = ? AND user_id = ?",
        (name, group_id, user_id)
    )
    conn.commit()
    changed = result.rowcount > 0
    conn.close()
    return changed


def delete_group(group_id, user_id):
    conn = get_db()
    # Verifica que o grupo pertence ao usuario
    group = conn.execute(
        "SELECT id FROM groups WHERE id = ? AND user_id = ?",
        (group_id, user_id)
    ).fetchone()
    if not group:
        conn.close()
        return False
    # Desassocia modulos do grupo
    conn.execute(
        "UPDATE modules SET group_id = NULL WHERE group_id = ?",
        (group_id,)
    )
    # Deleta o grupo
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return True


def assign_module_to_group(chip_id, group_id, user_id):
    conn = get_db()
    # Verifica que modulo pertence ao usuario
    module = conn.execute(
        "SELECT id FROM modules WHERE chip_id = ? AND user_id = ?",
        (chip_id, user_id)
    ).fetchone()
    if not module:
        conn.close()
        return False
    # Verifica que grupo pertence ao usuario
    group = conn.execute(
        "SELECT id FROM groups WHERE id = ? AND user_id = ?",
        (group_id, user_id)
    ).fetchone()
    if not group:
        conn.close()
        return False
    conn.execute(
        "UPDATE modules SET group_id = ? WHERE chip_id = ?",
        (group_id, chip_id)
    )
    conn.commit()
    conn.close()
    return True


def remove_module_from_group(chip_id, user_id):
    conn = get_db()
    conn.execute(
        "UPDATE modules SET group_id = NULL WHERE chip_id = ? AND user_id = ?",
        (chip_id, user_id)
    )
    conn.commit()
    conn.close()


# --- Captura agendada ---

def set_capture_config(chip_id, capture_interval=None, recording=None, cam_resolution=None, cam_quality=None, capture_folder=None,
                       cam_wb_mode=None, cam_brightness=None, cam_contrast=None, cam_saturation=None,
                       cam_ae_level=None, cam_gainceiling=None, cam_special_effect=None,
                       cam_hmirror=None, cam_vflip=None, cam_exposure_ctrl=None, cam_whitebal=None):
    data = {}
    if capture_interval is not None:
        data["capture_interval"] = int(capture_interval)
    if recording is not None:
        data["recording"] = 1 if recording else 0
    if cam_resolution is not None:
        data["cam_resolution"] = str(cam_resolution)
    if cam_quality is not None:
        data["cam_quality"] = int(cam_quality)
    if capture_folder is not None:
        data["capture_folder"] = str(capture_folder)
    if cam_wb_mode is not None:
        data["cam_wb_mode"] = int(cam_wb_mode)
    if cam_brightness is not None:
        data["cam_brightness"] = int(cam_brightness)
    if cam_contrast is not None:
        data["cam_contrast"] = int(cam_contrast)
    if cam_saturation is not None:
        data["cam_saturation"] = int(cam_saturation)
    if cam_ae_level is not None:
        data["cam_ae_level"] = int(cam_ae_level)
    if cam_gainceiling is not None:
        data["cam_gainceiling"] = int(cam_gainceiling)
    if cam_special_effect is not None:
        data["cam_special_effect"] = int(cam_special_effect)
    if cam_hmirror is not None:
        data["cam_hmirror"] = int(cam_hmirror)
    if cam_vflip is not None:
        data["cam_vflip"] = int(cam_vflip)
    if cam_exposure_ctrl is not None:
        data["cam_exposure_ctrl"] = int(cam_exposure_ctrl)
    if cam_whitebal is not None:
        data["cam_whitebal"] = int(cam_whitebal)
    if not data:
        return
    update_ctrl_data(chip_id, data)


def get_capture_config(chip_id):
    conn = get_db()
    row = conn.execute(
        "SELECT ctrl_data FROM modules WHERE chip_id = ?",
        (chip_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"capture_interval": 600, "recording": False, "last_capture_at": None, "cam_resolution": "UXGA", "cam_quality": 10}
    try:
        data = json.loads(row["ctrl_data"] or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    return {
        "capture_interval": data.get("capture_interval", 600),
        "recording": bool(data.get("recording", False)),
        "last_capture_at": data.get("last_capture_at"),
        "cam_resolution": data.get("cam_resolution", "UXGA"),
        "cam_quality": data.get("cam_quality", 10),
        "capture_folder": data.get("capture_folder", ""),
        "cam_wb_mode": data.get("cam_wb_mode", 0),
        "cam_brightness": data.get("cam_brightness", 0),
        "cam_contrast": data.get("cam_contrast", 0),
        "cam_saturation": data.get("cam_saturation", 0),
        "cam_ae_level": data.get("cam_ae_level", 0),
        "cam_gainceiling": data.get("cam_gainceiling", 2),
        "cam_special_effect": data.get("cam_special_effect", 0),
        "cam_hmirror": data.get("cam_hmirror", 0),
        "cam_vflip": data.get("cam_vflip", 0),
        "cam_exposure_ctrl": data.get("cam_exposure_ctrl", 1),
        "cam_whitebal": data.get("cam_whitebal", 1),
    }


def mark_capture(chip_id):
    update_ctrl_data(chip_id, {"last_capture_at": datetime.now().isoformat()})
