# Cultivee - Guia de Operacao

Resumo operacional rapido pra quem tira suporte, cuida da infra e responde em
horas criticas. Complementa o CLAUDE.md (convencoes tecnicas) e o PRD (escopo).

## 1. Monitoramento externo (Uptime Robot)

Grafana/Prometheus-interno vem depois. Pra v4.1.26 basta um **ping externo
gratuito** que alerta via email quando o site cai.

### Setup no Uptime Robot (free, 50 monitors)

1. Criar conta: <https://uptimerobot.com/signUp> (usar `contato@cultivee.com.br`)
2. **Add New Monitor**:
   - Type: `HTTPS`
   - Friendly Name: `Cultivee App`
   - URL: `https://app.cultivee.com.br/`
   - Monitoring Interval: `5 minutes` (free tier)
   - Keyword Monitoring (opcional): keyword `Cultivee` — falha se desaparecer
3. **Alert Contacts** → adicionar pelo menos:
   - Email do(s) admin(s)
   - Opcional: SMS/Telegram (Telegram free, SMS cobra)
4. Ligar monitor — recebe notificacao em <5min de queda.

Monitores sugeridos (todos HTTPS/GET):

| Monitor              | URL                                         | Keyword   |
|----------------------|---------------------------------------------|-----------|
| App Cultivee         | `https://app.cultivee.com.br/`              | `Cultivee`|
| Landing Cultivee     | `https://cultivee.com.br/`                  | `Cultivee`|
| Health API           | `https://app.cultivee.com.br/api/auth/me`   | (403 e OK — significa endpoint vivo) |

### Status page publica (opcional, v4.2)

Uptime Robot tem status page gratuita: `https://stats.uptimerobot.com/<id>`
— pode expor como `https://status.cultivee.com.br` (CNAME no Cloudflare)
pra clientes checarem antes de abrir ticket.

## 2. Backup

Script: [`backup-vps.sh`](../backup-vps.sh)

### Backup on-demand
```bash
bash backup-vps.sh                 # salva em ./backups/YYYYMMDD-HHMMSS/
bash backup-vps.sh /d/backups/ok   # salva em destino custom
```

O dump contem:
- `cultivee.db` — copia online via `sqlite3 .backup` (safe com WAL ativo)
- `data.tar.gz` — `captures/`, `thumbs/`, `live/`, `firmware/` da VPS
- `manifest.txt` — SHA-256 dos dois arquivos + timestamp + APP_VERSION

### Backup agendado (cron na maquina local)

O backup roda da maquina que tem a chave SSH. Opcao simples: Task Scheduler
do Windows rodando `bash backup-vps.sh` toda noite. Verificar o arquivo
criado no dia seguinte.

### Restore

Destrutivo — sobrescreve o banco e os dados da VPS:
```bash
bash backup-vps.sh --restore ./backups/20260421-030000
```
O script pede confirmacao (`RESTORE` literal) antes de aplicar. Para a VPS,
tira backup do banco atual (`cultivee.db.pre-restore.<epoch>`), aplica o
dump, sobe de volta.

**Dry-run de restore (mensal, recomendado):** restaurar num ambiente de teste
separado pra validar que o dump funciona. Um backup que voce nunca testou
restaurar nao e um backup.

## 3. Rotacao de secrets

Checklist trimestral (ou apos suspeita de vazamento):

| Secret                    | Onde vive                                 | Como rotacionar |
|---------------------------|-------------------------------------------|-----------------|
| SSH key da VPS            | `~/.ssh` local + `~/.ssh/authorized_keys` na VPS | Gera novo par, sobe pubkey, remove pubkey antiga. **Testar login com novo antes de remover o antigo.** |
| VAPID (Web Push)          | `.env` na VPS                             | `python -m pywebpush.generate_keys` local, atualiza `.env`, `docker compose up -d`. Usuarios precisam re-subscribe. |
| SMTP password (HostGator) | `.env` na VPS                             | Troca no painel HostGator, atualiza `.env`, reinicia container. |
| Turnstile (Cloudflare)    | `.env` na VPS                             | Gera novo site/secret key no dashboard Cloudflare, atualiza `.env`. |
| GitHub Actions SSH        | Repo Secrets → `VPS_SSH_KEY`              | Igual SSH key da VPS. |

**Nunca commitar** secret. Se um secret vazar no git, rotacionar imediatamente —
remover do repo nao apaga do historico. GitGuardian detecta VAPID/keys comuns.

## 4. Alertas internos do sistema (operacional)

Ja implementados, so pra referencia:
- **Push PWA + email** pra nivel baixo do reservatorio (hidro-farm) — `notifications.py` > `AlertManager`.
- **`min_free_heap` no register** (v4.1.26) — reporta menor heap observado do ESP32. Se cair abaixo de 5kB, firmware reinicia preventivamente.
- **Audit log admin** — todas as acoes administrativas viram linha em `audit_log`.

Ainda **nao** existe:
- Alerta quando um ESP32 para de reportar (`last_seen` > 10min) — seria util.
- Alerta quando SMTP falha — hoje so loga.
- Alerta quando VPS CPU/RAM passa 80%.
- Sentry/Datadog pra erros Python.

## 5. Suporte ao usuario (v4.1.26, mvp)

Canal unico: **`contato@cultivee.com.br`**. Inbox monitorada manualmente.

SLA sugerido pra publicar no site:
- Primeira resposta: **1 dia util** (seg-sex 9-18h BRT).
- Resolucao tecnica: **3 dias uteis** pra casos simples, maiores discutidos
  com o cliente.
- Incidente critico (plataforma fora do ar): **4 horas** de diagnostico inicial.

Planejado pra v4.2: sistema de tickets (pode ser uma inbox dedicada com
labels no Gmail, ou Help Scout/Front gratuito ate 50 conversas/mes).

## 6. Checklist de incidente "sistema fora do ar"

1. Abrir <https://app.cultivee.com.br/> — confirmar que cai.
2. Checar Uptime Robot — hora exata da queda.
3. SSH na VPS (**unica sessao**, respeitar fail2ban):
   ```bash
   ssh -i "D:/01-projetos-claude/.credentials/id_rsa" -p 22022 root@129.121.50.168 \
     "docker ps --filter name=cultivee-app && docker logs cultivee-app --tail 100 && df -h / && free -m"
   ```
4. Classificar:
   - Container caiu? `docker compose up -d`
   - Disco cheio? Ver `/var/lib/docker/volumes/...`, limpar captures antigas.
   - RAM cheia? Reboot da VPS (`reboot`). ESP32s reconectam sozinhos.
   - DB corrompido? Restore do ultimo backup (`backup-vps.sh --restore ...`).
5. Mensagem pro cliente (se ha um chamado aberto): status + ETA.
6. Pos-mortem (breve, <1h) — o que deu errado, o que evita repetir.

## 7. Deploy

Tres caminhos:

| Metodo                  | Quando usar                                  |
|-------------------------|----------------------------------------------|
| `git push origin main`  | Mudanca em `server/`, `docker-compose.yml`, workflows — CI/CD cuida |
| `bash deploy.sh`        | Fallback se GitHub Actions estiver lento/fora. Tudo numa sessao SSH. |
| `bash ota-remote.sh`    | Firmware — requer firmware >=v4.0.15 ja no ESP32. SHA-256 validado em v4.1.26+. |

Antes de gravar firmware em produto:
```bash
bash sync-version.sh --write   # alinha FIRMWARE_VERSION com APP_VERSION
bash compile-hidrofarm.sh      # ou compile.sh / compile-cam.sh
bash ota-remote.sh <chip_id> build/firmware.ino.bin <token>
```
