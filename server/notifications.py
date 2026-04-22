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
        """Chamado a cada register do ESP32. ctrl_data e dict (raw do ESP32), module e row do DB."""
        user_id = module.get("user_id")
        if not user_id:
            return  # Modulo nao pareado — sem usuario pra notificar

        # Merge: dados do ESP32 + dados do banco (low_since, alert_threshold_min, etc.)
        # O ESP32 nao manda campos gerenciados pelo servidor — precisa ler do banco.
        import json as _json
        try:
            db_data = _json.loads(module.get("ctrl_data", "{}"))
        except (ValueError, TypeError):
            db_data = {}
        merged = {**db_data, **ctrl_data}  # ESP32 sobrescreve dados do banco, mas campos ausentes ficam

        # Alerta: reservatorio vazio por 10+ minutos
        self._check_reservoir(chip_id, merged, user_id, module)

        # Futuros alertas:
        # self._check_temperature(chip_id, ctrl_data, user_id)
        # self._check_module_offline(chip_id, ctrl_data, user_id)

    def _check_reservoir(self, chip_id, ctrl_data, user_id, module=None):
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
            # Verifica se ja tinha low_since no banco (timer sobrevive restart do container)
            existing_since = ctrl_data.get("low_since")
            if existing_since:
                try:
                    from datetime import datetime, timezone
                    since_dt = datetime.fromisoformat(existing_since)
                    _alert_timers[timer_key] = since_dt.timestamp()
                    log.info(f"Reservatorio {chip_id}: timer restaurado do banco (low_since={existing_since})")
                except (ValueError, TypeError):
                    _alert_timers[timer_key] = now
            else:
                _alert_timers[timer_key] = now
                # Salva timestamp UTC no banco pra o PWA mostrar o contador
                from datetime import datetime, timezone
                import models as _m
                _m.update_ctrl_data(chip_id, {"low_since": datetime.now(timezone.utc).isoformat()})
                log.info(f"Reservatorio {chip_id}: boia baixa sem agua — timer iniciado")
                return  # Comecou agora — espera

        elapsed = now - _alert_timers[timer_key]
        threshold_min = ctrl_data.get("alert_threshold_min", 10)
        threshold_sec = threshold_min * 60
        if elapsed < threshold_sec:
            return  # Menos que o threshold configurado — espera

        # Threshold atingido — verifica cooldown
        import models
        if not models.should_send_alert(user_id, chip_id, "level_low"):
            return  # Ja notificou na ultima hora

        # Monta payload e envia
        module_name = (module.get("name") if module else None) or "Modulo"
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

        # 2. Email (usa notification_email se existir, senao email de login)
        user = models.get_user_by_id(user_id)
        email_sent = False
        to_email = None
        if user:
            try:
                to_email = user["notification_email"] or user["email"]
            except (IndexError, KeyError):
                to_email = user["email"]
        if to_email:
            try:
                _send_email_alert(to_email, payload)
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


def send_email(to_email, subject, body):
    """
    Envia email generico via SMTP (reutilizado por alertas, auth, onboarding, etc.)

    Retorna True se enviou, False se SMTP nao esta configurado.
    Lanca excecao em caso de erro SMTP — chamador decide se ignora ou re-lanca.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        log.warning("SMTP nao configurado — email ignorado")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "contato@cultivee.com.br")
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain="cultivee.com.br")
    msg["Date"] = formatdate(localtime=True)

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
    return True


def _send_email_alert(to_email, payload):
    """Envia email de alerta (wrapper sobre send_email com template de alerta)."""
    title = payload.get("title", "Alerta")
    body_text = payload.get("body", "")
    full_body = f"""Cultivee Alerta

{title}
{body_text}

Acesse: https://app.cultivee.com.br
---
Para desativar alertas, acesse o app e desabilite notificacoes.
"""
    try:
        send_email(to_email, f"Cultivee Alerta - {title}", full_body)
    except Exception as e:
        log.error(f"SMTP error (alerta): {e}")
        raise


# =====================================================================
# 2FA Email OTP — template (v4.1.29)
# =====================================================================

def send_email_2fa_code(user, code, context="login"):
    """
    Envia codigo OTP por email pra 2FA.
    context = 'login' (a cada tentativa de login) ou 'setup' (ativacao inicial).
    Usa notification_email se setado, senao email de login.
    """
    destination = None
    try:
        destination = user["notification_email"]
    except (KeyError, IndexError, TypeError):
        pass
    if not destination:
        destination = user["email"]
    name = user["name"] if user["name"] else "Usuario"

    if context == "setup":
        subject = "Cultivee - Confirme sua autenticacao por email"
        body = f"""Ola, {name}!

Voce solicitou ativar a autenticacao em duas etapas (2FA) por email.

Seu codigo de confirmacao:

    {code}

Digite esse codigo no app pra concluir a ativacao. O codigo e valido por
10 minutos. Se nao foi voce que solicitou, ignore este email.

--
Equipe Cultivee
contato@cultivee.com.br
"""
    else:
        subject = "Cultivee - Codigo de login"
        body = f"""Ola, {name}!

Alguem (provavelmente voce) tentou entrar na sua conta Cultivee. Use o
codigo abaixo pra concluir o login:

    {code}

O codigo e valido por 10 minutos e so pode ser usado uma vez.

Se nao foi voce, alguem pode ter sua senha. Recomendamos:
  1. Trocar a senha imediatamente
  2. Manter a 2FA ativa

--
Equipe Cultivee
contato@cultivee.com.br
"""
    send_email(destination, subject, body)


# Instancia global — usada por app.py
alert_manager = AlertManager()
