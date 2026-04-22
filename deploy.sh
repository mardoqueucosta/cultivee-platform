#!/bin/bash
# Deploy cultivee-platform (servidor IoT) para VPS
# Uso: bash deploy.sh

set -e

VPS_HOST="129.121.50.168"
VPS_PORT="22022"
VPS_USER="root"
SSH_KEY="D:/01-projetos-claude/.credentials/id_rsa"
REMOTE_DIR="/opt/sites/cultivee-platform"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

SSH_CMD="ssh -i $SSH_KEY -p $VPS_PORT $VPS_USER@$VPS_HOST"
SCP_CMD="scp -i $SSH_KEY -P $VPS_PORT"

echo "=== Deploy cultivee-platform ==="

# Garantir diretorio remoto
$SSH_CMD "mkdir -p $REMOTE_DIR"

# Enviar docker-compose.yml (fonte da verdade)
echo "-> Enviando docker-compose.yml..."
$SCP_CMD "$PROJECT_DIR/docker-compose.yml" "$VPS_USER@$VPS_HOST:$REMOTE_DIR/docker-compose.yml"

# Empacotar server/ (excluindo dados e cache)
# v4.1.17: estrutura em camadas — pacotes models/ + hardware/ + usuario/ + admin/
# substituem os antigos models.py e bp_*.py flat.
echo "-> Empacotando server/..."
cd "$PROJECT_DIR"
tar czf /tmp/cultivee-platform.tar.gz \
    --exclude='*.db' \
    --exclude='data/' \
    --exclude='__pycache__/' \
    --exclude='.env' \
    server/app.py server/config.py server/notifications.py \
    server/models/ \
    server/hardware/ server/usuario/ server/admin/ server/public/ \
    server/requirements.txt server/Dockerfile \
    server/static/ server/templates/ 2>/dev/null

echo "-> Enviando para VPS..."
$SCP_CMD /tmp/cultivee-platform.tar.gz "$VPS_USER@$VPS_HOST:/tmp/"
$SSH_CMD "cd $REMOTE_DIR && tar xzf /tmp/cultivee-platform.tar.gz && rm /tmp/cultivee-platform.tar.gz"

# Parar containers antigos e rebuild
echo "-> Reconstruindo container..."
$SSH_CMD "cd $REMOTE_DIR && docker compose down --remove-orphans 2>/dev/null; docker rm -f \$(docker ps -aq --filter name=cultivee-app) 2>/dev/null; docker compose build --no-cache && docker compose up -d"

# Verificar saude
echo "-> Verificando saude..."
sleep 3
$SSH_CMD "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep cultivee-app"

echo ""
echo "=== Deploy concluido! ==="
