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

import json
import logging
from flask import Blueprint, request, jsonify

import models
from bp_auth import require_admin


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
    """Lista as ultimas acoes administrativas (paginado)."""
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
    entries = models.get_audit_log(limit=limit, offset=offset)
    return jsonify({"entries": entries, "count": len(entries), "limit": limit, "offset": offset})
