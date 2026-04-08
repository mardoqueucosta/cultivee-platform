"""
Teste automatizado de todas as rotas do servidor Cultivee.
Roda contra o servidor local (ctrl na porta 5002, hidro-cam na 5003).

Uso:
  python test_routes.py              # testa ctrl local (porta 5002)
  python test_routes.py hidro-cam    # testa hidro-cam local (porta 5003)
  python test_routes.py ctrl vps     # testa ctrl na VPS (hidro.cultivee.com.br)
  python test_routes.py hidro-cam vps # testa hidro-cam na VPS
"""

import sys
import os
import json
import time
import urllib.request
import urllib.error

# --- Config ---
product = sys.argv[1] if len(sys.argv) > 1 else "ctrl"
env = sys.argv[2] if len(sys.argv) > 2 else "local"

PRODUCTS = {
    "ctrl": {
        "local": "http://localhost:5002",
        "vps": "https://app.cultivee.com.br",
        "prefix": "/api/ctrl",
        "chip_id": "TEST_CTRL_99", "short_id": "TC99", "caps": ["hidro"],
    },
    "hidro-cam": {
        "local": "http://localhost:5003",
        "vps": "https://app.cultivee.com.br",
        "prefix": "/api/hidro-cam",
        "chip_id": "TEST_HCAM_99", "short_id": "TH99", "caps": ["hidro", "cam"],
    },
}

if product not in PRODUCTS:
    print(f"Produto invalido: {product}. Use: ctrl ou hidro-cam")
    sys.exit(1)
if env not in ("local", "vps"):
    print(f"Ambiente invalido: {env}. Use: local ou vps")
    sys.exit(1)

cfg = PRODUCTS[product]
BASE = cfg[env]
PREFIX = cfg["prefix"]
CHIP = cfg["chip_id"]
SHORT = cfg["short_id"]

# VPS usa HTTPS — desabilitar verificacao de certificado para testes
if env == "vps":
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

passed = 0
failed = 0
errors = []


def test(name, method, url, body=None, headers=None, expect_status=200, expect_json=None, expect_key=None):
    """Executa um teste e reporta resultado."""
    global passed, failed
    full_url = BASE + url
    h = headers or {}

    try:
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(full_url, data=data, method=method)
            req.add_header("Content-Type", "application/json")
        else:
            req = urllib.request.Request(full_url, method=method)

        for k, v in h.items():
            req.add_header(k, v)

        try:
            resp = urllib.request.urlopen(req, timeout=5)
            status = resp.status
            resp_body = resp.read().decode()
        except urllib.error.HTTPError as e:
            status = e.code
            resp_body = e.read().decode()

        # Parse JSON
        try:
            resp_json = json.loads(resp_body)
        except (json.JSONDecodeError, ValueError):
            resp_json = None

        # Check status
        ok = True
        msgs = []

        if status != expect_status:
            ok = False
            msgs.append(f"status={status} (esperado {expect_status})")

        if expect_json and resp_json:
            for k, v in expect_json.items():
                if resp_json.get(k) != v:
                    ok = False
                    msgs.append(f"{k}={resp_json.get(k)} (esperado {v})")

        if expect_key and resp_json:
            if expect_key not in resp_json:
                ok = False
                msgs.append(f"chave '{expect_key}' ausente")

        if ok:
            passed += 1
            print(f"  OK {name}")
        else:
            failed += 1
            detail = "; ".join(msgs)
            errors.append(f"{name}: {detail}")
            print(f"  FAIL {name} — {detail}")

        return resp_json, status

    except Exception as e:
        failed += 1
        errors.append(f"{name}: {e}")
        print(f"  FAIL {name} — ERRO: {e}")
        return None, 0


# =====================================================================
print(f"\n=== Teste de Rotas -- {product} ({env}: {BASE}) ===\n")

# --- 1. PWA / Static ---
print("[PWA]")
test("GET /", "GET", "/")
test("GET /manifest.json", "GET", "/manifest.json", expect_key="name")
test("GET /sw.js", "GET", "/sw.js")
test("GET /static/style.css", "GET", "/static/style.css")
test("GET /static/app.js", "GET", "/static/app.js")

# --- 2. Auth ---
print("\n[AUTH]")
email = f"test_{int(time.time())}@test.com"

resp, _ = test("POST /api/auth/register", "POST", "/api/auth/register",
               body={"email": email, "password": "test123", "name": "Teste Auto"},
               expect_key="token")
token = resp["token"] if resp else None
auth = {"Authorization": f"Bearer {token}"} if token else {}

test("POST /api/auth/register (duplicado)", "POST", "/api/auth/register",
     body={"email": email, "password": "test123", "name": "Teste"},
     expect_status=409, expect_json={"error": "Email ja cadastrado"})

test("POST /api/auth/register (sem dados)", "POST", "/api/auth/register",
     body={}, expect_status=400)

resp, _ = test("POST /api/auth/login", "POST", "/api/auth/login",
               body={"email": email, "password": "test123"},
               expect_key="token")
if resp:
    token = resp["token"]
    auth = {"Authorization": f"Bearer {token}"}

test("POST /api/auth/login (senha errada)", "POST", "/api/auth/login",
     body={"email": email, "password": "wrong"}, expect_status=401)

test("GET /api/auth/me", "GET", "/api/auth/me", headers=auth,
     expect_json={"email": email})

test("GET /api/auth/me (sem token)", "GET", "/api/auth/me", expect_status=401)

# --- 3. Module Registration (simula ESP32) ---
print("\n[MODULE REGISTER]")
reg_data = {
    "chip_id": CHIP, "short_id": SHORT, "type": product,
    "ip": "192.168.4.1", "ssid": "TestWiFi", "rssi": -50,
    "uptime": 100, "free_heap": 240000,
    "capabilities": cfg["caps"],
    "ctrl_data": {
        "light": False, "pump": False, "mode": "auto",
        "camera_ready": "cam" in cfg["caps"],
        "phases": [{"name": "Teste", "days": 7,
                     "lightOnHour": 6, "lightOnMin": 0,
                     "lightOffHour": 22, "lightOffMin": 0,
                     "pumpOnDay": 15, "pumpOffDay": 15,
                     "pumpOnNight": 30, "pumpOffNight": 30}],
        "num_phases": 1, "start_date": "2026-03-23"
    }
}
test("POST /api/modules/register", "POST", "/api/modules/register",
     body=reg_data, expect_json={"status": "ok"}, expect_key="poll_interval")

# Re-register (update)
test("POST /api/modules/register (update)", "POST", "/api/modules/register",
     body=reg_data, expect_json={"status": "ok"})

# --- 4. Module Pairing ---
print("\n[MODULE PAIR]")
test("POST /api/modules/pair", "POST", "/api/modules/pair",
     body={"short_id": SHORT, "name": "Modulo Teste"},
     headers=auth, expect_json={"status": "ok"})

test("POST /api/modules/pair (sem token)", "POST", "/api/modules/pair",
     body={"short_id": SHORT}, expect_status=401)

test("POST /api/modules/pair (inexistente)", "POST", "/api/modules/pair",
     body={"short_id": "ZZZZ", "name": "Nope"},
     headers=auth, expect_status=404)

test("GET /api/modules", "GET", "/api/modules", headers=auth, expect_key="modules")

# --- 5. Polling ---
print("\n[POLLING]")
test("GET /api/modules/poll", "GET", f"/api/modules/poll?chip_id={CHIP}",
     expect_key="commands")

test("GET /api/modules/poll (sem chip)", "GET", "/api/modules/poll",
     expect_json={"commands": []})

# --- 6. Hidro Routes ---
print("\n[HIDRO]")
test("GET status", "GET", f"{PREFIX}/{CHIP}/status", headers=auth, expect_key="online")

test("GET relay (light)", "GET", f"{PREFIX}/{CHIP}/relay?device=light&action=toggle",
     headers=auth, expect_json={"status": "queued"})

test("GET relay (pump)", "GET", f"{PREFIX}/{CHIP}/relay?device=pump&action=toggle",
     headers=auth, expect_json={"status": "queued"})

test("GET relay (mode)", "GET", f"{PREFIX}/{CHIP}/relay?device=mode&action=toggle",
     headers=auth, expect_json={"status": "queued"})

test("GET relay (sem auth)", "GET", f"{PREFIX}/{CHIP}/relay?device=light",
     expect_status=401)

test("GET phases", "GET", f"{PREFIX}/{CHIP}/phases", headers=auth, expect_key="phases")

test("GET phases?live=1", "GET", f"{PREFIX}/{CHIP}/phases?live=1", headers=auth,
     expect_key="phases")

# Reset para estado conhecido antes de testar contagem
test("GET reset-phases (setup)", "GET", f"{PREFIX}/{CHIP}/reset-phases", headers=auth,
     expect_json={"status": "ok"})

test("GET add-phase", "GET", f"{PREFIX}/{CHIP}/add-phase", headers=auth,
     expect_json={"status": "ok"})

# Verify phase was added
resp, _ = test("GET phases (apos add)", "GET", f"{PREFIX}/{CHIP}/phases", headers=auth,
               expect_key="phases")
if resp and len(resp.get("phases", [])) != 4:
    failed += 1
    errors.append(f"add-phase: esperado 4 fases (3+1), tem {len(resp.get('phases', []))}")
    print(f"  FAIL add-phase count -- esperado 4, tem {len(resp.get('phases', []))}")
else:
    passed += 1
    print(f"  OK add-phase count (4 fases: 3 default + 1)")

test("GET remove-phase (idx=3)", "GET", f"{PREFIX}/{CHIP}/remove-phase?idx=3",
     headers=auth, expect_json={"status": "ok"})

# Verify phase was removed
resp, _ = test("GET phases (apos remove)", "GET", f"{PREFIX}/{CHIP}/phases", headers=auth,
               expect_key="phases")
if resp and len(resp.get("phases", [])) != 3:
    failed += 1
    errors.append(f"remove-phase: esperado 3 fases, tem {len(resp.get('phases', []))}")
    print(f"  FAIL remove-phase count -- esperado 3, tem {len(resp.get('phases', []))}")
else:
    passed += 1
    print(f"  OK remove-phase count (3 fases)")

test("POST save-config", "POST", f"{PREFIX}/{CHIP}/save-config",
     body={"start_date": "2026-04-01", "num_phases": 1,
           "n0": "Vegetativo", "d0": 21, "lon0": "06:00", "loff0": "20:00",
           "pod0": 15, "pfd0": 15, "pon0": 30, "pfn0": 30},
     headers=auth, expect_json={"status": "ok"})

# Verify config was saved
resp, _ = test("GET status (apos save)", "GET", f"{PREFIX}/{CHIP}/status",
               headers=auth, expect_key="start_date")
if resp and resp.get("start_date") != "2026-04-01":
    failed += 1
    errors.append(f"save-config: start_date={resp.get('start_date')} (esperado 2026-04-01)")
    print(f"  FAIL save-config verify — start_date errado")
else:
    passed += 1
    print(f"  OK save-config verify (start_date=2026-04-01)")

test("GET reset-phases", "GET", f"{PREFIX}/{CHIP}/reset-phases",
     headers=auth, expect_json={"status": "ok"})

# Verify reset
resp, _ = test("GET phases (apos reset)", "GET", f"{PREFIX}/{CHIP}/phases", headers=auth,
               expect_key="phases")
if resp and len(resp.get("phases", [])) != 3:
    failed += 1
    errors.append(f"reset-phases: esperado 3 fases, tem {len(resp.get('phases', []))}")
    print(f"  FAIL reset-phases count — esperado 3, tem {len(resp.get('phases', []))}")
else:
    passed += 1
    print(f"  OK reset-phases count (3 fases default)")

test("GET reset-wifi", "GET", f"{PREFIX}/{CHIP}/reset-wifi",
     headers=auth, expect_key="status")

# Verify pending commands were created
resp, _ = test("GET poll (commands)", "GET", f"/api/modules/poll?chip_id={CHIP}",
               expect_key="commands")
if resp:
    cmds = resp.get("commands", [])
    cmd_names = [c.get("cmd") for c in cmds]
    print(f"    -> Comandos pendentes consumidos: {cmd_names}")

# --- 7. Camera Routes (only for hidro-cam) ---
if "cam" in cfg["caps"]:
    print("\n[CAMERA]")
    test("GET capture", "GET", f"{PREFIX}/{CHIP}/capture",
         headers=auth, expect_json={"status": "queued"})

    test("GET last-capture (sem foto)", "GET", f"{PREFIX}/{CHIP}/last-capture",
         headers=auth, expect_status=200)

    # Simulate upload from ESP32
    import io
    # Create a minimal JPEG (2x2 white pixel)
    fake_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9
    ])

    try:
        boundary = "----TestBoundary123"
        body_parts = []
        body_parts.append(f"--{boundary}".encode())
        body_parts.append(b'Content-Disposition: form-data; name="image"; filename="capture.jpg"')
        body_parts.append(b"Content-Type: image/jpeg")
        body_parts.append(b"")
        body_parts.append(fake_jpeg)
        body_parts.append(f"--{boundary}--".encode())
        body_bytes = b"\r\n".join(body_parts)

        req = urllib.request.Request(
            f"{BASE}{PREFIX}/{CHIP}/upload-capture",
            data=body_bytes,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read().decode())
        if result.get("status") == "ok":
            passed += 1
            print(f"  OK POST upload-capture")
            image_url = result.get("url", "")
        else:
            failed += 1
            errors.append(f"upload-capture: {result}")
            print(f"  FAIL POST upload-capture — {result}")
            image_url = ""
    except Exception as e:
        failed += 1
        errors.append(f"upload-capture: {e}")
        print(f"  FAIL POST upload-capture — {e}")
        image_url = ""

    # Last capture should now return URL
    resp, _ = test("GET last-capture (com foto)", "GET", f"{PREFIX}/{CHIP}/last-capture",
                   headers=auth, expect_key="url")

    if image_url:
        # Extract filename from URL
        parts = image_url.split("/")
        if len(parts) >= 2:
            filename = parts[-1]
            test("GET image", "GET", f"{PREFIX}/{CHIP}/image/{filename}?token={token}",
                 expect_status=200)

# --- 8. Unpair ---
print("\n[UNPAIR]")
test("POST /api/modules/unpair", "POST", "/api/modules/unpair",
     body={"chip_id": CHIP}, headers=auth, expect_json={"status": "ok"})

# Verify unpaired
resp, _ = test("GET modules (apos unpair)", "GET", "/api/modules", headers=auth,
               expect_key="modules")
if resp:
    mods = resp.get("modules", [])
    has_test = any(m.get("chip_id") == CHIP for m in mods)
    if has_test:
        failed += 1
        errors.append("unpair: modulo ainda aparece na lista")
        print(f"  FAIL unpair verify — modulo ainda na lista")
    else:
        passed += 1
        print(f"  OK unpair verify (modulo removido da lista)")

# --- 9. Logout ---
print("\n[LOGOUT]")
test("POST /api/auth/logout", "POST", "/api/auth/logout", headers=auth,
     expect_json={"status": "ok"})

test("GET /api/auth/me (apos logout)", "GET", "/api/auth/me", headers=auth,
     expect_status=401)

# --- Resumo ---
total = passed + failed
print(f"\n{'='*50}")
print(f"RESULTADO: {passed}/{total} passaram", end="")
if failed:
    print(f" ({failed} falharam)")
    print(f"\nFalhas:")
    for e in errors:
        print(f"  - {e}")
else:
    print(" ALL PASSED")
print()

sys.exit(0 if failed == 0 else 1)
