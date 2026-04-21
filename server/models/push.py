"""
Cultivee — Push subscriptions (Web Push API) + Alert log (cooldown).

Gerencia subscricoes de push por usuario (N devices por user) e o log
de alertas disparados (usado pra cooldown: nao spammar com mesmo alerta).
"""

from datetime import datetime

from .db import get_db


# =====================================================================
# Push subscriptions (Web Push API)
# =====================================================================

def save_push_subscription(user_id, endpoint, p256dh, auth):
    """Salva ou atualiza subscription de push (um usuario pode ter N devices)."""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
        (user_id, endpoint, p256dh, auth)
    )
    conn.commit()
    conn.close()


def delete_push_subscription(user_id, endpoint):
    conn = get_db()
    conn.execute(
        "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
        (user_id, endpoint)
    )
    conn.commit()
    conn.close()


def delete_push_subscription_by_endpoint(endpoint):
    """Remove subscription expirada (sem user_id — chamado quando push falha com 410)."""
    conn = get_db()
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
    conn.commit()
    conn.close()


def get_push_subscriptions(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    conn.close()
    return [{"endpoint": r["endpoint"], "p256dh": r["p256dh"], "auth": r["auth"]} for r in rows]


def get_subscriptions_for_module(chip_id):
    """Retorna subscriptions do usuario dono do modulo (JOIN modules.user_id)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT ps.endpoint, ps.p256dh, ps.auth, m.user_id
        FROM push_subscriptions ps
        JOIN modules m ON m.user_id = ps.user_id
        WHERE m.chip_id = ?
    """, (chip_id,)).fetchall()
    conn.close()
    return [
        {"endpoint": r["endpoint"], "p256dh": r["p256dh"], "auth": r["auth"], "user_id": r["user_id"]}
        for r in rows
    ]


# =====================================================================
# Alert log (cooldown entre alertas iguais)
# =====================================================================

def should_send_alert(user_id, chip_id, alert_type, cooldown_seconds=3600):
    """Retorna True se nao mandou alerta desse tipo recentemente (dentro do cooldown)."""
    conn = get_db()
    row = conn.execute(
        "SELECT sent_at FROM alert_log WHERE user_id = ? AND chip_id = ? AND alert_type = ? "
        "ORDER BY sent_at DESC LIMIT 1",
        (user_id, chip_id, alert_type)
    ).fetchone()
    conn.close()
    if not row:
        return True
    try:
        last = datetime.fromisoformat(row["sent_at"])
        return (datetime.now() - last).total_seconds() >= cooldown_seconds
    except (ValueError, TypeError):
        return True


def log_alert(user_id, chip_id, alert_type):
    conn = get_db()
    conn.execute(
        "INSERT INTO alert_log (user_id, chip_id, alert_type) VALUES (?, ?, ?)",
        (user_id, chip_id, alert_type)
    )
    conn.commit()
    conn.close()
