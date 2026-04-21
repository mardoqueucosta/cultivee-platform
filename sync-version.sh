#!/usr/bin/env bash
# Cultivee - Sincroniza FIRMWARE_VERSION nos 3 products/*.h com APP_VERSION de server/config.py.
#
# Uso:
#   bash sync-version.sh          # mostra diff (dry-run)
#   bash sync-version.sh --write  # aplica nos arquivos
#
# Historicamente o firmware ficava numa versao diferente do backend porque era
# gravado por USB/OTA em momentos distintos. Deixa rastreio impossivel ("o que
# esse chip roda?"). Este script alinha os 3 arquivos na versao do servidor.
# Chamar antes de `compile.sh upload` ou `ota-remote.sh`.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$ROOT/server/config.py"
WRITE=0
if [[ "${1:-}" == "--write" ]]; then WRITE=1; fi

if [[ ! -f "$CONFIG" ]]; then
  echo "ERRO: nao achei $CONFIG" >&2
  exit 1
fi

# Extrai APP_VERSION = "X.Y.Z" do config.py
APP_VERSION=$(grep -oE 'APP_VERSION[[:space:]]*=[[:space:]]*"[^"]+"' "$CONFIG" | sed -E 's/.*"([^"]+)"/\1/')
if [[ -z "$APP_VERSION" ]]; then
  echo "ERRO: APP_VERSION nao encontrada em $CONFIG" >&2
  exit 1
fi

echo "APP_VERSION (fonte): $APP_VERSION"
echo

changed=0
for f in "$ROOT/products/hidro.h" "$ROOT/products/hidro-farm.h" "$ROOT/products/cam.h"; do
  if [[ ! -f "$f" ]]; then
    echo "AVISO: $f nao existe — pulando" >&2
    continue
  fi
  current=$(grep -oE '#define[[:space:]]+FIRMWARE_VERSION[[:space:]]+"[^"]+"' "$f" | sed -E 's/.*"([^"]+)"/\1/' || true)
  name=$(basename "$f")
  if [[ "$current" == "$APP_VERSION" ]]; then
    printf '  [ok] %-18s %s\n' "$name" "$current"
    continue
  fi
  printf '  [diff] %-16s %s -> %s\n' "$name" "${current:-<ausente>}" "$APP_VERSION"
  changed=1
  if [[ $WRITE -eq 1 ]]; then
    # Atualiza so a linha FIRMWARE_VERSION (sed portable: sem -i in-place em macOS)
    tmp="$(mktemp)"
    sed -E 's|(#define[[:space:]]+FIRMWARE_VERSION[[:space:]]+)"[^"]+"|\1"'"$APP_VERSION"'"|' "$f" > "$tmp"
    mv "$tmp" "$f"
  fi
done

echo
if [[ $changed -eq 0 ]]; then
  echo "Tudo sincronizado em v$APP_VERSION."
  exit 0
fi

if [[ $WRITE -eq 1 ]]; then
  echo "Arquivos atualizados. Recompile os firmwares antes de gravar."
else
  echo "Dry-run. Rode com --write para aplicar."
  exit 2
fi
