"""
Cultivee — Sistema de Alertas (Push PWA + Email)
Monitora condicoes dos modulos e notifica o usuario.

Chamado a cada register do ESP32 (a cada 10s). Verifica thresholds
e envia notificacao se condicao persistir alem do tempo configurado.

Alertas implementados:
- reservoir_empty: reservatorio vazio por 10+ minutos

Extensivel: adicionar metodos _check_* para novos tipos de alerta
(temperatura, modulo offline, bomba travada, etc.).
"""

import os
import json
import time
import logging
import smtplib
import uuid
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

log = logging.getLogger(__name__)

# Timer em memoria: {chip_id: {alert_type: first_seen_timestamp}}
# Reseta quando a condicao desaparece. Nao persiste entre reboots do servidor.
_alert_timers = {}


class AlertManager:
    """Verifica condicoes de alerta e envia notificacoes."""

    def check(self, chip_id, ctrl_data, module):
        """Chamado a cada register do ESP32. ctrl_data e dict, module e row do DB."""
        user_id = module.get("user_id")
        if not user_id:
            return  # Modulo nao pareado — sem usuario pra notificar

        # Alerta: reservatorio vazio por 10+ minutos
        self._check_reservoir(chip_id, ctrl_data, user_id)

        # Futuros alertas:
        # self._check_temperature(chip_id, ctrl_data, user_id)
        # self._check_module_offline(chip_id, ctrl_data, user_id)

    def _check_reservoir(self, chip_id, ctrl_data, user_id):
        """Timer baseado na BOIA DE NIVEL BAIXO (level_low).
        level_low = true  → boia detectou agua (nivel OK, acima da boia)
        level_low = false → boia NAO detectou agua (nivel BAIXO, precisa encher)

        Timer inicia quando level_low = FALSE (sem agua na boia baixa).
        Timer para quando level_low = TRUE (agua voltou).
        Se level_low fica false por 10+ min → envia alerta."""
        level_low = ctrl_data.get("level_low", True)  # default true = OK
        timer_key = f"{chip_id}:level_low"

        if level_low:
            # Boia baixa detectou agua — nivel OK, limpa timer
            if timer_key in _alert_timers:
                _alert_timers.pop(timer_key, None)
                import models as _m
                _m.update_ctrl_data(chip_id, {"low_since": None})
            return

        # Boia baixa SEM AGUA (level_low = false) — inicia ou verifica timer
        now = time.time()
        if timer_key not in _alert_timers:
            _alert_timers[timer_key] = now
            # Salva timestamp UTC no banco pra o PWA mostrar o contador
            from datetime import datetime, timezone
            import models as _m
            _m.update_ctrl_data(chip_id, {"low_since": datetime.now(timezone.utc).isoformat()})
            log.info(f"Reservatorio {chip_id}: boia baixa acionada — timer iniciado")
            return  # Comecou agora — espera 10 min

        elapsed = now - _alert_timers[timer_key]
        if elapsed < 600:
            return  # Menos de 10 minutos — espera

        # 10+ minutos com boia baixa ativa — verifica cooldown
        import models
        if not models.should_send_alert(user_id, chip_id, "level_low"):
            return  # Ja notificou na ultima hora

        # Monta payload e envia
        module_name = module.get("name") or module.get("type", "Modulo")
        payload = {
            "title": "Nivel baixo no reservatorio",
            "body": f"{module_name}: boia de nivel minimo ativa ha {int(elapsed/60)} min. Verificar abastecimento de agua.",
            "tag": f"reservoir-{chip_id}",
            "url": "/"
        }

        self._send_alert(user_id, chip_id, "level_low", payload)

    def _send_alert(self, user_id, chip_id, alert_type, payload):
        """Envia notificacao via todos os canais disponiveis."""
        import models

        # 1. Push PWA
        subscriptions = models.get_push_subscriptions(user_id)
        push_sent = 0
        for sub in subscriptions:
            try:
                _send_web_push(sub, payload)
                push_sent += 1
            except Exception as e:
                log.warning(f"Push falhou ({sub['endpoint'][:50]}...): {e}")
                # Subscription expirada ou invalida — remove
                models.delete_push_subscription_by_endpoint(sub["endpoint"])

        # 2. Email
        user = models.get_user_by_id(user_id)
        email_sent = False
        if user and user.get("email"):
            try:
                _send_email_alert(user["email"], payload)
                email_sent = True
            except Exception as e:
                log.warning(f"Email falhou ({user['email']}): {e}")

        # Loga o alerta
        models.log_alert(user_id, chip_id, alert_type)
        log.info(f"ALERTA [{alert_type}] chip={chip_id}: push={push_sent} email={email_sent}")


def _send_web_push(subscription, payload):
    """Envia push notification via Web Push (VAPID)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush nao instalado — push desabilitado")
        return

    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
    vapid_claim_email = os.environ.get("VAPID_CLAIM_EMAIL", "")
    if not vapid_private_key:
        log.warning("VAPID_PRIVATE_KEY nao configurada — push desabilitado")
        return

    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"]
                }
            },
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={"sub": vapid_claim_email},
            timeout=10
        )
    except WebPushException as e:
        # 410 Gone = subscription expirada
        if "410" in str(e) or "404" in str(e):
            raise  # Propaga pra AlertManager remover a subscription
        log.error(f"WebPush error: {e}")


def _send_email_alert(to_email, payload):
    """Envia email de alerta via SMTP."""
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        return  # Email nao configurado — skip silenciosamente

    title = payload.get("title", "Alerta")
    body = payload.get("body", "")

    msg = MIMEText(f"""Cultivee Alerta

{title}
{body}

Acesse: https://app.cultivee.com.br
---
Para desativar alertas, acesse o app e desabilite notificacoes.
""", "plain", "utf-8")

    msg["Subject"] = f"Cultivee Alerta - {title}"
    msg["From"] = os.environ.get("SMTP_FROM", "alertas@cultivee.com.br")
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain="cultivee.com.br")
    msg["Date"] = formatdate(localtime=True)

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ.get("SMTP_USER", "")
        passwd = os.environ.get("SMTP_PASS", "")
        if port == 465:
            # SSL direto (HostGator, Gmail com SSL)
            with smtplib.SMTP_SSL(smtp_host, port) as s:
                s.login(user, passwd)
                s.send_message(msg)
        else:
            # STARTTLS (porta 587)
            with smtplib.SMTP(smtp_host, port) as s:
                s.starttls()
                s.login(user, passwd)
                s.send_message(msg)
    except Exception as e:
        log.error(f"SMTP error: {e}")
        raise


# Instancia global — usada por app.py
alert_manager = AlertManager()
