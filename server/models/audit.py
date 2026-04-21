"""
Cultivee — Audit Log (v4.1.15).

Registra acoes administrativas pra rastreabilidade/compliance.
Hoje captura impersonation; no futuro: user.promote, module.transfer,
password.force_reset, etc.
"""

import json

from .db import get_db


def log_admin_action(admin, action, target_type=None, target_id=None,
                     target_label=None, details=None, ip=None, user_agent=None):
    """
    Grava uma entrada no audit_log.

    Args:
        admin: dict/Row com pelo menos 'id' e 'email'
        action: string descritiva (ex: 'impersonate', 'user.promote', 'module.transfer')
        target_type: 'user', 'module', 'system', None
        target_id: id do alvo (qualquer — convertido pra string)
        target_label: rotulo legivel (email, chip_id, etc.)
        details: dict serializado pra JSON (info extra contextual)
        ip, user_agent: metadata da request
    """
    admin_id = None
    admin_email = None
    try:
        admin_id = admin["id"]
        admin_email = admin["email"]
    except (KeyError, IndexError, TypeError):
        pass
    details_json = json.dumps(details or {})
    conn = get_db()
    conn.execute("""
        INSERT INTO audit_log
            (admin_id, admin_email, action, target_type, target_id, target_label, details, ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        admin_id, admin_email, action, target_type,
        str(target_id) if target_id is not None else None,
        target_label, details_json, ip, user_agent
    ))
    conn.commit()
    conn.close()


def get_audit_log(limit=100, offset=0):
    """Retorna entradas de audit log, mais recentes primeiro."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, admin_id, admin_email, action, target_type, target_id, target_label,
               details, ip, user_agent, created_at
        FROM audit_log
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d["details"] or "{}")
        except (json.JSONDecodeError, TypeError):
            d["details"] = {}
        out.append(d)
    return out
