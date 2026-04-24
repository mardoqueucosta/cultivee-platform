#!/bin/bash
# Cultivee — Deploy do Cloudflare Worker (uptime monitor) via API.
# Idempotente: roda quantas vezes quiser, sempre atualiza in-place.
#
# Pre-requisito:
#   D:/01-projetos-claude/.credentials/cloudflare-cultivee.env com:
#     CF_API_TOKEN  (escopo Account.Workers Scripts:Edit)
#     CF_ACCOUNT_ID
set -euo pipefail

CRED="D:/01-projetos-claude/.credentials/cloudflare-cultivee.env"
# Secret HMAC compartilhado entre Worker e VPS (webhook /api/platform-incident)
# Gerado com: python -c "import secrets; print(secrets.token_hex(32))"
# Se nao existir, o provisionamento do secret e pulado (feature fica inativa).
SECRET_FILE="D:/01-projetos-claude/.credentials/platform-incident-secret.env.tmp"
WORKER_NAME="cultivee-uptime"
WORKER_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPAT_DATE="2024-09-23"
CRON_SCHEDULE="*/5 * * * *"  # a cada 5 minutos (~576 writes/dia no free tier KV)
# KV namespace pra persistir checks/incidents (bindado como STATUS_KV no Worker)
KV_NAMESPACE_ID="3c4314b3fd394c6b8af6d31bf44678a2"
KV_BINDING_NAME="STATUS_KV"

# Curl no Windows e mingw32-native (nao MSYS2 unix), entao paths /tmp/...
# nao resolvem. Usar caminhos relativos ao cwd resolve.
cd "$WORKER_DIR"
SCRIPT_FILE="uptime.js"

if [[ ! -f "$CRED" ]]; then
  echo "ERRO: $CRED nao existe" >&2
  exit 1
fi
if [[ ! -f "$WORKER_DIR/$SCRIPT_FILE" ]]; then
  echo "ERRO: $WORKER_DIR/$SCRIPT_FILE nao existe" >&2
  exit 1
fi

# Carrega credenciais sem expor no shell
CF_API_TOKEN=$(grep -m1 '^CF_API_TOKEN=' "$CRED" | cut -d= -f2- | tr -d '\r')
CF_ACCOUNT_ID=$(grep -m1 '^CF_ACCOUNT_ID=' "$CRED" | cut -d= -f2- | tr -d '\r')

if [[ -z "$CF_API_TOKEN" || -z "$CF_ACCOUNT_ID" ]]; then
  echo "ERRO: CF_API_TOKEN ou CF_ACCOUNT_ID vazio" >&2
  exit 1
fi

API="https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME"

echo "=== 1. PUT do script $WORKER_NAME ==="
# Worker como ES module (necessario pra usar export default {scheduled})
META_FILE=".cf-meta.json"
cat > "$META_FILE" <<EOF
{
  "main_module": "uptime.js",
  "compatibility_date": "$COMPAT_DATE",
  "bindings": [
    {"type": "kv_namespace", "name": "$KV_BINDING_NAME", "namespace_id": "$KV_NAMESPACE_ID"}
  ]
}
EOF
RESP_FILE=".cf-resp.json"
HTTP_CODE=$(curl -sS -o "$RESP_FILE" -w "%{http_code}" -X PUT "$API" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -F "metadata=@$META_FILE;type=application/json" \
  -F "uptime.js=@$SCRIPT_FILE;type=application/javascript+module")
rm -f "$META_FILE"
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "FALHOU (HTTP $HTTP_CODE):" >&2
  cat "$RESP_FILE" >&2; echo >&2
  rm -f "$RESP_FILE"
  exit 1
fi
python -c "import json,sys;d=json.load(open('$RESP_FILE'));print('  success:',d.get('success'));
r=d.get('result') or {};print('  modified_on:',r.get('modified_on'));print('  size_bytes:',r.get('size'))"
rm -f "$RESP_FILE"

echo ""
echo "=== 2. Cron Trigger ($CRON_SCHEDULE) ==="
RESP_FILE=".cf-resp.json"
HTTP_CODE=$(curl -sS -o "$RESP_FILE" -w "%{http_code}" -X PUT "$API/schedules" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "[{\"cron\":\"$CRON_SCHEDULE\"}]")
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "FALHOU (HTTP $HTTP_CODE):" >&2
  cat "$RESP_FILE" >&2; echo >&2
  rm -f "$RESP_FILE"
  exit 1
fi
python -c "import json;d=json.load(open('$RESP_FILE'));print('  success:',d.get('success'));
r=d.get('result') or [];
[print('  cron:',c) if isinstance(c,str) else print('  cron:',c.get('cron'),'modified_on:',c.get('modified_on')) for c in r]"
rm -f "$RESP_FILE"

# === 3. Secret PLATFORM_INCIDENT_SECRET (v4.1.33) ===
# Usado pra HMAC do webhook CF Worker -> VPS (/api/platform-incident).
# So configura se o arquivo local existir. Idempotente: re-put atualiza.
if [[ -f "$SECRET_FILE" ]]; then
  echo ""
  echo "=== 3. Secret PLATFORM_INCIDENT_SECRET ==="
  SECRET_VALUE=$(tr -d '\r\n' < "$SECRET_FILE")
  if [[ -z "$SECRET_VALUE" ]]; then
    echo "  AVISO: $SECRET_FILE vazio — pulando" >&2
  else
    RESP_FILE=".cf-resp.json"
    SECRET_BODY_FILE=".cf-secret-body.json"
    python -c "import json; open('$SECRET_BODY_FILE','w').write(json.dumps({'name':'PLATFORM_INCIDENT_SECRET','text':'$SECRET_VALUE','type':'secret_text'}))"
    HTTP_CODE=$(curl -sS -o "$RESP_FILE" -w "%{http_code}" -X PUT "$API/secrets" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      --data-binary "@$SECRET_BODY_FILE")
    rm -f "$SECRET_BODY_FILE"
    if [[ "$HTTP_CODE" != "200" ]]; then
      echo "  FALHOU (HTTP $HTTP_CODE):" >&2
      cat "$RESP_FILE" >&2; echo >&2
      rm -f "$RESP_FILE"
      echo "  (deploy continua — secret pode ser configurado manualmente via dashboard CF)"
    else
      python -c "import json;d=json.load(open('$RESP_FILE'));print('  success:',d.get('success'),' name:',(d.get('result') or {}).get('name'))"
      rm -f "$RESP_FILE"
    fi
  fi
  unset SECRET_VALUE
else
  echo ""
  echo "=== 3. Secret PLATFORM_INCIDENT_SECRET — arquivo nao existe, pulando ==="
  echo "  (criar $SECRET_FILE com 64 hex chars pra ativar o webhook)"
fi

echo ""
echo "=== Pronto ==="
echo "Dashboard:  https://dash.cloudflare.com/$CF_ACCOUNT_ID/workers/services/view/$WORKER_NAME/production"
echo "Cron:       $CRON_SCHEDULE  (proxima execucao em ate 5min)"
echo "Logs live:  Dashboard > Workers > $WORKER_NAME > Logs"
