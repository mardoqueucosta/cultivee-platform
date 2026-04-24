# cultivee-platform

Plataforma IoT para cultivo inteligente — **um único firmware modular em ESP32**, **um servidor Flask unificado** e **uma PWA** com pareamento por código de 4 caracteres. Cada hardware faz uma coisa só (controle hidropônico, controle hidropônico premium com reservatório, ou câmera) e a UI do app monta a interface dinamicamente em runtime a partir das `capabilities` que o módulo reporta ao se registrar.

Produção: <https://app.cultivee.com.br> · Versão atual: **v4.1.28** ([changelog completo no CLAUDE.md](./CLAUDE.md#changelog))

> Se você é um agente de código (Claude Code, Copilot, etc.), leia também [`CLAUDE.md`](./CLAUDE.md) — traz as regras operacionais, arquitetura em 3 camadas, fluxo de deploy, convenções do servidor + firmware + PWA e a lista completa de gotchas do ESP32, da câmera, do SSH/`fail2ban` da VPS e da migração `ctrl→hidro` em curso.

## O que é

Três componentes que conversam entre si:

- **Firmware** (`firmware/` + `products/`) — um único projeto Arduino em C++ com **compilação condicional** por produto. A seleção do produto ativo fica em [`firmware/config.h`](./firmware/config.h) (descomenta um dos `#include "../products/*.h"`). Os módulos (`mod_hidro.h`, `mod_hidrofarm.h`, `mod_cam.h`) são ativados pelos `#define MOD_*` do produto. Inclui WiFi AP+STA com captive portal multi-SO (Android/iOS/Windows), dashboard HTML embutido para operação offline, OTA local via `/update` e **OTA remoto via servidor** com validação SHA-256 (v4.1.26+) e rollback A/B automático em caso de boot ruim.
- **Servidor** (`server/`) — Flask 3.1 + Gunicorn em um único container Docker atrás de Traefik. Organizado em **3 camadas** (v4.1.17+): `server/usuario/` (auth, perfil, 2FA, LGPD), `server/admin/` (painel admin, impersonation, audit log, OTA admin) e `server/hardware/` (blueprints por capability). Banco SQLite em volume persistente com WAL e migrações idempotentes no boot.
- **PWA** (`server/static/` + `server/templates/`) — frontend em JavaScript vanilla (`app.js`, `gallery.js`, `style.css`) com Service Worker e manifest gerados dinamicamente pelo `app.py` a partir de `APP_VERSION` em [`server/config.py`](./server/config.py) — **fonte única da versão**. Dark theme responsivo, push notifications, instalável, registry pattern para renderização por capability.

### Três produtos hoje

| Produto | Hardware | Capability | Pinos / sensores extras |
|---|---|---|---|
| **HIDRO** ([`products/hidro.h`](./products/hidro.h)) | ESP32-WROOM-32D + módulo relé 4 canais + RTC DS3231 | `hidro` | 4 relés (luz, bomba, ventilação, aeração), RTC I2C |
| **HIDRO-FARM** (Premium) ([`products/hidro-farm.h`](./products/hidro-farm.h)) | ESP32-WROOM-32D + 6 relés + 2 boias reed-switch + DHT11 | `hidro-farm` | 4 relés automatizados + válvula entrada + bomba de homogeneização, reposição automática de água, sensor temp/umidade |
| **CAM** ([`products/cam.h`](./products/cam.h)) | ESP32-WROVER-DEV + câmera OV2640 always-on | `cam` | Captura agendada, live MJPEG/push frames, 11 parâmetros sensor ajustáveis via PWA |

A landing page institucional (pitch, blog, cursos) vive no subprojeto irmão [`../Site/`](../Site/) e é hospedada separadamente em `cultivee.com.br`.

## Stack

### Firmware
- **Framework:** Arduino core para ESP32 (`esp32:esp32` via [`arduino-cli`](https://github.com/arduino/arduino-cli))
- **Bibliotecas:** `WiFi`, `WebServer`, `DNSServer`, `HTTPClient`, `ESPmDNS`, `Preferences`, `Update`, `mbedtls/sha256`, `esp_ota_ops`, `esp_camera` (só em `MOD_CAM`)
- **Arquitetura modular:** `core_wifi.h`, `core_server.h`, `core_register.h`, `core_ota.h` (sempre ativos) + `mod_hidro.h` / `mod_hidrofarm.h` / `mod_cam.h` (ativados por `#ifdef`)
- **Partições:** `min_spiffs` em todos os produtos desde v4.1.8 (1.9MB app0 + 1.9MB app1 OTA — ~63% ocupado)
- **Hardening (v4.1.26):** brownout detector nível 4, telemetria + protecao de heap (`min_free_heap`), timeout de 30min em MODE_SETUP, SHA-256 validado no OTA, rollback A/B manual via NVS

### Servidor
- **Linguagem:** Python 3.10 (imagem base `python:3.10-slim`)
- **Framework:** Flask 3.1 + Gunicorn 23 (2 workers × 4 threads)
- **Banco:** SQLite em `data/cultivee.db` com `PRAGMA journal_mode=WAL` e `foreign_keys=ON`. Schema: `users`, `modules`, `tokens`, `password_reset_tokens`, `pending_commands`, `groups`, `push_subscriptions`, `alert_log`, `audit_log`. Migrações idempotentes no `init_db`.
- **Auth:** bcrypt rounds=12 (v4.1.26 — migração transparente do SHA-256 legado no primeiro login). Tokens de sessão de 30 dias. **2FA TOTP** opcional (`pyotp`). Rate limiting por IP. Anti-enumeration em `/forgot-password`.
- **Observabilidade:** logs estruturados, audit log persistido (impersonation, mudanças de role, transferências de módulo, uploads de firmware).
- **Notificações:** push web (`pywebpush` + VAPID) + email SMTP SSL (HostGator). AlertManager monitora reservatório e dispara após `alert_threshold_min` minutos com cooldown de 1h.
- **Imagens:** Pillow 11 para gerar thumbnails 200×150.
- **Env:** `python-dotenv` 1.1.

### PWA
- **JavaScript vanilla:** `app.js` (registry pattern, login, lista de módulos, wizards, modais admin/firmware/role/impersonate, 2FA setup, sessões), `gallery.js` (galeria modal com pastas)
- **CSS:** `style.css` — dark theme responsivo (verde Cultivee `#27ae60`, layout até 3 colunas no desktop)
- **Service Worker + manifest:** gerados dinamicamente em `app.py` com cache busting por `APP_VERSION`. Push handler + notificationclick.
- **Security headers (v4.1.23):** HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, ProxyFix do Werkzeug.
- **LGPD (v4.1.20):** export, delete cascade (incluindo arquivos de captures/thumbs), consentimento, páginas `/termos` e `/privacidade`.

### Runtime VPS
- Docker Compose + Traefik + Let's Encrypt. Imagem buildada a partir de `server/Dockerfile`. Volume externo `cultivee_cultivee-data` persiste o DB e as imagens. Duas entradas Traefik no mesmo container: `websecure` (HTTPS para PWA) e `web` (HTTP puro, **sem redirect**, para os ESP32s que não fazem TLS).

## Requisitos

- **Para o servidor (dev local):** Python 3.10+, `pip`, opcionalmente Docker 24+ se quiser rodar o container
- **Para o firmware:** [arduino-cli](https://github.com/arduino/arduino-cli) instalado em `C:/Users/user/arduino-cli/arduino-cli.exe` (caminho hardcoded nos `compile*.sh`) e o core `esp32:esp32` instalado (`arduino-cli core install esp32:esp32`)
- **Hardware de teste:**
  - Hidro: ESP32-WROOM-32D em COM7 + módulo relé 4 canais + DS3231
  - Hidro-Farm: ESP32-WROOM-32D em COM16 + módulo relé 6 canais + 2 boias + DHT11 + DS3231
  - Cam: ESP32-WROVER-DEV em COM7 (ou outra) + câmera OV2640
- **Para deploy:** acesso SSH à VPS da Cultivee (`129.121.50.168:22022`) com a chave em `D:/01-projetos-claude/.credentials/id_rsa`

## Instalação

```bash
git clone https://github.com/mardoqueucosta/cultivee-platform.git
cd cultivee-platform

# Servidor
cd server
python -m venv venv
source venv/bin/activate       # Linux/Mac
# ou: venv\Scripts\activate    # Windows
pip install -r requirements.txt
cp .env.example .env           # opcional — defaults funcionam para dev
```

O firmware **não** precisa de `npm install` nem `pip install` — basta o arduino-cli com o core `esp32:esp32` instalado.

## Uso

### Servidor em dev local

```bash
cd server
python run-app.py              # http://localhost:5002
```

Alternativa: `python run-hidro.py` — servidor dedicado para testes do produto Hidro (`MODULE_TYPE=hidro`, DB separado em `data/cultivee-hidro.db`).

### Simulador de ESP32 (sem hardware)

```bash
cd server
python -u sim_esp32.py hidro       # simulador Hidro      — código de pareamento: SH01
python -u sim_esp32.py hidro-farm  # simulador Hidro-Farm — código de pareamento: HF01
python -u sim_esp32.py cam         # simulador Cam        — código de pareamento: CA01
```

O simulador fala HTTP com o servidor local (registra, recebe comandos, envia status) — bom para desenvolver o PWA sem mexer no hardware. Aceita `ctrl` como alias deprecated de `hidro`.

### Compilar e gravar firmware

Antes de tudo, ajustar [`firmware/config.h`](./firmware/config.h):

1. Escolher ambiente: `ENV_LOCAL` (aponta para `LOCAL_SERVER_IP`) ou `ENV_PRODUCTION` (aponta para `app.cultivee.com.br`)
2. Escolher produto: descomentar UM de `#include "../products/hidro.h"`, `"../products/hidro-farm.h"` ou `"../products/cam.h"`

Depois, sincronizar a versão do firmware com `APP_VERSION` (recomendado antes de cada build):

```bash
bash sync-version.sh --write   # alinha FIRMWARE_VERSION nos 3 products/*.h
```

E compilar/gravar:

```bash
# HIDRO (ESP32-WROOM, COM7) — partição min_spiffs
bash compile.sh                # só compila → build/firmware.ino.bin
bash compile.sh upload         # compila + grava via USB em COM7

# HIDRO-FARM (ESP32-WROOM, COM16) — partição min_spiffs
bash compile-hidrofarm.sh
bash compile-hidrofarm.sh upload

# CAM (ESP32-WROVER, COM7) — partição min_spiffs (OTA habilitado v4.1.8+)
bash compile-cam.sh
bash compile-cam.sh upload
```

### OTA — três caminhos

1. **OTA remoto via servidor (preferido)** — pelo painel admin (Admin → Módulos → botão **Firmware**) ou via script:
   ```bash
   bash ota-remote.sh <chip_id> build/firmware.ino.bin <token_user>
   ```
   Servidor calcula SHA-256, ESP32 valida antes de aplicar; se hash não bater, firmware atual é preservado. Rollback A/B automático após 3 boots sem self-test.
2. **OTA local** — abrir `http://<ip-do-esp32>/update` no navegador na mesma rede e fazer upload manual do `.bin`.
3. **USB** — `bash compile*.sh upload` (sempre funciona; única opção pra primeira gravação de um ESP32 novo).

### Backup e operação

```bash
bash backup-vps.sh                              # dump SQLite + tarball captures/thumbs/firmware
bash backup-vps.sh --restore ./backups/...      # restaura dump na VPS (destrutivo, pede confirmação)
```

Mais detalhes operacionais (Uptime Robot, rotação de secrets, checklist de incidente) em [`docs/operacao.md`](./docs/operacao.md).

## Estrutura de diretórios

```
cultivee-platform/
├── firmware/                      # 1 projeto Arduino, múltiplos produtos
│   ├── firmware.ino               # setup() + loop() — orquestrador
│   ├── config.h                   # Seletor de produto + ambiente (local/prod)
│   ├── core_wifi.h                # WiFi AP+STA, captive portal + RTC DS3231
│   ├── core_server.h              # WebServer, rotas setup/save WiFi
│   ├── core_register.h            # Register no servidor + polling + OTA remoto + SHA-256 + rollback A/B
│   ├── core_ota.h                 # Rotas /update e /doUpdate (todos os produtos)
│   ├── mod_hidro.h                # MOD_HIDRO — 4 relés, fases, automação, dashboard
│   ├── mod_hidrofarm.h            # MOD_HIDROFARM — 6 relés (4 auto + 2 manuais), boias, DHT11, dashboard
│   └── mod_cam.h                  # MOD_CAM — câmera OV2640: capture, stream, dashboard
│
├── products/                      # 1 arquivo = 1 produto (pinos + URLs + capabilities)
│   ├── hidro.h                    # ESP32-WROOM, 4 relés, RTC, MODULE_TYPE="hidro" (v4.1.28)
│   ├── hidro-farm.h               # ESP32-WROOM, 6 relés (GPIO 4/5/16/17/18/19), boias, DHT11
│   └── cam.h                      # ESP32-WROVER, OV2640, min_spiffs (OTA habilitado v4.1.8+)
│
├── server/                        # Servidor Flask unificado — 3 camadas (v4.1.17+)
│   ├── app.py                     # Core: setup, middleware readonly, registra blueprints, security headers
│   ├── config.py                  # PORT, DB_PATH, APP_VERSION (fonte única da versão)
│   ├── notifications.py           # AlertManager + send_email() (alertas + auth)
│   │
│   ├── models/                    # Camada de dados (pacote desde v4.1.16)
│   │   ├── db.py                  # get_db, init_db, todas as migrações
│   │   ├── users.py               # users + auth + bcrypt + tokens + 2FA + roles + LGPD
│   │   ├── modules.py             # módulos + grupos + captura
│   │   ├── push.py                # push subscriptions + alert_log
│   │   └── audit.py               # audit_log (ações administrativas)
│   │
│   ├── usuario/                   # Camada USUARIO — cliente comum
│   │   ├── auth.py                # /api/auth: register, login, logout, forgot/reset password, verify-email
│   │   └── profile.py             # /api/profile: GET/PUT, troca senha, 2FA, sessões, ViaCEP, export, delete
│   │
│   ├── admin/                     # Camada ADMIN — só role='admin'
│   │   └── admin.py               # /api/admin: stats, users, modules, audit, impersonate, role, transfer, OTA
│   │
│   ├── hardware/                  # Camada HARDWARE — ESP32
│   │   ├── hidro.py               # /api/hidro (+ /api/ctrl alias deprecated v4.1.28) — capability "hidro"
│   │   ├── hidrofarm.py           # /api/hidro-farm — capability "hidro-farm"
│   │   ├── cam.py                 # /api/cam — capability "cam" (path traversal fix v4.1.26)
│   │   └── gallery.py             # /api/gallery — pastas, grid, seleção, exclusão
│   │
│   ├── templates/index.html       # PWA template (config injetada em runtime) + modais
│   ├── templates/terms.html       # Termos de uso (LGPD)
│   ├── templates/privacy.html     # Política de privacidade (LGPD)
│   ├── static/app.js              # PWA — registry pattern, UI principal, todos os modais
│   ├── static/gallery.js          # Galeria modal (pastas, grid, seleção)
│   ├── static/style.css           # Dark theme responsivo (desktop até 3 colunas, mobile 1)
│   ├── sim_esp32.py               # Simulador (hidro, hidro-farm, cam) para dev sem ESP32
│   ├── run-app.py                 # Launcher dev (porta 5002)
│   ├── run-hidro.py               # Launcher alternativo (MODULE_TYPE=hidro, DB separado)
│   ├── test_routes.py             # Smoke tests das rotas HTTP (51 testes)
│   ├── Dockerfile                 # python:3.10-slim + gunicorn
│   ├── requirements.txt           # flask, dotenv, gunicorn, pillow, pywebpush, pyotp, bcrypt
│   └── .env.example               # Template de variáveis (DATA_DIR, DB_PATH, etc.)
│
├── docs/                          # Documentação técnica e operacional
│   ├── api-reference.md           # Referência completa das rotas REST
│   ├── guia-otimizacao-esp32-cam.md  # Otimização da câmera OV2640
│   ├── operacao.md                # Uptime Robot, backup/restore, secrets, incidente
│   ├── manual-usuario.md          # Guia para o cliente final
│   ├── lgpd-aipd.md               # Avaliação de Impacto à Proteção de Dados (draft)
│   ├── termos-uso.md              # Minuta dos Termos de Uso (draft legal)
│   ├── license-gate.md            # Proposta de modelo de monetização (4 opções)
│   └── produtos.md                # Detalhes técnicos dos 3 produtos
│
├── docker-compose.yml             # FONTE DA VERDADE do container VPS (Traefik labels)
├── deploy.sh                      # Deploy manual do servidor para VPS (encadeia tudo numa SSH)
├── compile.sh                     # Compila firmware Hidro (com/sem upload)
├── compile-hidrofarm.sh           # Compila firmware Hidro-Farm
├── compile-cam.sh                 # Compila firmware Cam (min_spiffs, OTA habilitado)
├── ota-remote.sh                  # Envia .bin para OTA remoto (via servidor)
├── sync-version.sh                # Alinha FIRMWARE_VERSION nos 3 products/*.h com APP_VERSION
├── backup-vps.sh                  # Dump + tarball + manifest SHA-256 (modo --restore disponível)
├── .github/workflows/deploy.yml   # Deploy automático em push para main (filtrado por paths)
├── ESP32_SAFE_FLASH_GUIDE.md      # Guia de gravação segura do ESP32 (histórico)
└── CLAUDE.md                      # Instruções operacionais para agentes (também serve de overview)
```

## Scripts disponíveis

| Script | O que faz |
|---|---|
| `bash compile.sh [upload]` | Compila firmware Hidro → `build/firmware.ino.bin`. Com `upload`: grava via USB em COM7 |
| `bash compile-hidrofarm.sh [upload]` | Compila firmware Hidro-Farm. Com `upload`: grava em COM16 |
| `bash compile-cam.sh [upload]` | Compila firmware Cam (min_spiffs OTA). Com `upload`: grava em COM7 |
| `bash sync-version.sh [--write]` | Alinha `FIRMWARE_VERSION` nos 3 `products/*.h` com `APP_VERSION` em `config.py`. Sem `--write` faz dry-run |
| `bash ota-remote.sh <chip_id> <bin> <token>` | Envia firmware ao servidor para OTA remoto (com SHA-256) |
| `bash deploy.sh` | Deploy manual do servidor à VPS (alternativa ao GitHub Actions) |
| `bash backup-vps.sh [destino]` | Dump online do banco (`sqlite3 .backup`) + tarball de imagens + manifest SHA-256 |
| `bash backup-vps.sh --restore <dump>` | Restaura dump na VPS (destrutivo, pede confirmação `RESTORE`) |
| `python server/run-app.py` | Servidor dev unificado na porta 5002 |
| `python server/run-hidro.py` | Servidor dev com `MODULE_TYPE=hidro` e DB separado |
| `python -u server/sim_esp32.py hidro\|hidro-farm\|cam` | Simulador de hardware ESP32 |
| `python server/test_routes.py [hidro] [local\|vps]` | Smoke tests das rotas HTTP (51 testes) |

## Variáveis de ambiente

Template em [`server/.env.example`](./server/.env.example). Defaults funcionam para dev. Em produção, o container recebe os valores via `environment:` no [`docker-compose.yml`](./docker-compose.yml) e do `.env` na VPS (nunca no repo):

| Variável | Default (dev) | Produção (VPS) | Notas |
|---|---|---|---|
| `PORT` | `5002` | `5002` | Porta do Gunicorn |
| `DB_PATH` | `data/cultivee.db` | `/app/data/cultivee.db` | Caminho do SQLite |
| `DATA_DIR` | `./data` | `/app/data` | Base de captures/thumbs/live/firmware |
| `VAPID_PUBLIC_KEY` | — | obrigatório p/ push | Chave pública Web Push (sem isso, push é desativado) |
| `VAPID_PRIVATE_KEY` | — | obrigatório p/ push | Chave privada Web Push |
| `VAPID_CLAIMS_EMAIL` | — | `mailto:...` | Email do remetente VAPID |
| `SMTP_USER` | — | obrigatório p/ alertas/reset | `contato@cultivee.com.br` |
| `SMTP_PASS` | — | obrigatório p/ alertas/reset | Senha SMTP HostGator |
| `TURNSTILE_SITE_KEY` | — | opcional | CAPTCHA Cloudflare (frontend); se ausente, widget não aparece |
| `TURNSTILE_SECRET` | — | opcional | CAPTCHA Cloudflare (backend); se ausente, validação é bypass |

**Nunca commitar `.env` real.** GitGuardian monitora o repo — VAPID keys já vazaram uma vez (v4.1.0) e foram rotacionadas.

## Deploy

Servidor em produção roda na VPS da Cultivee como container Docker `cultivee-app` atrás de Traefik + Let's Encrypt, servindo `app.cultivee.com.br`. Diretório remoto: `/opt/sites/cultivee-platform/`. Volume externo `cultivee_cultivee-data` persiste o DB e as imagens.

### 1. Automático via GitHub Actions (preferido)

Push para `main` dispara [`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml), que filtra por paths: só deploya se algo mudou em `server/**`, `docker-compose.yml` ou `.github/workflows/**`. Alterações **só no firmware** (`firmware/**`, `products/**`) não disparam deploy — o firmware é gravado localmente via USB ou OTA, nunca pela pipeline. Também pode ser disparado manualmente via `workflow_dispatch`.

A action usa `appleboy/ssh-action@v1`, clona `github.com/mardoqueucosta/cultivee-platform.git`, sincroniza no diretório remoto via `rsync`, para o container antigo e roda `docker compose build --no-cache && docker compose up -d`.

### 2. Manual via `deploy.sh` (fallback)

```bash
cd "D:/01-projetos-claude/00-Sites/site-cultivee.com.br/cultivee-platform"
bash deploy.sh
```

Empacota apenas os arquivos necessários (`app.py`, `config.py`, `notifications.py`, pacotes `models/`, `usuario/`, `admin/`, `hardware/`, `requirements.txt`, `Dockerfile`, `static/`, `templates/`) + `docker-compose.yml`, envia via `scp`, para containers antigos e rebuilda. Encadeia tudo numa única sessão SSH (respeita `fail2ban`).

### 3. OTA remoto de firmware

Ver seção **Uso → OTA** acima. Resumo: compila local → `bash ota-remote.sh <chip> <bin> <token>` (ou painel admin) → ESP32 baixa, valida SHA-256, aplica.

### Verificar status / logs

```bash
ssh -p 22022 -i "D:/01-projetos-claude/.credentials/id_rsa" root@129.121.50.168 "docker logs cultivee-app --tail 50"
ssh -p 22022 -i "D:/01-projetos-claude/.credentials/id_rsa" root@129.121.50.168 "docker ps --filter name=cultivee-app"
```

Detalhes de infra, armadilhas de SSH (`fail2ban` ativo), convenções de firmware e gotchas operacionais estão em [`CLAUDE.md`](./CLAUDE.md) e [`docs/operacao.md`](./docs/operacao.md).

## Troubleshooting

**ESP32 não conecta ao WiFi e abre o AP `Cultivee-Hidro` / `Cultivee-HidroFarm` / `Cultivee-Cam`**
Comportamento esperado no primeiro boot ou quando as credenciais são inválidas. Conectar ao AP (senha em branco) e abrir qualquer URL HTTP — o captive portal redireciona para o form de setup. ESP32 salva em `Preferences` (NVS) e reinicia. Para resetar manualmente: segurar BOOT (GPIO0) por 3 segundos. Após 30 minutos sem configurar, o ESP32 cai automaticamente para `MODE_OFFLINE` (v4.1.26).

**`esp_camera_init` falha no boot com erro `0x105`**
Na maioria dos casos é fonte fraca (câmera puxa pico de corrente no init). Usar fonte 5V ≥ 1A. Evitar cabo USB barato. Se continuar, confirmar que o board é `esp32wroverkit` (precisa de PSRAM para `fb_count=2`).

**`docker compose up` falha com `network web not found`**
A rede externa `web` precisa existir na VPS antes do primeiro deploy. Criar com:
```bash
docker network create web
docker volume create cultivee_cultivee-data
```

**PWA em produção continua mostrando versão antiga depois do deploy**
O service worker faz cache busting por `APP_VERSION` em [`server/config.py`](./server/config.py). **Sempre incrementar `APP_VERSION`** ao fazer deploy com mudanças visuais. Sem isso, o SW entrega o cache antigo até invalidar sozinho (horas/dias).

**Hidro retorna 404 em `/api/hidro/<chip>/status` mesmo com módulo pareado**
A validação em `server/hardware/hidro.py` exige que o módulo tenha capability `"hidro"` no campo `capabilities` (array JSON no DB). Módulos antigos podem ter `capabilities=[]` — atualizar o firmware para v4+ e rebootar. A rota `/api/ctrl/*` ainda funciona como alias deprecated desde v4.1.28 — verificar logs do servidor por linhas `[deprecated]` para rastrear quem ainda chama.

**OTA remoto aborta com hash mismatch**
Esperado se o `.bin` foi corrompido em transito (ou trocado entre upload e download). O firmware atual é preservado (não é gravado nada inválido). Reenviar o mesmo `.bin` resolve.

**ESP32 entra em loop de reboot após OTA**
Rollback A/B (v4.1.26) deve disparar automaticamente após 3 boots sem self-test bem-sucedido — o ESP32 troca de partição e volta para a versão anterior. Se isso falhar, gravar via USB.

**Deploy SSH falha com `Permission denied (publickey)` ou host banido**
A chave esperada é `D:/01-projetos-claude/.credentials/id_rsa` (hardcoded em [`deploy.sh`](./deploy.sh)). **Nunca disparar múltiplas conexões SSH em sequência rápida** à VPS — há `fail2ban` ativo e duas ou três tentativas próximas banem o IP por horas. Se banido, só recupera via painel do provedor. O `deploy.sh` e o workflow já encadeiam tudo numa única sessão.

**Login retorna 401 mesmo com senha certa após v4.1.26**
A migração de SHA-256 para bcrypt é **transparente** — acontece no primeiro login bem-sucedido. Se receber 401, conferir email e usar "Esqueci minha senha" para recuperar via email (gera novo hash bcrypt direto). Sem fallback manual necessário.

## Histórico

Três fontes complementares, na ordem do mais público pro mais interno:

- **[`CHANGELOG.md`](./CHANGELOG.md)** — changelog formal por versão (formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)). "O que mudou em cada release." Fonte única pra human-readable.
- **[`docs/sessoes/`](./docs/sessoes/)** — log detalhado por rodada de trabalho (dia/bloco). "Por que foi feito assim, o que foi tentado e descartado, que incidentes rolaram." Contexto rico pra retomar trabalho depois.
- **`git log --oneline`** — fonte técnica. "Quem mudou qual arquivo, quando, com que mensagem." Use quando o changelog/sessões não têm o detalhe que você precisa.

**Convenção pros agentes / devs:** ao fazer uma release significativa, atualizar `CHANGELOG.md` junto com o commit de bump de `APP_VERSION`. Em rodadas longas (várias releases no mesmo dia, decisões arquiteturais, incidentes), criar `docs/sessoes/YYYY-MM-DD.md` para capturar o contexto que não cabe no changelog.

## Licença

© Cultivee — Todos os direitos reservados. Código privado.
