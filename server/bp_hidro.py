"""
Cultivee — Blueprint Hidroponia
Rotas de controle: status, reles, fases, config.
Registrado com url_prefix dinamico (ex: /api/ctrl ou /api/hidro-cam).
"""

import json
import urllib.request
from flask import Blueprint, request, jsonify, Response

import models

hidro_bp = Blueprint("hidro", __name__)


def _get_module_or_404(chip_id):
    """Helper: retorna modulo se pertence ao usuario autenticado e tem capability hidro."""
    module = models.get_module_by_chip_id(chip_id)
    if not module or module.get("user_id") != request.user["id"]:
        return None
    try:
        caps = json.loads(module.get("capabilities", "[]"))
    except (json.JSONDecodeError, TypeError):
        caps = []
    if "hidro" not in caps:
        return None
    return module


# =====================================================================
# Hidro routes — montadas no prefix configurado (ex: /api/ctrl/<chip_id>)
# =====================================================================

@hidro_bp.route("/<chip_id>/status")
def status(chip_id):
    """Retorna ultimo status salvo do modulo."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    from datetime import datetime
    now = datetime.now()
    online = False
    if module.get("last_seen"):
        last = datetime.fromisoformat(module["last_seen"])
        online = (now - last).total_seconds() < 120

    try:
        ctrl_data = json.loads(module.get("ctrl_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        ctrl_data = {}

    return jsonify({
        "online": online,
        "ip": module.get("ip", ""),
        "ssid": module.get("ssid", ""),
        "rssi": module.get("rssi", 0),
        "uptime": module.get("uptime", 0),
        "last_seen": module.get("last_seen", ""),
        **ctrl_data
    })


@hidro_bp.route("/<chip_id>/relay")
def relay(chip_id):
    """Controle de rele: proxy direto ou fila de comandos."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    device = request.args.get("device", "")
    action = request.args.get("action", "toggle")

    params = json.dumps({"device": device, "action": action})
    models.add_pending_command(chip_id, "relay", params)

    if module.get("ip"):
        try:
            url = f"http://{module['ip']}/relay?device={device}&action={action}"
            resp = urllib.request.urlopen(url, timeout=2)
            data = resp.read()
            # Proxy OK: atualiza ctrl_data no banco e retorna status real
            try:
                status = json.loads(data)
                models.update_ctrl_data(chip_id, status)
            except (json.JSONDecodeError, TypeError):
                pass
            return Response(data, status=200, mimetype="application/json")
        except Exception:
            pass
    return jsonify({"status": "queued", "message": "Comando enviado, sera executado em breve"})


@hidro_bp.route("/<chip_id>/phases")
def phases(chip_id):
    """Status completo com fases: proxy direto (local) ou banco (producao)."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    if request.args.get("live") and module.get("ip"):
        try:
            url = f"http://{module['ip']}/status"
            resp = urllib.request.urlopen(url, timeout=1)
            data = resp.read()
            return Response(data, mimetype="application/json")
        except Exception:
            pass

    try:
        ctrl_data = json.loads(module.get("ctrl_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        ctrl_data = {}
    return jsonify(ctrl_data)


@hidro_bp.route("/<chip_id>/save-config", methods=["POST"])
def save_config(chip_id):
    """Salvar config: atualiza banco (instantaneo) + enfileira pro ESP32."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    data = request.get_json()

    updates = {}
    if "start_date" in data:
        updates["start_date"] = data["start_date"]
    np = int(data.get("num_phases", 0))
    if np > 0:
        phases_list = []
        for i in range(np):
            phase = {
                "name": data.get(f"n{i}", f"Fase {i+1}"),
                "days": int(data.get(f"d{i}", 0)),
                "pumpOnDay": int(data.get(f"pod{i}", 15)) or 15,
                "pumpOffDay": int(data.get(f"pfd{i}", 15)) or 15,
                "pumpOnNight": int(data.get(f"pon{i}", 15)) or 15,
                "pumpOffNight": int(data.get(f"pfn{i}", 45)) or 45,
            }
            lon = data.get(f"lon{i}", "06:00")
            loff = data.get(f"loff{i}", "18:00")
            if ":" in str(lon):
                parts = str(lon).split(":")
                phase["lightOnHour"] = int(parts[0])
                phase["lightOnMin"] = int(parts[1])
            if ":" in str(loff):
                parts = str(loff).split(":")
                phase["lightOffHour"] = int(parts[0])
                phase["lightOffMin"] = int(parts[1])
            phases_list.append(phase)
        updates["phases"] = phases_list
        updates["num_phases"] = np
    if updates:
        models.update_ctrl_data(chip_id, updates)

    models.add_pending_command(chip_id, "save-config", json.dumps(data))

    if module.get("ip"):
        try:
            form_parts = [f"{k}={v}" for k, v in data.items()]
            form_body = "&".join(form_parts).encode()
            req = urllib.request.Request(
                f"http://{module['ip']}/save-config",
                data=form_body, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass

    return jsonify({"status": "ok"})


@hidro_bp.route("/<chip_id>/add-phase")
def add_phase(chip_id):
    """Adicionar fase: atualiza banco + enfileira pro ESP32."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    try:
        ctrl = json.loads(module.get("ctrl_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        ctrl = {}
    phases_list = ctrl.get("phases", [])
    phases_list.append({
        "name": "Nova Fase", "days": 7,
        "lightOnHour": 6, "lightOnMin": 0, "lightOffHour": 18, "lightOffMin": 0,
        "pumpOnDay": 15, "pumpOffDay": 15, "pumpOnNight": 15, "pumpOffNight": 45
    })
    models.update_ctrl_data(chip_id, {"phases": phases_list, "num_phases": len(phases_list)})

    models.add_pending_command(chip_id, "add-phase")
    if module.get("ip"):
        try:
            urllib.request.urlopen(f"http://{module['ip']}/add-phase", timeout=1)
        except Exception:
            pass
    return jsonify({"status": "ok"})


@hidro_bp.route("/<chip_id>/remove-phase")
def remove_phase(chip_id):
    """Remover fase: atualiza banco + enfileira pro ESP32."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404
    idx = int(request.args.get("idx", "0"))

    try:
        ctrl = json.loads(module.get("ctrl_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        ctrl = {}
    phases_list = ctrl.get("phases", [])
    if 0 <= idx < len(phases_list) and len(phases_list) > 1:
        phases_list.pop(idx)
        models.update_ctrl_data(chip_id, {"phases": phases_list, "num_phases": len(phases_list)})

    models.add_pending_command(chip_id, "remove-phase", json.dumps({"idx": idx}))
    if module.get("ip"):
        try:
            urllib.request.urlopen(f"http://{module['ip']}/remove-phase?idx={idx}", timeout=1)
        except Exception:
            pass
    return jsonify({"status": "ok"})


@hidro_bp.route("/<chip_id>/reset-phases")
def reset_phases(chip_id):
    """Restaurar fases: atualiza banco + enfileira pro ESP32."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    default_phases = [
        {"name": "Muda", "days": 3, "lightOnHour": 6, "lightOnMin": 0, "lightOffHour": 18, "lightOffMin": 0, "pumpOnDay": 15, "pumpOffDay": 15, "pumpOnNight": 15, "pumpOffNight": 45},
        {"name": "Berçário", "days": 17, "lightOnHour": 6, "lightOnMin": 0, "lightOffHour": 19, "lightOffMin": 0, "pumpOnDay": 15, "pumpOffDay": 15, "pumpOnNight": 15, "pumpOffNight": 45},
        {"name": "Engorda", "days": 0, "lightOnHour": 6, "lightOnMin": 0, "lightOffHour": 20, "lightOffMin": 0, "pumpOnDay": 15, "pumpOffDay": 15, "pumpOnNight": 15, "pumpOffNight": 45}
    ]
    models.update_ctrl_data(chip_id, {"phases": default_phases, "num_phases": 3})

    models.add_pending_command(chip_id, "reset-phases")
    if module.get("ip"):
        try:
            urllib.request.urlopen(f"http://{module['ip']}/reset-phases", timeout=1)
        except Exception:
            pass
    return jsonify({"status": "ok"})


@hidro_bp.route("/<chip_id>/reset-wifi")
def reset_wifi(chip_id):
    """Reset WiFi: proxy direto ou fila."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404
    if module.get("ip"):
        try:
            urllib.request.urlopen(f"http://{module['ip']}/reset-wifi", timeout=1)
            return jsonify({"status": "ok"})
        except Exception:
            pass
    models.add_pending_command(chip_id, "reset-wifi")
    return jsonify({"status": "queued"})
