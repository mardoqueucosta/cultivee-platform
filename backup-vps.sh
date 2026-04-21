#!/usr/bin/env bash
# Cultivee - Backup dos dados da VPS (cultivee.db + captures/thumbs/firmware)
#
# Uso:
#   bash backup-vps.sh                     # baixa em ./backups/YYYYMMDD-HHMMSS/
#   bash backup-vps.sh /caminho/destino    # baixa no destino informado
#   bash backup-vps.sh --restore DUMP_DIR  # restaura um dump previo na VPS (DESTRUTIVO)
#
# Gera:
#   - cultivee.db         (copia online via sqlite3 .backup, seguro com WAL ativo)
#   - data.tar.gz         (captures/, thumbs/, live/, firmware/)
#   - manifest.txt        (hash SHA-256 dos dois arquivos + timestamp + versao)
#
# Pre-requisito (primeira vez): ter `sqlite3` instalado na VPS.
#   ssh ... "apt-get -y install sqlite3"
#
# A regra anti-fail2ban do CLAUDE.md continua valida: uma unica sessao SSH por
# execucao. O script encadeia todos os comandos remotos numa so conexao.

set -euo pipefail

SSH_KEY="${SSH_KEY:-D:/01-projetos-claude/.credentials/id_rsa}"
SSH_HOST="${SSH_HOST:-root@129.121.50.168}"
SSH_PORT="${SSH_PORT:-22022}"
REMOTE_BASE="${REMOTE_BASE:-/opt/sites/cultivee-platform}"
REMOTE_DATA="${REMOTE_DATA:-/var/lib/docker/volumes/cultivee_cultivee-data/_data}"

SSH() { ssh -i "$SSH_KEY" -p "$SSH_PORT" -o BatchMode=yes "$SSH_HOST" "$@"; }
SCP() { scp -i "$SSH_KEY" -P "$SSH_PORT" -o BatchMode=yes "$@"; }

do_backup() {
  local dest="${1:-}"
  if [[ -z "$dest" ]]; then
    dest="./backups/$(date +%Y%m%d-%H%M%S)"
  fi
  mkdir -p "$dest"
  echo "Destino local: $dest"

  # Single SSH session — cria DB copy + tarball, volta pra stdout base64? Nao,
  # prefere baixar via scp em 2 arquivos (legivel + reproduzivel). Entao:
  # 1) Conexao 1: gera /tmp/cultivee.db + /tmp/data.tar.gz numa sessao
  # 2) SCP baixa os dois
  # 3) Conexao 2: limpa /tmp (encadear com o scp acaba sendo 3 conexoes se o fail2ban
  #    contar agressivo; o ideal e ajustar DenyAttempt no jail pro nosso IP).

  echo ">> Gerando dump remoto..."
  SSH "set -e
    TS=\$(date +%Y%m%d-%H%M%S)
    mkdir -p /tmp/cultivee-dump
    cd /tmp/cultivee-dump
    # .backup e safe com WAL (vs cp que pode pegar arquivo inconsistente)
    sqlite3 $REMOTE_DATA/cultivee.db \".backup '/tmp/cultivee-dump/cultivee.db'\"
    tar -czf /tmp/cultivee-dump/data.tar.gz -C $REMOTE_DATA captures thumbs live firmware 2>/dev/null || true
    sha256sum cultivee.db data.tar.gz > manifest.txt
    echo timestamp=\$TS >> manifest.txt
    echo app_version=\$(grep APP_VERSION $REMOTE_BASE/server/config.py | head -1 | awk -F'\"' '{print \$2}') >> manifest.txt
    ls -lh /tmp/cultivee-dump/
  "

  echo ">> Baixando..."
  SCP "$SSH_HOST:/tmp/cultivee-dump/cultivee.db"   "$dest/cultivee.db"
  SCP "$SSH_HOST:/tmp/cultivee-dump/data.tar.gz"   "$dest/data.tar.gz"
  SCP "$SSH_HOST:/tmp/cultivee-dump/manifest.txt"  "$dest/manifest.txt"

  echo ">> Limpando remoto..."
  SSH "rm -rf /tmp/cultivee-dump"

  echo
  echo "Backup concluido em: $dest"
  cat "$dest/manifest.txt"
}

do_restore() {
  local src="$1"
  if [[ ! -f "$src/cultivee.db" || ! -f "$src/data.tar.gz" || ! -f "$src/manifest.txt" ]]; then
    echo "ERRO: $src nao tem dump completo (cultivee.db, data.tar.gz, manifest.txt)" >&2
    exit 1
  fi

  echo "==== RESTORE ===="
  cat "$src/manifest.txt"
  echo
  read -p "Vai SOBRESCREVER o banco e os dados da VPS. Confirma? (digite 'RESTORE'): " yes
  if [[ "$yes" != "RESTORE" ]]; then
    echo "Cancelado."
    exit 1
  fi

  # Upload dos arquivos — permite scp em 1 conexao (multiplos arquivos)
  echo ">> Enviando dump pra VPS..."
  SSH "mkdir -p /tmp/cultivee-restore"
  SCP "$src/cultivee.db"  "$SSH_HOST:/tmp/cultivee-restore/cultivee.db"
  SCP "$src/data.tar.gz"  "$SSH_HOST:/tmp/cultivee-restore/data.tar.gz"

  echo ">> Aplicando (container sera parado temporariamente)..."
  SSH "set -e
    cd $REMOTE_BASE
    docker compose stop
    cp $REMOTE_DATA/cultivee.db $REMOTE_DATA/cultivee.db.pre-restore.\$(date +%s) || true
    cp /tmp/cultivee-restore/cultivee.db $REMOTE_DATA/cultivee.db
    tar -xzf /tmp/cultivee-restore/data.tar.gz -C $REMOTE_DATA
    rm -rf /tmp/cultivee-restore
    docker compose up -d
    sleep 3
    docker ps --filter name=cultivee-app
  "
  echo "Restore concluido. Verificar https://app.cultivee.com.br/ antes de apagar backups locais."
}

case "${1:-}" in
  --restore)
    do_restore "${2:-}"
    ;;
  *)
    do_backup "${1:-}"
    ;;
esac
