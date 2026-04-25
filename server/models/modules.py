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

def register_module(chip_id, short_id, module_type="hidro", ip="", ssid="", rssi=0,
                    uptime=0, free_heap=0, ctrl_data="{}", capabilities="[]"):
    """
    Registra/atualiza o modulo no banco. Chamado a cada poll do ESP32.

    Merge do ctrl_data: campos marcados como "server_keys" (config de camera,
    estado de alerta, etc.) sao preservados do banco — o ESP32 nao sobrescreve.
    Demais campos vem frescos do ESP32 a cada register.

    v4.1.28: Normaliza module_type="ctrl" (legado firmware <v4.1.28) -> "hidro".
    O firmware do hidro sera atualizado via OTA, mas aceita dois valores durante
    a transicao pra nao brickar ESP32 em campo com firmware antigo.
    """
    if module_type == "ctrl":
        module_type = "hidro"
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


# =====================================================================
# Historico online/offline (v4.1.31)
# =====================================================================
# Cada transicao e um evento. duration_seconds do evento anterior e
# preenchido quando o proximo entra (simplifica queries de uptime).
#
# Retencao: 90 dias (purge lazy no init_db + a cada N registers).
# Threshold de offline: 120 segundos sem register.
# =====================================================================

MODULE_OFFLINE_THRESHOLD_SEC = 120
MODULE_STATUS_RETENTION_DAYS = 90


def _get_last_status_event(conn, chip_id):
    """Ultimo evento registrado pro chip — None se historico vazio."""
    return conn.execute(
        "SELECT id, status, occurred_at, duration_seconds "
        "FROM module_status_events WHERE chip_id = ? "
        "ORDER BY occurred_at DESC, id DESC LIMIT 1",
        (chip_id,)
    ).fetchone()


def _close_event_duration(conn, event_id, start_iso, end_dt):
    """Preenche duration_seconds do evento anterior ao fechar."""
    try:
        start_dt = datetime.fromisoformat(start_iso)
        dur = int((end_dt - start_dt).total_seconds())
        if dur < 0:
            dur = 0
    except (ValueError, TypeError):
        dur = 0
    conn.execute(
        "UPDATE module_status_events SET duration_seconds = ? WHERE id = ?",
        (dur, event_id)
    )


def record_module_status(chip_id, status, reason=None, rssi=None, when=None):
    """
    Grava evento de transicao. Idempotente: se o ultimo evento ja e do mesmo
    status, nao cria novo (heartbeat silencioso).
    """
    if status not in ("online", "offline"):
        return
    now = when or datetime.now()
    conn = get_db()
    last = _get_last_status_event(conn, chip_id)
    if last and last["status"] == status:
        # Heartbeat do mesmo estado — nao registra novo evento
        conn.close()
        return
    if last:
        _close_event_duration(conn, last["id"], last["occurred_at"], now)
    conn.execute(
        "INSERT INTO module_status_events (chip_id, status, occurred_at, reason, rssi) "
        "VALUES (?, ?, ?, ?, ?)",
        (chip_id, status, now.isoformat(), reason, rssi)
    )
    conn.commit()
    conn.close()


def compute_module_status_lazy(chip_id, now=None):
    """
    Verifica se o modulo esta silencioso (last_seen > threshold). Se sim e
    o ultimo evento era 'online', marca transicao pra 'offline' automaticamente.

    Chamado em GET /api/modules (por cada modulo do user) e depois de um
    register (pra garantir que online foi registrado).
    """
    now = now or datetime.now()
    conn = get_db()
    row = conn.execute(
        "SELECT last_seen FROM modules WHERE chip_id = ?", (chip_id,)
    ).fetchone()
    if not row or not row["last_seen"]:
        conn.close()
        return
    try:
        last_seen = datetime.fromisoformat(row["last_seen"])
    except (ValueError, TypeError):
        conn.close()
        return
    age = (now - last_seen).total_seconds()
    last = _get_last_status_event(conn, chip_id)
    if age > MODULE_OFFLINE_THRESHOLD_SEC:
        # Modulo silencioso ha mais que o threshold -> offline
        if not last or last["status"] != "offline":
            if last:
                _close_event_duration(conn, last["id"], last["occurred_at"], last_seen)
            # O evento offline comeca quando o modulo foi visto pela ultima vez
            conn.execute(
                "INSERT INTO module_status_events (chip_id, status, occurred_at, reason) "
                "VALUES (?, 'offline', ?, ?)",
                (chip_id, last_seen.isoformat(), "timeout")
            )
            conn.commit()
    conn.close()


def get_module_uptime_summary(chip_id, days=7, now=None, exclude_server_down=True):
    """
    Agrega uptime do chip nos ultimos N dias.

    v4.1.33: por default filtra eventos offline com reason='server_down' — esses
    sao quedas causadas pelo proprio servidor Cultivee (registradas retroativamente
    via webhook do CF Worker). Filtrando, uptime_pct reflete a saude real do
    hardware/conectividade do modulo. uptime_pct_raw mantem o calculo antigo
    (inclui tudo) pra referencia.

    Retorna dict:
      {
        period_days, period_start, period_end,
        online_seconds, offline_seconds, server_down_seconds, total_seconds,
        uptime_pct, uptime_pct_raw,
        offline_count, offline_count_raw,
        longest_offline_seconds, last_offline_at, current_status,
        exclude_server_down,
      }
    """
    now = now or datetime.now()
    start = now - _timedelta_days(days)
    conn = get_db()
    # Busca ultimo evento antes do periodo pra saber estado inicial
    pre = conn.execute(
        "SELECT status, occurred_at, reason FROM module_status_events "
        "WHERE chip_id = ? AND occurred_at < ? "
        "ORDER BY occurred_at DESC LIMIT 1",
        (chip_id, start.isoformat())
    ).fetchone()
    # Eventos dentro do periodo
    rows = conn.execute(
        "SELECT status, occurred_at, duration_seconds, reason FROM module_status_events "
        "WHERE chip_id = ? AND occurred_at >= ? "
        "ORDER BY occurred_at ASC",
        (chip_id, start.isoformat())
    ).fetchall()
    # Current status (para exibir)
    last = _get_last_status_event(conn, chip_id)
    conn.close()

    online_sec = 0
    offline_sec = 0              # offline "real" do modulo (filtrado)
    server_down_sec = 0          # offline causado pelo servidor
    offline_count = 0            # conta filtrada
    offline_count_raw = 0        # conta bruta (inclui server_down)
    longest_offline = 0
    last_offline_at = None

    # Estado inicial dentro do periodo
    cur_status = pre["status"] if pre else None
    cur_reason = pre["reason"] if pre else None
    cur_start = start

    def _accum(status, reason, segment_start, segment_end):
        nonlocal online_sec, offline_sec, server_down_sec, offline_count, offline_count_raw
        nonlocal longest_offline, last_offline_at
        if segment_end <= segment_start:
            return
        seg = int((segment_end - segment_start).total_seconds())
        if status == "online":
            online_sec += seg
        elif status == "offline":
            is_server_down = (reason == "server_down")
            offline_count_raw += 1
            if is_server_down and exclude_server_down:
                server_down_sec += seg
                # Nao conta em offline_count/longest/last_offline_at
            else:
                offline_sec += seg
                offline_count += 1
                if seg > longest_offline:
                    longest_offline = seg
                if last_offline_at is None or segment_start > last_offline_at:
                    last_offline_at = segment_start

    for r in rows:
        try:
            evt_at = datetime.fromisoformat(r["occurred_at"])
        except (ValueError, TypeError):
            continue
        if cur_status is not None:
            _accum(cur_status, cur_reason, cur_start, evt_at)
        cur_status = r["status"]
        cur_reason = r["reason"]
        cur_start = evt_at

    if cur_status is not None:
        _accum(cur_status, cur_reason, cur_start, now)

    # Filtrado (padrao): online vs offline "real"
    total_filt = online_sec + offline_sec
    uptime_pct = (100.0 * online_sec / total_filt) if total_filt > 0 else None
    # Raw: inclui server_down no offline total
    total_raw = online_sec + offline_sec + server_down_sec
    uptime_pct_raw = (100.0 * online_sec / total_raw) if total_raw > 0 else None

    return {
        "period_days": days,
        "period_start": start.isoformat(),
        "period_end": now.isoformat(),
        "online_seconds": online_sec,
        "offline_seconds": offline_sec,
        "server_down_seconds": server_down_sec,
        "total_seconds": total_raw,  # mantido = online+offline+server_down (compatibilidade)
        "uptime_pct": round(uptime_pct, 2) if uptime_pct is not None else None,
        "uptime_pct_raw": round(uptime_pct_raw, 2) if uptime_pct_raw is not None else None,
        "offline_count": offline_count,
        "offline_count_raw": offline_count_raw,
        "longest_offline_seconds": longest_offline,
        "last_offline_at": last_offline_at.isoformat() if last_offline_at else None,
        "current_status": last["status"] if last else "unknown",
        "exclude_server_down": bool(exclude_server_down),
    }


def get_module_status_events(chip_id, days=60, limit=200, only_offline=False):
    """Lista eventos pra timeline. Default: todos. only_offline=True filtra."""
    start = (datetime.now() - _timedelta_days(days)).isoformat()
    conn = get_db()
    sql = (
        "SELECT id, status, occurred_at, duration_seconds, reason, rssi "
        "FROM module_status_events "
        "WHERE chip_id = ? AND occurred_at >= ?"
    )
    params = [chip_id, start]
    if only_offline:
        sql += " AND status = 'offline'"
    sql += " ORDER BY occurred_at DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def purge_old_status_events(retention_days=MODULE_STATUS_RETENTION_DAYS):
    """Remove eventos mais antigos que retention_days. Idempotente."""
    conn = get_db()
    cutoff = (datetime.now() - _timedelta_days(retention_days)).isoformat()
    conn.execute(
        "DELETE FROM module_status_events WHERE occurred_at < ?", (cutoff,)
    )
    conn.commit()
    conn.close()


def _timedelta_days(n):
    """Helper: evita import extra de timedelta no topo do arquivo."""
    from datetime import timedelta
    return timedelta(days=int(n))


# =====================================================================
# Incidentes da plataforma (v4.1.33)
# =====================================================================
# Recebidos via webhook do CF Worker (status.cultivee.com.br) em
# POST /api/platform-incident. Upsert por `webhook_id` + update retroativo
# em module_status_events pra marcar quedas que foram na verdade do servidor.
# =====================================================================

def upsert_platform_incident(webhook_id, component, component_name,
                              start_at, end_at, reason):
    """
    Idempotente. Insere ou atualiza (end_at/reason) por webhook_id.
    Retorna ('inserted' | 'updated', dict_da_linha).
    """
    conn = get_db()
    existing = conn.execute(
        "SELECT id, start_at, end_at FROM platform_incidents WHERE webhook_id = ?",
        (webhook_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE platform_incidents SET end_at = ?, reason = COALESCE(?, reason), "
            "component_name = COALESCE(?, component_name) WHERE webhook_id = ?",
            (end_at, reason, component_name, webhook_id)
        )
        status = "updated"
    else:
        conn.execute(
            "INSERT INTO platform_incidents "
            "(webhook_id, component, component_name, start_at, end_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (webhook_id, component, component_name, start_at, end_at, reason)
        )
        status = "inserted"
    row = conn.execute(
        "SELECT id, webhook_id, component, component_name, start_at, end_at, reason "
        "FROM platform_incidents WHERE webhook_id = ?",
        (webhook_id,)
    ).fetchone()
    conn.commit()
    conn.close()
    return status, dict(row) if row else {}


def mark_module_events_as_server_down(start_at, end_at=None):
    """
    Marca eventos offline de QUALQUER modulo que caem dentro da janela
    [start_at, end_at] como reason='server_down'. Idempotente — so afeta
    linhas que ainda nao estao marcadas.

    end_at=None (incidente em curso) usa "agora" como limite superior.
    Retorna numero de linhas afetadas.
    """
    if not end_at:
        end_at = datetime.now().isoformat()
    conn = get_db()
    # So pega offline cuja janela esta DENTRO do incidente. Eventos cuja
    # janela so parcialmente se sobrepoe tambem sao marcados — o visitante
    # ve o aviso + badge e entende o contexto.
    cur = conn.execute(
        "UPDATE module_status_events "
        "SET reason = 'server_down' "
        "WHERE status = 'offline' "
        "  AND occurred_at >= ? AND occurred_at <= ? "
        "  AND (reason IS NULL OR reason != 'server_down')",
        (start_at, end_at)
    )
    affected = cur.rowcount or 0
    conn.commit()
    conn.close()
    return affected


def get_recent_platform_incidents(days=30, limit=100):
    """Lista incidentes recentes — usado pelo admin pra auditar."""
    start = (datetime.now() - _timedelta_days(days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, webhook_id, component, component_name, start_at, end_at, reason, received_at "
        "FROM platform_incidents WHERE start_at >= ? "
        "ORDER BY start_at DESC LIMIT ?",
        (start, int(limit))
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =====================================================================
# Offline watcher lock (v4.1.38)
# =====================================================================
# Lock distribuido pra garantir que so 1 worker do Gunicorn rode o ciclo
# do offline_watcher por intervalo. UPDATE atomico no SQLite — quem vencer
# ganha o ciclo, os outros workers fazem skip.
# =====================================================================

def try_acquire_offline_watcher_lock(min_interval_sec=60):
    """
    Retorna True se este processo deve executar o ciclo agora (lider).
    Usa UPDATE atomico no SQLite. Se outro worker rodou ha menos de
    min_interval_sec, retorna False.
    """
    from datetime import timedelta
    conn = get_db()
    now_dt = datetime.now()
    cutoff_dt = now_dt - timedelta(seconds=int(min_interval_sec))
    now_iso = now_dt.isoformat()
    cutoff_iso = cutoff_dt.isoformat()
    # Garante a linha singleton (id=1) existe
    conn.execute(
        "INSERT OR IGNORE INTO offline_watcher_state (id, last_run) VALUES (1, ?)",
        ("1970-01-01T00:00:00",)
    )
    # UPDATE atomico — so vence se o ultimo run foi antes do cutoff
    cur = conn.execute(
        "UPDATE offline_watcher_state SET last_run = ? WHERE id = 1 AND last_run < ?",
        (now_iso, cutoff_iso)
    )
    won = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return won


def _get_last_status_event_public(chip_id):
    """Wrapper publico de _get_last_status_event pra uso em jobs externos."""
    conn = get_db()
    row = _get_last_status_event(conn, chip_id)
    conn.close()
    return dict(row) if row else None
