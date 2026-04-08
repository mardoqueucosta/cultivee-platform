# Cultivee - Plataforma IoT Modular

## REGRAS OBRIGATORIAS

### Sincronizacao Offline/Online
Toda alteracao na interface DEVE ser feita nas DUAS versoes simultaneamente:
- **Online**: `server/static/app.js`, `server/static/style.css`, `server/templates/index.html`
- **Offline**: `firmware/mod_hidro.h` (`hidro_dashboard_html/js`), `firmware/mod_cam.h` (`cam_dashboard_html/js`)

Se nao for possivel replicar exatamente (limitacao do ESP32), documentar a diferenca e o motivo.

### Registry Pattern
Toda funcionalidade de modulo DEVE ser registrada no `moduleRenderers` em `app.js`.
Nunca hardcodar logica de modulo especifico fora do registry.

---

## Visao Geral

Plataforma IoT para cultivo inteligente. Arquitetura modular:
- **1 firmware** com compilacao condicional (`#ifdef`) por produto
- **1 servidor Flask** unificado que serve todos os tipos de modulo
- **1 PWA** com registry pattern — UI renderizada por capabilities do hardware
- **1 dominio principal**: `app.cultivee.com.br`

Hardware especializado: cada ESP32 faz uma coisa so.
Composicao por software: o app mostra os modulos que o usuario adicionar.

## Estrutura do Projeto

```
cultivee/
├── firmware/                 # UM firmware, multiplos produtos
│   ├── firmware.ino          # setup() + loop() — orquestrador modular
│   ├── config.h              # Selecao de produto + ambiente (local/prod)
│   ├── core_wifi.h           # WiFi AP+STA, captive portal (204 Android, Success iOS)
│   ├── core_server.h         # WebServer, CORS, rotas setup WiFi, save WiFi
│   ├── core_register.h       # Registro no servidor, polling, command dispatch
│   ├── mod_hidro.h           # Reles, fases, automacao, dashboard local
│   └── mod_cam.h             # Camera OV2640: capture, stream MJPEG, dashboard local
│
├── products/                 # 1 arquivo = 1 produto (define modulos + pinos)
│   ├── hidro.h               # MOD_HIDRO — ESP32-WROOM, GPIO 4/5, reles
│   └── cam.h                 # MOD_CAM — ESP32-WROVER, camera standalone
│
├── server/                   # UM servidor Flask unificado
│   ├── app.py                # Core: auth, modules, PWA, blueprints em multiplos prefixos
│   ├── models.py             # SQLite (users, modules, commands, tokens, groups)
│   ├── config.py             # PORT, DB_PATH, PRODUCT_NAME
│   ├── bp_hidro.py           # Blueprint: status, relay, phases (valida capability hidro)
│   ├── bp_cam.py             # Blueprint: capture, upload, live (valida capability cam)
│   ├── templates/index.html  # PWA template (config injetada)
│   ├── static/app.js         # PWA v3.0 — registry pattern, lista modulos
│   ├── static/style.css      # Dark theme responsivo
│   ├── sim_esp32.py          # Simulador de hardware (ctrl, cam, hidro-cam)
│   ├── run-app.py            # Dev server local (porta 5002)
│   ├── Dockerfile
│   └── requirements.txt
│
├── site/                     # cultivee.com.br — Landing page (React + Nginx)
├── docker-compose.yml        # FONTE DA VERDADE — 2 containers (site + app)
├── deploy.sh                 # Deploy automatizado para VPS
├── PRD-Cultivee.md           # FONTE DA VERDADE — Product Requirements Document
└── CLAUDE.md                 # ESTE ARQUIVO
```

---

## Arquitetura

### Firmware: Compilacao condicional
```
config.h → inclui products/cam.h (ou hidro.h, hidro-cam.h)
         → define MOD_CAM e/ou MOD_HIDRO
         → firmware.ino usa #ifdef para ativar modulos
```

Cada modulo implementa: `*_setup()`, `*_loop()`, `*_register_routes()`, `*_process_command()`, `*_status_json()`, `*_dashboard_html()`, `*_dashboard_js()`.

### Servidor: Blueprints em multiplos prefixos
```python
# 1 servidor, todos os prefixos (firmware constroi URL com MODULE_TYPE)
app.register_blueprint(hidro_bp, url_prefix="/api/ctrl", name="hidro_ctrl")
app.register_blueprint(hidro_bp, url_prefix="/api/hidro-cam", name="hidro_hcam")
app.register_blueprint(cam_bp, url_prefix="/api/cam", name="cam_standalone")
app.register_blueprint(cam_bp, url_prefix="/api/hidro-cam", name="cam_hcam")
```

Validacao por capability: blueprint hidro rejeita modulo sem capability "hidro" (e vice-versa).

### PWA: Registry Pattern
```javascript
const moduleRenderers = {
    hidro: { label: 'Controle', renderContent: renderModule_hidro, getStatusText: ... },
    cam:   { label: 'Camera',   renderContent: renderModule_cam,   getStatusText: ... },
};
```

Capability nao registrada → mostra "Modulo sem interface configurada".

### Comunicacao ESP32 → Servidor
```
ESP32 boot → connectWiFi → registerOnServer (POST /api/modules/register)
          → envia: chip_id, type, capabilities, ctrl_data, IP
          → recebe: commands[], poll_interval
          → loop: pollCommands + registerOnServer a cada poll_interval
```

### Fluxo do usuario
```
1. Liga ESP32 → cria rede AP (ex: Cultivee-Cam)
2. Conecta no AP → portal configura WiFi
3. ESP32 reinicia → conecta WiFi → registra no servidor
4. Abre app.cultivee.com.br → login → "Adicionar Modulo" → codigo
5. Modulo aparece na lista com checkbox
6. Seleciona → conteudo do modulo aparece (fases/reles ou camera)
```

---

## Produtos

### HIDRO (ESP32-WROOM-32D)
- **Porta:** COM7
- **Board:** esp32:esp32:esp32doit-devkit-v1
- **Flash:** 90%
- **Reles:** GPIO4 (Luz), GPIO5 (Bomba) — ativos em LOW
- **AP:** Cultivee-Hidro
- **SERVER_URL prod:** `http://hidro.cultivee.com.br`
- **APP_URL prod:** `https://hidro.cultivee.com.br`

### CAM (ESP32-WROVER-DEV) — Standalone
- **Porta:** COM9
- **Board:** esp32:esp32:esp32wroverkit
- **Flash:** 94%
- **Camera:** OV2640, VGA 640x480, JPEG quality 12, 2 frame buffers (PSRAM)
- **AP:** Cultivee-Cam
- **SERVER_URL prod:** `http://cam.cultivee.com.br`
- **APP_URL prod:** `https://cam.cultivee.com.br`

### Compilar e gravar
```bash
# 1. Editar config.h — selecionar produto e ambiente
# 2. Compilar
"C:/Users/user/arduino-cli/arduino-cli.exe" compile --fqbn esp32:esp32:esp32doit-devkit-v1 "D:/01-projetos-claude/cultivee/firmware"   # WROOM
"C:/Users/user/arduino-cli/arduino-cli.exe" compile --fqbn esp32:esp32:esp32wroverkit "D:/01-projetos-claude/cultivee/firmware"        # WROVER

# 3. Gravar
"C:/Users/user/arduino-cli/arduino-cli.exe" upload --fqbn esp32:esp32:esp32doit-devkit-v1 -p COM7 "D:/01-projetos-claude/cultivee/firmware"  # WROOM
"C:/Users/user/arduino-cli/arduino-cli.exe" upload --fqbn esp32:esp32:esp32wroverkit -p COM9 "D:/01-projetos-claude/cultivee/firmware"       # WROVER
```

---

## Firmware: Detalhes

### Ambiente (config.h)
```c
// #define ENV_LOCAL        // http://192.168.7.233:5002
#define ENV_PRODUCTION      // http://cam.cultivee.com.br (ou hidro, hidro-cam)
```

Cada produto define dois URLs:
- `SERVER_URL` — onde o ESP32 envia dados (HTTP, sem SSL)
- `APP_URL` — onde o usuario abre o app (HTTPS em prod, HTTP em local)

### Captive Portal
- **Android:** `/generate_204`, `/gen_204`, `/generate204` → HTTP 204 (faz Android confiar no WiFi e nao priorizar 4G)
- **iOS:** `/hotspot-detect.html` → responde "Success" (mesmo efeito)
- **Windows:** `/connecttest.txt` → 302 redirect

### Stream local protegido
Flag `localStreamActive` suspende `registerOnServer()` e `pollCommands()` durante stream MJPEG local, evitando que timeouts HTTP congelem o stream.

---

## Servidor: API

### Autenticacao
| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/api/auth/register` | POST | Criar conta {name, email, password} |
| `/api/auth/login` | POST | Login {email, password} → {token, user} |
| `/api/auth/me` | GET | Info do usuario (requer token) |
| `/api/auth/logout` | POST | Invalidar token |

### Modulos
| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/api/modules/register` | POST | ESP32 se registra (chip_id, type, capabilities) |
| `/api/modules/poll` | GET | ESP32 busca comandos pendentes |
| `/api/modules/pair` | POST | Vincular modulo ao usuario (short_id, name) |
| `/api/modules/unpair` | POST | Desvincular modulo |
| `/api/modules` | GET | Listar modulos do usuario |

### Hidro (prefixos: `/api/ctrl`, `/api/hidro-cam`)
| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/<chip_id>/status` | GET | Status (light, pump, mode, phases) |
| `/<chip_id>/relay` | GET | Controle rele (?device=light&action=toggle) |
| `/<chip_id>/phases` | GET | Fases (?live=1 para proxy ESP32) |
| `/<chip_id>/save-config` | POST | Salvar config fases |
| `/<chip_id>/add-phase` | GET | Adicionar fase |
| `/<chip_id>/remove-phase` | GET | Remover fase (?idx=N) |
| `/<chip_id>/reset-phases` | GET | Restaurar fases default |
| `/<chip_id>/reset-wifi` | GET | Reset WiFi do ESP32 |

### Camera (prefixos: `/api/cam`, `/api/hidro-cam`)
| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/<chip_id>/capture` | GET | Enfileira captura |
| `/<chip_id>/upload-capture` | POST | ESP32 envia foto (sem auth, valida capability) |
| `/<chip_id>/image/<file>` | GET | Serve imagem (requer token) |
| `/<chip_id>/start-live` | GET | Inicia live mode |
| `/<chip_id>/stop-live` | GET | Para live mode |
| `/<chip_id>/live-frame` | GET/POST | GET: PWA poll frame, POST: ESP32 push frame |
| `/<chip_id>/last-capture` | GET | URL da ultima captura |

---

## PWA (app.js v3.0)

### Funcionalidades
- Lista de modulos com checkbox (seleciona quais mostrar)
- Setas ↑↓ para reordenar (salvo no localStorage)
- `[+ Adicionar Modulo]` → wizard de pareamento
- Conteudo renderizado por capabilities via registry
- Long press → desvincular modulo
- Login/registro, tela offline, PWA install/update
- Migracao automatica de token (prefix antigo → novo)

### Registry Pattern
Para adicionar novo tipo de modulo:
```javascript
moduleRenderers.sensor = {
    label: 'Sensor',
    renderContent: renderModule_sensor,
    getStatusText: (data) => data ? `${data.ph} pH` : 'Offline'
};
```

### Versionamento
- `APP_VERSION` em `app.js` (linha 6)
- `sw.js` e `manifest.json` gerados dinamicamente em `app.py`
- Incrementar versao ao fazer deploy com mudancas visuais

---

## Infraestrutura

### VPS
- **IP:** 129.121.50.168
- **SSH:** `ssh -i "D:/01-projetos-claude/.credentials/id_rsa" -p 22022 root@129.121.50.168`
- **SO:** Ubuntu 24.04
- **Stack:** Docker + Traefik + Let's Encrypt

### Containers
| Container | Servico | Porta | Dominios |
|-----------|---------|-------|----------|
| cultivee-site | Landing page (Nginx) | 80 | cultivee.com.br, www.cultivee.com.br |
| cultivee-app | Servidor unificado (Flask/Gunicorn) | 5002 | app.cultivee.com.br, hidro.cultivee.com.br, cam.cultivee.com.br |

### Deploy
```bash
bash deploy.sh app        # servidor
bash deploy.sh site       # landing page
bash deploy.sh all        # tudo
```

### DNS (Cloudflare)
- **Conta:** mardo.abc@gmail.com
- cultivee.com.br → proxied
- app.cultivee.com.br → DNS only
- hidro.cultivee.com.br → DNS only (alias retrocompat)
- cam.cultivee.com.br → DNS only

### Desenvolvimento local
```bash
cd server/

# Servidor unificado
python run-app.py                   # porta 5002

# Simuladores (em terminais separados)
python -u sim_esp32.py ctrl         # codigo: SC01
python -u sim_esp32.py cam          # codigo: CA01
```

---

## Checklist

### Alterar firmware
1. Editar `config.h` (produto + ambiente)
2. Compilar + gravar no board correspondente
3. Se mudou API: atualizar servidor junto

### Alterar servidor/app
1. `bash deploy.sh app`
2. Incrementar `APP_VERSION` em `app.js` se mudou UI
3. Testar no celular
4. **Se mudou UI: atualizar versao offline no firmware tambem**

### Alterar docker-compose.yml
1. Editar no REPOSITORIO (nunca no servidor)
2. `bash deploy.sh` envia automaticamente

---

## Adicionar Novo Modulo

Exemplo: modulo "sensor":

### Firmware (3 arquivos)
1. `firmware/mod_sensor.h` — `sensor_setup()`, `sensor_loop()`, `sensor_register_routes()`, `sensor_dashboard_html()`, `sensor_dashboard_js()`, `sensor_process_command()`, `sensor_status_json()`, `sensor_register_json()`
2. `products/sensor.h` — `#define MOD_SENSOR`, MODULE_TYPE, pinos, SERVER_URL, APP_URL
3. `firmware/firmware.ino` — adicionar `#ifdef MOD_SENSOR` nos pontos de integracao

### Servidor (2 arquivos)
4. `server/bp_sensor.py` — Flask Blueprint com rotas do sensor (valida capability "sensor")
5. `server/app.py` — registrar blueprint: `app.register_blueprint(sensor_bp, url_prefix="/api/sensor", name="sensor")`

### PWA (1 registro)
6. `server/static/app.js` — adicionar no registry:
```javascript
moduleRenderers.sensor = {
    label: 'Sensor',
    renderContent: renderModule_sensor,
    getStatusText: (data) => ...
};
function renderModule_sensor(container, mod) { ... }
```

### Infra (2 configs)
7. DNS: `sensor.cultivee.com.br` → DNS only no Cloudflare
8. `docker-compose.yml`: adicionar subdominio nos labels do Traefik

**Total: ~4 arquivos novos, ~15 linhas em existentes.**

---

## Informacoes do Desenvolvedor
- **Git:** Mardoqueu Costa (mardo.abc@gmail.com)
- **Arduino CLI:** `C:/Users/user/arduino-cli/arduino-cli.exe`
- **WiFi teste:** Mardo-Dri / mardodri1609
