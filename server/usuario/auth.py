"""
Cultivee — Blueprint de Autenticacao e Validacao de Usuario
Centraliza todo o fluxo: registro, login, logout, recuperacao de senha.

Endpoints (prefixo /api/auth):
    POST /register           — cria conta
    POST /login              — autentica e retorna token
    GET  /me                 — dados do usuario logado
    POST /logout             — invalida token
    POST /forgot-password    — envia email com link de reset
    POST /reset-password     — valida token e define nova senha

Features v4.1.12:
    - Validacao de formato de email (regex RFC-lite)
    - Rate limiting in-memory por IP (anti brute-force, anti spam)
    - Recuperacao de senha com token temporario (1h) enviado por email
    - Anti-enumeration: nao revela se email existe no forgot-password
    - SMTP reutilizado de notifications.py (contato@cultivee.com.br)
"""

import re
import time
from functools import wraps
from flask import Blueprint, request, jsonify

import models


auth_bp = Blueprint("auth", __name__)


# =====================================================================
# Validacao de formato de email (regex pragmatica, nao RFC completa)
# =====================================================================

_EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def is_valid_email(email):
    if not email or len(email) > 254:
        return False
    return bool(_EMAIL_REGEX.match(email))


# =====================================================================
# Rate limiting em memoria (per-IP, per-endpoint)
# Implementacao simples — serve pro MVP. Pra escalar multi-worker,
# migrar pra Redis ou usar flask-limiter.
# =====================================================================

_rate_store = {}  # {"endpoint:ip": [t1, t2, ...]}


# =====================================================================
# Decorator de admin (v4.1.13)
# =====================================================================

def require_admin(func):
    """
    Garante que a rota so execute se o usuario autenticado tiver role='admin'.
    Retorna 401 se nao autenticado, 403 se autenticado mas nao admin.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        from app import require_auth_func
        user = require_auth_func()
        if not user:
            return jsonify({"error": "Nao autenticado"}), 401
        role = None
        try:
            role = user["role"]
        except (KeyError, IndexError, TypeError):
            pass
        if role != "admin":
            return jsonify({"error": "Acesso negado — requer permissao de admin"}), 403
        request.user = user
        return func(*args, **kwargs)
    return wrapper


def _get_client_ip():
    """Extrai IP do cliente (respeita X-Forwarded-For do Traefik)."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limit(max_requests, window_seconds):
    """
    Decorator: bloqueia se exceder X requests em Y segundos por IP+endpoint.
    Retorna HTTP 429 com mensagem amigavel.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{_get_client_ip()}"
            now = time.time()
            entries = _rate_store.get(key, [])
            # Limpa timestamps fora da janela
            entries = [t for t in entries if now - t < window_seconds]
            if len(entries) >= max_requests:
                wait = int(window_seconds - (now - entries[0]))
                return jsonify({
                    "error": f"Muitas tentativas. Tente novamente em {wait}s."
                }), 429
            entries.append(now)
            _rate_store[key] = entries
            return func(*args, **kwargs)
        return wrapper
    return decorator


# =====================================================================
# Rotas
# =====================================================================

@auth_bp.route("/register", methods=["POST"])
@rate_limit(max_requests=5, window_seconds=300)  # 5 cadastros por IP a cada 5 min
def register():
    data = request.get_json(silent=True, force=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()
    # v4.1.20: aceite obrigatorio de termos + privacidade (LGPD)
    accepted_terms = bool(data.get("accepted_terms", False))

    if not email or not password or not name:
        return jsonify({"error": "email, password e name obrigatorios"}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Formato de email invalido"}), 400
    if len(password) < 6:
        return jsonify({"error": "Senha deve ter pelo menos 6 caracteres"}), 400
    if len(name) < 2 or len(name) > 80:
        return jsonify({"error": "Nome deve ter entre 2 e 80 caracteres"}), 400
    if not accepted_terms:
        return jsonify({
            "error": "Voce precisa aceitar os Termos de Uso e a Politica de Privacidade"
        }), 400

    user_id = models.create_user(email, password, name)
    if not user_id:
        return jsonify({"error": "Email ja cadastrado"}), 409

    # Registra aceite com timestamp (LGPD — prova que o user consentiu)
    models.mark_terms_accepted(user_id)

    # v4.1.20: envia email de verificacao (nao bloqueia cadastro se SMTP falhar)
    verify_token = models.generate_email_verification_token(user_id)
    try:
        _send_verification_email(email, name, verify_token)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Falha ao enviar email de verificacao: {e}")

    token = models.create_token(user_id)
    return jsonify({
        "token": token,
        "user": {
            "id": user_id, "email": email, "name": name, "role": "user",
            "email_verified": False,
        }
    })


def _send_verification_email(email, name, verify_token):
    """Envia email com link pro user confirmar o endereco."""
    from notifications import send_email
    url = f"https://app.cultivee.com.br/?verify={verify_token}"
    body = f"""Ola, {name}!

Bem-vindo ao Cultivee! Pra ativar sua conta e garantir que os alertas
cheguem no email certo, confirme este endereco clicando no link abaixo:

    {url}

Se nao foi voce que se cadastrou, ignore este email — a conta nao sera
ativada sem confirmacao.

--
Equipe Cultivee
contato@cultivee.com.br
"""
    send_email(email, "Cultivee - Confirme seu email", body)


@auth_bp.route("/verify-email", methods=["GET", "POST"])
@rate_limit(max_requests=10, window_seconds=60)
def verify_email():
    """Confirma email via token (usado pelo link do email ou chamada do frontend)."""
    token = request.args.get("token", "") or (request.get_json(silent=True, force=True) or {}).get("token", "")
    if not token:
        return jsonify({"error": "Token obrigatorio"}), 400

    user_id = models.verify_email_with_token(token)
    if not user_id:
        return jsonify({"error": "Token invalido ou ja usado"}), 400

    return jsonify({"status": "ok", "message": "Email confirmado com sucesso!"})


@auth_bp.route("/resend-verification", methods=["POST"])
@rate_limit(max_requests=3, window_seconds=600)  # 3 por IP a cada 10 min
def resend_verification():
    """Reenvia o email de verificacao (user precisa estar logado)."""
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    # Ja verificado? Sucesso silencioso
    try:
        if user["email_verified_at"]:
            return jsonify({"status": "ok", "message": "Email ja estava verificado"})
    except (KeyError, IndexError, TypeError):
        pass

    verify_token = models.generate_email_verification_token(user["id"])
    try:
        _send_verification_email(user["email"], user["name"], verify_token)
    except Exception as e:
        return jsonify({"error": f"Falha ao enviar email: {e}"}), 502
    return jsonify({"status": "ok", "message": "Email de verificacao reenviado"})


@auth_bp.route("/login", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60)  # 10 tentativas por IP por minuto
def login():
    data = request.get_json(silent=True, force=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email e senha obrigatorios"}), 400

    user = models.get_user_by_email(email)
    if not user or not models.check_password(password, user["password_hash"]):
        return jsonify({"error": "Email ou senha invalidos"}), 401

    token = models.create_token(user["id"])
    # v4.1.13: inclui role na resposta (PWA usa pra mostrar/esconder aba Admin)
    role = "user"
    try: role = user["role"] or "user"
    except (KeyError, IndexError, TypeError): pass
    # v4.1.20: inclui email_verified (PWA mostra banner se false)
    email_verified = False
    try: email_verified = bool(user["email_verified_at"])
    except (KeyError, IndexError, TypeError): pass
    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": role,
            "email_verified": email_verified,
        }
    })


@auth_bp.route("/me")
def me():
    from app import require_auth_func
    user = require_auth_func()
    if not user:
        return jsonify({"error": "Nao autenticado"}), 401
    role = "user"
    try: role = user["role"] or "user"
    except (KeyError, IndexError, TypeError): pass
    email_verified = False
    try: email_verified = bool(user["email_verified_at"])
    except (KeyError, IndexError, TypeError): pass
    return jsonify({
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": role,
        "email_verified": email_verified,
    })


@auth_bp.route("/logout", methods=["POST"])
def logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        models.delete_token(auth[7:])
    return jsonify({"status": "ok"})


# =====================================================================
# Recuperacao de senha
# =====================================================================

@auth_bp.route("/forgot-password", methods=["POST"])
@rate_limit(max_requests=3, window_seconds=900)  # 3 pedidos por IP a cada 15 min
def forgot_password():
    """
    Envia email com link de reset (se o email existir no banco).
    Sempre retorna sucesso pra evitar enumeration attack (atacante descobrir
    quais emails tem conta no sistema).
    """
    data = request.get_json(silent=True, force=True) or {}
    email = data.get("email", "").strip().lower()

    if not is_valid_email(email):
        return jsonify({"error": "Formato de email invalido"}), 400

    user = models.get_user_by_email(email)
    if user:
        try:
            token = models.create_password_reset_token(user["id"], expires_minutes=60)
            _send_reset_email(user, token)
        except Exception as e:
            # Nao vaza erro pro cliente — log interno
            import logging
            logging.getLogger(__name__).error(f"Erro ao enviar email de reset: {e}")

    # Sempre retorna OK (anti-enumeration)
    return jsonify({
        "status": "ok",
        "message": "Se o email estiver cadastrado, voce recebera instrucoes em alguns instantes."
    })


@auth_bp.route("/reset-password", methods=["POST"])
@rate_limit(max_requests=5, window_seconds=300)
def reset_password():
    """Valida token recebido por email e define nova senha."""
    data = request.get_json(silent=True, force=True) or {}
    token = data.get("token", "").strip()
    new_password = data.get("password", "")

    if not token:
        return jsonify({"error": "Token obrigatorio"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Senha deve ter pelo menos 6 caracteres"}), 400

    user_id = models.validate_password_reset_token(token)
    if not user_id:
        return jsonify({"error": "Token invalido ou expirado. Solicite um novo link."}), 400

    models.update_user_password(user_id, new_password)
    models.consume_password_reset_token(token)

    return jsonify({
        "status": "ok",
        "message": "Senha alterada com sucesso. Faca login com a nova senha."
    })


def _send_reset_email(user, token):
    """Envia email de reset pro usuario (usa notification_email se configurado)."""
    from notifications import send_email

    # Destino: notification_email se setado, senao email de login
    destination = None
    try:
        destination = user["notification_email"]
    except (KeyError, IndexError, TypeError):
        pass
    if not destination:
        destination = user["email"]

    reset_url = f"https://app.cultivee.com.br/?reset={token}"
    name = user["name"] if user["name"] else "Usuario"

    body = f"""Ola, {name}!

Voce solicitou a redefinicao da senha da sua conta Cultivee.

Clique no link abaixo para criar uma nova senha (valido por 1 hora):

    {reset_url}

Se nao foi voce que solicitou, ignore este email — nenhuma alteracao foi feita
e sua senha atual continua valida.

Por seguranca, nunca compartilhe este link com ninguem.

--
Equipe Cultivee
contato@cultivee.com.br
https://cultivee.com.br
"""

    send_email(destination, "Cultivee - Recuperacao de senha", body)
