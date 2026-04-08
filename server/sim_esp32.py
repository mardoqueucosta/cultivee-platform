"""
Simulador de ESP32 para testes locais.
Finge ser um modulo ESP32 registrando no servidor local.

Uso:
  python sim_esp32.py              # simula produto ctrl (porta 5002)
  python sim_esp32.py hidro-cam    # simula produto hidro-cam (porta 5003)

O simulador:
  1. Registra um modulo fake com chip_id/short_id fixos
  2. Envia heartbeat periodico (como o ESP32 real faz)
  3. Processa comandos pendentes (relay, capture, config, etc)
  4. Simula estados de reles, fases e camera
"""

import sys
import time
import json
import urllib.request
import urllib.error
import random

# --- Config baseada no produto ---
product = sys.argv[1] if len(sys.argv) > 1 else "ctrl"

PRODUCTS = {
    "ctrl": {
        "port": 5002,
        "chip_id": "SIM_CTRL_0001",
        "short_id": "SC01",
        "module_type": "ctrl",
        "capabilities": ["hidro"],
    },
    "cam": {
        "port": 5002,
        "chip_id": "SIM_CAM_0001",
        "short_id": "CA01",
        "module_type": "cam",
        "capabilities": ["cam"],
    },
}

if product not in PRODUCTS:
    print(f"Produto invalido: {product}. Use: ctrl ou cam")
    sys.exit(1)

cfg = PRODUCTS[product]
BASE_URL = f"http://localhost:{cfg['port']}"

# --- Estado simulado do ESP32 ---
state = {
    "light": False,
    "pump": False,
    "mode_auto": True,
    "camera_ready": "cam" in cfg["capabilities"],
    "uptime": 0,
    "free_heap": 245000,
    "ip": "192.168.4.1",
    "ssid": "Mardo-Dri",
    "rssi": -45,
    "phases": [
        {
            "name": "Germinacao",
            "days": 7,
            "lightOnHour": 6, "lightOnMin": 0,
            "lightOffHour": 22, "lightOffMin": 0,
            "pumpOnDay": 15, "pumpOffDay": 15,
            "pumpOnNight": 30, "pumpOffNight": 30,
        },
        {
            "name": "Vegetativo",
            "days": 21,
            "lightOnHour": 6, "lightOnMin": 0,
            "lightOffHour": 0, "lightOffMin": 0,
            "pumpOnDay": 15, "pumpOffDay": 15,
            "pumpOnNight": 30, "pumpOffNight": 30,
        },
    ],
    "num_phases": 2,
    "start_date": "2026-03-23",
}


def build_ctrl_data():
    """Monta ctrl_data igual ao ESP32 real."""
    d = {
        "light": state["light"],
        "pump": state["pump"],
        "mode": "auto" if state["mode_auto"] else "manual",
        "phases": state["phases"],
        "num_phases": state["num_phases"],
        "start_date": state["start_date"],
    }
    if state.get("camera_ready"):
        d["camera_ready"] = True
    return d


def post_json(url, data):
    """POST JSON e retorna resposta."""
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"  [ERRO] {e}")
        return None


def get_json(url):
    """GET e retorna resposta."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"  [ERRO] {e}")
        return None


def process_command(cmd_obj):
    """Processa comando como o ESP32 faria."""
    cmd = cmd_obj.get("cmd", "")
    print(f"  CMD: {cmd} -> ", end="")

    if cmd == "relay":
        device = cmd_obj.get("device", "")
        action = cmd_obj.get("action", "toggle")
        if device == "light":
            if action == "toggle":
                state["light"] = not state["light"]
            elif action == "on":
                state["light"] = True
            elif action == "off":
                state["light"] = False
            print(f"light={'ON' if state['light'] else 'OFF'}")
        elif device == "pump":
            if action == "toggle":
                state["pump"] = not state["pump"]
            elif action == "on":
                state["pump"] = True
            elif action == "off":
                state["pump"] = False
            print(f"pump={'ON' if state['pump'] else 'OFF'}")
        elif device == "mode":
            state["mode_auto"] = not state["mode_auto"]
            print(f"mode={'AUTO' if state['mode_auto'] else 'MANUAL'}")
        else:
            print(f"device desconhecido: {device}")

    elif cmd == "save-config":
        if "phases" in cmd_obj:
            state["phases"] = cmd_obj["phases"]
            state["num_phases"] = len(cmd_obj["phases"])
        if "start_date" in cmd_obj:
            state["start_date"] = cmd_obj["start_date"]
        print("config salva")

    elif cmd == "add-phase":
        state["phases"].append({
            "name": f"Fase {state['num_phases'] + 1}",
            "days": 7,
            "lightOnHour": 6, "lightOnMin": 0,
            "lightOffHour": 22, "lightOffMin": 0,
            "pumpOnDay": 15, "pumpOffDay": 15,
            "pumpOnNight": 30, "pumpOffNight": 30,
        })
        state["num_phases"] = len(state["phases"])
        print(f"fase adicionada (total: {state['num_phases']})")

    elif cmd == "remove-phase":
        idx = cmd_obj.get("idx", -1)
        if 0 <= idx < len(state["phases"]):
            removed = state["phases"].pop(idx)
            state["num_phases"] = len(state["phases"])
            print(f"fase '{removed['name']}' removida")
        else:
            print(f"indice invalido: {idx}")

    elif cmd == "reset-phases":
        state["phases"] = [
            {"name": "Germinacao", "days": 7, "lightOnHour": 6, "lightOnMin": 0,
             "lightOffHour": 22, "lightOffMin": 0, "pumpOnDay": 15, "pumpOffDay": 15,
             "pumpOnNight": 30, "pumpOffNight": 30},
        ]
        state["num_phases"] = 1
        print("fases resetadas")

    elif cmd == "reset-wifi":
        print("WiFi reset (simulado)")

    elif cmd == "capture":
        print("captura solicitada (simulado — sem imagem real)")

    elif cmd == "start-live":
        state["live_mode"] = True
        print("live mode INICIADO (simulado)")

    elif cmd == "stop-live":
        state["live_mode"] = False
        print("live mode PARADO")

    else:
        print(f"desconhecido")


def register():
    """Registra no servidor (como o ESP32 faz a cada N segundos)."""
    state["uptime"] += 10
    state["free_heap"] = 245000 + random.randint(-5000, 5000)
    state["rssi"] = -45 + random.randint(-10, 5)

    data = {
        "chip_id": cfg["chip_id"],
        "short_id": cfg["short_id"],
        "type": cfg["module_type"],
        "ip": state["ip"],
        "ssid": state["ssid"],
        "rssi": state["rssi"],
        "uptime": state["uptime"],
        "free_heap": state["free_heap"],
        "capabilities": cfg["capabilities"],
        "ctrl_data": build_ctrl_data(),
    }

    resp = post_json(f"{BASE_URL}/api/modules/register", data)
    if not resp:
        return

    # Processar comandos pendentes
    commands = resp.get("commands", [])
    poll_interval = resp.get("poll_interval", 10000)

    if commands:
        for cmd in commands:
            process_command(cmd)
        # Re-registra imediatamente para enviar estado atualizado
        time.sleep(0.5)
        data["ctrl_data"] = build_ctrl_data()
        post_json(f"{BASE_URL}/api/modules/register", data)

    return poll_interval


# --- Main loop ---
print(f"=== Simulador ESP32 ({product}) ===")
print(f"Servidor: {BASE_URL}")
print(f"Chip ID: {cfg['chip_id']} ({cfg['short_id']})")
print(f"Capabilities: {cfg['capabilities']}")
print(f"")
print(f"O modulo simulado vai aparecer no app.")
print(f"Para vincular, use o codigo: {cfg['short_id']}")
print(f"")
print("Ctrl+C para parar\n")

interval = 10
while True:
    try:
        ts = time.strftime("%H:%M:%S")
        light = "ON" if state["light"] else "OFF"
        pump = "ON" if state["pump"] else "OFF"
        print(f"[{ts}] Registro (uptime={state['uptime']}s, light={light}, pump={pump})")

        poll_ms = register()
        if poll_ms:
            interval = max(poll_ms / 1000, 2)

        time.sleep(interval)

    except KeyboardInterrupt:
        print("\nSimulador encerrado.")
        break
    except Exception as e:
        print(f"Erro: {e}")
        time.sleep(5)
