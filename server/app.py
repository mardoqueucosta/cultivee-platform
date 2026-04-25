#!/usr/bin/env python3
"""
Cultivee — Servidor Unificado
Core: auth, modules, groups, dashboard.
Blueprints registrados por capability: /api/hidro, /api/hidro-farm, /api/cam, /api/gallery.
(/api/ctrl e alias deprecated de /api/hidro desde v4.1.28 — manter ate todos ESP32 migrarem)
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
from werkzeug.middleware.proxy_fix import ProxyFix

from config import PORT, PRODUCT_NAME, APP_VERSION
import models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="/static")

# v4.1.26: Limite global de request body (6MB). ESP32 envia fotos UXGA que raramente
# passam de 400KB; upload de firmware .bin fica ~1.3MB. 6MB cobre ambos com folga e
# evita que um cliente comprometido encha RAM/disco com uploads gigantes.
# Blueprints individuais (cam.py) podem ter limites mais apertados.
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

# v4.1.23: ProxyFix — honra X-Forwarded-* do Traefik (scheme, host, IP real)
# Sem isso, request.scheme sempre volta "http" (mesmo atras de HTTPS),
# request.remote_addr volta o IP do proxy e nao do cliente, e request.host
# pode volta o interno. Necessario antes de security headers (HSTS precisa
# saber se request e HTTPS) e logs estruturados com IP real do usuario.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

models.init_db()
log.info(f"Banco de dados inicializado ({PRODUCT_NAME})")

# v4.1.31: contador pra cleanup periodico do historico de status
# (usado em register_module; ver comentario la embaixo)
_REGISTER_COUNTER = 0

# v4.1.38: thread de background pra detectar modulos offline > threshold
# e disparar alerta proativo (push + email). Lock distribuido no banco
# garante que so 1 worker do Gunicorn execute o ciclo por intervalo.
try:
    from jobs.offline_watcher import start as _start_offline_watcher
    _start_offline_watcher()
except Exception as e:
    log.error(f"falhou start offline_watcher: {e}", exc_info=True)


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
    # v4.1.28: "ctrl" legado -> "hidro" normalizado. Ambos sao aceitos.
    module_type = data.get("type", "hidro")
    if module_type == "ctrl":
        module_type = "hidro"
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

    # v4.1.31: grava transicao offline->online no historico. Se o ultimo
    # evento ja e 'online', record_module_status e no-op (heartbeat silencioso).
    try:
        models.record_module_status(chip_id, "online", rssi=int(rssi) if rssi else None)
    except Exception as e:
        log.warning(f"status_event online falhou pra {chip_id}: {e}")

    # Cleanup periodico do historico (retencao 90 dias). Nao toda requisicao
    # pra nao virar hotspot — uma amostra a cada ~1000 registers.
    global _REGISTER_COUNTER
    _REGISTER_COUNTER = (_REGISTER_COUNTER + 1) % 1000
    if _REGISTER_COUNTER == 0:
        try:
            models.purge_old_status_events()
        except Exception as e:
            log.warning(f"purge_old_status_events falhou: {e}")

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
    # + SHA-256 pre-calculado (v4.1.26). ESP32 valida antes de aplicar.
    import pathlib
    _fw_dir = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    _fw_path = _fw_dir / f"{chip_id}.bin"
    _sha_path = _fw_dir / f"{chip_id}.sha256"
    firmware_url = None
    firmware_sha256 = None
    if _fw_path.exists():
        # Usa HTTP (nao HTTPS) porque o ESP32 nao faz TLS
        firmware_url = f"http://{request.host}/api/modules/{chip_id}/firmware"
        if _sha_path.exists():
            try:
                firmware_sha256 = _sha_path.read_text(encoding="utf-8").strip()
            except OSError:
                firmware_sha256 = None
        log.info(f"OTA remoto: firmware pendente pra {chip_id} ({_fw_path.stat().st_size} bytes, sha={firmware_sha256 or 'ausente'})")

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
        "firmware_sha256": firmware_sha256,
    })


# =====================================================================
# OTA Remoto — upload/download de firmware via servidor
# =====================================================================

@app.route("/api/modules/<chip_id>/firmware", methods=["POST"])
def firmware_upload(chip_id):
    """Upload de firmware .bin para OTA remoto. Requer auth + modulo pertence ao usuario.
    v4.1.26: calcula SHA-256 e armazena em <chip_id>.sha256 para o ESP32 validar."""
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    module = models.get_module_by_chip_id(chip_id)
    if not module or module.get("user_id") != user["id"]:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    file = request.files.get("firmware")
    if not file:
        return jsonify({"error": "Campo 'firmware' obrigatorio (multipart form)"}), 400

    import hashlib
    import pathlib
    fw_dir = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    fw_dir.mkdir(parents=True, exist_ok=True)
    fw_path = fw_dir / f"{chip_id}.bin"
    sha_path = fw_dir / f"{chip_id}.sha256"

    # Le o arquivo uma vez: salva + hasheia. Arquivo .bin cabe em RAM (~1.3MB).
    blob = file.read()
    fw_path.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    sha_path.write_text(digest, encoding="utf-8")

    size = fw_path.stat().st_size
    log.info(f"OTA remoto: firmware recebido pra {chip_id} ({size} bytes, sha256={digest})")
    return jsonify({
        "status": "ok",
        "size": size,
        "sha256": digest,
        "message": f"Firmware salvo. ESP32 vai baixar no proximo register (~10s).",
    })


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
    _fw_dir = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    fw_path = _fw_dir / f"{chip_id}.bin"
    sha_path = _fw_dir / f"{chip_id}.sha256"
    if not fw_path.exists():
        return jsonify({"error": "Sem firmware pendente"}), 404

    size = fw_path.stat().st_size
    log.info(f"OTA remoto: ESP32 {chip_id} baixando firmware ({size} bytes)")

    @after_this_request
    def remove_after_download(response):
        # v4.1.26: remove .bin + .sha256 juntos (sidecar do hash)
        try:
            if fw_path.exists():
                fw_path.unlink()
                log.info(f"OTA remoto: {chip_id}.bin removido apos download ({size} bytes) — loop prevenido")
            if sha_path.exists():
                sha_path.unlink()
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
    _fw_dir = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    fw_path = _fw_dir / f"{chip_id}.bin"
    sha_path = _fw_dir / f"{chip_id}.sha256"
    removed = False
    if fw_path.exists():
        fw_path.unlink()
        removed = True
    if sha_path.exists():
        sha_path.unlink()
    if removed:
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
        # v4.1.31: detecta offline silencioso (last_seen > threshold) e grava
        # transicao no historico. Barato — so escreve se mudou.
        try:
            models.compute_module_status_lazy(m["chip_id"], now=now)
        except Exception as e:
            log.warning(f"compute_module_status_lazy falhou pra {m.get('chip_id')}: {e}")

    return jsonify({"modules": modules})


@app.route("/api/modules/<chip_id>/uptime")
@require_auth
def module_uptime(chip_id):
    """
    Historico de online/offline do modulo. Proprio dono do modulo.
    Query: days=N (1..90, default 7), events=N (0..200, default 20).
    """
    module = models.get_module_by_chip_id(chip_id)
    if not module or module.get("user_id") != request.user["id"]:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    try:
        days = int(request.args.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(models.MODULE_STATUS_RETENTION_DAYS, days))
    try:
        n_events = int(request.args.get("events", 20))
    except (TypeError, ValueError):
        n_events = 20
    n_events = max(0, min(200, n_events))

    # Recalcula status antes de agregar (captura offline silencioso)
    try:
        models.compute_module_status_lazy(chip_id)
    except Exception as e:
        log.warning(f"compute_lazy em uptime: {e}")

    summary = models.get_module_uptime_summary(chip_id, days=days)
    events = models.get_module_status_events(chip_id, days=days, limit=n_events) if n_events > 0 else []
    return jsonify({
        "chip_id": chip_id,
        "summary": summary,
        "events": events,
    })


# =====================================================================
# v4.1.33 — Webhook de incidentes da plataforma (CF Worker → VPS)
# =====================================================================
# POST /api/platform-incident — recebido pelo Cloudflare Worker (status
# page externa) quando abre/fecha um incidente. Autenticacao: HMAC-SHA256
# sobre "{timestamp}.{body_bytes}" com o secret PLATFORM_INCIDENT_SECRET
# compartilhado. Anti-replay: timestamp deve estar dentro de 5min do agora.
#
# Efeito colateral: upsert em `platform_incidents` + marca retroativa em
# `module_status_events` (reason='server_down') — quedas dos modulos que
# coincidem com a janela do incidente sao marcadas e ficam excluidas do
# calculo de uptime do hardware (a menos que se pergunte o uptime_pct_raw).
#
# Se PLATFORM_INCIDENT_SECRET nao estiver no env, o endpoint retorna 401 —
# feature fica silenciosamente desligada ate que o operador configure.

_INCIDENT_WEBHOOK_MAX_SKEW_SEC = 300  # 5min de tolerancia p/ drift de relogio


def _verify_incident_webhook_signature(body_bytes, timestamp_str, signature_hex):
    """
    Valida HMAC-SHA256 + anti-replay. Retorna (True, None) se OK,
    (False, "erro") se invalido.
    """
    import hmac
    import hashlib
    secret = (os.environ.get("PLATFORM_INCIDENT_SECRET") or "").strip()
    if not secret:
        return False, "webhook_disabled"
    if not timestamp_str or not signature_hex:
        return False, "missing_headers"
    try:
        ts = int(timestamp_str)
    except (TypeError, ValueError):
        return False, "bad_timestamp"
    now = int(datetime.now().timestamp())
    if abs(now - ts) > _INCIDENT_WEBHOOK_MAX_SKEW_SEC:
        return False, "timestamp_too_old"
    payload = f"{ts}.".encode("utf-8") + body_bytes
    expected = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_hex.strip().lower()):
        return False, "bad_signature"
    return True, None


@app.route("/api/platform-incident", methods=["POST"])
def platform_incident_webhook():
    """
    Webhook do CF Worker. Chamado em open/close de incidentes.
    Idempotente — re-post com o mesmo webhook_id so atualiza end_at/reason.
    """
    raw = request.get_data() or b""
    sig = request.headers.get("X-Platform-Signature", "")
    ts = request.headers.get("X-Platform-Timestamp", "")
    ok, err = _verify_incident_webhook_signature(raw, ts, sig)
    if not ok:
        log.warning(f"platform_incident webhook rejected: {err}")
        return jsonify({"error": err or "unauthorized"}), 401

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"error": "bad_json"}), 400

    webhook_id = (payload.get("webhook_id") or "").strip()
    component = (payload.get("component") or "").strip()
    start_at = (payload.get("start") or "").strip()
    if not webhook_id or not component or not start_at:
        return jsonify({"error": "missing_fields"}), 400

    component_name = payload.get("component_name") or None
    end_at = (payload.get("end") or "").strip() or None
    reason = payload.get("reason") or None

    status, row = models.upsert_platform_incident(
        webhook_id=webhook_id,
        component=component,
        component_name=component_name,
        start_at=start_at,
        end_at=end_at,
        reason=reason,
    )
    affected = models.mark_module_events_as_server_down(start_at, end_at)
    log.info(
        f"platform_incident {status} id={row.get('id')} "
        f"webhook_id={webhook_id} events_marked={affected}"
    )
    return jsonify({
        "status": status,
        "incident_id": row.get("id"),
        "events_marked": affected,
    }), 200


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
from public.contact import public_bp  # v4.1.30: formularios do site institucional

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
# v4.1.28: hidro registrado em /api/hidro (novo padrao) E /api/ctrl (alias
# deprecated — manter ate 100% dos ESP32 + PWAs cacheados estarem em >=v4.1.28).
app.register_blueprint(hidro_bp, url_prefix="/api/hidro", name="hidro")
app.register_blueprint(hidro_bp, url_prefix="/api/ctrl", name="hidro_ctrl_legacy")
app.register_blueprint(hidrofarm_bp, url_prefix="/api/hidro-farm", name="hidrofarm")
app.register_blueprint(cam_bp, url_prefix="/api/cam", name="cam_standalone")
app.register_blueprint(gallery_bp, url_prefix="/api/gallery", name="gallery")

# --- Camada PUBLIC (v4.1.30) ---
# Formularios do site institucional (cultivee.com.br) — sem auth, com honeypot
# e rate limit in-memory. CORS seletivo configurado mais abaixo.
app.register_blueprint(public_bp, url_prefix="/api/public", name="public")

log.info("  [+] auth_bp registrado em /api/auth")
log.info("  [+] profile_bp registrado em /api/profile")
log.info("  [+] admin_bp registrado em /api/admin")
log.info("  [+] hidro_bp registrado em /api/hidro (novo) + /api/ctrl (alias deprecated)")
log.info("  [+] hidrofarm_bp registrado em /api/hidro-farm")
log.info("  [+] cam_bp registrado em /api/cam")
log.info("  [+] gallery_bp registrado em /api/gallery")
log.info("  [+] public_bp registrado em /api/public")


# v4.1.30: CORS seletivo so para /api/public/*
# Permite que o site institucional (cultivee.com.br + www) faca POST nos
# formularios publicos. Outras rotas (auth, hardware, admin) continuam sem CORS
# por design — sao acessadas so pelo PWA do mesmo dominio (app.cultivee.com.br)
# e pelos ESP32 que nao respeitam CORS mesmo.
_PUBLIC_CORS_ORIGINS = {
    "https://cultivee.com.br",
    "https://www.cultivee.com.br",
    "http://localhost:8080",   # vite dev (porta padrao do site)
    "http://localhost:8081",   # vite dev (porta alternativa quando 8080 ocupada)
    "http://localhost:5173",   # vite default
}


@app.after_request
def _public_cors(response):
    """Adiciona headers CORS em /api/public/* se origem for conhecida."""
    if request.path.startswith("/api/public/"):
        origin = request.headers.get("Origin", "")
        if origin in _PUBLIC_CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Max-Age"] = "3600"
    return response


# v4.1.28: loga uso do alias /api/ctrl com aviso de deprecacao — pra rastrear
# quando podemos remover com seguranca (alvo: zero calls em /api/ctrl por ~1 semana).
@app.before_request
def _log_ctrl_alias_deprecation():
    if request.path.startswith("/api/ctrl/"):
        log.info(f"[deprecated] /api/ctrl -> /api/hidro | {request.method} {request.path} | ua={request.headers.get('User-Agent', '')[:60]}")

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


# =====================================================================
# Security Headers (v4.1.23) — Rodada 1 infra quick wins
# =====================================================================
# Headers aplicados em todas as respostas exceto endpoints do ESP32
# (onde sao texto morto e so aumentam banda). HSTS so em request HTTPS.
#
# CSP atual usa 'unsafe-inline' + 'unsafe-eval' por causa de:
#   - scripts inline no index.html (PWA gera handlers inline)
#   - Turnstile (Cloudflare CAPTCHA)
# Evolucao ideal: migrar pra nonces por request (mais restritivo).
#
# Hosts externos liberados:
#   - fonts.googleapis.com / fonts.gstatic.com → Google Fonts (Inter)
#   - challenges.cloudflare.com → Turnstile (CAPTCHA scaffolding)
#   - api.qrserver.com → QR code do 2FA TOTP
#   - status.cultivee.com.br → CF Worker externo (status da plataforma, v4.1.32)

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://challenges.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https://api.qrserver.com; "
    "connect-src 'self' https://status.cultivee.com.br; "
    "frame-src https://challenges.cloudflare.com; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'self'"
)

# Permissions-Policy — desativa APIs sensiveis que a PWA nao usa
# (camera/mic do navegador nao sao usadas — fotos vem do ESP32 via HTTP)
_PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
    "accelerometer=(), gyroscope=(), magnetometer=()"
)


def _is_esp32_endpoint():
    """Retorna True para rotas chamadas pelo ESP32 (nao pelo navegador).
    Essas rotas nao precisam de security headers — ESP32 ignora e so gasta banda."""
    p = request.path
    if p in ("/api/modules/register", "/api/modules/poll"):
        return True
    # GET /api/modules/<chip_id>/firmware — ESP32 baixa .bin
    if p.endswith("/firmware") and request.method == "GET" and "/modules/" in p:
        return True
    # POST /api/cam/<chip_id>/upload-capture — ESP32 envia foto
    if p.endswith("/upload-capture") and request.method == "POST":
        return True
    # POST /api/cam/<chip_id>/live-frame — ESP32 faz push de frame
    if p.endswith("/live-frame") and request.method == "POST":
        return True
    return False


@app.after_request
def _add_security_headers(response):
    if _is_esp32_endpoint():
        return response
    # HSTS so em HTTPS (navegador ignora via HTTP) — ProxyFix garante
    # que request.scheme reflete o X-Forwarded-Proto do Traefik
    if request.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains"
        )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
    # CSP — so em respostas HTML (nao em JSON/imagens pra economizar banda)
    ctype = response.headers.get("Content-Type", "")
    if ctype.startswith("text/html") or "html" in ctype:
        response.headers.setdefault("Content-Security-Policy", _CSP)
    return response


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
