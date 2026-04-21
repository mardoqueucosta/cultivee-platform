"""
Cultivee — Modulos do hardware (ESP32), comandos, grupos, captura.

Tudo relacionado aos modulos em si: registro, pareamento com usuario,
comandos pendentes, grupos de organizacao, configuracao de captura de camera.
"""

import json
from datetime import datetime

from .db import get_db, POLL_FAST, POLL_NORMAL, ACTIVITY_TIMEOUT


# =====================================================================
# Registro + pareamento
# =====================================================================

def register_module(chip_id, short_id, module_type="ctrl", ip="", ssid="", rssi=0,
                    uptime=0, free_heap=0, ctrl_data="{}", capabilities="[]"):
    """
    Registra/atualiza o modulo no banco. Chamado a cada poll do ESP32.

    Merge do ctrl_data: campos marcados como "server_keys" (config de camera,
    estado de alerta, etc.) sao preservados do banco — o ESP32 nao sobrescreve.
    Demais campos vem frescos do ESP32 a cada register.
    """
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()

    now = datetime.now().isoformat()

    # Auto-migrate defensivo
    try:
        conn.execute("SELECT capabilities FROM modules LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE modules ADD COLUMN capabilities TEXT DEFAULT '[]'")

    if existing:
        try:
            existing_data = json.loads(existing["ctrl_data"] or "{}")
        except (json.JSONDecodeError, TypeError):
            existing_data = {}
        try:
            new_data = json.loads(ctrl_data or "{}")
        except (json.JSONDecodeError, TypeError):
            new_data = {}

        # server_keys: campos gerenciados pelo SERVIDOR (nao pelo ESP32).
        # Inclui: camera config (PWA configura) + alertas (AlertManager gerencia)
        server_keys = (
            "recording", "capture_interval", "cam_resolution", "cam_quality",
            "last_capture_at", "capture_folder",
            "cam_wb_mode", "cam_brightness", "cam_contrast", "cam_saturation",
            "cam_ae_level", "cam_gainceiling", "cam_special_effect",
            "cam_hmirror", "cam_vflip", "cam_exposure_ctrl", "cam_whitebal",
            "low_since", "last_activity", "alert_threshold_min",
        )
        for k in server_keys:
            if k in existing_data:
                new_data[k] = existing_data[k]
        merged_ctrl = json.dumps(new_data)
        conn.execute(
            "UPDATE modules SET type = ?, ip = ?, last_seen = ?, ssid = ?, rssi = ?, "
            "uptime = ?, free_heap = ?, ctrl_data = ?, capabilities = ? WHERE chip_id = ?",
            (module_type, ip, now, ssid, rssi, uptime, free_heap, merged_ctrl, capabilities, chip_id)
        )
    else:
        conn.execute(
            "INSERT INTO modules (chip_id, short_id, type, ip, last_seen, ssid, rssi, uptime, "
            "free_heap, ctrl_data, capabilities) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chip_id, short_id, module_type, ip, now, ssid, rssi, uptime, free_heap, ctrl_data, capabilities)
        )
    conn.commit()
    conn.close()


def pair_module(chip_id, user_id, name=""):
    """Vincula modulo a um usuario. Retorna (sucesso, mensagem)."""
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


def get_module_by_chip_id(chip_id):
    conn = get_db()
    module = conn.execute(
        "SELECT * FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()
    conn.close()
    return dict(module) if module else None


def get_all_modules_admin():
    """Lista todos os modulos do sistema com email do dono (admin only)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            m.chip_id, m.short_id, m.type, m.name, m.ip, m.ssid, m.rssi, m.uptime,
            m.last_seen, m.capabilities, m.user_id,
            u.email AS user_email, u.name AS user_name
        FROM modules m
        LEFT JOIN users u ON u.id = m.user_id
        ORDER BY m.last_seen DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =====================================================================
# Polling adaptativo + ctrl_data helpers
# =====================================================================

def mark_activity(chip_id):
    """Marca atividade no banco (compartilhado entre workers)."""
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE modules SET ctrl_data = json_set(COALESCE(ctrl_data,'{}'), '$.last_activity', ?) "
        "WHERE chip_id = ?",
        (now, chip_id)
    )
    conn.commit()
    conn.close()


def get_poll_interval(chip_id):
    """Retorna intervalo baseado na ultima atividade."""
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
    """Merge parcial de campos no ctrl_data do modulo."""
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


# =====================================================================
# Pending commands (fila de comandos pro ESP32)
# =====================================================================

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
    """Retorna + deleta os comandos pendentes do chip (one-shot)."""
    conn = get_db()
    cmds = conn.execute(
        "SELECT * FROM pending_commands WHERE chip_id = ? ORDER BY id", (chip_id,)
    ).fetchall()
    conn.execute("DELETE FROM pending_commands WHERE chip_id = ?", (chip_id,))
    conn.commit()
    conn.close()
    return [dict(c) for c in cmds]


# =====================================================================
# Groups (organizacao de modulos do usuario)
# =====================================================================

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
    group = conn.execute(
        "SELECT id FROM groups WHERE id = ? AND user_id = ?",
        (group_id, user_id)
    ).fetchone()
    if not group:
        conn.close()
        return False
    conn.execute("UPDATE modules SET group_id = NULL WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return True


def assign_module_to_group(chip_id, group_id, user_id):
    conn = get_db()
    module = conn.execute(
        "SELECT id FROM modules WHERE chip_id = ? AND user_id = ?", (chip_id, user_id)
    ).fetchone()
    if not module:
        conn.close()
        return False
    group = conn.execute(
        "SELECT id FROM groups WHERE id = ? AND user_id = ?", (group_id, user_id)
    ).fetchone()
    if not group:
        conn.close()
        return False
    conn.execute("UPDATE modules SET group_id = ? WHERE chip_id = ?", (group_id, chip_id))
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


# =====================================================================
# Captura agendada (camera config)
# =====================================================================

def set_capture_config(chip_id, capture_interval=None, recording=None, cam_resolution=None,
                       cam_quality=None, capture_folder=None,
                       cam_wb_mode=None, cam_brightness=None, cam_contrast=None, cam_saturation=None,
                       cam_ae_level=None, cam_gainceiling=None, cam_special_effect=None,
                       cam_hmirror=None, cam_vflip=None, cam_exposure_ctrl=None, cam_whitebal=None):
    data = {}
    if capture_interval is not None: data["capture_interval"] = int(capture_interval)
    if recording is not None: data["recording"] = 1 if recording else 0
    if cam_resolution is not None: data["cam_resolution"] = str(cam_resolution)
    if cam_quality is not None: data["cam_quality"] = int(cam_quality)
    if capture_folder is not None: data["capture_folder"] = str(capture_folder)
    if cam_wb_mode is not None: data["cam_wb_mode"] = int(cam_wb_mode)
    if cam_brightness is not None: data["cam_brightness"] = int(cam_brightness)
    if cam_contrast is not None: data["cam_contrast"] = int(cam_contrast)
    if cam_saturation is not None: data["cam_saturation"] = int(cam_saturation)
    if cam_ae_level is not None: data["cam_ae_level"] = int(cam_ae_level)
    if cam_gainceiling is not None: data["cam_gainceiling"] = int(cam_gainceiling)
    if cam_special_effect is not None: data["cam_special_effect"] = int(cam_special_effect)
    if cam_hmirror is not None: data["cam_hmirror"] = int(cam_hmirror)
    if cam_vflip is not None: data["cam_vflip"] = int(cam_vflip)
    if cam_exposure_ctrl is not None: data["cam_exposure_ctrl"] = int(cam_exposure_ctrl)
    if cam_whitebal is not None: data["cam_whitebal"] = int(cam_whitebal)
    if not data:
        return
    update_ctrl_data(chip_id, data)


def get_capture_config(chip_id):
    conn = get_db()
    row = conn.execute(
        "SELECT ctrl_data FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {
            "capture_interval": 600, "recording": False, "last_capture_at": None,
            "cam_resolution": "UXGA", "cam_quality": 10,
        }
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
