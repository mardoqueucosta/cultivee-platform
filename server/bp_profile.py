"""
Cultivee — Blueprint de Perfil do Usuario (v4.1.16).

Area pessoal do usuario logado. Independente do admin.

Endpoints (prefixo /api/profile):
    GET  /                  — retorna perfil completo do usuario logado
    PUT  /                  — atualiza campos editaveis do perfil
    POST /password          — troca senha (requer senha atual)
    GET  /cep/<cep>         — proxy pra ViaCEP (auto-preenchimento de endereco)

Arquitetura:
  - So o proprio usuario acessa seus dados (nao ha "ver perfil de outro user" aqui)
  - Admin ve perfis alheios via /api/admin/users/<id> (bp_admin)
  - Campos whitelist em models.users.PROFILE_EDITABLE_FIELDS (nao aceita id/email/role)
  - Alteracao de senha requer senha atual (anti-session-hijack)
  - Apos trocar senha: todos os OUTROS tokens do usuario sao invalidados,
    sessao atual continua ativa (UX boa — nao desloga do lugar onde ta trocando).
"""

import json
import logging
from functools import wraps
from urllib import request as urlreq, error as urlerr
from flask import Blueprint, request, jsonify

import models


log = logging.getLogger(__name__)
profile_bp = Blueprint("profile", __name__)


# =====================================================================
# Helper: decorator pra exigir auth + expor request.user
# =====================================================================

def _require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        from app import require_auth_func
        user = require_auth_func()
        if not user:
            return jsonify({"error": "Nao autenticado"}), 401
        request.user = user
        return func(*args, **kwargs)
    return wrapper


# =====================================================================
# Perfil
# =====================================================================

@profile_bp.route("/", methods=["GET"])
@_require_auth
def get_profile():
    """Retorna dados do usuario logado (sem password_hash)."""
    user = request.user
    d = dict(user)
    d.pop("password_hash", None)
    # Normaliza campos que podem ser None (pra UI nao precisar fazer null-check)
    for k in models.PROFILE_EDITABLE_FIELDS:
        if d.get(k) is None:
            d[k] = ""
    return jsonify(d)


@profile_bp.route("/", methods=["PUT"])
@_require_auth
def update_profile():
    """Atualiza campos do perfil (whitelist). Email e role NAO sao editaveis aqui."""
    user = request.user
    data = request.get_json(silent=True, force=True) or {}
    updated = models.update_user_profile(user["id"], data)
    return jsonify({
        "status": "ok",
        "updated": list(updated.keys()),
        "fields": updated,
    })


@profile_bp.route("/password", methods=["POST"])
@_require_auth
def change_password():
    """
    Troca a senha do usuario logado.

    Body: { current_password, new_password }

    Validacoes:
      - nova senha >= 6 caracteres
      - current_password confere com hash atual
      - nova senha != atual (opcional — evita trocar pra mesma)

    Apos sucesso:
      - todos os tokens do usuario SAO invalidados exceto o atual
        (usuario continua logado onde trocou, mas outros devices deslogam)
    """
    user = request.user
    data = request.get_json(silent=True, force=True) or {}
    current = data.get("current_password", "")
    new = data.get("new_password", "")

    if not current or not new:
        return jsonify({"error": "Senha atual e nova senha sao obrigatorias"}), 400
    if len(new) < 6:
        return jsonify({"error": "Nova senha deve ter pelo menos 6 caracteres"}), 400

    # Valida senha atual
    if not models.check_password(current, user["password_hash"]):
        return jsonify({"error": "Senha atual incorreta"}), 401

    if current == new:
        return jsonify({"error": "A nova senha nao pode ser igual a atual"}), 400

    # Atualiza
    models.update_user_password(user["id"], new)

    # Invalida OUTROS tokens do usuario (mantem o atual)
    current_token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    conn = models.get_db()
    if current_token:
        conn.execute(
            "DELETE FROM tokens WHERE user_id = ? AND token != ?",
            (user["id"], current_token)
        )
    else:
        conn.execute("DELETE FROM tokens WHERE user_id = ?", (user["id"],))
    conn.commit()
    conn.close()

    log.info(f"[profile] senha alterada: user {user['email']} (id={user['id']})")

    return jsonify({
        "status": "ok",
        "message": "Senha alterada com sucesso. Outros dispositivos foram deslogados.",
    })


# =====================================================================
# ViaCEP proxy — auto-preenchimento de endereco pelo CEP
# =====================================================================

@profile_bp.route("/cep/<cep>", methods=["GET"])
@_require_auth
def lookup_cep(cep):
    """
    Consulta CEP via ViaCEP (https://viacep.com.br/).

    Proxy server-side por 2 motivos:
      1. Evita problemas de CORS no browser
      2. Permite cache futuro (hoje nao cacheia, mas e trivial adicionar)

    Retorna o JSON do ViaCEP normalizado pros nomes que usamos no banco.
    """
    # Limpa CEP (aceita "01310100" ou "01310-100")
    clean = "".join(c for c in cep if c.isdigit())
    if len(clean) != 8:
        return jsonify({"error": "CEP invalido — 8 digitos obrigatorios"}), 400

    url = f"https://viacep.com.br/ws/{clean}/json/"
    try:
        resp = urlreq.urlopen(url, timeout=4)
        data = json.loads(resp.read())
    except urlerr.URLError as e:
        return jsonify({"error": f"Falha ao consultar CEP: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Erro inesperado: {str(e)}"}), 502

    if data.get("erro"):
        return jsonify({"error": "CEP nao encontrado"}), 404

    # Normaliza pra campos do nosso banco
    return jsonify({
        "cep": data.get("cep", "").replace("-", ""),
        "street": data.get("logradouro", ""),
        "neighborhood": data.get("bairro", ""),
        "city": data.get("localidade", ""),
        "state": data.get("uf", ""),
        "complement": data.get("complemento", ""),
    })
