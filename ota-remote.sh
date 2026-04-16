#!/bin/bash
# OTA Remoto — Envia firmware para o ESP32 via servidor Cultivee
#
# O servidor salva o .bin e sinaliza o ESP32 no proximo register (~10s).
# O ESP32 baixa o .bin via HTTP e se auto-atualiza.
#
# Uso:
#   bash ota-remote.sh <chip_id> <bin_path> <token>
#
# Exemplos:
#   # Hidro (chip_id do banco):
#   bash ota-remote.sh E04730A7DBCC build/firmware.ino.bin "seu_token_aqui"
#
#   # Hidro-Farm:
#   bash ota-remote.sh 348257088304 build/firmware.ino.bin "seu_token_aqui"
#
# Para obter o token: fazer login no app.cultivee.com.br e copiar do localStorage
# (chave cultivee_auth_token) ou fazer POST /api/auth/login.
#
# Para obter o chip_id: ver na lista de modulos no app ou no banco de dados.

set -e

CHIP_ID="$1"
BIN_PATH="$2"
TOKEN="$3"
SERVER="${4:-https://app.cultivee.com.br}"

if [ -z "$CHIP_ID" ] || [ -z "$BIN_PATH" ] || [ -z "$TOKEN" ]; then
    echo "Uso: bash ota-remote.sh <chip_id> <bin_path> <token> [server_url]"
    echo ""
    echo "  chip_id   ID do modulo (ex: E04730A7DBCC)"
    echo "  bin_path  Caminho do firmware.ino.bin"
    echo "  token     Token de autenticacao (Bearer)"
    echo "  server    (opcional) URL do servidor (default: https://app.cultivee.com.br)"
    exit 1
fi

if [ ! -f "$BIN_PATH" ]; then
    echo "ERRO: Arquivo nao encontrado: $BIN_PATH"
    exit 1
fi

SIZE=$(stat --format="%s" "$BIN_PATH" 2>/dev/null || stat -f "%z" "$BIN_PATH" 2>/dev/null)
echo "=== OTA Remoto ==="
echo "Servidor: $SERVER"
echo "Chip ID:  $CHIP_ID"
echo "Firmware: $BIN_PATH ($SIZE bytes)"
echo ""
echo "Enviando..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -F "firmware=@$BIN_PATH" \
    "$SERVER/api/modules/$CHIP_ID/firmware")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "OK: $BODY"
    echo ""
    echo "Firmware enviado! O ESP32 vai baixar no proximo register (~10s)."
    echo "Acompanhe via: ssh ... 'docker logs cultivee-app --tail 20 | grep OTA'"
else
    echo "ERRO HTTP $HTTP_CODE: $BODY"
    exit 1
fi
