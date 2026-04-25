"""
Cultivee — Offline watcher (v4.1.38)

Thread daemon que verifica periodicamente se algum modulo esta offline
ha mais que o threshold (60min default) e dispara alerta proativo
(push + email) sem precisar do dono abrir o painel.

Quando o modulo volta apos uma queda longa, dispara um alerta de
recuperacao ("voltou apos Xmin offline").

Cuidados:
- Lock distribuido (try_acquire_offline_watcher_lock) garante que so 1
  worker do Gunicorn execute o ciclo por intervalo (sem duplicar checks).
- Cooldown via alert_log impede spam: P1 = 4h, P0 = 12h, recovery = 1h.
- Severidade escala: P1 se >= 60min, P0 se >= 24h offline.
- (Futuro: ignorar quando ha platform_incident ativo no periodo —
  evita alerta ruidoso quando o servidor cair.)
"""

import threading
import time
import logging
from datetime import datetime
import models

log = logging.getLogger(__name__)

# Configuracao
OFFLINE_CHECK_INTERVAL_SEC = 60                # ciclo a cada 1min
DEFAULT_OFFLINE_THRESHOLD_MIN = 15             # default global (era 60 em v4.1.38)
OFFLINE_ALERT_P0_THRESHOLD_MIN = 24 * 60       # escala pra P0 se >= 24h, mesmo se threshold for menor
COOLDOWN_OFFLINE_P1_SEC = 4 * 3600             # 4h entre alertas P1 do mesmo modulo
COOLDOWN_OFFLINE_P0_SEC = 12 * 3600            # 12h entre alertas P0
COOLDOWN_RECOVERY_SEC = 3600                   # 1h entre alertas de recovery


def _module_threshold_min(module):
    """
    v4.1.39: threshold pode ser configurado por modulo via
    POST /api/modules/<chip>/notification-prefs.
    Lido de ctrl_data.offline_alert_threshold_min, fallback ao default global.
    """
    import json as _json
    try:
        cd = _json.loads(module.get("ctrl_data") or "{}")
    except (ValueError, TypeError):
        cd = {}
    val = cd.get("offline_alert_threshold_min")
    if val is None:
        return DEFAULT_OFFLINE_THRESHOLD_MIN
    try:
        return max(1, min(1440, int(val)))
    except (TypeError, ValueError):
        return DEFAULT_OFFLINE_THRESHOLD_MIN


def _module_alert_enabled(module):
    """v4.1.39: dono pode desativar alerta por modulo (default: ativo)."""
    import json as _json
    try:
        cd = _json.loads(module.get("ctrl_data") or "{}")
    except (ValueError, TypeError):
        cd = {}
    val = cd.get("offline_alert_enabled")
    if val is None:
        return True  # default ON pra modulos novos
    return bool(val)


def _human_min(minutes):
    """Formata minutos como '45min' ou '2h 15min'."""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}min"
    h = minutes // 60
    m = minutes % 60
    return f"{h}h {m}min" if m else f"{h}h"


def _calc_offline_age_min(summary):
    """Tempo desde o inicio da queda atual em minutos. 0 se nao ha queda."""
    last_off = summary.get("last_offline_at")
    if not last_off:
        return 0
    try:
        delta = datetime.now() - datetime.fromisoformat(last_off)
        return int(delta.total_seconds() / 60)
    except (ValueError, TypeError):
        return 0


def _maybe_send_offline_alert(module, age_min):
    """Dispara alerta P1/P0 se passou do threshold + cooldown."""
    user_id = module.get("user_id")
    chip_id = module["chip_id"]
    if not user_id:
        return  # nao pareado — sem dono pra alertar
    if not _module_alert_enabled(module):
        return  # dono desativou alerta de offline pra esse modulo

    severity = "P0" if age_min >= OFFLINE_ALERT_P0_THRESHOLD_MIN else "P1"
    cooldown = COOLDOWN_OFFLINE_P0_SEC if severity == "P0" else COOLDOWN_OFFLINE_P1_SEC

    # alert_log usa "module_offline" como tipo unico — cooldown ja deduplica
    if not models.should_send_alert(user_id, chip_id, "module_offline",
                                     cooldown_seconds=cooldown):
        return

    name = module.get("name") or chip_id
    age_text = _human_min(age_min)
    title = f"[{severity}] Modulo offline ha {age_text}"
    body = (f"{name} parou de responder ha {age_text}. "
            f"Verifique conexao WiFi e energia do dispositivo.")
    payload = {
        "title": title,
        "body": body,
        "tag": f"offline-{chip_id}",
        "url": "/"
    }
    log.info(f"[offline_watcher] dispara {severity} alert pra {chip_id} "
             f"(offline ha {age_text}, user_id={user_id})")
    # Reusa _send_alert do AlertManager (push + email + log)
    from notifications import alert_manager
    alert_manager._send_alert(user_id, chip_id, "module_offline", payload)


def _maybe_send_recovery_alert(module):
    """
    Quando modulo volta apos queda >= threshold, manda alerta de recovery.
    Usa o ultimo evento offline fechado pra calcular duracao.
    """
    user_id = module.get("user_id")
    chip_id = module["chip_id"]
    if not user_id:
        return

    # Ultimos 2 eventos: o atual (online) + o anterior (offline fechado)
    events = models.get_module_status_events(chip_id, days=1, limit=3)
    if len(events) < 2:
        return  # historico curto demais
    # events vem em ordem DESC (mais recente primeiro)
    if events[0].get("status") != "online":
        return  # nao acabou de voltar
    last_offline = next((e for e in events if e.get("status") == "offline"), None)
    if not last_offline or not last_offline.get("duration_seconds"):
        return  # nao houve queda fechada
    # Recovery so vale a pena se a queda foi >= threshold do modulo (ou
    # default global se nao configurado). Senao gera ruido com glitches curtos.
    threshold_min = _module_threshold_min(module)
    if last_offline["duration_seconds"] < threshold_min * 60:
        return  # queda foi curta — nao alerta sobre voltar

    if not models.should_send_alert(user_id, chip_id, "module_recovered",
                                     cooldown_seconds=COOLDOWN_RECOVERY_SEC):
        return

    name = module.get("name") or chip_id
    dur_min = int(last_offline["duration_seconds"] / 60)
    payload = {
        "title": "Modulo voltou online",
        "body": f"{name} voltou apos {_human_min(dur_min)} offline.",
        "tag": f"recovered-{chip_id}",
        "url": "/"
    }
    log.info(f"[offline_watcher] dispara recovery pra {chip_id} "
             f"(ficou {dur_min}min offline, user_id={user_id})")
    from notifications import alert_manager
    alert_manager._send_alert(user_id, chip_id, "module_recovered", payload)


def _check_modules():
    """1 ciclo do watcher: itera modulos pareados, checa estado, alerta se necessario."""
    # Lock distribuido — so 1 worker por intervalo
    if not models.try_acquire_offline_watcher_lock(
            min_interval_sec=OFFLINE_CHECK_INTERVAL_SEC - 10):
        return  # outro worker ja rodou recentemente

    try:
        modules = models.get_all_modules_admin()
    except Exception as e:
        log.error(f"[offline_watcher] erro ao listar modulos: {e}")
        return

    for m in modules:
        try:
            chip_id = m["chip_id"]
            if not m.get("user_id"):
                continue  # nao pareado

            # compute_lazy: marca offline se last_seen > 120s sem precisar do
            # poll do user (essa thread roda mesmo sem ninguem aberto na UI)
            try:
                models.compute_module_status_lazy(chip_id)
            except Exception as e:
                log.warning(f"[offline_watcher] compute_lazy {chip_id}: {e}")
                continue

            summary = models.get_module_uptime_summary(chip_id, days=1)
            cur_status = summary.get("current_status")

            if cur_status == "offline":
                age_min = _calc_offline_age_min(summary)
                # v4.1.39: threshold por modulo (configuravel via UI). Default 15min.
                threshold = _module_threshold_min(m)
                if age_min >= threshold:
                    _maybe_send_offline_alert(m, age_min)
            elif cur_status == "online":
                # Pode ter acabado de voltar — verifica se a queda anterior
                # foi longa o suficiente pra alertar recovery
                _maybe_send_recovery_alert(m)
        except Exception as e:
            log.error(f"[offline_watcher] erro processando {m.get('chip_id')}: {e}")


def _watcher_loop():
    """Loop principal — chamado dentro do thread daemon."""
    log.info("[offline_watcher] thread iniciada "
             f"(intervalo={OFFLINE_CHECK_INTERVAL_SEC}s, "
             f"threshold P1 default={DEFAULT_OFFLINE_THRESHOLD_MIN}min "
             f"(configuravel por modulo via UI), "
             f"threshold P0={OFFLINE_ALERT_P0_THRESHOLD_MIN}min)")
    # Pequeno delay inicial pra evitar 2 workers competirem na mesma janela
    time.sleep(5)
    while True:
        try:
            _check_modules()
        except Exception as e:
            log.error(f"[offline_watcher] cycle error: {e}", exc_info=True)
        time.sleep(OFFLINE_CHECK_INTERVAL_SEC)


def start():
    """Cria a thread daemon. Idempotente — chamado 1x por worker no startup."""
    t = threading.Thread(target=_watcher_loop,
                         daemon=True,
                         name="offline-watcher")
    t.start()
    log.info("[offline_watcher] thread agendada (daemon)")
