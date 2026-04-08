"""
Cultivee — Blueprint Camera
Rotas de captura: enfileirar captura, upload push, live frame, servir imagem.
Registrado com url_prefix dinamico (ex: /api/hidro-cam).
"""

import os
import json
import pathlib
import logging
import threading
import time
from datetime import datetime

from flask import Blueprint, request, jsonify, Response

import models

log = logging.getLogger(__name__)

cam_bp = Blueprint("cam", __name__)

CAPTURE_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "captures"
THUMB_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "thumbs"
LIVE_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "live"
THUMB_SIZE = (200, 150)


def generate_thumbnail(chip_id, filename, img_data):
    """Gera thumbnail 200x150 a partir dos bytes JPEG."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_data))
        img.thumbnail(THUMB_SIZE)
        thumb_dir = THUMB_DIR / chip_id
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / filename
        img.save(thumb_path, "JPEG", quality=70)
    except Exception as e:
        log.warning(f"Erro gerando thumbnail: {e}")

# In-memory live frame buffer (thread-safe)
_live_frames = {}  # chip_id -> {"data": bytes, "ts": float}
_live_lock = threading.Lock()


def _get_cam_module_or_404(chip_id):
    """Helper: retorna modulo se pertence ao usuario autenticado e tem capability cam."""
    module = models.get_module_by_chip_id(chip_id)
    if not module or module.get("user_id") != request.user["id"]:
        return None
    try:
        caps = json.loads(module.get("capabilities", "[]"))
    except (json.JSONDecodeError, TypeError):
        caps = []
    if "cam" not in caps:
        return None
    return module


# =====================================================================
# Camera routes — montadas no prefix configurado
# =====================================================================

@cam_bp.route("/<chip_id>/capture")
def capture(chip_id):
    """Enfileira comando de captura — ESP32 vai tirar foto e enviar via push."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    models.add_pending_command(chip_id, "capture")
    models.mark_activity(chip_id)
    return jsonify({"status": "queued"})


@cam_bp.route("/<chip_id>/upload-capture", methods=["POST"])
def upload_capture(chip_id):
    """ESP32 envia foto capturada (push). Sem auth mas valida chip_id + capability."""
    module = models.get_module_by_chip_id(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404
    try:
        caps = json.loads(module.get("capabilities", "[]"))
    except (json.JSONDecodeError, TypeError):
        caps = []
    if "cam" not in caps:
        return jsonify({"error": "Modulo sem capability cam"}), 403

    img_data = request.get_data()
    if not img_data or len(img_data) < 100:
        return jsonify({"error": "Imagem vazia"}), 400

    save_dir = CAPTURE_DIR / chip_id
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.jpg"
    (save_dir / filename).write_bytes(img_data)
    generate_thumbnail(chip_id, filename, img_data)

    models.mark_capture(chip_id)
    log.info(f"Capture push [{chip_id[:4]}]: {filename} ({len(img_data)/1024:.1f} KB)")
    return jsonify({"status": "ok"})


@cam_bp.route("/<chip_id>/image/<filename>")
def image(chip_id, filename):
    """Serve imagem capturada."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Nao autorizado"}), 403

    filepath = CAPTURE_DIR / chip_id / filename
    if not filepath.exists() or not filepath.is_file():
        return jsonify({"error": "Imagem nao encontrada"}), 404

    return Response(
        filepath.read_bytes(),
        mimetype="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"}
    )


@cam_bp.route("/<chip_id>/thumb/<filename>")
def thumb(chip_id, filename):
    """Serve thumbnail da imagem (200x150, ~5KB)."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Nao autorizado"}), 403

    # Tenta thumb, fallback pra imagem original
    thumb_path = THUMB_DIR / chip_id / filename
    if thumb_path.exists():
        return Response(thumb_path.read_bytes(), mimetype="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    filepath = CAPTURE_DIR / chip_id / filename
    if not filepath.exists():
        return jsonify({"error": "Imagem nao encontrada"}), 404
    return Response(filepath.read_bytes(), mimetype="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


@cam_bp.route("/<chip_id>/start-live")
def start_live(chip_id):
    """Enfileira comando start-live — ESP32 vai começar a enviar frames."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    models.add_pending_command(chip_id, "start-live")
    models.mark_activity(chip_id)
    return jsonify({"status": "queued"})


@cam_bp.route("/<chip_id>/stop-live")
def stop_live(chip_id):
    """Enfileira comando stop-live — ESP32 para de enviar frames."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    models.add_pending_command(chip_id, "stop-live")
    models.mark_activity(chip_id)

    # Limpa frame em memoria
    with _live_lock:
        _live_frames.pop(chip_id, None)

    return jsonify({"status": "queued"})


@cam_bp.route("/<chip_id>/live-frame", methods=["GET", "POST"])
def live_frame(chip_id):
    """POST: ESP32 envia frame live. GET: PWA busca ultimo frame (long-poll)."""
    if request.method == "POST":
        # ESP32 push — sem auth, mas valida chip_id + capability
        module = models.get_module_by_chip_id(chip_id)
        if not module:
            return jsonify({"error": "Modulo nao encontrado"}), 404
        try:
            caps = json.loads(module.get("capabilities", "[]"))
        except (json.JSONDecodeError, TypeError):
            caps = []
        if "cam" not in caps:
            return jsonify({"error": "Modulo sem capability cam"}), 403

        img_data = request.get_data()
        if not img_data or len(img_data) < 100:
            return jsonify({"error": "Frame vazio"}), 400

        with _live_lock:
            _live_frames[chip_id] = {"data": img_data, "ts": time.time()}

        return jsonify({"status": "ok"})

    # GET — PWA busca frame (resposta imediata, sem bloquear worker)
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Nao autorizado"}), 403

    last_ts = float(request.args.get("after", 0))

    with _live_lock:
        frame = _live_frames.get(chip_id)

    if frame and frame["ts"] > last_ts and (time.time() - frame["ts"]) < 10:
        return Response(
            frame["data"],
            mimetype="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Frame-Ts": str(frame["ts"]),
            }
        )

    # Sem frame novo — retorna 204 imediatamente
    return "", 204


@cam_bp.route("/<chip_id>/last-capture")
def last_capture(chip_id):
    """Retorna URL da ultima imagem capturada."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    cap_dir = CAPTURE_DIR / chip_id
    if not cap_dir.exists():
        return jsonify({"status": "empty"})

    files = sorted(cap_dir.glob("*.jpg"), reverse=True)
    if not files:
        return jsonify({"status": "empty"})

    # Monta URL usando o tipo do modulo para determinar o prefixo
    mod_type = module.get("type", "cam")
    filename = files[0].name
    return jsonify({
        "status": "ok",
        "url": f"/api/{mod_type}/{chip_id}/image/{filename}",
        "size_kb": round(files[0].stat().st_size / 1024, 1)
    })


# =====================================================================
# Captura agendada — config + galeria
# =====================================================================

@cam_bp.route("/<chip_id>/config", methods=["POST"])
def set_config(chip_id):
    """Configurar captura agendada: intervalo e recording on/off."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON invalido"}), 400

    interval = data.get("capture_interval")
    recording = data.get("recording")
    resolution = data.get("cam_resolution")
    quality = data.get("cam_quality")

    if interval is not None:
        interval = int(interval)
        if interval < 30 or interval > 86400:
            return jsonify({"error": "Intervalo deve ser entre 10s e 24h"}), 400

    valid_resolutions = ["VGA", "SVGA", "UXGA"]
    if resolution is not None and resolution not in valid_resolutions:
        return jsonify({"error": f"Resolucao invalida. Use: {valid_resolutions}"}), 400

    if quality is not None:
        quality = int(quality)
        if quality not in [8, 10, 15]:
            return jsonify({"error": "Qualidade invalida. Use: 8, 10 ou 15"}), 400

    models.set_capture_config(chip_id, capture_interval=interval, recording=recording,
                              cam_resolution=resolution, cam_quality=quality)

    # Se mudou resolucao ou qualidade, enfileira comando pro ESP32
    if resolution is not None or quality is not None:
        cfg = models.get_capture_config(chip_id)
        models.add_pending_command(chip_id, "set-camera",
            json.dumps({"resolution": cfg["cam_resolution"], "quality": cfg["cam_quality"]}))
    cfg = models.get_capture_config(chip_id)
    return jsonify({"status": "ok", **cfg})


@cam_bp.route("/<chip_id>/images")
def list_images(chip_id):
    """Lista capturas com paginacao."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    request.user = user

    module = _get_cam_module_or_404(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    cap_dir = CAPTURE_DIR / chip_id
    if not cap_dir.exists():
        return jsonify({"images": [], "total": 0, "page": 1, "pages": 0})

    all_files = sorted(cap_dir.glob("*.jpg"), reverse=True)
    total = len(all_files)

    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    files = all_files[start:start + per_page]

    mod_type = module.get("type", "cam")
    images = []
    for f in files:
        # Parse timestamp do nome: YYYYMMDD_HHMMSS.jpg
        name = f.stem
        try:
            created = datetime.strptime(name, "%Y%m%d_%H%M%S").isoformat()
        except ValueError:
            created = ""
        images.append({
            "filename": f.name,
            "url": f"/api/{mod_type}/{chip_id}/image/{f.name}",
            "thumb_url": f"/api/{mod_type}/{chip_id}/thumb/{f.name}",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": created,
        })

    return jsonify({"images": images, "total": total, "page": page, "pages": pages})
