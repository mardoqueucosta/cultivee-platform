#!/usr/bin/env python3
"""
Cultivee — Servidor Unificado
Core: auth, modules, groups, dashboard.
Blueprints registrados por capability: /api/ctrl, /api/hidro-farm, /api/cam, /api/gallery.
"""

import os
import json
import logging
from datetime import datetime
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

import urllib.request
import urllib.error
from flask import Flask, request, jsonify, send_from_directory, render_template, Response, after_this_request

from config import PORT, PRODUCT_NAME, APP_VERSION
import models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="/static")

models.init_db()
log.info(f"Banco de dados inicializado ({PRODUCT_NAME})")


# =====================================================================
# Auth helpers (exportados para blueprints)
# =====================================================================

def _extract_token():
    """Extrai token do header Authorization: Bearer ou da query string ?token."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.args.get("token", "")


def require_auth_func():
    """Retorna usuario autenticado ou None. Usado pelos blueprints."""
    tok = _extract_token()
    if not tok:
        return None
    user_id = models.validate_token(tok)
    if not user_id:
        return None
    return models.get_user_by_id(user_id)


# v4.1.15: middleware de escopo readonly
# Bloqueia mutacoes em rotas /api/* quando o token em uso tem scope='readonly'.
# Usado pelo modo "Ver como" do admin — permite inspecionar mas nao alterar nada.
#
# Mutacoes detectadas de duas formas:
#  1. Metodo HTTP: POST/PUT/DELETE/PATCH sempre sao mutacoes
#  2. Path com segmento tipico de acao: /relay, /capture, etc. (herdado do legado
#     onde controlamos reles via GET — simples de chamar no ESP32 mas nao RESTful).
#     Nao eh ideal, mas ampliar a lista abaixo funciona ate refatoracao RESTful.
_READONLY_EXEMPT_PATHS = {
    "/api/auth/logout",         # user precisa poder finalizar a sessao
    "/api/modules/register",    # ESP32 nao usa token de user
    "/api/modules/poll",        # ESP32 nao usa token
}

# Endpoints GET que MUTAM estado (convencao legada de controle)
_GET_MUTATION_SEGMENTS = (
    "/relay",          # aciona rele
    "/save-config",
    "/add-phase",
    "/remove-phase",
    "/reset-phases",
    "/reset-wifi",
    "/capture",
    "/start-live",
    "/stop-live",
    "/sensor-config",
)


def _is_mutation_request():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        return True
    if request.method == "GET":
        p = request.path
        for seg in _GET_MUTATION_SEGMENTS:
            if p.endswith(seg) or seg + "?" in p:
                return True
    return False


@app.before_request
def _readonly_scope_guard():
    if not request.path.startswith("/api/"):
        return
    if request.path in _READONLY_EXEMPT_PATHS:
        return
    if not _is_mutation_request():
        return  # leitura pura — sempre permitida
    tok = _extract_token()
    if not tok:
        return  # deixa o route handler cuidar da autenticacao
    info = models.validate_token_full(tok)
    if not info:
        return  # token invalido — deixa o route handler retornar 401
    _, scope = info
    if scope == "readonly":
        log.info(f"[readonly] bloqueado {request.method} {request.path}")
        return jsonify({
            "error": "Sessao somente leitura — mutacoes nao permitidas neste modo"
        }), 403


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = require_auth_func()
        if not user:
            return jsonify({"error": "Nao autenticado"}), 401
        request.user = user
        return f(*args, **kwargs)
    return decorated


# =====================================================================
# Auth endpoints — movidos para bp_auth.py (v4.1.12)
# register, login, me, logout, forgot-password, reset-password
# Registrado abaixo no bloco de blueprints.
# =====================================================================


# =====================================================================
# User module prefs (v4.1.10) — persiste ordem + selecao no servidor
# (antes so localStorage, perdia ao limpar cache do browser)
# =====================================================================

@app.route("/api/user/prefs", methods=["GET"])
@require_auth
def get_user_prefs():
    user = request.user
    return jsonify(models.get_user_module_prefs(user["id"]))


@app.route("/api/user/prefs", methods=["PUT"])
@require_auth
def save_user_prefs():
    user = request.user
    # force=True: aceita JSON mesmo sem Content-Type: application/json
    # (defesa contra clientes que esquecem o header)
    data = request.get_json(silent=True, force=True) or {}
    # Validacao basica: aceita apenas chaves conhecidas, listas de strings
    clean = {}
    if isinstance(data.get("selected"), list):
        clean["selected"] = [str(x) for x in data["selected"] if x]
    if isinstance(data.get("order"), list):
        clean["order"] = [str(x) for x in data["order"] if x]
    models.save_user_module_prefs(user["id"], clean)
    return jsonify({"status": "ok"})


# =====================================================================
# Module endpoints (core — todos os produtos)
# =====================================================================

@app.route("/api/modules/register", methods=["POST"])
def register_module():
    """ESP32 chama ao conectar para se registrar."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON invalido"}), 400

    chip_id = data.get("chip_id", "")
    short_id = data.get("short_id", "")
    module_type = data.get("type", "ctrl")
    ip = data.get("ip", "")
    ssid = data.get("ssid", "")
    rssi = data.get("rssi", 0)
    uptime = data.get("uptime", 0)
    free_heap = data.get("free_heap", 0)
    ctrl_data = json.dumps(data.get("ctrl_data", {}))
    capabilities = json.dumps(data.get("capabilities", []))

    if not chip_id:
        return jsonify({"error": "chip_id obrigatorio"}), 400

    models.register_module(chip_id, short_id, module_type, ip, ssid, rssi, uptime, free_heap, ctrl_data, capabilities)

    # Alertas — verifica condicoes e notifica se necessario (non-blocking)
    try:
        from notifications import alert_manager
        module_row = models.get_module_by_chip_id(chip_id)
        if module_row and module_row.get("user_id"):
            alert_manager.check(chip_id, json.loads(ctrl_data), module_row)
    except Exception as e:
        log.error(f"Alert check error: {e}")

    # Busca comandos pendentes
    pending = models.get_pending_commands(chip_id)
    if pending:
        log.info(f"Modulo {short_id}: enviando {len(pending)} comando(s) pendente(s)")

    simple_cmds = []
    for cmd in pending:
        simple = {"cmd": cmd["command"]}
        try:
            params = json.loads(cmd.get("params", "{}"))
            simple.update(params)
        except (json.JSONDecodeError, TypeError):
            pass
        simple_cmds.append(simple)

    poll_interval = models.get_poll_interval(chip_id)

    # Captura agendada: se recording ativo e intervalo passou, enfileira captura
    capture_cfg = models.get_capture_config(chip_id)
    if capture_cfg["recording"]:
        interval = capture_cfg["capture_interval"]
        last = capture_cfg["last_capture_at"]
        should_capture = False
        if not last:
            should_capture = True
        else:
            try:
                elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
                should_capture = elapsed >= interval
            except (ValueError, TypeError):
                should_capture = True
        if should_capture:
            simple_cmds.append({"cmd": "capture"})
            models.mark_capture(chip_id)
            log.info(f"Captura agendada: {chip_id} (intervalo={interval}s)")

    # OTA remoto: se existe firmware pendente pra esse chip, inclui URL de download
    import pathlib
    _fw_dir = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    _fw_path = _fw_dir / f"{chip_id}.bin"
    firmware_url = None
    if _fw_path.exists():
        # Usa HTTP (nao HTTPS) porque o ESP32 nao faz TLS
        firmware_url = f"http://{request.host}/api/modules/{chip_id}/firmware"
        log.info(f"OTA remoto: firmware pendente pra {chip_id} ({_fw_path.stat().st_size} bytes)")

    log.info(f"Modulo registrado: {module_type} {chip_id} ({short_id}) IP={ip} poll={poll_interval}ms")
    return jsonify({
        "status": "ok",
        "commands": simple_cmds,
        "poll_interval": poll_interval,
        "capture_interval": capture_cfg["capture_interval"],
        "recording": capture_cfg["recording"],
        "cam_resolution": capture_cfg["cam_resolution"],
        "cam_quality": capture_cfg["cam_quality"],
        "firmware_url": firmware_url,
    })


# =====================================================================
# OTA Remoto — upload/download de firmware via servidor
# =====================================================================

@app.route("/api/modules/<chip_id>/firmware", methods=["POST"])
def firmware_upload(chip_id):
    """Upload de firmware .bin para OTA remoto. Requer auth + modulo pertence ao usuario."""
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    module = models.get_module_by_chip_id(chip_id)
    if not module or module.get("user_id") != user["id"]:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    file = request.files.get("firmware")
    if not file:
        return jsonify({"error": "Campo 'firmware' obrigatorio (multipart form)"}), 400

    import pathlib
    fw_dir = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    fw_dir.mkdir(parents=True, exist_ok=True)
    fw_path = fw_dir / f"{chip_id}.bin"
    file.save(str(fw_path))

    size = fw_path.stat().st_size
    log.info(f"OTA remoto: firmware recebido pra {chip_id} ({size} bytes)")
    return jsonify({"status": "ok", "size": size, "message": f"Firmware salvo. ESP32 vai baixar no proximo register (~10s)."})


@app.route("/api/modules/<chip_id>/firmware", methods=["GET"])
def firmware_download(chip_id):
    """Download do firmware .bin pelo ESP32. Sem auth (ESP32 nao carrega token).

    CRITICO: apos download bem-sucedido, o .bin eh removido automaticamente.
    Sem isso, o ESP32 entraria em loop infinito de OTA (apos reboot, nova tentativa
    da mesma versao). A flag otaRemoteAttempted eh RAM e reseta a cada reboot, entao
    a unica forma segura de cortar o loop eh remover o arquivo no servidor.
    Se o download falhar no ESP32, o usuario precisa fazer upload novamente.
    """
    import pathlib
    fw_path = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware" / f"{chip_id}.bin"
    if not fw_path.exists():
        return jsonify({"error": "Sem firmware pendente"}), 404

    size = fw_path.stat().st_size
    log.info(f"OTA remoto: ESP32 {chip_id} baixando firmware ({size} bytes)")

    @after_this_request
    def remove_after_download(response):
        try:
            if fw_path.exists():
                fw_path.unlink()
                log.info(f"OTA remoto: {chip_id}.bin removido apos download ({size} bytes) — loop prevenido")
        except Exception as e:
            log.error(f"OTA remoto: falha ao remover {chip_id}.bin: {e}")
        return response

    return Response(
        fw_path.read_bytes(),
        mimetype="application/octet-stream",
        headers={"Content-Length": str(size)}
    )


@app.route("/api/modules/<chip_id>/firmware", methods=["DELETE"])
def firmware_delete(chip_id):
    """Remove firmware pendente (cancela OTA). Requer auth."""
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401

    import pathlib
    fw_path = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware" / f"{chip_id}.bin"
    if fw_path.exists():
        fw_path.unlink()
        log.info(f"OTA remoto: firmware removido pra {chip_id}")
        return jsonify({"status": "ok", "message": "Firmware pendente removido"})
    return jsonify({"status": "ok", "message": "Nenhum firmware pendente"})


@app.route("/api/modules/poll")
def poll_commands():
    """Endpoint leve: ESP32 busca comandos pendentes rapidamente."""
    chip_id = request.args.get("chip_id", "")
    if not chip_id:
        return jsonify({"commands": []})

    pending = models.get_pending_commands(chip_id)
    simple_cmds = []
    for cmd in pending:
        simple = {"cmd": cmd["command"]}
        try:
            params = json.loads(cmd.get("params", "{}"))
            simple.update(params)
        except (json.JSONDecodeError, TypeError):
            pass
        simple_cmds.append(simple)

    poll_interval = models.get_poll_interval(chip_id)
    return jsonify({"commands": simple_cmds, "poll_interval": poll_interval})


# =====================================================================
# Push Notifications — subscribe/unsubscribe
# =====================================================================

@app.route("/api/push/subscribe", methods=["POST"])
@require_auth
def push_subscribe():
    """PWA envia subscription apos o usuario permitir notificacoes."""
    data = request.get_json()
    sub = data.get("subscription", {})
    endpoint = sub.get("endpoint")
    keys = sub.get("keys", {})
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return jsonify({"error": "Subscription incompleta"}), 400
    models.save_push_subscription(request.user["id"], endpoint, keys["p256dh"], keys["auth"])
    log.info(f"Push subscription salva: user={request.user['id']} endpoint={endpoint[:60]}...")
    return jsonify({"status": "ok"})


@app.route("/api/push/unsubscribe", methods=["POST"])
@require_auth
def push_unsubscribe():
    """Remove subscription de push (usuario desativou notificacoes)."""
    data = request.get_json()
    endpoint = data.get("endpoint", "")
    if endpoint:
        models.delete_push_subscription(request.user["id"], endpoint)
        log.info(f"Push subscription removida: user={request.user['id']}")
    return jsonify({"status": "ok"})


@app.route("/api/modules/pair", methods=["POST"])
@require_auth
def pair_module():
    data = request.get_json()
    short_id = data.get("short_id", "").upper()
    name = data.get("name", "")

    if not short_id:
        return jsonify({"error": "short_id obrigatorio"}), 400

    module = models.get_module_by_short_id(short_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado. Verifique se esta ligado."}), 404

    ok, msg = models.pair_module(module["chip_id"], request.user["id"], name)
    if not ok:
        return jsonify({"error": msg}), 400

    module = models.get_module_by_chip_id(module["chip_id"])
    return jsonify({"status": "ok", "message": msg, "module": module})


@app.route("/api/modules/unpair", methods=["POST"])
@require_auth
def unpair_module():
    data = request.get_json()
    chip_id = data.get("chip_id", "")
    models.unpair_module(chip_id, request.user["id"])
    return jsonify({"status": "ok"})


@app.route("/api/modules")
@require_auth
def list_modules():
    modules = models.get_user_modules(request.user["id"])

    now = datetime.now()
    for m in modules:
        if m.get("last_seen"):
            last = datetime.fromisoformat(m["last_seen"])
            m["online"] = (now - last).total_seconds() < 120
        else:
            m["online"] = False
        try:
            m["ctrl_data"] = json.loads(m.get("ctrl_data", "{}"))
        except (json.JSONDecodeError, TypeError):
            m["ctrl_data"] = {}
        try:
            m["capabilities"] = json.loads(m.get("capabilities", "[]"))
        except (json.JSONDecodeError, TypeError):
            m["capabilities"] = []

    return jsonify({"modules": modules})




# =====================================================================
# Registro de blueprints — todos os prefixos (servidor unico)
# =====================================================================

# v4.1.17: blueprints organizados em pastas por camada (hardware/usuario/admin)
# Mesma convencao do models/ — materializa as 3 camadas no filesystem.
from usuario.auth import auth_bp
from usuario.profile import profile_bp
from admin.admin import admin_bp
from hardware.hidro import hidro_bp
from hardware.hidrofarm import hidrofarm_bp
from hardware.cam import cam_bp
from hardware.gallery import gallery_bp

# --- Camada de USUARIO ---
# Auth (registro, login, logout, recuperacao de senha)
app.register_blueprint(auth_bp, url_prefix="/api/auth", name="auth")
# Perfil do usuario logado (dados pessoais + endereco + troca de senha)
app.register_blueprint(profile_bp, url_prefix="/api/profile", name="profile")

# --- Camada de ADMIN ---
# Rotas protegidas por role='admin' (stats, users, audit, impersonation)
app.register_blueprint(admin_bp, url_prefix="/api/admin", name="admin")

# --- Camada de HARDWARE ---
# Cada tipo de firmware encontra suas rotas pelo prefixo
app.register_blueprint(hidro_bp, url_prefix="/api/ctrl", name="hidro_ctrl")
app.register_blueprint(hidrofarm_bp, url_prefix="/api/hidro-farm", name="hidrofarm")
app.register_blueprint(cam_bp, url_prefix="/api/cam", name="cam_standalone")
app.register_blueprint(gallery_bp, url_prefix="/api/gallery", name="gallery")

log.info("  [+] auth_bp registrado em /api/auth")
log.info("  [+] profile_bp registrado em /api/profile")
log.info("  [+] admin_bp registrado em /api/admin")
log.info("  [+] hidro_bp registrado em /api/ctrl")
log.info("  [+] hidrofarm_bp registrado em /api/hidro-farm")
log.info("  [+] cam_bp registrado em /api/cam")
log.info("  [+] gallery_bp registrado em /api/gallery")

# Migrar fotos existentes (flat) para _sem-pasta (uma vez)
import pathlib
_capture_base = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "captures"
_thumb_base = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "thumbs"
if _capture_base.exists():
    for chip_dir in _capture_base.iterdir():
        if not chip_dir.is_dir():
            continue
        flat_jpgs = list(chip_dir.glob("*.jpg"))
        if flat_jpgs:
            sem_pasta = chip_dir / "_sem-pasta"
            sem_pasta.mkdir(exist_ok=True)
            thumb_sem = _thumb_base / chip_dir.name / "_sem-pasta"
            thumb_sem.mkdir(parents=True, exist_ok=True)
            for jpg in flat_jpgs:
                jpg.rename(sem_pasta / jpg.name)
                thumb = _thumb_base / chip_dir.name / jpg.name
                if thumb.exists():
                    thumb.rename(thumb_sem / jpg.name)
            log.info(f"Migradas {len(flat_jpgs)} fotos de {chip_dir.name} para _sem-pasta")


# =====================================================================
# Config do PWA (unificada — features descobertas via API)
# =====================================================================

pwa_cfg = {
    "title": "Cultivee",
    "subtitle": "Cultivo inteligente",
    "navbar_subtitle": "Cultivo Inteligente",
    "short_name": "Cultivee",
    "description": "Plataforma IoT para cultivo inteligente",
    "default_name": "Dispositivo",
    "ap_ssid": "Cultivee",
    "storage_prefix": "cultivee",
    "cache_prefix": "cultivee",
    "version": APP_VERSION,
    "vapid_public_key": os.environ.get("VAPID_PUBLIC_KEY", ""),
    # v4.1.22: CAPTCHA — se site key nao esta setada, widget nao aparece no frontend
    "turnstile_site_key": os.environ.get("TURNSTILE_SITE_KEY", ""),
}


# =====================================================================
# Dashboard / PWA (template dinamico com config injetada)
# =====================================================================

@app.route("/")
def dashboard():
    return render_template("index.html", config=pwa_cfg)


# v4.1.20: paginas estaticas de compliance (termos + privacidade LGPD)
@app.route("/termos")
def terms_page():
    return render_template("terms.html", config=pwa_cfg)


@app.route("/privacidade")
def privacy_page():
    return render_template("privacy.html", config=pwa_cfg)


@app.route("/manifest.json")
def manifest():
    data = json.dumps({
        "name": pwa_cfg["title"],
        "short_name": pwa_cfg["short_name"],
        "description": pwa_cfg["description"],
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f1923",
        "theme_color": "#0f1923",
        "orientation": "portrait",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }, indent=2)
    return Response(data, mimetype="application/json",
                    headers={"Cache-Control": "no-cache, must-revalidate"})


@app.route("/sw.js")
def service_worker():
    sw_js = f"""const APP_VERSION = '{APP_VERSION}';
const CACHE_NAME = '{pwa_cfg["cache_prefix"]}-v' + APP_VERSION;
const STATIC_ASSETS = [
    '/',
    '/static/style.css',
    '/static/app.js',
    '/static/icon-192.png',
    '/static/icon-512.png',
    '/manifest.json'
];

self.addEventListener('install', (event) => {{
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {{
            return cache.addAll(STATIC_ASSETS);
        }})
    );
}});

self.addEventListener('activate', (event) => {{
    event.waitUntil(
        caches.keys().then((keys) => {{
            const oldKeys = keys.filter(k => k.startsWith('cultivee') && k !== CACHE_NAME);
            if (oldKeys.length > 0) {{
                self.clients.matchAll().then(clients => {{
                    clients.forEach(client => {{
                        client.postMessage({{ type: 'APP_UPDATED', version: APP_VERSION }});
                    }});
                }});
            }}
            return Promise.all(oldKeys.map(k => caches.delete(k)));
        }})
    );
}});

self.addEventListener('fetch', (event) => {{
    if (event.request.url.includes('/api/')) return;
    event.respondWith(
        fetch(event.request)
            .then((response) => {{
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {{
                    cache.put(event.request, clone);
                }});
                return response;
            }})
            .catch(() => {{
                return caches.match(event.request);
            }})
    );
}});

self.addEventListener('message', (event) => {{
    if (event.data === 'SKIP_WAITING') {{
        self.skipWaiting();
    }}
}});

// Push notification handler (alertas do servidor)
self.addEventListener('push', (event) => {{
    const data = event.data ? event.data.json() : {{}};
    const title = data.title || 'Cultivee Alerta';
    const options = {{
        body: data.body || '',
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        tag: data.tag || 'cultivee-alert',
        data: {{ url: data.url || '/' }}
    }};
    event.waitUntil(self.registration.showNotification(title, options));
}});

// Click na notificacao — abre o app
self.addEventListener('notificationclick', (event) => {{
    event.notification.close();
    const url = event.notification.data.url || '/';
    event.waitUntil(
        clients.matchAll({{ type: 'window' }}).then((list) => {{
            for (const c of list) {{
                if (c.url.includes(self.location.origin) && 'focus' in c) return c.focus();
            }}
            return clients.openWindow(url);
        }})
    );
}});
"""
    return Response(sw_js, mimetype="application/javascript",
                    headers={
                        "Service-Worker-Allowed": "/",
                        "Cache-Control": "no-cache, no-store, must-revalidate"
                    })


@app.after_request
def add_no_cache_for_static(response):
    if request.path.startswith('/static/') or request.path == '/':
        response.headers['Cache-Control'] = 'no-cache, must-revalidate, max-age=0'
    return response


# =====================================================================
# Main
# =====================================================================

if __name__ == "__main__":
    log.info(f"{PRODUCT_NAME} Server: http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
