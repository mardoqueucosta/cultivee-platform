"""
Cultivee — Blueprint de Administracao (v4.1.13)
Rotas exclusivas para usuarios com role='admin'.

Todas as rotas sao protegidas pelo decorator @require_admin do bp_auth,
que retorna 401 se nao autenticado ou 403 se autenticado mas nao admin.

Endpoints (prefixo /api/admin):
    GET  /users           — lista todos os usuarios + contagem de modulos
    GET  /users/<id>      — detalhes de um usuario + seus modulos
    GET  /modules         — lista todos os modulos do sistema com dono
    GET  /stats           — contadores de sistema (usuarios, modulos, alertas)

Fase 1 e READ-ONLY: sem endpoints de mutacao (promote, delete, transfer, etc.)
Fase 2 adicionara: set_role, reset-password forcado, transfer, deactivate.
"""

import os
import json
import hashlib
import pathlib
import logging
from flask import Blueprint, request, jsonify

import models
from usuario.auth import require_admin


log = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/users")
@require_admin
def list_users():
    """Lista todos os usuarios do sistema com metricas."""
    users = models.get_all_users()
    # Remove password_hash por seguranca (defesa adicional, embora get_all_users nao retorne)
    for u in users:
        u.pop("password_hash", None)
    return jsonify({"users": users, "count": len(users)})


@admin_bp.route("/users/<int:user_id>")
@require_admin
def user_detail(user_id):
    """Detalhes de um usuario + lista de modulos pareados."""
    user = models.get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "Usuario nao encontrado"}), 404

    # Converte Row pra dict, remove hash
    user_dict = dict(user)
    user_dict.pop("password_hash", None)

    # Lista modulos do usuario
    mods = models.get_user_modules(user_id)
    # Remove ctrl_data do payload (pesado) — deixa so resumo
    for m in mods:
        try:
            ctrl = json.loads(m.get("ctrl_data", "{}") or "{}")
            m["camera_ready"] = ctrl.get("camera_ready")
            m["wifi_last_error"] = ctrl.get("wifi_last_error")
            m["cam_live_mode"] = ctrl.get("cam_live_mode")
        except (json.JSONDecodeError, TypeError):
            pass
        m.pop("ctrl_data", None)

    return jsonify({"user": user_dict, "modules": mods})


@admin_bp.route("/modules")
@require_admin
def list_modules():
    """Lista todos os modulos do sistema (cross-user view)."""
    mods = models.get_all_modules_admin()
    # Agrega se esta online (last_seen < 120s)
    from datetime import datetime
    now = datetime.now()
    for m in mods:
        online = False
        ls = m.get("last_seen")
        if ls:
            try:
                last = datetime.fromisoformat(ls)
                online = (now - last).total_seconds() < 120
            except (ValueError, TypeError):
                pass
        m["online"] = online
    return jsonify({"modules": mods, "count": len(mods)})


@admin_bp.route("/stats")
@require_admin
def stats():
    """Dashboard de contadores: usuarios, modulos, alertas, push subs."""
    return jsonify(models.get_admin_stats())


# =====================================================================
# Impersonation (v4.1.14) — admin entra como outro user
#
# Gera token temporario (30 min) para o user-alvo. Frontend salva o token
# original do admin em localStorage separado, troca o token ativo, recarrega
# a pagina e mostra banner "Acessando como X — voltar pra admin".
#
# Restricoes de seguranca:
#   - Admin nao pode impersonar a si mesmo (UI bug guard)
#   - Admin nao pode impersonar outro admin (prevent escalation + accountability)
#   - Token de impersonation expira em 30 min (nao 30 dias)
#   - Acao e registrada no log (admin X -> user Y from IP Z)
# =====================================================================

@admin_bp.route("/users/<int:target_id>/impersonate", methods=["POST"])
@require_admin
def impersonate_user(target_id):
    admin = request.user
    admin_id = admin["id"]
    data = request.get_json(silent=True, force=True) or {}

    # Parametros opcionais (v4.1.15):
    #   minutes: 5-240 (default 30)
    #   view_only: bool (default false) — se true, token eh scope='readonly' (bloqueia mutacoes)
    try:
        minutes = int(data.get("minutes", 30))
    except (TypeError, ValueError):
        minutes = 30
    minutes = max(5, min(240, minutes))
    view_only = bool(data.get("view_only", False))
    scope = "readonly" if view_only else "full"

    # Validacao 1: nao pode impersonar a si mesmo
    if target_id == admin_id:
        return jsonify({"error": "Nao pode impersonar a propria conta"}), 400

    # Validacao 2: target existe
    target = models.get_user_by_id(target_id)
    if not target:
        return jsonify({"error": "Usuario alvo nao encontrado"}), 404

    # Validacao 3: target nao eh admin (prevent privilege escalation / accountability)
    target_role = None
    try: target_role = target["role"]
    except (KeyError, IndexError, TypeError): pass
    if target_role == "admin":
        return jsonify({"error": "Nao eh permitido impersonar outro admin"}), 403

    imp_token = models.create_impersonation_token(target_id, minutes=minutes, scope=scope)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")

    # v4.1.15: persiste no audit_log (antes so stderr)
    models.log_admin_action(
        admin, "impersonate",
        target_type="user", target_id=target_id, target_label=target["email"],
        details={"minutes": minutes, "scope": scope, "view_only": view_only},
        ip=ip, user_agent=user_agent,
    )
    log.warning(
        f"[IMPERSONATE] admin {admin['email']} (id={admin_id}) -> "
        f"user {target['email']} (id={target_id}) from IP {ip} — "
        f"scope={scope} expires={minutes}min"
    )

    # v4.1.15: notifica outros admins por email (transparencia)
    _notify_other_admins_impersonation(admin, target, ip, minutes, view_only)

    return jsonify({
        "token": imp_token,
        "user": {
            "id": target["id"],
            "email": target["email"],
            "name": target["name"],
            "role": target_role or "user",
        },
        "impersonator": {
            "id": admin_id,
            "email": admin["email"],
            "name": admin["name"],
        },
        "expires_minutes": minutes,
        "scope": scope,
    })


def _notify_other_admins_impersonation(admin, target, ip, minutes, view_only):
    """Envia email pra outros admins (exceto o que iniciou) sobre a acao."""
    conn = models.get_db()
    rows = conn.execute(
        "SELECT email, notification_email FROM users WHERE role='admin' AND id != ?",
        (admin["id"],)
    ).fetchall()
    conn.close()
    if not rows:
        return  # solitario — nenhum outro admin pra avisar

    from notifications import send_email
    scope_label = "SOMENTE LEITURA" if view_only else "acesso completo"
    subject = f"[Cultivee Admin] {admin['email']} impersonou {target['email']}"
    body = f"""Alerta de atividade administrativa no Cultivee.

Admin que executou:  {admin['email']} (id={admin['id']})
Acao:                impersonate ({scope_label})
Usuario alvo:        {target['email']} (id={target['id']})
Duracao do token:    {minutes} minutos
Origem (IP):         {ip}

Se voce eh admin deste sistema e NAO autorizou esta acao, alguma coisa pode
estar errada com a conta de {admin['email']}. Revise o painel de admin
(/admin -> Audit Log) e considere trocar senhas.

--
Cultivee Admin Monitor
"""
    for r in rows:
        dest = r["notification_email"] or r["email"]
        try:
            send_email(dest, subject, body)
        except Exception as e:
            log.error(f"Falha ao notificar admin {dest} sobre impersonation: {e}")


@admin_bp.route("/audit")
@require_admin
def audit_log():
    """
    Lista acoes administrativas com filtros opcionais (v4.1.21).

    Query params (todos opcionais):
      limit      — default 100, max 500
      offset     — default 0
      action     — filtra por tipo de acao (ex: 'impersonate')
      admin_id   — filtra por quem executou
      from       — ISO date/datetime (inclusive)
      to         — ISO date/datetime (inclusive)
    """
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(500, limit))
    offset = max(0, offset)

    action = request.args.get("action", "").strip() or None
    try:
        admin_id = int(request.args.get("admin_id")) if request.args.get("admin_id") else None
    except (TypeError, ValueError):
        admin_id = None
    date_from = request.args.get("from", "").strip() or None
    date_to = request.args.get("to", "").strip() or None

    entries = models.get_audit_log_filtered(
        limit=limit, offset=offset,
        action=action, admin_id=admin_id,
        date_from=date_from, date_to=date_to,
    )
    return jsonify({
        "entries": entries,
        "count": len(entries),
        "limit": limit,
        "offset": offset,
        "filters": {
            "action": action, "admin_id": admin_id,
            "from": date_from, "to": date_to,
        },
    })


# =====================================================================
# R2.1: Promover/rebaixar role (v4.1.21)
# =====================================================================

@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@require_admin
def set_role(user_id):
    """
    Altera role do usuario. Protege contra remover o ultimo admin.
    Body: {role: 'user'/'support'/'admin'}
    """
    admin = request.user
    data = request.get_json(silent=True, force=True) or {}
    new_role = (data.get("role") or "").strip().lower()

    if new_role not in ("user", "support", "admin"):
        return jsonify({"error": "Role invalida. Use 'user', 'support' ou 'admin'"}), 400

    target = models.get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "Usuario nao encontrado"}), 404

    current_role = None
    try: current_role = target["role"] or "user"
    except (KeyError, IndexError, TypeError): pass

    # Sem mudanca? Retorna ok sem log
    if current_role == new_role:
        return jsonify({"status": "ok", "message": "Role nao alterada (ja era {})".format(new_role)})

    # Protecao: nao pode rebaixar o ULTIMO admin
    if current_role == "admin" and new_role != "admin" and models.count_admins() <= 1:
        return jsonify({
            "error": "Nao e possivel rebaixar o ultimo admin do sistema. Promova outro usuario primeiro."
        }), 400

    if not models.set_user_role(user_id, new_role):
        return jsonify({"error": "Falha ao alterar role"}), 500

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    models.log_admin_action(
        admin, "user.role_change",
        target_type="user", target_id=user_id, target_label=target["email"],
        details={"from": current_role, "to": new_role},
        ip=ip, user_agent=request.headers.get("User-Agent"),
    )
    log.warning(f"[admin] role change: {target['email']} {current_role} -> {new_role} by {admin['email']}")

    return jsonify({
        "status": "ok",
        "message": f"Role alterada de '{current_role}' para '{new_role}'",
        "user": {"id": user_id, "email": target["email"], "role": new_role},
    })


# =====================================================================
# R2.2: Forcar reset de senha (v4.1.21)
# =====================================================================

@admin_bp.route("/users/<int:user_id>/force-password-reset", methods=["POST"])
@require_admin
def force_password_reset(user_id):
    """
    Admin forca reset de senha do usuario:
      - Gera token de reset (1h) como se o user tivesse clicado em "esqueci"
      - Envia email com link pro user
      - Invalida TODOS os tokens ativos do user (deslog forcado)
    """
    admin = request.user
    target = models.get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "Usuario nao encontrado"}), 404

    # Gera token + envia email
    token = models.create_password_reset_token(user_id, expires_minutes=60)
    try:
        _send_admin_forced_reset_email(target, admin, token)
    except Exception as e:
        log.error(f"Falha ao enviar email de reset forcado: {e}")
        # Mesmo sem email, invalida tokens e prossegue — admin pode avisar por outro meio

    # Invalida TODOS os tokens do user (forca re-login em todos os devices)
    conn = models.get_db()
    conn.execute("DELETE FROM tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    models.log_admin_action(
        admin, "user.force_password_reset",
        target_type="user", target_id=user_id, target_label=target["email"],
        details={"email_sent": True},
        ip=ip, user_agent=request.headers.get("User-Agent"),
    )
    log.warning(f"[admin] force reset: {target['email']} by {admin['email']}")

    return jsonify({
        "status": "ok",
        "message": f"Reset forcado. Email enviado para {target['email']}. Sessoes ativas revogadas.",
    })


def _send_admin_forced_reset_email(target, admin, token):
    """Email pro user avisando que um admin forcou reset."""
    from notifications import send_email
    destination = None
    try: destination = target["notification_email"]
    except (KeyError, IndexError, TypeError): pass
    if not destination:
        destination = target["email"]

    reset_url = f"https://app.cultivee.com.br/?reset={token}"
    name = target["name"] if target["name"] else "Usuario"

    body = f"""Ola, {name}!

Um administrador do Cultivee iniciou um reset de senha da sua conta
(provavelmente como parte de suporte — ex: voce entrou em contato pedindo
ajuda pra recuperar acesso).

Clique no link abaixo pra definir uma nova senha (valido por 1 hora):

    {reset_url}

Todas as suas sessoes ativas foram encerradas por seguranca.
Se nao foi voce que solicitou, entre em contato imediatamente.

--
Equipe Cultivee
contato@cultivee.com.br
"""
    send_email(destination, "Cultivee - Reset de senha solicitado por administrador", body)


# =====================================================================
# R2.3: Transferir modulo entre users (v4.1.21)
# =====================================================================

@admin_bp.route("/modules/<chip_id>/transfer", methods=["POST"])
@require_admin
def transfer_module(chip_id):
    """
    Move um modulo pra outro usuario. Usado quando cliente trocou de conta
    ou modulo foi repassado pra outro user.

    Body: {new_user_id: N, new_name?: "..."}
    Valida que ambos existem (modulo + user target).
    """
    admin = request.user
    data = request.get_json(silent=True, force=True) or {}
    try:
        new_user_id = int(data.get("new_user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "new_user_id invalido"}), 400
    new_name = (data.get("new_name") or "").strip()

    module = models.get_module_by_chip_id(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    target_user = models.get_user_by_id(new_user_id)
    if not target_user:
        return jsonify({"error": "Usuario alvo nao encontrado"}), 404

    # Se ja eh do target, no-op
    if module.get("user_id") == new_user_id:
        return jsonify({"status": "ok", "message": "Modulo ja pertence a este usuario"})

    old_user_id = module.get("user_id")
    old_user_email = None
    if old_user_id:
        old_user = models.get_user_by_id(old_user_id)
        if old_user:
            old_user_email = old_user["email"]

    # Transfere (UPDATE direto, ignora validacao de propriedade que pair_module faz)
    conn = models.get_db()
    conn.execute(
        "UPDATE modules SET user_id = ?, name = ? WHERE chip_id = ?",
        (new_user_id, new_name or module.get("name", ""), chip_id)
    )
    conn.commit()
    conn.close()

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    models.log_admin_action(
        admin, "module.transfer",
        target_type="module", target_id=chip_id, target_label=module.get("name") or chip_id,
        details={
            "from_user_id": old_user_id,
            "from_user_email": old_user_email,
            "to_user_id": new_user_id,
            "to_user_email": target_user["email"],
            "module_type": module.get("type"),
        },
        ip=ip, user_agent=request.headers.get("User-Agent"),
    )
    log.warning(f"[admin] transfer {chip_id}: {old_user_email} -> {target_user['email']} by {admin['email']}")

    return jsonify({
        "status": "ok",
        "message": f"Modulo transferido para {target_user['email']}",
        "module": {
            "chip_id": chip_id,
            "new_user_id": new_user_id,
            "new_user_email": target_user["email"],
        },
    })


# =====================================================================
# R3: OTA Remoto via Admin (v4.1.27)
# =====================================================================
# Admin pode enviar firmware .bin para qualquer modulo sem precisar do token
# do dono. Mesmo fluxo do endpoint legacy (POST /api/modules/<chip>/firmware)
# mas com gate por role=admin + audit log.
#
# Rotas:
#   POST   /api/admin/modules/<chip>/firmware  upload .bin + hash
#   GET    /api/admin/modules/<chip>/firmware  status (pendente? sha? tamanho?)
#   DELETE /api/admin/modules/<chip>/firmware  cancela
# =====================================================================

# Limite defensivo — .bin tipico e 1.25MB; 3MB cobre crescimento futuro
_ADMIN_OTA_MAX_BYTES = 3 * 1024 * 1024


def _admin_ota_paths(chip_id):
    base = pathlib.Path(os.environ.get("DATA_DIR", "data")) / "firmware"
    return base, base / f"{chip_id}.bin", base / f"{chip_id}.sha256"


@admin_bp.route("/modules/<chip_id>/firmware", methods=["POST"])
@require_admin
def admin_firmware_upload(chip_id):
    """Upload OTA com autenticacao admin (sem precisar do token do dono).
    Calcula SHA-256, grava .bin + sidecar .sha256, registra no audit_log."""
    admin = request.user
    module = models.get_module_by_chip_id(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404

    file = request.files.get("firmware")
    if not file or not file.filename:
        return jsonify({"error": "Campo 'firmware' obrigatorio (multipart form)"}), 400

    # Le ate o limite; se exceder, rejeita sem gravar
    blob = file.read(_ADMIN_OTA_MAX_BYTES + 1)
    if len(blob) > _ADMIN_OTA_MAX_BYTES:
        return jsonify({
            "error": f"Firmware maior que {_ADMIN_OTA_MAX_BYTES // (1024*1024)}MB"
        }), 413

    fw_dir, fw_path, sha_path = _admin_ota_paths(chip_id)
    fw_dir.mkdir(parents=True, exist_ok=True)
    fw_path.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    sha_path.write_text(digest, encoding="utf-8")

    size = len(blob)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    models.log_admin_action(
        admin, "module.firmware_upload",
        target_type="module", target_id=chip_id,
        target_label=module.get("name") or chip_id,
        details={
            "size_bytes": size,
            "sha256": digest,
            "filename": (file.filename or "")[:80],
            "module_type": module.get("type"),
            "owner_email": (
                models.get_user_by_id(module["user_id"])["email"]
                if module.get("user_id") else None
            ),
        },
        ip=ip, user_agent=request.headers.get("User-Agent"),
    )
    log.warning(
        f"[admin] firmware upload: {chip_id} ({size} bytes, sha={digest[:12]}...) by {admin['email']}"
    )
    return jsonify({
        "status": "ok",
        "size": size,
        "sha256": digest,
        "message": "Firmware pendente. ESP32 vai baixar no proximo register (~10s).",
    })


@admin_bp.route("/modules/<chip_id>/firmware", methods=["GET"])
@require_admin
def admin_firmware_status(chip_id):
    """Retorna se ha firmware pendente para o modulo + metadata."""
    if not models.get_module_by_chip_id(chip_id):
        return jsonify({"error": "Modulo nao encontrado"}), 404
    _, fw_path, sha_path = _admin_ota_paths(chip_id)
    if not fw_path.exists():
        return jsonify({"pending": False})
    sha = None
    if sha_path.exists():
        try:
            sha = sha_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            sha = None
    stat = fw_path.stat()
    return jsonify({
        "pending": True,
        "size": stat.st_size,
        "sha256": sha,
        "uploaded_at": stat.st_mtime,
    })


@admin_bp.route("/modules/<chip_id>/firmware", methods=["DELETE"])
@require_admin
def admin_firmware_cancel(chip_id):
    """Cancela OTA pendente (remove .bin + .sha256) e registra no audit."""
    admin = request.user
    module = models.get_module_by_chip_id(chip_id)
    if not module:
        return jsonify({"error": "Modulo nao encontrado"}), 404
    _, fw_path, sha_path = _admin_ota_paths(chip_id)
    had_bin = fw_path.exists()
    if had_bin:
        fw_path.unlink()
    if sha_path.exists():
        sha_path.unlink()
    if not had_bin:
        return jsonify({"status": "ok", "message": "Nenhum firmware pendente"})

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    models.log_admin_action(
        admin, "module.firmware_cancel",
        target_type="module", target_id=chip_id,
        target_label=module.get("name") or chip_id,
        details={"module_type": module.get("type")},
        ip=ip, user_agent=request.headers.get("User-Agent"),
    )
    log.warning(f"[admin] firmware cancel: {chip_id} by {admin['email']}")
    return jsonify({"status": "ok", "message": "Firmware pendente cancelado"})
