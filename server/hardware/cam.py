"""
Cultivee — Blueprint Camera
Rotas de captura: enfileirar captura, upload push, live frame, servir imagem.
Registrado em /api/cam (valida capability "cam").
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

# Limite de upload de imagens do ESP32 (bytes). Fotos UXGA q4 raramente passam de 400KB;
# 5MB cobre com folga e evita ESP32 comprometido encher o disco.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _safe_join(base: pathlib.Path, *parts: str) -> pathlib.Path | None:
    """Junta partes validando que o resultado esta dentro de base (previne path traversal).
    Retorna o Path resolvido ou None se houver tentativa de escape."""
    try:
        target = (base.joinpath(*parts)).resolve()
        base_resolved = base.resolve()
        target.relative_to(base_resolved)
        return target
    except (ValueError, OSError):
        return None


def generate_thumbnail(chip_id, filename, img_data, folder=""):
    """Gera thumbnail 200x150 a partir dos bytes JPEG."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_data))
        img.thumbnail(THUMB_SIZE)
        thumb_dir = THUMB_DIR / chip_id / folder if folder else THUMB_DIR / chip_id
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
    if len(img_data) > MAX_UPLOAD_BYTES:
        log.warning(f"Upload rejeitado [{chip_id[:4]}]: {len(img_data)} bytes > {MAX_UPLOAD_BYTES}")
        return jsonify({"error": "Imagem muito grande"}), 413

    # Salva na pasta ativa (capture_folder) ou _sem-pasta
    capture_cfg = models.get_capture_config(chip_id)
    folder = capture_cfg.get("capture_folder", "") or "_sem-pasta"
    save_dir = _safe_join(CAPTURE_DIR, chip_id, folder)
    if save_dir is None:
        return jsonify({"error": "Caminho invalido"}), 400
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.jpg"
    (save_dir / filename).write_bytes(img_data)
    generate_thumbnail(chip_id, filename, img_data, folder)

    models.mark_capture(chip_id)
    # v4.1.59: rolling window dos ultimos 10 tamanhos pra alerta cam_dark_frame.
    # Tamanho do JPEG e proxy de complexidade visual — frames anormalmente
    # pequenos (lente tampada, escuridao) ficam abaixo do baseline.
    # Le ctrl_data direto (get_capture_config nao expoe recent_capture_sizes).
    try:
        mod_row = models.get_module_by_chip_id(chip_id)
        if mod_row:
            try:
                cd = json.loads(mod_row.get("ctrl_data") or "{}")
            except (json.JSONDecodeError, TypeError):
                cd = {}
            recent = cd.get("recent_capture_sizes") if isinstance(cd.get("recent_capture_sizes"), list) else []
            recent = (recent + [len(img_data)])[-10:]
            models.update_ctrl_data(chip_id, {
                "last_capture_size_bytes": len(img_data),
                "recent_capture_sizes": recent,
            })
    except Exception as e:
        log.warning(f"Erro ao trackear capture size [{chip_id[:4]}]: {e}")

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

    filepath = _safe_join(CAPTURE_DIR, chip_id, filename)
    if filepath is None:
        return jsonify({"error": "Caminho invalido"}), 400
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
    thumb_path = _safe_join(THUMB_DIR, chip_id, filename)
    if thumb_path is None:
        return jsonify({"error": "Caminho invalido"}), 400
    if thumb_path.exists() and thumb_path.is_file():
        return Response(thumb_path.read_bytes(), mimetype="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    filepath = _safe_join(CAPTURE_DIR, chip_id, filename)
    if filepath is None:
        return jsonify({"error": "Caminho invalido"}), 400
    if not filepath.exists() or not filepath.is_file():
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

    # v4.1.9: escreve cam_live_mode=true otimisticamente (ESP32 confirma no proximo register)
    # Isso persiste o estado mesmo se o usuario recarregar o browser antes do ESP32 reportar
    models.update_ctrl_data(chip_id, {"cam_live_mode": True})
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

    # v4.1.9: escreve cam_live_mode=false otimisticamente
    models.update_ctrl_data(chip_id, {"cam_live_mode": False})
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
        if len(img_data) > MAX_UPLOAD_BYTES:
            return jsonify({"error": "Frame muito grande"}), 413

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

    # Busca em todas as subpastas (novo layout com pastas)
    files = sorted(cap_dir.rglob("*.jpg"), key=lambda f: f.name, reverse=True)
    if not files:
        return jsonify({"status": "empty"})

    mod_type = module.get("type", "cam")
    f = files[0]
    folder = f.parent.name
    return jsonify({
        "status": "ok",
        "url": f"/api/gallery/{chip_id}/folders/{folder}/image/{f.name}",
        "thumb_url": f"/api/gallery/{chip_id}/folders/{folder}/thumb/{f.name}",
        "size_kb": round(f.stat().st_size / 1024, 1)
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
    folder = data.get("capture_folder")

    wb_mode = data.get("cam_wb_mode")
    brightness = data.get("cam_brightness")
    contrast = data.get("cam_contrast")
    saturation = data.get("cam_saturation")
    ae_level = data.get("cam_ae_level")
    gainceiling = data.get("cam_gainceiling")
    special_effect = data.get("cam_special_effect")
    hmirror = data.get("cam_hmirror")
    vflip = data.get("cam_vflip")
    exposure_ctrl = data.get("cam_exposure_ctrl")
    whitebal = data.get("cam_whitebal")

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
                              cam_resolution=resolution, cam_quality=quality,
                              capture_folder=folder,
                              cam_wb_mode=wb_mode, cam_brightness=brightness,
                              cam_contrast=contrast, cam_saturation=saturation,
                              cam_ae_level=ae_level, cam_gainceiling=gainceiling,
                              cam_special_effect=special_effect, cam_hmirror=hmirror,
                              cam_vflip=vflip, cam_exposure_ctrl=exposure_ctrl,
                              cam_whitebal=whitebal)

    # Se mudou resolucao ou qualidade, enfileira comando pro ESP32
    if resolution is not None or quality is not None:
        cfg = models.get_capture_config(chip_id)
        models.add_pending_command(chip_id, "set-camera",
            json.dumps({"resolution": cfg["cam_resolution"], "quality": cfg["cam_quality"]}))

    # If any sensor param changed, send to ESP32
    sensor_fields = ["cam_wb_mode", "cam_brightness", "cam_contrast", "cam_saturation",
                     "cam_ae_level", "cam_gainceiling", "cam_special_effect",
                     "cam_hmirror", "cam_vflip", "cam_exposure_ctrl", "cam_whitebal"]
    if any(data.get(f) is not None for f in sensor_fields):
        cfg = models.get_capture_config(chip_id)
        params = {
            "wb_mode": cfg["cam_wb_mode"],
            "brightness": cfg["cam_brightness"],
            "contrast": cfg["cam_contrast"],
            "saturation": cfg["cam_saturation"],
            "ae_level": cfg["cam_ae_level"],
            "gainceiling": cfg["cam_gainceiling"],
            "special_effect": cfg["cam_special_effect"],
            "hmirror": cfg["cam_hmirror"],
            "vflip": cfg["cam_vflip"],
            "exposure_ctrl": cfg["cam_exposure_ctrl"],
            "whitebal": cfg["cam_whitebal"],
        }
        # Also include resolution/quality
        params["resolution"] = cfg["cam_resolution"]
        params["quality"] = cfg["cam_quality"]
        models.add_pending_command(chip_id, "set-camera", json.dumps(params))

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

    # Busca em todas as subpastas (novo layout com pastas)
    all_files = sorted(cap_dir.rglob("*.jpg"), key=lambda f: f.name, reverse=True)
    total = len(all_files)

    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    files = all_files[start:start + per_page]

    images = []
    for f in files:
        name = f.stem
        folder = f.parent.name
        try:
            created = datetime.strptime(name, "%Y%m%d_%H%M%S").isoformat()
        except ValueError:
            created = ""
        images.append({
            "filename": f.name,
            "folder": folder,
            "url": f"/api/gallery/{chip_id}/folders/{folder}/image/{f.name}",
            "thumb_url": f"/api/gallery/{chip_id}/folders/{folder}/thumb/{f.name}",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": created,
        })

    return jsonify({"images": images, "total": total, "page": page, "pages": pages})
