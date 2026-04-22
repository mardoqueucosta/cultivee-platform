"""
Blueprint publico de formularios do site institucional.

Rotas:
- POST /api/public/contact     — formulario de contato (cultivee.com.br/contato)
- POST /api/public/newsletter  — inscricao newsletter (rodape/newsletter section)

Padrao inspirado no /api/contact do biopdi-nextjs:
- Honeypot `company_fax` (bots preenchem, humanos nao — retornamos 200 fake)
- Rate limit 5 req/hora por IP (in-memory, igual usuario/auth.py)
- escape HTML antes de inserir no template
- Validacao de tamanho (5000 chars max na mensagem)
- Template HTML bonito com cores do Cultivee
"""

import html
import logging
import os
import smtplib
import time
from collections import defaultdict, deque
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from flask import Blueprint, request, jsonify

log = logging.getLogger(__name__)
public_bp = Blueprint("public", __name__)

# ============================================================
# Configuracao
# ============================================================

RATE_LIMIT_WINDOW = 3600  # 1 hora em segundos
RATE_LIMIT_MAX = 5         # maximo de envios por IP por janela
MAX_MESSAGE_LEN = 5000
MAX_NAME_LEN = 120
MAX_EMAIL_LEN = 200

# In-memory rate store: {"contact:1.2.3.4": deque([timestamp1, timestamp2, ...])}
# Mesmo padrao do rate limit em usuario/auth.py — nao escala multi-worker mas
# serve pro volume baixo de contatos do site institucional.
_rate_store = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX + 5))

# Labels amigaveis dos subjects (dropdown do form)
SUBJECT_LABELS = {
    "cursos-agro": "Cursos Agro (Microverdes, Hidroponia, Cultivo Indoor)",
    "cursos-educa": "Cursos Educa",
    "cursos-tech": "Cursos Tech",
    "hortalicas": "Hortalicas",
    "produtos": "Produtos (Cultivee Hidro / Hidro Farm / Cam)",
    "projeto": "Projeto Cultivee",
    "parcerias": "Parcerias",
    "outro": "Outro",
}


# ============================================================
# Helpers
# ============================================================

def _get_client_ip():
    """Retorna IP real do cliente (ProxyFix do app.py ja processou X-Forwarded-For)."""
    return request.remote_addr or "unknown"


def _rate_limit_check(ip, prefix):
    """Retorna True se ainda pode enviar, False se passou do limite."""
    key = f"{prefix}:{ip}"
    now = time.time()
    q = _rate_store[key]
    # Purga timestamps fora da janela
    while q and q[0] < now - RATE_LIMIT_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT_MAX:
        return False
    q.append(now)
    return True


def _valid_email(email):
    """Validacao basica de email (regex simplificado, nao RFC-completo)."""
    if not email or len(email) > MAX_EMAIL_LEN:
        return False
    if "@" not in email:
        return False
    local, _, domain = email.rpartition("@")
    if not local or "." not in domain:
        return False
    return True


def _send_html_email(to_email, subject, body_html, reply_to=None):
    """
    Envia email HTML via SMTP SSL (porta 465, HostGator).

    Identico ao `notifications.send_email()` exceto que manda HTML em vez de texto
    puro. Usa as mesmas env vars (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    SMTP_FROM) — ja configuradas no .env da VPS.

    Raises:
        RuntimeError: se SMTP nao esta configurado
        smtplib.SMTPException: em caso de falha de envio
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        raise RuntimeError("SMTP nao configurado (SMTP_HOST ausente)")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Cultivee <{os.environ.get('SMTP_FROM', 'contato@cultivee.com.br')}>"
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain="cultivee.com.br")
    msg["Date"] = formatdate(localtime=True)
    if reply_to:
        msg["Reply-To"] = reply_to

    # Fallback em texto puro (clientes sem HTML)
    text_fallback = (
        "Para visualizar esta mensagem corretamente, use um cliente de email "
        "que suporte HTML."
    )
    msg.attach(MIMEText(text_fallback, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER", "")
    passwd = os.environ.get("SMTP_PASS", "")

    if port == 465:
        with smtplib.SMTP_SSL(smtp_host, port, timeout=15) as s:
            s.login(user, passwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, port, timeout=15) as s:
            s.starttls()
            s.login(user, passwd)
            s.send_message(msg)


# ============================================================
# Rota: /api/public/contact
# ============================================================

@public_bp.route("/contact", methods=["POST", "OPTIONS"])
def contact():
    # OPTIONS preflight — CORS tratado em app.py @after_request
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}

    # 1) Honeypot — bots preenchem, humanos nao veem o campo
    if data.get("company_fax") or data.get("website"):
        log.info(f"[CONTACT] Honeypot triggered from {_get_client_ip()}")
        # Retorna sucesso fake — bot pensa que funcionou
        return jsonify({"message": "Mensagem enviada com sucesso"}), 200

    # 2) Extrai e sanitiza campos
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()

    # 3) Validacao
    if not name or not email or not message:
        return jsonify({"error": "Nome, email e mensagem sao obrigatorios."}), 400
    if len(name) > MAX_NAME_LEN:
        return jsonify({"error": "Nome muito longo."}), 400
    if not _valid_email(email):
        return jsonify({"error": "Email invalido."}), 400
    if len(message) > MAX_MESSAGE_LEN:
        return jsonify({"error": f"Mensagem muito longa (maximo {MAX_MESSAGE_LEN} caracteres)."}), 400

    # 4) Rate limit
    ip = _get_client_ip()
    if not _rate_limit_check(ip, "contact"):
        log.warning(f"[CONTACT] Rate limit hit for {ip}")
        return jsonify({"error": "Muitas mensagens enviadas. Tente novamente mais tarde ou fale pelo WhatsApp."}), 429

    # 5) Escape HTML de tudo que vai pro template
    safe_name = html.escape(name)
    safe_email = html.escape(email)
    safe_phone = html.escape(phone) if phone else ""
    safe_message = html.escape(message)
    subject_label = SUBJECT_LABELS.get(subject, subject or "Contato geral")
    safe_subject = html.escape(subject_label)

    # 6) Monta email HTML (tabela de campos + bloco destacado com a mensagem)
    phone_row = ""
    if safe_phone:
        phone_row = (
            f'<tr>'
            f'<td style="padding: 10px 14px; background: #f0fdf4; font-weight: 600; color: #166534; border-bottom: 1px solid #dcfce7;">Telefone</td>'
            f'<td style="padding: 10px 14px; border-bottom: 1px solid #dcfce7;">{safe_phone}</td>'
            f'</tr>'
        )

    body_html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Nova mensagem Cultivee</title></head>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); overflow: hidden;">
    <div style="background: linear-gradient(135deg, #21c45d, #29a38f); padding: 20px 24px;">
      <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 700;">
        Nova mensagem Cultivee
      </h1>
      <p style="margin: 4px 0 0 0; color: rgba(255,255,255,0.9); font-size: 13px;">
        Formulario de contato de cultivee.com.br
      </p>
    </div>

    <div style="padding: 24px;">
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
        <tr>
          <td style="padding: 10px 14px; background: #f0fdf4; font-weight: 600; color: #166534; border-bottom: 1px solid #dcfce7; width: 110px;">Nome</td>
          <td style="padding: 10px 14px; border-bottom: 1px solid #dcfce7;">{safe_name}</td>
        </tr>
        <tr>
          <td style="padding: 10px 14px; background: #f0fdf4; font-weight: 600; color: #166534; border-bottom: 1px solid #dcfce7;">E-mail</td>
          <td style="padding: 10px 14px; border-bottom: 1px solid #dcfce7;"><a href="mailto:{safe_email}" style="color: #15803d; text-decoration: none;">{safe_email}</a></td>
        </tr>
        {phone_row}
        <tr>
          <td style="padding: 10px 14px; background: #f0fdf4; font-weight: 600; color: #166534;">Assunto</td>
          <td style="padding: 10px 14px;">{safe_subject}</td>
        </tr>
      </table>

      <div style="padding: 16px 18px; background: #f8fafc; border-left: 4px solid #15803d; border-radius: 4px; white-space: pre-wrap; font-size: 14px; line-height: 1.5; color: #1e293b;">{safe_message}</div>

      <p style="margin-top: 24px; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 12px;">
        Responder este email manda a resposta direto para <strong>{safe_email}</strong>.<br/>
        IP de origem: {html.escape(ip)}
      </p>
    </div>
  </div>
</body>
</html>"""

    # 7) Envia
    email_subject = f"[Cultivee] {subject_label} - {name}"
    recipient = os.environ.get("CONTACT_EMAIL", "contato@cultivee.com.br")

    try:
        _send_html_email(recipient, email_subject, body_html, reply_to=email)
    except Exception as e:
        log.error(f"[CONTACT_ERROR] {type(e).__name__}: {e}", exc_info=True)
        return jsonify({
            "error": "Nao conseguimos enviar sua mensagem agora. Tente novamente em alguns minutos ou fale com a gente no WhatsApp."
        }), 500

    log.info(f"[CONTACT] {name} <{email}> - {subject_label} (ip={ip})")
    return jsonify({"message": "Mensagem enviada com sucesso. Responderemos em breve!"}), 200


# ============================================================
# Rota: /api/public/newsletter
# ============================================================

@public_bp.route("/newsletter", methods=["POST", "OPTIONS"])
def newsletter():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}

    # Honeypot
    if data.get("company_fax") or data.get("website"):
        log.info(f"[NEWSLETTER] Honeypot triggered from {_get_client_ip()}")
        return jsonify({"message": "Inscricao realizada"}), 200

    email = (data.get("email") or "").strip().lower()

    if not _valid_email(email):
        return jsonify({"error": "Email invalido."}), 400

    ip = _get_client_ip()
    if not _rate_limit_check(ip, "newsletter"):
        log.warning(f"[NEWSLETTER] Rate limit hit for {ip}")
        return jsonify({"error": "Muitas tentativas. Tente novamente mais tarde."}), 429

    safe_email = html.escape(email)

    # Por enquanto: so notifica o admin sobre a nova inscricao.
    # Double opt-in + persistencia em DB podem ser adicionados depois quando
    # o volume justificar a complexidade.
    body_html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"></head>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc;">
  <div style="max-width: 500px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
    <h2 style="margin: 0 0 12px 0; color: #15803d;">Nova inscricao na newsletter</h2>
    <p style="margin: 0 0 8px 0; font-size: 15px;">
      <strong>Email:</strong> <a href="mailto:{safe_email}" style="color: #15803d;">{safe_email}</a>
    </p>
    <p style="margin: 0; font-size: 12px; color: #64748b;">IP: {html.escape(ip)}</p>
  </div>
</body>
</html>"""

    admin_email = os.environ.get("CONTACT_EMAIL", "contato@cultivee.com.br")
    try:
        _send_html_email(admin_email, f"[Cultivee] Nova inscricao: {email}", body_html)
    except Exception as e:
        log.error(f"[NEWSLETTER_ERROR] {type(e).__name__}: {e}", exc_info=True)
        return jsonify({"error": "Nao conseguimos processar sua inscricao. Tente novamente."}), 500

    log.info(f"[NEWSLETTER] {email} (ip={ip})")
    return jsonify({
        "message": "Inscricao realizada! Em breve voce recebera nossas novidades por email."
    }), 200
