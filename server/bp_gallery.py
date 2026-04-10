"""
Cultivee — Blueprint Gallery
Organizacao de imagens capturadas em pastas.
Registrado com url_prefix dinamico (ex: /api/gallery).
"""

import os
import re
import json
import math
import shutil
import pathlib
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, Response

import models

log = logging.getLogger(__name__)

gallery_bp = Blueprint("gallery", __name__)

CAPTURE_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "captures"
THUMB_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "thumbs"


# =====================================================================
# Helpers
# =====================================================================

def _get_cam_module_or_error(chip_id):
    """Valida autenticacao, propriedade do modulo e capability cam.
    Retorna (module, None) em caso de sucesso ou (None, response_tuple) em caso de erro.
    """
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return None, (jsonify({"error": "Nao autenticado"}), 401)
    request.user = user

    module = models.get_module_by_chip_id(chip_id)
    if not module or module.get("user_id") != user["id"]:
        return None, (jsonify({"error": "Modulo nao encontrado"}), 404)

    try:
        caps = json.loads(module.get("capabilities", "[]"))
    except (json.JSONDecodeError, TypeError):
        caps = []
    if "cam" not in caps:
        return None, (jsonify({"error": "Modulo sem camera"}), 400)

    return module, None


def _sanitize_folder_name(name):
    """Converte nome de pasta para formato seguro: lowercase, hifens, sem especiais."""
    name = name.strip().lower()
    # Substituir espacos por hifen
    name = name.replace(" ", "-")
    # Manter apenas letras, numeros, hifens e underscores
    name = re.sub(r"[^a-z0-9\-_]", "", name)
    # Colapsar hifens multiplos
    name = re.sub(r"-{2,}", "-", name)
    # Remover hifens nas pontas
    name = name.strip("-")
    return name


def _validate_folder_name(folder):
    """Valida que o nome da pasta nao contem path traversal."""
    if not folder or ".." in folder or "/" in folder or "\\" in folder:
        return False
    # Re-sanitizar e comparar — se mudou, o nome era invalido
    if _sanitize_folder_name(folder) != folder:
        return False
    return True


def _get_folder_info(chip_id, folder_name, module):
    """Retorna metadados de uma pasta de capturas."""
    folder_path = CAPTURE_DIR / chip_id / folder_name
    files = sorted(folder_path.glob("*.jpg"), reverse=True)
    count = len(files)
    size_kb = round(sum(f.stat().st_size for f in files) / 1024, 1) if files else 0

    last_image = None
    thumb_url = None
    if files:
        last_image = files[0].name
        mod_type = module.get("type", "cam")
        thumb_url = f"/api/gallery/{chip_id}/folders/{folder_name}/thumb/{last_image}"

    return {
        "name": folder_name,
        "count": count,
        "size_kb": size_kb,
        "last_image": last_image,
        "thumb_url": thumb_url,
    }


def _get_newest_timestamp(folder_path):
    """Retorna timestamp do arquivo mais recente na pasta (para ordenacao)."""
    files = list(folder_path.glob("*.jpg"))
    if not files:
        return 0
    return max(f.stat().st_mtime for f in files)


# =====================================================================
# Rotas
# =====================================================================

@gallery_bp.route("/<chip_id>/folders")
def list_folders(chip_id):
    """Lista todas as pastas de um dispositivo, ordenadas pela imagem mais recente."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    chip_dir = CAPTURE_DIR / chip_id
    if not chip_dir.exists():
        return jsonify({"folders": []})

    folders = []
    for item in chip_dir.iterdir():
        if item.is_dir():
            folders.append((item, _get_newest_timestamp(item)))

    # Ordenar por mais recente primeiro
    folders.sort(key=lambda x: x[1], reverse=True)

    result = []
    for folder_path, _ in folders:
        result.append(_get_folder_info(chip_id, folder_path.name, module))

    return jsonify({"folders": result})


@gallery_bp.route("/<chip_id>/folders", methods=["POST"])
def create_folder(chip_id):
    """Cria pasta vazia para organizar capturas."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Nome da pasta obrigatorio"}), 400

    folder_name = _sanitize_folder_name(data["name"])
    if not folder_name:
        return jsonify({"error": "Nome da pasta invalido"}), 400

    # Criar diretorio em captures e thumbs
    cap_folder = CAPTURE_DIR / chip_id / folder_name
    thumb_folder = THUMB_DIR / chip_id / folder_name

    if cap_folder.exists():
        return jsonify({"error": "Pasta ja existe"}), 409

    cap_folder.mkdir(parents=True, exist_ok=True)
    thumb_folder.mkdir(parents=True, exist_ok=True)

    log.info(f"Pasta criada [{chip_id[:4]}]: {folder_name}")
    return jsonify({"status": "ok", "folder": folder_name})


@gallery_bp.route("/<chip_id>/folders/<folder>/images")
def list_images(chip_id, folder):
    """Lista imagens de uma pasta com paginacao."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    if not _validate_folder_name(folder):
        return jsonify({"error": "Nome de pasta invalido"}), 400

    folder_path = CAPTURE_DIR / chip_id / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return jsonify({"error": "Pasta nao encontrada"}), 404

    all_files = sorted(folder_path.glob("*.jpg"), reverse=True)
    total = len(all_files)

    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    pages = max(1, math.ceil(total / per_page)) if total > 0 else 0
    start = (page - 1) * per_page
    files = all_files[start:start + per_page]

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
            "url": f"/api/gallery/{chip_id}/folders/{folder}/image/{f.name}",
            "thumb_url": f"/api/gallery/{chip_id}/folders/{folder}/thumb/{f.name}",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": created,
        })

    return jsonify({
        "images": images,
        "total": total,
        "page": page,
        "pages": pages,
    })


@gallery_bp.route("/<chip_id>/folders/<folder>/image/<filename>")
def serve_image(chip_id, folder, filename):
    """Serve imagem capturada em tamanho original."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    if not _validate_folder_name(folder):
        return jsonify({"error": "Nome de pasta invalido"}), 400

    filepath = CAPTURE_DIR / chip_id / folder / filename
    if not filepath.exists() or not filepath.is_file():
        return jsonify({"error": "Imagem nao encontrada"}), 404

    # Seguranca: garantir que o arquivo resolvido esta dentro do diretorio esperado
    try:
        filepath.resolve().relative_to((CAPTURE_DIR / chip_id / folder).resolve())
    except ValueError:
        return jsonify({"error": "Caminho invalido"}), 400

    return Response(
        filepath.read_bytes(),
        mimetype="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@gallery_bp.route("/<chip_id>/folders/<folder>/thumb/<filename>")
def serve_thumb(chip_id, folder, filename):
    """Serve thumbnail da imagem. Fallback para imagem original se nao houver thumb."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    if not _validate_folder_name(folder):
        return jsonify({"error": "Nome de pasta invalido"}), 400

    # Tenta thumb primeiro
    thumb_path = THUMB_DIR / chip_id / folder / filename
    if thumb_path.exists() and thumb_path.is_file():
        try:
            thumb_path.resolve().relative_to((THUMB_DIR / chip_id / folder).resolve())
        except ValueError:
            return jsonify({"error": "Caminho invalido"}), 400
        return Response(
            thumb_path.read_bytes(),
            mimetype="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Fallback para imagem original
    filepath = CAPTURE_DIR / chip_id / folder / filename
    if not filepath.exists() or not filepath.is_file():
        return jsonify({"error": "Imagem nao encontrada"}), 404

    try:
        filepath.resolve().relative_to((CAPTURE_DIR / chip_id / folder).resolve())
    except ValueError:
        return jsonify({"error": "Caminho invalido"}), 400

    return Response(
        filepath.read_bytes(),
        mimetype="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@gallery_bp.route("/<chip_id>/folders/<folder>/images", methods=["DELETE"])
def delete_images(chip_id, folder):
    """Deleta imagens selecionadas de uma pasta (captures + thumbs)."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    if not _validate_folder_name(folder):
        return jsonify({"error": "Nome de pasta invalido"}), 400

    data = request.get_json()
    if not data or not data.get("filenames"):
        return jsonify({"error": "Lista de arquivos obrigatoria"}), 400

    filenames = data["filenames"]
    if not isinstance(filenames, list):
        return jsonify({"error": "filenames deve ser uma lista"}), 400

    cap_folder = CAPTURE_DIR / chip_id / folder
    thumb_folder = THUMB_DIR / chip_id / folder
    deleted = 0

    for fname in filenames:
        # Validar filename — sem path traversal
        if not fname or ".." in fname or "/" in fname or "\\" in fname:
            continue

        cap_file = cap_folder / fname
        thumb_file = thumb_folder / fname

        if cap_file.exists() and cap_file.is_file():
            try:
                cap_file.resolve().relative_to(cap_folder.resolve())
                cap_file.unlink()
                deleted += 1
            except (ValueError, OSError) as e:
                log.warning(f"Erro deletando captura {fname}: {e}")

        if thumb_file.exists() and thumb_file.is_file():
            try:
                thumb_file.resolve().relative_to(thumb_folder.resolve())
                thumb_file.unlink()
            except (ValueError, OSError) as e:
                log.warning(f"Erro deletando thumbnail {fname}: {e}")

    log.info(f"Imagens deletadas [{chip_id[:4]}]: {deleted} de {folder}")
    return jsonify({"status": "ok", "deleted": deleted})


@gallery_bp.route("/<chip_id>/folders/<folder>", methods=["DELETE"])
def delete_folder(chip_id, folder):
    """Deleta pasta inteira (captures + thumbs)."""
    module, err = _get_cam_module_or_error(chip_id)
    if err:
        return err

    if not _validate_folder_name(folder):
        return jsonify({"error": "Nome de pasta invalido"}), 400

    cap_folder = CAPTURE_DIR / chip_id / folder
    thumb_folder = THUMB_DIR / chip_id / folder

    if not cap_folder.exists():
        return jsonify({"error": "Pasta nao encontrada"}), 404

    try:
        shutil.rmtree(cap_folder)
    except OSError as e:
        log.error(f"Erro deletando pasta captures/{chip_id}/{folder}: {e}")
        return jsonify({"error": "Erro ao deletar pasta"}), 500

    try:
        if thumb_folder.exists():
            shutil.rmtree(thumb_folder)
    except OSError as e:
        log.warning(f"Erro deletando pasta thumbs/{chip_id}/{folder}: {e}")

    log.info(f"Pasta deletada [{chip_id[:4]}]: {folder}")
    return jsonify({"status": "ok"})
