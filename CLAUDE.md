# Cultivee - Plataforma IoT Modular

Contexto publico do projeto (pitch, stack resumida, instalacao, troubleshooting) esta em [`README.md`](./README.md). Este arquivo foca nas instrucoes operacionais para agentes: arquitetura detalhada, convencoes, deploy e regras criticas. O site institucional (landing, blog, cursos, marketing dos produtos) vive no subprojeto irmao [`../Site/`](../Site/) — ver [`../Site/CLAUDE.md`](../Site/CLAUDE.md) para convencoes do frontend institucional.

## REGRAS OBRIGATORIAS

### Sincronizacao Offline/Online
Toda alteracao na interface DEVE ser feita nas DUAS versoes simultaneamente:
- **Online**: `server/static/app.js`, `server/static/style.css`, `server/templates/index.html`
- **Offline**: `firmware/mod_hidro.h` (`hidro_dashboard_html/js`), `firmware/mod_hidrofarm.h` (`hidrofarm_dashboard_html/js`), `firmware/mod_cam.h` (`cam_dashboard_html/js`)

Se nao for possivel replicar exatamente (limitacao do ESP32), documentar a diferenca e o motivo.

### Registry Pattern
Toda funcionalidade de modulo DEVE ser registrada no `moduleRenderers` em `app.js`.
Nunca hardcodar logica de modulo especifico fora do registry.

### Deploy e SSH a VPS
NUNCA disparar multiplas conexoes SSH em sequencia rapida contra a VPS (`129.121.50.168:22022`). A VPS tem `fail2ban` ativo — duas ou tres tentativas proximas banem o IP por horas e so o usuario recupera via painel do provedor. Fazer **uma conexao por vez**, esperar terminar; se precisar de varios comandos, encadear com `&&` numa unica sessao SSH. Nunca rodar SSH em paralelo (Bash em background + foreground contra a mesma VPS). O `deploy.sh` e o workflow do GitHub Actions ja encadeiam tudo numa sessao — usar esses caminhos ao inves de comandos SSH avulsos.

### Container Docker — gotchas operacionais (v4.1.34+)
- **Nome do service no compose** e `app` (nao `cultivee-app` — este e o `container_name`). Comando correto: `docker compose restart app` ou `docker compose up -d --force-recreate app`.
- **`docker compose restart` NAO re-le `env_file`**. As env vars sao capturadas na CRIACAO do container. Apos editar `.env` da VPS, **sempre** usar `docker compose up -d --force-recreate app` (recreate forca releitura do `env_file`). Sintoma do bug: secret novo no `.env` mas endpoint reporta `webhook_disabled` ate recreate.
- **Diagnostico de env vars no container**: NUNCA usar `${VAR:-X}` (vaza o valor da variavel se setada). Usar `${#VAR}` (so length) ou `[ -n "$VAR" ] && echo YES`.

### Compilar firmware pra COM diferente (v4.1.34+)
`compile.sh` aceita `PORT` via env var. Default `COM7` (Hidro). Pra gravar segundo HIDRO em outra porta:
```bash
PORT=COM17 bash compile.sh upload
```
Mesma ideia vale pra `compile-cam.sh` e `compile-hidrofarm.sh` se evoluirem (hoje eles tem porta hardcoded — atualizar quando precisar de segundo Cam ou Farm).

### OTA admin sem token (v4.1.34+ — operacao avancada)
Pra atualizar modulo em campo sem precisar do token de admin do user, SSH single-session enviando `.bin` direto pro volume Docker:
```bash
SHA=$(sha256sum build/firmware.ino.bin | awk '{print $1}')
base64 -w0 build/firmware.ino.bin | ssh ... "
  FW='/var/lib/docker/volumes/cultivee_cultivee-data/_data/firmware'
  base64 -d > \"\$FW/<chip_id>.bin\"
  printf '%s' \"\$SHA\" > \"\$FW/<chip_id>.sha256\"
"
```
Servidor detecta no proximo poll do ESP32 e serve. Anti-loop ja built-in (auto-deleta `.bin` apos download — fix da v4.1.8).

### Background jobs em `server/jobs/` (v4.1.38+)
Threads daemon iniciadas no startup do `app.py`. Cada job e responsavel pelo proprio loop + sleep + tratamento de erros (nao quebra o app se falhar). Iniciado **uma vez por worker do Gunicorn** — pra evitar duplicacao de trabalho, usar lock distribuido no banco (UPDATE atomico).

Exemplo atual:
- `jobs/offline_watcher.py` — verifica modulos offline > threshold (default 15min, v4.1.39) e dispara alerta proativo (push + email). Lock via `models.try_acquire_offline_watcher_lock(min_interval_sec)` na tabela `offline_watcher_state` (singleton id=1).

### Firmware Arduino: `String += String` em JSON grandes (lecao da rodada 2026-04-25, v4.1.47)
Quando montar JSON > 1.5kB com `String +=` em ~30+ lugares, o heap **fragmenta silenciosamente** por reallocacoes. Em Hidro-Farm (3 fases × 18 campos = `phasesJson` ~1.5kB), os ultimos 2 campos do JSON (`min_free_heap`, `firmware_version`) NAO eram adicionados — `String((unsigned long)val)` falhava silenciosamente, `json += ""` nao fazia nada. JSON sintaticamente valido mas truncado.

**Sempre `reserve()` capacity antes do primeiro `+=`** em strings que vao crescer alem de 200 bytes:
```cpp
String json;
json.reserve(3000);  // 1 alocacao, sem realloc/fragmentacao
json += "{";
// ... 30+ +=
```

Bug latente desde v4.1.26, manifestou apenas no Hidro-Farm em v4.1.45-46. Hidro/Cam tinham JSON menor (~1.2kB) e nao fragmentavam o suficiente.

### Refator de simbolo — checklist obrigatorio (lecao da rodada 2026-04-25)
Antes de commitar qualquer rename/refator de constante, classe ou funcao:
```bash
grep -rn "NOME_ANTIGO" server/ firmware/ products/ static/ templates/ | grep -v "\.git"
# Se sobrar — corrigir TODAS antes do commit. Senao, NameError silencioso em runtime.
```
**4 bugs consecutivos na rodada 2026-04-25** seguiram esse padrao. Bug mais grave: `OFFLINE_ALERT_THRESHOLD_MIN` renomeada na v4.1.39 com 2 ocorrencias esquecidas → thread offline_watcher crashou no startup, sistema sem alerta automatico por ~25min.

### `sqlite3.Row` vs `dict` — usar `_row_field()` (lecao reforcada 3x — v4.1.0, v4.1.39, v4.1.53)
Funcoes `models/get_*` retornam tipos DIFERENTES — armadilha clássica:
- `get_user_by_id` -> `sqlite3.Row` (NAO tem `.get()`)
- `get_module_by_chip_id` -> `dict` (tem `.get()`, vem com `return dict(module) if module else None`)
- Outros: variavel — checar antes de usar `.get()`

Usar `request.user.get("role")` quebra com `AttributeError: 'sqlite3.Row' object has no attribute 'get'`. Frontend recebe HTML 500 e tenta parsear como JSON — sintoma `Unexpected token '<', '<!doctype "...`.

**Padrao defensivo (use sempre que tocar `request.user` ou outra Row):**
```python
def _row_field(row, field, default=None):
    """Le campo de sqlite3.Row OU dict. Defensive — Row nao tem .get()."""
    try:
        return row[field]
    except (IndexError, KeyError, TypeError):
        return default

# Em vez de:
is_admin = (request.user.get("role") == "admin")  # CRASHA com Row
# Usar:
is_admin = (_row_field(request.user, "role") == "admin")  # OK pra ambos
```

Helper ja existe em `server/app.py`. **Bug repetiu 3x na historia** (v4.1.0, v4.1.39 latente, v4.1.53) — toda vez que alguem escreve endpoint novo tocando `request.user`. **Quando em duvida**, use `_row_field`.

### `<details>` + estado UI persistente (lecao da rodada 2026-04-26, v4.1.55)
Qualquer estado UI transient (open/closed, scroll, selected tab) sobre componentes dentro de containers re-renderizados a cada poll PRECISA ser persistido em `localStorage`. Mesma raiz do flash visual da v4.1.50, mas pra estado de componente.

`renderDashboard` reescreve `container.innerHTML` a cada poll do ESP32 (~5s) porque `_lastCtrlKey` inclui `temperature/humidity` (DHT11 muda toda leitura). `<details>` recriado = volta pro default (fechado). User clica → abre → 5s depois fecha sozinho.

**Padrao**:
```js
function _isXxxOpen(chipId) {
    try { return localStorage.getItem(`xxx-open-${chipId}`) === '1'; }
    catch(e) { return false; }
}
function _setXxxOpen(chipId, isOpen) {
    try {
        if (isOpen) localStorage.setItem(`xxx-open-${chipId}`, '1');
        else localStorage.removeItem(`xxx-open-${chipId}`);
    } catch(e) {}
}
// No template:
`<details ${_isXxxOpen(chipId) ? 'open' : ''} ontoggle="_setXxxOpen('${chipId}', this.open)">`
```

Chave per-chip — cada modulo tem seu proprio estado.

### Cache write-through em PUTs (lecao da rodada 2026-04-26, v4.1.50)
Caches no frontend (TTL 60s) precisam ser **atualizados imediatamente apos um PUT bem-sucedido**, senao a proxima re-renderizacao usa cache antigo e reverte visualmente o que o user acabou de mudar.

**Padrao** (optimistic update — preferido por evitar latencia de re-fetch):
```js
async function saveCardAlertPref(chipId, alertType, channel, enabled) {
    try {
        await api(`/api/modules/${chipId}/alert-prefs/${alertType}`,
                  { method: 'PUT', body: { [`enabled_${channel}`]: enabled }});
        // ATUALIZA CACHE LOCAL — senao re-render volta pro valor antigo
        const cache = _notifCardCacheByChip[chipId];
        if (cache && cache.catalog) {
            const item = cache.catalog.catalog.find(i => i.alert_type === alertType);
            if (item) item[`enabled_${channel}`] = enabled;
        }
    } catch(e) { _invalidateAndReloadAll(); }
}
```

Vale pra qualquer cache TTL — alerta prefs, silent_hours, ordem de modulos, etc.

### `const obj = {...}` em JS — mutar, NAO reatribuir (lecao da rodada 2026-04-26, v4.1.54)
`const` em JS impede REATRIBUICAO da referencia, nao MUTACAO do conteudo. Strict mode (modo padrao do JS moderno) lanca `TypeError: Assignment to constant variable`.

```js
const _cache = { ts: 0, alerts: null };

// ERRADO (TypeError em strict mode):
_cache = { ts: now, alerts: data };

// CERTO:
_cache.ts = now;
_cache.alerts = data;
```

Vale pra qualquer cache global, configuracao em memoria, etc. Se var precisa ser reatribuida, usar `let`.

### Compile scripts — `PORT` via env var (convencao desde v4.1.34, v4.1.59 reforcada)
`compile.sh`, `compile-cam.sh`, `compile-hidrofarm.sh` aceitam `PORT` como env var:
```bash
# Default da porta hardcoded (geralmente COM7)
bash compile.sh upload

# Override pra outra porta:
PORT=COM8 bash compile-cam.sh upload
PORT=COM17 bash compile.sh upload
```

Sintoma de porta errada: `Could not open COMx, the port is busy or doesn't exist`. Listar portas disponiveis: `wmic path Win32_SerialPort get DeviceID,Name` no PowerShell. Pra novos scripts/produtos, sempre usar `PORT="${PORT:-COMxx}"`.

### Refator BREAKING — entregar em fases pequenas (lecao da rodada 2026-04-26, v4.1.52)
A v4.1.52 mexeu **schema + 3 endpoints novos + 2 endpoints removidos + frontend grande + janela silencio movida** numa unica release. Resultou em **3 hotfixes consecutivos** (v4.1.53/54/55) — 2 erros logo no deploy + 1 latente do refator que so apareceu quando user mexeu.

**Padrao**: refator grande deve ser entregue em fases (catalogo → endpoints → frontend → migracao de UI), com smoke test em cada fase. A urgencia de validar bate com a complexidade — fragmentar reduz risco de regressao composta.

---

## Visao Geral

Plataforma IoT para cultivo inteligente. Arquitetura modular:
- **1 firmware** com compilacao condicional (`#ifdef`) por produto
- **1 servidor Flask** unificado que serve todos os tipos de modulo
- **1 PWA** com registry pattern — UI renderizada por capabilities do hardware
- **1 dominio principal**: `app.cultivee.com.br`

Hardware especializado: cada ESP32 faz uma coisa so.
Composicao por software: o app mostra os modulos que o usuario adicionar.

Versao ativa: **v4.1.60** (backend/PWA — emails de alerta contextualizados: subject inclui nome do modulo + severidade) / **firmware: 4 modulos sincronizados em v4.1.60** (rodada OTA 2026-04-26: Cam 704CAAF7C630 + Hidro-Farm 348257088304 + Hidro 50B525077000 + Hidro E04730A7DBCC). `APP_VERSION` definida como fonte unica em [`server/config.py:24`](./server/config.py). Sync com firmware via [`sync-version.sh`](./sync-version.sh).

Firmware: **v4.1.26** em todos os produtos — sincronizado automaticamente via [`sync-version.sh`](./sync-version.sh) em [`products/hidro.h:11`](./products/hidro.h), [`products/hidro-farm.h:16`](./products/hidro-farm.h) e [`products/cam.h:11`](./products/cam.h) (`FIRMWARE_VERSION`). Rode `bash sync-version.sh --write` antes de recompilar.

Tres produtos ativos: **HIDRO** (4 reles, automacao por fase), **HIDRO-FARM** (Premium — 6 reles, 4 automatizados + 2 manuais puros), **CAM** (camera standalone com OTA desde v4.1.8).

**Arquitetura em 3 camadas** (v4.1.17+) — o backend esta organizado em pastas que espelham o modelo mental:
- `server/hardware/` — blueprints que falam com ESP32 (hidro, hidrofarm, cam, gallery)
- `server/usuario/` — auth, perfil, troca de senha, 2FA, LGPD
- `server/admin/` — painel administrativo, impersonation, audit, gerenciamento de users/modulos

## Repositorios

Este projeto foi separado do monorepo original (mardoqueucosta/cultivee tag v1.0-monorepo):
- **cultivee-platform** (este repo) — firmware + servidor + PWA (app.cultivee.com.br). Repo GitHub: `github.com/mardoqueucosta/cultivee-platform`.
- **cultivee.com.br** — landing page React + Vite em repositorio proprio (`github.com/mardoqueucosta/cultivee.com.br`), mas o codigo-fonte tambem vive localmente como subprojeto irmao em [`../Site/`](../Site/) dentro desta mesma pasta `site-cultivee.com.br/`. Dominio: `cultivee.com.br` + `www.cultivee.com.br`. Ver [`../Site/CLAUDE.md`](../Site/CLAUDE.md) para convencoes do frontend institucional.

## Estrutura do Projeto

```
cultivee-platform/
├── firmware/                 # UM firmware, multiplos produtos
│   ├── firmware.ino          # setup() + loop() — orquestrador modular
│   ├── config.h              # Selecao de produto + ambiente (local/prod)
│   ├── core_wifi.h           # WiFi AP+STA, captive portal + RTC DS3231 (compartilhado hidro/hidro-farm)
│   ├── core_server.h         # WebServer, rotas setup WiFi, save WiFi
│   ├── core_register.h       # Registro no servidor, polling, command dispatch
│   ├── core_ota.h            # Rotas /update e /doUpdate (todos os produtos — Cam migrou pra min_spiffs em v4.1.8)
│   ├── mod_hidro.h           # MOD_HIDRO — 4 reles, fases, automacao, dashboard local
│   ├── mod_hidrofarm.h       # MOD_HIDROFARM — 6 reles (4 auto + 2 manuais), dashboard local
│   └── mod_cam.h             # MOD_CAM — Camera OV2640: capture, stream MJPEG, dashboard local
│
├── products/                 # 1 arquivo = 1 produto (define modulos + pinos)
│   ├── hidro.h               # MOD_HIDRO — ESP32-WROOM, 4 reles, RTC DS3231, min_spiffs
│   ├── hidro-farm.h          # MOD_HIDROFARM — ESP32-WROOM, 6 reles (GPIO 4/5/16/17/18/19), min_spiffs
│   └── cam.h                 # MOD_CAM — ESP32-WROVER, OV2640 standalone, min_spiffs (OTA habilitado v4.1.8+)
│
├── server/                   # UM servidor Flask unificado — organizado em 3 camadas (v4.1.17)
│   ├── app.py                # Core: setup, middleware readonly, registra blueprints
│   ├── config.py             # PORT, DB_PATH, PRODUCT_NAME, APP_VERSION (fonte unica)
│   ├── notifications.py      # AlertManager + send_email() generico (usado por alertas e auth)
│   │
│   ├── models/               # Camada de dados — pacote por dominio (v4.1.16 refactor)
│   │   ├── __init__.py       # re-exporta tudo pra backward compat (import models continua)
│   │   ├── db.py             # get_db(), init_db(), todas as migracoes idempotentes
│   │   ├── users.py          # usuarios + auth + tokens + password reset + roles + prefs + profile
│   │   ├── modules.py        # modulos do hardware + grupos + captura de camera
│   │   ├── push.py           # push subscriptions + alert_log
│   │   └── audit.py          # audit_log (acoes administrativas)
│   │
│   ├── usuario/              # Camada USUARIO — cliente comum (v4.1.17)
│   │   ├── __init__.py
│   │   ├── auth.py           # Blueprint auth_bp: register, login, logout, forgot/reset password
│   │   │                     # + decorators require_auth, require_admin
│   │   └── profile.py        # Blueprint profile_bp: GET/PUT perfil, troca senha, ViaCEP proxy
│   │
│   ├── admin/                # Camada ADMIN — so role='admin' (v4.1.17)
│   │   ├── __init__.py
│   │   └── admin.py          # Blueprint admin_bp: users/modules/stats/audit/impersonate
│   │
│   ├── hardware/             # Camada HARDWARE — ESP32 (v4.1.17)
│   │   ├── __init__.py
│   │   ├── hidro.py          # Blueprint hidro_bp: status, relay, phases (capability "hidro")
│   │   ├── hidrofarm.py      # Blueprint hidrofarm_bp: idem hidro + boias + DHT11 (capability "hidro-farm")
│   │   ├── cam.py            # Blueprint cam_bp: capture, upload, live, sensor config
│   │   └── gallery.py        # Blueprint gallery_bp: galeria com pastas, selecao, exclusao
│   │
│   ├── templates/index.html  # PWA template (config injetada)
│   ├── static/app.js         # PWA — registry pattern, hidro + hidro-farm + cam UI
│   ├── static/gallery.js     # Galeria modal: pastas, grid, selecao, exclusao
│   ├── static/style.css      # Dark theme responsivo (desktop ate 3 colunas, mobile 1)
│   ├── sim_esp32.py          # Simulador de hardware (hidro, hidro-farm, cam) para dev sem ESP32
│   ├── run-app.py            # Dev server local preferido (porta 5002)
│   ├── run-hidro.py          # Dev server dedicado ao Hidro (DB separado)
│   ├── test_routes.py        # Smoke tests das rotas HTTP
│   ├── Dockerfile            # python:3.10-slim + gunicorn (2w x 4t)
│   ├── requirements.txt      # flask, python-dotenv, gunicorn, pillow, pywebpush
│   └── .env.example          # Template: DATA_DIR, DB_PATH, CAPTURE_INTERVAL
│
├── docs/                     # Documentacao tecnica
│   └── guia-otimizacao-esp32-cam.md  # Referencia otimizacao camera OV2640
│
├── mockup/
│   └── dashboard.html        # Mockup estatico historico do dashboard (referencia de design)
│
├── .github/workflows/
│   └── deploy.yml            # Deploy automatico em push para main (filtrado por paths)
│
├── docker-compose.yml        # FONTE DA VERDADE — container app (Flask/Gunicorn)
├── deploy.sh                 # Deploy server para VPS (manual — empacota so server/)
├── compile.sh                # Compila firmware Hidro (com/sem upload, COM7)
├── compile-hidrofarm.sh      # Compila firmware Hidro-Farm (com/sem upload, COM16)
├── ota-remote.sh             # Envia .bin para OTA remoto via servidor (uso: bash ota-remote.sh <chip_id> <bin_path> <token>)
├── PRD-Cultivee.md           # FONTE DA VERDADE — Product Requirements Document
├── PLANO-VISAO-GERAL-SOFTWARE.md  # Visao geral de arquitetura (historico, 53KB)
├── ESP32_SAFE_FLASH_GUIDE.md # Guia de gravacao segura do ESP32 (historico, 15KB)
├── README.md                 # Contexto publico (pitch, stack, instalacao, scripts)
└── CLAUDE.md                 # ESTE ARQUIVO
```

---

## Arquitetura

### Firmware: Compilacao condicional
```
config.h → inclui UM de: products/hidro.h, products/hidro-farm.h, products/cam.h
         → produto define MOD_HIDRO, MOD_HIDROFARM ou MOD_CAM
         → firmware.ino usa #ifdef para ativar modulos
```

Cada modulo implementa: `*_setup()`, `*_loop()`, `*_register_routes()`, `*_process_command()`, `*_status_json()`, `*_dashboard_html()`, `*_dashboard_js()`.

**Exclusao mutua:** `MOD_HIDRO` e `MOD_HIDROFARM` sao mutuamente exclusivos. Ambos compartilham a mesma `struct Phase` e as variaveis globais de fase/rele em `firmware.ino` — so um pode estar ativo. Um `#error` em [`firmware.ino:25-28`](./firmware/firmware.ino) impede o build com os dois definidos.

**Codigo compartilhado em `core_*.h`:** recursos de hardware compartilhados entre produtos (ex: RTC DS3231 em [`core_wifi.h:75-146`](./firmware/core_wifi.h)) usam guards `#if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)` — NAO `#ifdef MOD_HIDRO` sozinho. Ver "Adicionar Novo Modulo" abaixo.

### Servidor: Blueprints (v4.1.17+ — organizados em camadas)

```python
# 3 camadas, 7 blueprints — filesystem espelha o mental model
from usuario.auth     import auth_bp      # /api/auth/*
from usuario.profile  import profile_bp   # /api/profile/*
from admin.admin      import admin_bp     # /api/admin/*
from hardware.hidro     import hidro_bp      # /api/hidro/* (+ /api/ctrl/* alias deprecated)
from hardware.hidrofarm import hidrofarm_bp  # /api/hidro-farm/*
from hardware.cam       import cam_bp        # /api/cam/*
from hardware.gallery   import gallery_bp    # /api/gallery/*

app.register_blueprint(auth_bp,      url_prefix="/api/auth",       name="auth")
app.register_blueprint(profile_bp,   url_prefix="/api/profile",    name="profile")
app.register_blueprint(admin_bp,     url_prefix="/api/admin",      name="admin")
app.register_blueprint(hidro_bp,     url_prefix="/api/hidro",      name="hidro")
app.register_blueprint(hidro_bp,     url_prefix="/api/ctrl",       name="hidro_ctrl_legacy")  # alias deprecated v4.1.28
app.register_blueprint(hidrofarm_bp, url_prefix="/api/hidro-farm", name="hidrofarm")
app.register_blueprint(cam_bp,       url_prefix="/api/cam",        name="cam_standalone")
app.register_blueprint(gallery_bp,   url_prefix="/api/gallery",    name="gallery")

# Rotas diretas em app.py (nao em blueprint):
# POST /api/push/subscribe       — registra subscription do navegador
# POST /api/push/unsubscribe     — remove subscription
# GET  /api/push/status          — retorna se usuario tem subscription
# GET  /api/user/prefs           — ordem + selecao de modulos (v4.1.10)
# PUT  /api/user/prefs           — salva prefs
# GET  /termos, /privacidade     — paginas estaticas LGPD (v4.1.20)
# POST /api/modules/<id>/firmware — OTA upload (admin)
# GET  /api/modules/<id>/firmware — OTA download pelo ESP32 (sem auth)
```

Validacao por capability nos blueprints de hardware:
- `hardware/hidro.py` exige `"hidro"` nas capabilities
- `hardware/hidrofarm.py` exige `"hidro-farm"`
- `hardware/cam.py` exige `"cam"`

**Middleware global de escopo readonly** (v4.1.15, em `app.py` — `@before_request`):
- Tokens de impersonation podem ser criados com `scope='readonly'`
- Quando scope=readonly, qualquer `POST/PUT/DELETE/PATCH` em `/api/*` retorna 403
- GET-mutations legados (`/relay`, `/capture`, `/save-config`, `/start-live`, `/reset-wifi`, etc.) tambem bloqueados
- Permite "Ver como" do admin inspecionar sem alterar estado

As capabilities sao reportadas pelo ESP32 em cada `POST /api/modules/register` e armazenadas como JSON array no DB.

> **v4.1.28 — migracao do legado `ctrl`:** `MODULE_TYPE` do hidro virou `"hidro"` (antes `"ctrl"` por motivo historico). Todos os produtos agora seguem `MODULE_TYPE == capability`. Servidor normaliza ESP32 com firmware antigo (`type="ctrl"` -> `"hidro"`) e mantem `/api/ctrl/*` como alias deprecated de `/api/hidro/*` com log de warning. A migracao do banco (`UPDATE modules SET type='hidro' WHERE type='ctrl'`) ocorre automaticamente no `init_db`. O helper [`getCtrlContainer(chipId, moduleType)`](./server/static/app.js) continua tolerando ambos como safety net — remover depois de ~1 semana sem hits em `/api/ctrl`.

### PWA: Registry Pattern
```javascript
const moduleRenderers = {
    hidro:        { label: 'Controle Hidro', renderContent: renderModule_hidro,     getStatusText: ... },
    'hidro-farm': { label: 'Controle Farm',  renderContent: renderModule_hidrofarm, getStatusText: ... },
    cam:          { label: 'Câmera',         renderContent: renderModule_cam,       getStatusText: ... },
};
```

`renderModule_hidrofarm` atualmente delega a `renderModule_hidro` (mesma UI base). O `renderDashboard()` detecta hidro-farm pela presenca dos campos `data.valve_entrada`/`data.bomba_homo` e adiciona a 3a linha de botoes (VALVULA + HOMOG) dentro do bloco manual.

Capability nao registrada → mostra "Modulo sem interface configurada".

### Fluxo de Dados — como as 3 camadas se comunicam

O projeto tem **3 camadas** que trocam dados bidirecionalmente:

```
  ┌────────────────┐       ┌──────────────────┐       ┌────────────────────┐
  │ ESP32 (firmware)│◄─────►│ Servidor (Flask)  │◄─────►│ PWA (navegador)    │
  │ dashboard local │       │ API REST + DB     │       │ app.cultivee.com.br│
  │ reles, sensores │       │ app.cultivee.com  │       │ UI do usuario      │
  └────────────────┘       └──────────────────┘       └────────────────────┘
```

**1. ESP32 → Servidor (a cada 10s, polling)**
```
POST /api/modules/register
  ENVIA:  chip_id, type, capabilities, ctrl_data (estados, fases, sensores, temp, nivel)
  RECEBE: commands[], poll_interval, firmware_url, cam_resolution, cam_quality
```
O ESP32 NAO tem token de autenticacao — e identificado pelo `chip_id`. O `ctrl_data` e um JSON blob com TUDO que o modulo reporta (reles, fases, ciclo, sensores). O servidor armazena no banco e a PWA le.

**2. App (PWA) → Servidor → ESP32 (quando usuario faz acao)**
```
Exemplo: usuario clica "toggle luz" no app
  1. PWA: POST /api/hidro/<chip_id>/relay?device=light&action=toggle
  2. Servidor (hardware/hidro.py):
     a) Tenta PROXY DIRETO: HTTP GET http://<ip_esp32>/relay?device=light&action=toggle (timeout 2s)
     b) Se proxy OK: retorna resposta do ESP32 direto pra PWA
     c) Se proxy falha: ENFILEIRA pending_command no banco + retorna "queued"
  3. ESP32 (se proxy falhou): no proximo poll, recebe o command e executa
```
Esse padrao "proxy direto + fallback pra fila" se aplica a: relay, save-config, add-phase, remove-phase, reset-phases, reset-wifi, capture, start-live, stop-live.

**3. Sincronizacao de config (fases, start_date)**
```
  App salva config → Servidor atualiza banco + enfileira comando save-config
                   → ESP32 recebe no poll → atualiza NVS
                   → proximo register → servidor aceita dados do ESP32
```
- **Fonte de verdade para fases/start_date:** o ESP32 (NVS). O servidor aceita o que o ESP32 manda.
- **Fonte de verdade para camera config:** o servidor (banco). O ESP32 apenas ecoa.
- **`server_keys` em `register_module()`:** campos de camera sao protegidos no merge (servidor nao deixa o ESP32 sobrescrever). Campos de hidro (fases, start_date) NAO sao protegidos — o ESP32 e soberano. Campos do sistema de alertas (`low_since`, `alert_threshold_min`) tambem sao server_keys — o ESP32 nao manda esses campos, o servidor os gerencia.
- **`cycle_day`/`phase`:** recalculados pelo PWA usando `Date()` do navegador, nao confiando no relogio do ESP32 (licao v4.0.14).

**4. OTA Remoto (firmware via servidor)**
```
  Dev: upload .bin → Servidor salva em disco
  ESP32: register → resposta inclui firmware_url → baixa .bin → Update → restart
```
Ver secao "OTA Remoto via Servidor" em "Compilar e gravar" para detalhes.

**5. Versao offline (dashboard local no ESP32)**
Quando o usuario acessa o IP do ESP32 diretamente (via rede local ou AP), o firmware serve um **dashboard HTML/JS inline** (`*_dashboard_html()` / `*_dashboard_js()`). Esse dashboard e uma replica visual da PWA online, mas:
- Roda SEM servidor (HTTP direto no ESP32, porta 80)
- Usa as mesmas rotas locais: `/status`, `/relay`, `/config`, `/save-config`, `/update` (OTA)
- REGRA CRITICA: toda mudanca na UI online (app.js) DEVE ser replicada no offline (mod_*.h) e vice-versa

**6. Sistema de Alertas — Push PWA + Email (v4.1.0 + refator per-module v4.1.52)**
```
  AlertManager (notifications.py) roda no servidor, ativado a cada register do ESP32:
  1. register_module() salva ctrl_data → chama AlertManager.check(chip_id, ctrl_data, module)
  2. Merge: dados do ESP32 + dados do banco (server_keys protegidos)
  3. Roda 9+ checks. Cada check filtrado por module_type (DHT so em hidro-farm, etc).
  4. Se condicao + cooldown OK: _send_alert(user, chip, alert_type, payload)
     a) Severity resolvida via get_alert_meta(alert_type, module_type)
     b) Silent hours global (P0 ignora) — _is_in_silent_hours(user, sev)
     c) Push PWA — _user_wants_channel(user, chip, type, "push") + pywebpush
     d) Email SMTP — _user_wants_channel(user, chip, type, "email") + _send_email_alert
     e) Sempre log em alert_log (mesmo silenciado — historico mostra que disparou)
```

**Catalogo de alertas (v4.1.52+ — POR MODULO):**

```python
UNIVERSAL_ALERTS = {       # todo modulo tem (4)
    "module_offline":          P1, cooldown 4h
    "module_recovered":        P3, cooldown 1h
    "low_heap_warning":        P2, cooldown 24h
    "wifi_disconnect_burst":   P2, cooldown 6h
}

PRODUCT_ALERTS = {
    "hidro": {},  # so universais
    "hidro-farm": {           # 6 especificos
        "level_low":              P1, cooldown 1h
        "sensor_invalid":         P2, cooldown 12h  (DHT11)
        "dht_temperature_high":   P2, cooldown 6h   (>= 35C / 30min)
        "dht_temperature_low":    P2, cooldown 6h   (<= 10C / 30min)
        "dht_humidity_extreme":   P3, cooldown 12h  (<20% ou >95% / 1h)
        "reservoir_fill_stuck":   P1, cooldown 4h   (valvula 30min sem boia alta)
    },
    "cam": {                  # 3 especificos
        "cam_capture_failed":     P2, cooldown 12h  (last_capture > 2x interval)
        "cam_init_failed":        P1, cooldown 24h  (firmware reporta cam_init_error_code)
        "cam_dark_frame":         P3, cooldown 24h  (5 capturas < 30% baseline)
    },
}

def get_alerts_for_module(module_type):
    return {**UNIVERSAL_ALERTS, **PRODUCT_ALERTS.get(module_type, {})}
```

Adicionar produto novo: criar entry em `PRODUCT_ALERTS["nome"]`, implementar
`_check_*` em `AlertManager`, filtrar em `check()` por `module_type`.
Zero mudanca em endpoint, schema, UI ou banco.

**Tabelas:**
- `push_subscriptions (user_id, endpoint, p256dh, auth)` — Web Push do navegador
- `alert_log (module_id, alert_type, severity, sent_at, ack_at, ack_by)` — historico
- `module_alert_prefs (user_id, chip_id, alert_type, enabled_push, enabled_email)` — prefs PER-MODULO (v4.1.52)
- `users.notification_email` — email pra alertas (pode diferir do login)
- `users.alert_silent_hours_start/_end` — janela de silencio GLOBAL por user

**Endpoints (v4.1.52+):**
- `GET /api/modules/<chip>/alerts/catalog` — lista alertas aplicaveis ao modulo + prefs
- `PUT /api/modules/<chip>/alert-prefs/<type>` — atualiza pref de canal
- `GET /api/modules/<chip>/alerts/history?days=N` — historico filtrado por chip + stats (v4.1.57)
- `GET /api/profile/alert-silent-hours` / `PUT` — janela global (consumida pelo modal no menu user)
- `POST /api/profile/alerts/<id>/ack` — ack de alerta individual

**Frontend:**
- `renderNotificationCard(chipId, ctrlData)` em `app.js` — renderiza card per-modulo
- Cache `_notifCardCacheByChip[chipId]` + `_notifHistoryCacheByChip[chipId]` (TTL 60s)
- Tabs 7d/30d/60d + estado `<details>` open persistidos em `localStorage` per-chip
- Janela de silencio: modal aberto pelo menu do user (`openSilentHoursModal()`)

**Email (v4.1.60 — contextualizado):**
- Subject: `Cultivee · {nome do modulo} · {tipo do alerta} [P{sev}]`
- Body: bloco metadados (Modulo / Severidade / Hora) + body original + footer educativo
- Permite filter Gmail por modulo (`subject:"Hidro 7000"`)

Service Worker (`sw.js` dinamico): handlers `push` + `notificationclick` — exibe notificacao e abre o app ao clicar.
PWA: `requestPermission()` + `pushManager.subscribe()` chamado 2s apos login. Toggle iOS-style no card Reservatorio (ON verde / OFF cinza / BLOCKED vermelho).

### Fluxo do usuario (primeiro uso)
```
1. Liga ESP32 → cria rede AP (ex: Cultivee-HidroFarm, sem senha)
2. Conecta no AP via celular → captive portal configura WiFi
3. ESP32 reinicia → conecta WiFi → registra no servidor (POST /register)
4. Abre app.cultivee.com.br → login → "Adicionar Modulo" → digita codigo (short_id)
5. Modulo aparece na lista com checkbox + setas ↑↓
6. Seleciona → dashboard do modulo aparece (cards: stats, fases, ambiente, reservatorio, controles)
7. Controle: toggle reles via app → servidor → ESP32 (proxy direto ou fila)
8. Config: edita fases/start_date → app salva no banco + envia comando pro ESP32
9. OTA: firmware .bin enviado ao servidor → ESP32 baixa e atualiza remotamente
```

---

## Produtos

### HIDRO (ESP32-WROOM-32D)
- **Porta:** COM7
- **Board:** `esp32:esp32:esp32doit-devkit-v1` com particao `min_spiffs` (OTA habilitado — `1.9MB app0 + 1.9MB app1`)
- **Reles:** 4 canais ativos em LOW (modulo rele de 4 canais). Pinos em [`products/hidro.h:38-41`](./products/hidro.h):
  - `RELE_LAMPADA` GPIO4 — Luz
  - `RELE_BOMBA` GPIO5 — Bomba d'agua
  - `RELE_VENTILACAO` GPIO18 — Ventilacao
  - `RELE_AERACAO` GPIO19 — Aeracao (pedra porosa, etc.)
- **RTC DS3231:** I2C em GPIO21 (SDA) / GPIO22 (SCL), endereco `0x68` ([`products/hidro.h:47-50`](./products/hidro.h)) — mantem hora mesmo sem WiFi/NTP, usado pela automacao offline
- **LED de status:** GPIO2 (LED azul onboard — `LED_ONBOARD`)
- **Reset WiFi:** botao BOOT (GPIO0 — `RESET_BTN`), segurar por 3s
- **Automacao:** `MAX_PHASES = 10` fases, cada fase tem luz + bomba + ventilacao + aeracao com ciclos dia/noite independentes (struct `Phase` em [`firmware/firmware.ino:28-47`](./firmware/firmware.ino))
- **AP:** `Cultivee-Hidro-XXXXXX` (sufixo MAC desde v4.1.34 — antes era so `Cultivee-Hidro` que colidia entre 2+ modulos do mesmo produto na mesma rede)
- **mDNS:** `cultivee-hidro-xxxxxx.local` (sufixo MAC lowercase desde v4.1.34; v4.1.28+ era so `cultivee-hidro.local`; legado pre-v4.1.28: `cultivee-ctrl.local`)
- **SERVER_URL prod:** `http://app.cultivee.com.br` (HTTP puro — ESP32 nao faz TLS)
- **APP_URL prod:** `https://app.cultivee.com.br` (usuario acessa PWA via HTTPS)

### HIDRO-FARM (ESP32-WROOM-32D) — versao Premium

Variante avancada do HIDRO: mesma placa, mesmo RTC, mesmo sistema de fases. Adiciona **6 reles**, **reposicao automatica de agua** no reservatorio (2 boias + valvula) e **sensor DHT11** (temperatura + umidade ambiente).

- **Porta (sugerida):** COM16 (definida em [`compile-hidrofarm.sh`](./compile-hidrofarm.sh))
- **Board:** `esp32:esp32:esp32doit-devkit-v1` com particao `min_spiffs` (OTA habilitado — identico ao HIDRO)
- **AP:** `Cultivee-HidroFarm-XXXXXX` (sufixo MAC desde v4.1.34)
- **mDNS:** `cultivee-hidro-farm-xxxxxx.local` (sufixo MAC desde v4.1.34)
- **SERVER_URL prod:** `http://app.cultivee.com.br`
- **APP_URL prod:** `https://app.cultivee.com.br`
- **Preferences NVS:** namespace `"hydrofarm"` (separado do HIDRO `"hydro"` — nao compartilham configuracao de fases). Persiste: fases, `start_date`, `mode_auto`, `valve_auto`
- **MODULE_TYPE:** `"hidro-farm"` (capability e module_type sao iguais — padrao novo, ver nota em "Servidor: Blueprints")
- **LED de status:** GPIO2 (`LED_ONBOARD`)
- **Reset WiFi:** botao BOOT (GPIO0), 3s
- **RTC DS3231:** idem HIDRO — I2C GPIO21/22, endereco `0x68`

#### Reles (6 canais ativos em LOW) — [`products/hidro-farm.h:44-49`](./products/hidro-farm.h)

**Automatizados (controlados por fase, como no HIDRO):**
- `RELE_LAMPADA` GPIO4 — Luz
- `RELE_BOMBA` GPIO5 — Bomba de irrigacao (NFT/gotejamento)
- `RELE_VENTILACAO` GPIO16 — Ventilacao (exaustor) *(difere do HIDRO que usa GPIO18)*
- `RELE_AERACAO` GPIO17 — Aeracao *(difere do HIDRO que usa GPIO19)*

**Controle de reservatorio (automacao independente das fases):**
- `RELE_VALVULA_ENTRADA` GPIO18 — Valvula de entrada de agua. Controlada pela maquina de estados do reservatorio (quando `valveAuto=true`, default) ou manualmente via comando remoto/serial.

**Manual puro (fora de qualquer automacao):**
- `RELE_BOMBA_HOMO` GPIO19 — Bomba de homogeneizacao (mistura nutrientes). So liga/desliga via usuario.

#### Reposicao automatica do reservatorio (boias + valvula)

Duas boias reed-switch monitoram o nivel do reservatorio, lidas com `INPUT_PULLUP` (fail-safe: fio quebrado = inativo):
- `SENSOR_NIVEL_ALTO` GPIO13 — boia alta, ativa quando reservatorio atinge o nivel maximo
- `SENSOR_NIVEL_BAIXO` GPIO14 — boia baixa, ativa quando reservatorio cai ate o nivel minimo
- `LEVEL_SENSOR_ACTIVE` = `LOW` (boia float lateral tipo NO — contato fecha pro GND quando agua empurra a boia)

**Polaridade correta (validada e atualizada via OTA remoto):**
- Sem agua → contato aberto → GPIO HIGH (pullup) → `level = false`
- Com agua → contato fecha → GPIO LOW → `level = true`
- `level_low = false` → reservatorio precisa encher (timer de alerta inicia)
- `level_low = true` → agua OK (timer para)

Leitura das boias com **debounce de 2 amostras consecutivas** (~600ms total) em [`readLevelSensorsFarm()`](./firmware/mod_hidrofarm.h), chamada a cada 300ms no loop. Uma mudanca so vira estado "confirmado" (`highLevelState`/`lowLevelState`) depois de 2 leituras iguais — evita falsos positivos por vibracao/ondas.

**Maquina de estados** ([`reservoirControlFarm()`](./firmware/mod_hidrofarm.h)):

| Boia Alta | Boia Baixa | `reservoir_state` | Acao |
|:---:|:---:|:---:|:---|
| OFF | OFF | `empty` | **Abrir valvula** (tratado como "precisa encher") |
| OFF | ON | `filling` | Manter estado anterior (**histerese**) |
| ON | ON | `full` | **Fechar valvula** (atingiu maximo) |
| ON | OFF | `error` | Fechar por seguranca (sensor defeituoso) |

A maquina de estados so atua quando `valveAuto == true`. Com `valveAuto == false`, as boias sao lidas e reportadas mas a valvula e 100% manual. A flag `valveAuto` e persistida em NVS (`prefs.getBool("valve_auto", true)` no setup) e pode ser alterada via:
- Comando remoto `{cmd: "relay", device: "valve_auto"}`
- Serial `VA1` (auto) / `VA0` (manual)
- **Nao ha mais UI no PWA para alterar** — a partir da v4.0.11 o card Reservatorio nao mostra mais o badge de modo nem os botoes ABRIR/FECHAR. Controle continua no firmware mas exposto so via serial/comando remoto.

#### Sensor DHT11 (ambiente)

- `DHT_PIN` GPIO25 — pino "out" do modulo DHT11 (+ VCC em 3.3V, - GND)
- **Implementacao inline** (sem biblioteca externa) em [`readDHT11Farm()`](./firmware/mod_hidrofarm.h). Protocolo 1-wire bit-banging: start signal ~20ms + leitura de 40 bits + checksum XOR. Bloqueia o loop por ~22ms.
- Chamada a cada **5 segundos** no loop (spec minima do DHT11: 1s entre leituras)
- Retorna apenas valores inteiros (DHT11 nao tem casa decimal — os bytes fracionarios sao sempre 0)
- Falha na leitura marca `dhtValid = false` — UI mostra "sensor offline"

#### JSON do status/register (campos do hidro-farm)

Alem dos campos herdados do HIDRO (`light`, `pump`, `ventilation`, `aeration`, `mode`, fases, etc.), o hidro-farm adiciona:

| Campo | Tipo | Descricao |
|---|---|---|
| `valve_entrada` | bool | Estado atual do rele da valvula |
| `bomba_homo` | bool | Estado atual do rele de homogeneizacao |
| `valve_auto` | bool | Modo da valvula (true = automacao por boias, false = manual) |
| `level_high` | bool | Boia alta confirmada (pos-debounce) |
| `level_low` | bool | Boia baixa confirmada (pos-debounce) |
| `reservoir_state` | string | `"full"` / `"filling"` / `"empty"` / `"error"` |
| `temperature` | int | Temperatura em °C (DHT11, inteiro) |
| `humidity` | int | Umidade relativa em % (DHT11, inteiro) |
| `dht_valid` | bool | true se a ultima leitura do DHT11 foi valida |
| `low_since` | string/null | Timestamp UTC (ISO 8601) de quando level_low virou false (server_key, salvo no banco) |
| `alert_threshold_min` | int | Minutos de nivel baixo antes de disparar alerta (default 10, range 1-120, server_key) |

#### Comandos serial (115200 baud)

Alem dos herdados do HIDRO (`L1`/`L0`, `P1`/`P0`, `V1`/`V0`, `A1`/`A0`, `AUTO`, `STATUS`):

| Comando | Acao |
|---|---|
| `VE1` / `VE0` | Valvula de entrada ON/OFF |
| `BH1` / `BH0` | Bomba de homogeneizacao ON/OFF |
| `VA1` / `VA0` | Modo da valvula AUTO/MANUAL (persistido no NVS) |
| `LEVEL` | Imprime estado completo do reservatorio (boias + valvula + modo) |
| `STATUS` | (expandido) L/P/V/A/VE/BH/VA/LH/LL/M |

#### Dashboard local (offline) — ordem dos cards

Ordem do HTML renderizado por [`hidrofarm_dashboard_html()`](./firmware/mod_hidrofarm.h):
1. **Card principal** — ciclo/fase/inicio/hoje + indicadores + botao Modo Auto/Manual + botoes manuais (quando `!modeAuto`)
2. **Fases Configuradas** — lista detalhada das fases
3. **Ambiente** — temperatura e umidade do DHT11
4. **Reservatorio** — tanque visual + indicadores das boias + estado + valvula + timer nivel baixo + threshold configuravel + toggle notificacoes (sem botao de modo nem manual)
5. **Controles Extras** — botao unico HOMOG (sempre visivel)

O PWA online replica a mesma ordem em [`renderDashboard()`](./server/static/app.js) via variaveis `phasesHtml`, `ambientHtml`, `reservoirHtml`, `extrasHtml`.

#### Funcoes publicas + convencao

- Publicas (chamadas por `firmware.ino`): `hidrofarm_setup()`, `hidrofarm_loop()`, `hidrofarm_register_routes()`, `hidrofarm_process_command()`, `hidrofarm_status_json()`, `hidrofarm_register_json()`, `hidrofarm_dashboard_html()`, `hidrofarm_dashboard_js()`, `hidrofarm_serial_command()`
- Internas: sufixo `*Farm` (`setRelayFarm`, `loadPhasesFarm`, `readLevelSensorsFarm`, `reservoirControlFarm`, `readDHT11Farm`, `handleRelayFarm`, etc.) — isolamento caso eventualmente convivam com HIDRO
- **NVS namespace:** `"hydrofarm"` (separado do `"hydro"` do HIDRO)
- **Exclusao mutua:** `MOD_HIDRO` e `MOD_HIDROFARM` compartilham `struct Phase` e globals em `firmware.ino` — `#error` impede build com os dois definidos

Os 4 reles automatizados compartilham toda a logica de fases do HIDRO via `struct Phase` comum. Os estados `valveEntradaState` e `bombaHomoState` ficam so em RAM — **NAO persistem no NVS** (resetam para OFF no reboot). Ja o `valveAuto` persiste. Se quiser persistir os estados dos reles extras, criar chaves no NVS `"hydrofarm"`.

### CAM (ESP32-WROVER-DEV) — Standalone
- **Porta:** COM9
- **Board:** `esp32:esp32:esp32wroverkit` com particao `min_spiffs` (1.9 MB app0 + 1.9 MB app1, OTA habilitado desde v4.1.8 — antes era `no_ota`). Firmware ocupa 1.27 MB (64% — sobra ~690 KB)
- **Camera:** OV2640 always-on (init unico no boot, nunca `esp_camera_deinit()`)
- **Reset WiFi:** botao BOOT (GPIO0 — `RESET_BTN`), segurar por 3s
- **AP:** `Cultivee-Cam-XXXXXX` (sufixo MAC desde v4.1.34)
- **mDNS:** `cultivee-cam-xxxxxx.local` (sufixo MAC desde v4.1.34)
- **SERVER_URL prod:** `http://app.cultivee.com.br` (HTTP para upload de fotos)
- **APP_URL prod:** `https://app.cultivee.com.br`
- **Pinos OV2640:** completos em [`products/cam.h:42-58`](./products/cam.h) (XCLK=21, SIOD=26, SIOC=27, data Y2-Y9, VSYNC=25, HREF=23, PCLK=22)

#### Otimizacao da Camera (ref: [`docs/guia-otimizacao-esp32-cam.md`](./docs/guia-otimizacao-esp32-cam.md))

A camera tem **tres estados de resolucao/qualidade** que sao facil de confundir. Implementacao em [`firmware/mod_cam.h:12-72`](./firmware/mod_cam.h) e firmware globals em [`firmware/firmware.ino:99-100`](./firmware/firmware.ino).

**Init (boot) — maior buffer possivel:**
- `XCLK`: 8 MHz (minima EMI WiFi — ping 35ms vs 1435ms@20MHz — testado e documentado)
- `fb_count`: 2 (double buffering, DMA continuo, captura instantanea)
- `grab_mode`: `CAMERA_GRAB_LATEST` (sempre frame mais recente)
- `fb_location`: `CAMERA_FB_IN_PSRAM` (PSRAM do WROVER)
- `frame_size`: `FRAMESIZE_UXGA` (aloca buffer para 1600x1200)
- `jpeg_quality`: 4 (buffer GRANDE — runtime pode subir resolucao sem truncar)
- `flush boot`: 4 frames descartados apos init (AWB/AEC estabiliza, elimina tonalidade verde)

**Runtime preview (apos init) — frame rapido para stream:**
- Logo depois do `esp_camera_init()`, o codigo chama `set_framesize(VGA)` e `set_quality(12)` ([`mod_cam.h:67-68`](./firmware/mod_cam.h))
- Usada pelo MJPEG stream local (`/stream`) e pelos live frames push para o PWA
- `LIVE_FRAME_INTERVAL` = 800ms, `LIVE_MAX_DURATION` = 120s (auto-stop apos 2min)

**Captura agendada — sweet spot qualidade/tamanho:**
- Globals em `firmware.ino`: `captureFrameSize = FRAMESIZE_SVGA` (800x600), `captureQuality = 5`
- O firmware sobe para SVGA q5 **sob demanda** (comando `capture` recebido via `/api/modules/poll` ou `/register`), tira a foto, retorna framebuffer e volta para VGA q12
- **Configuravel por modulo:** o PWA pode sobrescrever `cam_resolution` e `cam_quality` via `/api/cam/<chip_id>/sensor-config`; defaults no DB sao `UXGA` / `10` (ver migracao em [`server/models/db.py`](./server/models/db.py))
- O servidor envia `cam_resolution` e `cam_quality` na resposta de `/api/modules/register` a cada poll — o firmware aplica antes da proxima captura

**Regras absolutas:**
- **NUNCA fazer** `esp_camera_deinit()` repetido — corrompe DMA, testado e falha na pratica
- **NUNCA usar** init/deinit on-demand — mesmo motivo; always-on e a unica estrategia que funciona
- **SEMPRE retornar** framebuffer com `esp_camera_fb_return(fb)` apos `esp_camera_fb_get()`
- **Resolucao acima de SVGA** so para captura sob demanda (UXGA q4 init e q10 DB default sao suportados, mas o default de captura continua SVGA q5 por margem)

### Compilar e gravar

Antes de tudo, ajustar [`firmware/config.h`](./firmware/config.h):
1. Escolher o ambiente: descomentar `ENV_LOCAL` (aponta para `LOCAL_SERVER_IP`) ou `ENV_PRODUCTION` (aponta para `app.cultivee.com.br`). So um pode estar ativo — o `#error` em `config.h:19-24` impede o build com os dois.
2. Escolher o produto: descomentar UM de `#include "../products/hidro.h"`, `#include "../products/hidro-farm.h"` ou `#include "../products/cam.h"`.

```bash
# HIDRO (ESP32-WROOM) — script usa particao min_spiffs (OTA habilitado), grava em COM7
bash compile.sh              # compila → build/firmware.ino.bin
bash compile.sh upload       # compila + grava via USB em COM7

# HIDRO-FARM (ESP32-WROOM) — mesmo board e particao, grava em COM16
bash compile-hidrofarm.sh            # compila
bash compile-hidrofarm.sh upload     # compila + grava via USB em COM16

# Atualizar via OTA (sem cabo): com o ESP32 rodando, abrir
#   http://<ip-do-esp32>/update
# no navegador e enviar o build/firmware.ino.bin gerado.
# O IP e 192.168.4.1 se estiver no AP do ESP32, ou o IP na rede local se ja conectado.
# Funciona para HIDRO, HIDRO-FARM e CAM (todos usam min_spiffs a partir da v4.1.8).

# CAM (ESP32-WROVER) — OTA habilitado desde v4.1.8 (antes era no_ota).
# A PRIMEIRA gravacao apos migracao de partition table DEVE ser via USB.
# Depois disso, atualizacoes podem ser remotas via ota-remote.sh.
bash compile-cam.sh            # compila
bash compile-cam.sh upload     # compila + grava via USB em COM7
```

### OTA Remoto via Servidor (v4.0.15)

Atualiza firmware sem acesso fisico ao ESP32 e sem estar na mesma rede local. O .bin e enviado ao servidor, e o ESP32 baixa na proxima vez que fizer `registerOnServer()`.

**Fluxo completo:**
```
1. Compilar .bin localmente (compile.sh ou compile-hidrofarm.sh, sem "upload")
2. Enviar .bin ao servidor: bash ota-remote.sh <chip_id> <build/firmware.ino.bin> <token>
   (ou POST /api/modules/<chip_id>/firmware com multipart/form-data)
3. Servidor salva em DATA_DIR/firmware/<chip_id>.bin
4. ESP32 faz registerOnServer() no proximo poll → resposta inclui firmware_url
5. core_register.h detecta firmware_url → chama performRemoteOTA(url)
6. performRemoteOTA(): HTTP GET streaming → Update.writeStream() → ESP.restart()
7. Apos restart, ESP32 registra novamente (agora com firmware novo, sem firmware_url)
```

**Componentes:**
- **Servidor (`app.py`)**: 3 rotas novas (ver "Servidor: API" > "Firmware OTA")
- **Firmware (`core_register.h`)**: `performRemoteOTA(url)` + checagem de `firmware_url` em `registerOnServer()`
- **CLI (`ota-remote.sh`)**: wrapper para enviar .bin — `bash ota-remote.sh <chip_id> <bin_path> <token>`

**Protecoes:**
- Flag `otaRemoteAttempted` (RAM, nao NVS): so tenta OTA 1x por boot. Evita loop infinito se o .bin for invalido (ESP32 reinicia → registra → ve firmware_url → tenta → falha → reinicia → ...). Apos reboot por OTA bem-sucedido, a flag reseta naturalmente.
- Desde v4.1.8 todos os produtos (incluindo Cam) usam `min_spiffs` — OTA funciona em todos. Antes disso, Cam tinha particao `no_ota` e `Update.begin()` retornava false silenciosamente.
- O .bin e servido via `GET /api/modules/<chip_id>/firmware` **sem auth** (ESP32 nao carrega token). Seguranca por obscuridade do chip_id + o arquivo e removido apos download ou cancelamento.

**Bootstrap problem:** a feature de OTA remoto precisa estar no firmware do ESP32 para funcionar. A **primeira gravacao** de um ESP32 novo (ou de um que nao tem essa feature) **sempre** precisa ser via USB ou OTA local (`/update`). Depois da primeira gravacao com core_register.h v4.0.15+, todas as atualizacoes seguintes podem ser remotas.

**Tres formas de atualizar firmware (em ordem de preferencia):**
1. **OTA Remoto** (v4.0.15+) — sem acesso fisico, sem rede local. Requer firmware >=v4.0.15 ja gravado.
2. **OTA Local** (`/update`) — navegador na mesma rede, upload manual do .bin. Funciona para Hidro e Hidro-Farm.
3. **USB** — cabo fisico, `compile.sh upload` ou `compile-hidrofarm.sh upload`. Sempre funciona, unica opcao para Cam.

---

## Firmware: Detalhes

### Ambiente (config.h)
```c
// #define ENV_LOCAL        // http://192.168.7.233:5002
#define ENV_PRODUCTION      // http://app.cultivee.com.br
```

Cada produto define dois URLs:
- `SERVER_URL` — onde o ESP32 envia dados (HTTP, sem SSL)
- `APP_URL` — onde o usuario abre o app (HTTPS em prod, HTTP em local)

### Captive Portal
- **Android:** `/generate_204`, `/gen_204`, `/generate204` → HTTP 204 (faz Android confiar no WiFi e nao priorizar 4G)
- **iOS:** `/hotspot-detect.html` → responde "Success" (mesmo efeito)
- **Windows:** `/connecttest.txt` → 302 redirect

### OTA Remoto em core_register.h (v4.0.15)
- `performRemoteOTA(url)`: HTTP GET streaming com `httpUpdate`-style manual — `Update.begin()`, `http.getStream()`, `Update.writeStream()`, `Update.end()`, `ESP.restart()`. Funciona com particao `min_spiffs` em todos os produtos (Hidro, Hidro-Farm, Cam). Cam foi migrado de `no_ota` para `min_spiffs` na v4.1.8.
- `registerOnServer()` checa campo `firmware_url` na resposta JSON do servidor. Se presente e `otaRemoteAttempted == false`, dispara `performRemoteOTA()`.
- Flag `otaRemoteAttempted` (bool em RAM): inicializa false, setada true antes de tentar. So reseta no reboot. Evita loop infinito de reboot se o .bin for invalido.

### Stream local protegido
Flag `localStreamActive` suspende `registerOnServer()` e `pollCommands()` durante stream MJPEG local, evitando que timeouts HTTP congelem o stream.

---

## Servidor: API

### Autenticacao (atualizado v4.1.22)
| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/api/auth/register` | POST | Cadastro `{name, email, password, accepted_terms: true, captcha_token?}`. Dispara email de verificacao |
| `/api/auth/login` | POST | Login `{email, password, totp_code?}`. Se `totp_enabled`, retorna 401 com `{totp_required: true}` na 1a tentativa |
| `/api/auth/me` | GET | Info do user logado (inclui `role`, `email_verified`) |
| `/api/auth/logout` | POST | Invalida token atual |
| `/api/auth/forgot-password` | POST | `{email}` → envia link de reset (anti-enumeration) |
| `/api/auth/reset-password` | POST | `{token, password}` — valida + troca senha |
| `/api/auth/verify-email` | GET/POST | Consome token de verificacao de email |
| `/api/auth/resend-verification` | POST | Reenvia email de verificacao pro user logado |

### Perfil (v4.1.16 + v4.1.20 + v4.1.22)
Documentacao completa em "Camada de USUARIO" mais acima. Prefixo: `/api/profile/*`.

### Admin (v4.1.13+)
Documentacao completa em "Camada de ADMIN" mais acima. Prefixo: `/api/admin/*`.

### Modulos
| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/api/modules/register` | POST | ESP32 se registra (chip_id, type, capabilities) |
| `/api/modules/poll` | GET | ESP32 busca comandos pendentes |
| `/api/modules/pair` | POST | Vincular modulo ao usuario (short_id, name) |
| `/api/modules/unpair` | POST | Desvincular modulo |
| `/api/modules` | GET | Listar modulos do usuario |

### Push Notifications (rotas em `/api/push`)

Implementado diretamente em [`server/app.py`](./server/app.py). Gerencia subscriptions Web Push do navegador. Todas requerem auth.

| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/api/push/subscribe` | POST | Registra push subscription {endpoint, keys: {p256dh, auth}} |
| `/api/push/unsubscribe` | POST | Remove subscription do usuario |
| `/api/push/status` | GET | Retorna {subscribed: bool} |

### Firmware OTA (rotas em `/api/modules/<chip_id>/firmware`)

Implementado em [`server/app.py`](./server/app.py). Permite enviar .bin para OTA remoto via servidor.

| Rota | Metodo | Auth | Descricao |
|------|--------|------|-----------|
| `/api/modules/<chip_id>/firmware` | POST | Token (usuario) | Upload do .bin (multipart/form-data, campo `firmware`) |
| `/api/modules/<chip_id>/firmware` | GET | Sem auth (ESP32) | Download do .bin pendente pelo ESP32 |
| `/api/modules/<chip_id>/firmware` | DELETE | Token (usuario) | Cancela OTA pendente (remove o .bin) |

O `POST /api/modules/register` inclui campo `firmware_url` na resposta quando ha .bin pendente para o `chip_id`. Armazenamento: `DATA_DIR/firmware/<chip_id>.bin`.

### Hidro (prefixo: `/api/hidro` + `/api/ctrl` alias deprecated)

Implementado em [`server/hardware/hidro.py`](./server/hardware/hidro.py). Todas as rotas exigem `Authorization` e validam que o modulo pertence ao usuario autenticado **e** tem `"hidro"` em `capabilities`.

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

### Hidro-Farm (prefixo: `/api/hidro-farm`)

Implementado em [`server/hardware/hidrofarm.py`](./server/hardware/hidrofarm.py). Clone funcional de `hardware/hidro.py` — mesmas rotas, mesma semantica, mas valida capability `"hidro-farm"`. Aceita os mesmos `device` do `/relay` (`light`, `pump`, `ventilation`, `aeration`, `mode`) **mais os dois novos**: `valve_entrada` e `bomba_homo`. O endpoint `/relay` e generico — ele so faz proxy/enfileiramento para o ESP32 sem validacao por `device`.

| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/<chip_id>/status` | GET | Status (inclui `valve_entrada` e `bomba_homo`) |
| `/<chip_id>/relay` | GET | Controle rele (?device=valve_entrada&action=toggle, etc.) |
| `/<chip_id>/phases` | GET | Fases (?live=1) — so afeta os 4 reles automatizados |
| `/<chip_id>/save-config` | POST | Salvar config fases |
| `/<chip_id>/add-phase`, `/remove-phase`, `/reset-phases`, `/reset-wifi` | GET | idem HIDRO |

### Camera (prefixo: `/api/cam`)

Implementado em [`server/hardware/cam.py`](./server/hardware/cam.py). Validacao analoga para capability `"cam"`. `upload-capture` e `live-frame POST` sao endpoints sem auth (o ESP32 nao carrega token) — validacao e feita via capability + chip_id.

| Rota | Metodo | Descricao |
|------|--------|-----------|
| `/<chip_id>/capture` | GET | Enfileira captura |
| `/<chip_id>/upload-capture` | POST | ESP32 envia foto (sem auth, valida capability) |
| `/<chip_id>/image/<file>` | GET | Serve imagem (requer token) |
| `/<chip_id>/start-live` | GET | Inicia live mode |
| `/<chip_id>/stop-live` | GET | Para live mode |
| `/<chip_id>/live-frame` | GET/POST | GET: PWA poll frame, POST: ESP32 push frame |
| `/<chip_id>/last-capture` | GET | URL da ultima captura |

### Gallery (prefixo: `/api/gallery`)

Implementado em [`server/hardware/gallery.py`](./server/hardware/gallery.py). Gerencia a organizacao em pastas das imagens capturadas — listar pastas, listar imagens por pasta, mover entre pastas, deletar em lote. Usado pelo `gallery.js` do PWA. Todas as rotas exigem auth.

---

## PWA (v4.1)

### Funcionalidades
- Lista de modulos com checkbox (seleciona quais mostrar)
- Setas ↑↓ para reordenar (salvo no localStorage)
- `[+ Adicionar Modulo]` → wizard de pareamento via short_id de 4 caracteres
- Conteudo renderizado por capabilities via registry (`moduleRenderers` em `app.js`)
- Long press → desvincular modulo
- Login/registro, tela offline, PWA install/update
- Migracao automatica de token (prefix antigo → novo) no boot
- Galeria com pastas (`gallery.js`): grid, selecao multipla, exclusao em lote, mover entre pastas
- **Push Notifications** (v4.1.0): subscribe automatico 2s apos login, toggle iOS-style no card Reservatorio
- **Timer de nivel baixo** no card Reservatorio: "Nivel baixo ha Xmin Xs" (laranja/vermelho pulsante)
- **Threshold configuravel** (v4.1.7): input numerico "Alerta apos [10] min" (1-120) no card Reservatorio
- **Header de identificacao** nos modulos: icone colorido + nome (Controle Hidro / Controle Farm / Camera)
- **localStates Map per-chipId** (v4.0.16): refactor completo do singleton — cada chip tem estado independente

### Registry Pattern
Para adicionar novo tipo de modulo:
```javascript
moduleRenderers.sensor = {
    label: 'Sensor',
    renderContent: renderModule_sensor,
    getStatusText: (data) => data ? `${data.ph} pH` : 'Offline'
};
```

### Bug fixes criticos (v4.0.11-v4.1.7)

**Estado per-chipId (v4.0.11-v4.0.12):** `localState`, `pendingCommands` e `lastToggleTimes` sao todos chaveados por chipId. Antes, eram globais — clicar em um botao de qualquer modulo afetava visualmente todos os modulos por 35s (cooldown).
- `localState` usa `__chipId` + validacao antes de aplicar
- `pendingCommands` usa keys compostas `${chipId}:${device}`
- `lastToggleTimes` e um Map `{}` per-chipId (era `lastToggleTime` global). Polling loop checa cooldown per-chip com `continue` em vez de `return` (v4.0.12).

**Merge de server_keys (v4.0.13):** `register_module()` em `models/modules.py` protegia `phases`, `num_phases`, `start_date` como "server_keys" — o ESP32 mandava dados mas o servidor mantinha valores antigos do banco. Causava dessincronizacao entre `start_date` do banco e `cycle_day` calculado pelo ESP32. Fix: esses 3 campos foram removidos de `server_keys`. ESP32 e fonte de verdade para fases/config.

**Recalculo de cycle_day no cliente (v4.0.14):** O PWA agora recalcula `cycle_day` e `phase` no navegador usando `Date()` do browser (mais confiavel que o relogio do ESP32 que pode ter NTP desincronizado). Implementado em `loadCtrlStatus()` antes de `renderDashboard()`.

**localStates Map (v4.0.16):** refactor completo — `localState` singleton virou `localStates` Map per-chipId. Elimina qualquer chance de vazamento de estado entre modulos.

**Flash visual eliminado (v4.0.17):** `renderSelectedContent` so recria DOM quando selecao de modulos realmente muda. Antes, cada poll reconstruia os cards e causava flash visual.

**Headers de modulo (v4.0.18-23):** icone colorido + label de identificacao nos cards (Controle Hidro / Controle Farm / Camera). Labels renomeados: "Controle" → "Controle Hidro", "Camera" → "Camera".

**VAPID keys vazamento (v4.1.0):** keys VAPID foram commitadas no docker-compose.yml, GitGuardian detectou. Keys rotacionadas e movidas para `.env` na VPS (nunca no repo).

**Timer perdido entre deploys (v4.1.0):** `low_since` era so em RAM no AlertManager. Apos restart do container, timer zerava. Fix: `low_since` salvo em `ctrl_data` no banco e restaurado no boot.

**AlertManager merge (v4.1.0):** recebia `ctrl_data` raw do ESP32 (que nao tem `low_since`). Fix: merge dados do banco (`low_since`, `alert_threshold_min`) com dados do ESP32 (`level_low`) antes de processar.

**Email RFC 5322 (v4.1.0):** Gmail rejeitava emails sem `Message-ID` e `Date` headers. Adicionados como obrigatorios no envio SMTP.

**sqlite3.Row (v4.1.0):** `sqlite3.Row` nao tem `.get()` — substituido por `row["campo"]` direto com try/except.

**notification_email (v4.1.0):** email de alertas separado do email de login — nova coluna `notification_email` na tabela `users`.

### Versionamento
- **Fonte unica:** `APP_VERSION` em [`server/config.py:24`](./server/config.py) (atualmente `"4.1.22"`)
- O `sw.js` e o `manifest.json` sao **gerados dinamicamente** em [`server/app.py:372-436`](./server/app.py) — nao sao arquivos estaticos. O Service Worker usa `CACHE_NAME = cultivee-v + APP_VERSION`, entao bater o numero invalida o cache automaticamente.
- `FIRMWARE_VERSION` nos 3 produtos ([`products/hidro.h:11`](./products/hidro.h), [`products/hidro-farm.h:16`](./products/hidro-farm.h), [`products/cam.h:11`](./products/cam.h)) deve ser mantido sincronizado com `APP_VERSION` **manualmente** — nao ha script que faca isso.
- **Incrementar versao** ao fazer deploy com mudancas visuais (CSS/JS/template). Sem isso, o SW entrega cache antigo ate invalidar sozinho (pode levar horas/dias).

---

## Camada de USUARIO (v4.1.12-4.1.22)

Feature enorme adicionada em rodadas: autenticacao completa, perfil, LGPD, 2FA.
Implementada em `server/usuario/` como blueprints separados.

### Autenticacao (`server/usuario/auth.py` — prefixo `/api/auth`)

| Rota | Metodo | Descricao |
|---|---|---|
| `/register` | POST | Cadastro. Exige `accepted_terms=true` + valida formato de email + senha >= 6 chars. Dispara email de verificacao automaticamente. Rate-limit 5/5min por IP |
| `/login` | POST | `{email, password}` → token (30 dias). Se usuario tem 2FA ativo, primeiro retorna `401 {totp_required: true}`; repetir com `totp_code`. Rate-limit 10/1min |
| `/me` | GET | Dados do usuario logado (inclui `role`, `email_verified`) |
| `/logout` | POST | Invalida o token atual |
| `/forgot-password` | POST | Envia email com link de reset (valido 1h). Anti-enumeration: sempre retorna 200 mesmo pra email inexistente. Rate-limit 3/15min |
| `/reset-password` | POST | `{token, password}` — valida token + atualiza senha. One-shot (token marcado como usado) |
| `/verify-email` | GET/POST | Consome token de verificacao (via link no email ou chamada do PWA) |
| `/resend-verification` | POST | Reenviar email de verificacao pro user logado. Rate-limit 3/10min |

**Rate limiting:** in-memory por IP+endpoint (`_rate_store` dict). Nao escala multi-worker, mas serve pro MVP. Migrar pra Redis quando for preciso.

**Password hashing:** SHA-256 + salt aleatorio de 16 bytes (`salt:hash` format em `password_hash`). Considerar migrar pra bcrypt/argon2 no futuro.

### Perfil do usuario (`server/usuario/profile.py` — prefixo `/api/profile`)

Todas as rotas exigem auth e operam **apenas na propria conta** do usuario.

| Rota | Metodo | Descricao |
|---|---|---|
| `/` | GET | Retorna perfil completo (sem `password_hash`). Inclui `email_verified`, `totp_enabled`, `role` |
| `/` | PUT | Atualiza campos (whitelist em `PROFILE_EDITABLE_FIELDS`): `name`, `phone`, `birth_date`, `notification_email`, endereco (CEP, street, number, complement, neighborhood, city, state), dados fiscais (`person_type='pf'/'pj'`, `tax_id`, `company_name`). Tentativas de alterar `role`, `email` ou `password_hash` sao silenciosamente ignoradas |
| `/` | DELETE | Deleta a conta. Exige senha atual. Protege ultimo admin. Cascade: remove tokens/subs/reset tokens, despareia modulos, preserva audit_log/alert_log |
| `/password` | POST | Troca de senha. `{current_password, new_password}`. Ao concluir, invalida TODOS os outros tokens do user (sessao atual mantida) |
| `/cep/<cep>` | GET | Proxy pra ViaCEP. Evita CORS e permite cache futuro. Retorna campos normalizados (street, neighborhood, city, state) |
| `/export` | GET | Baixa JSON com todos os dados do user (LGPD — portabilidade). Filename `cultivee-dados-YYYYMMDD.json` |
| `/2fa/setup` | POST | Gera secret TOTP (base32) + URI pro QR code. Nao ativa ainda |
| `/2fa/enable` | POST | `{code}` — confirma primeiro codigo, ativa 2FA. Tolera +/-30s drift |
| `/2fa/disable` | POST | `{password, code}` — desativa exigindo senha + codigo valido |
| `/sessions` | GET | Lista tokens ativos com `user_agent`, `ip`, `last_used_at`, `created_at`, `scope`. Marca `is_current=true` no atual |
| `/sessions/<id>` | DELETE | Revoga uma sessao especifica (valida ownership) |
| `/sessions/revoke-others` | POST | Revoga tudo exceto a atual |

**2FA TOTP** (v4.1.22): usa `pyotp` (Google Authenticator, Authy, 1Password compativel). UI mostra QR code via API externa `api.qrserver.com` (free, sem auth).

### Roles e permissoes

| Role | Descricao |
|---|---|
| `user` | Default. Cliente comum — ve/controla so os proprios modulos |
| `support` | (Reservado) — atendente futuro |
| `admin` | Acesso total a `/api/admin/*` + gerencia outros users |

**Bootstrap:** na migracao `v4.1.13`, se nao houver admin no sistema, user `id=1` e promovido automaticamente. `count_admins()` garante que nao da pra rebaixar o ultimo admin.

---

## Camada de ADMIN (v4.1.13-4.1.22)

`server/admin/admin.py` com prefixo `/api/admin`. Todas as rotas protegidas por `@require_admin` (401 sem auth, 403 sem role=admin).

### Gerenciamento

| Rota | Metodo | Descricao |
|---|---|---|
| `/stats` | GET | Contadores agregados: total/online de modulos, users/admins, alertas 24h, push subs |
| `/users` | GET | Lista todos os usuarios com contagem de modulos + `last_token_at` estimado |
| `/users/<id>` | GET | Detalhes de um user + modulos pareados |
| `/users/<id>/role` | POST | `{role: 'user'/'support'/'admin'}`. Protege ultimo admin |
| `/users/<id>/force-password-reset` | POST | Gera reset token (1h) + envia email pro user + revoga TODOS os tokens ativos |
| `/users/<id>/impersonate` | POST | `{minutes: 5-240, view_only: bool}` — gera token curto pro user alvo. Bloqueia: impersonar a si mesmo, impersonar outro admin, user inexistente. Notifica outros admins por email |
| `/modules` | GET | Lista todos os modulos do sistema com dono (JOIN user_email) |
| `/modules/<chip_id>/transfer` | POST | `{new_user_id, new_name?}` — muda dono do modulo entre users |
| `/audit` | GET | Audit log paginado com filtros: `action`, `admin_id`, `from` (date), `to` (date), `limit`, `offset` |

### Audit log

Tabela `audit_log` registra todas as acoes administrativas. Campos: `admin_id`, `admin_email`, `action`, `target_type`, `target_id`, `target_label`, `details` (JSON), `ip`, `user_agent`, `created_at`.

Acoes registradas atualmente:
- `impersonate` — quando admin usa "Acessar como"
- `user.role_change` — mudanca de role
- `user.force_password_reset` — reset forcado
- `module.transfer` — transferencia entre users

**Retencao:** audit_log e alert_log sao PRESERVADOS mesmo quando user e deletado (compliance + historico legal). Outros dados do user sao cascade-removidos.

### Impersonation (Fase 2 admin)

Fluxo pra admin ver a aplicacao como outro user veria:
```
admin clica "Acessar como" (escolhe minutes + view_only)
  → POST /api/admin/users/<id>/impersonate
  → backend gera token de 30min (ou customizado 5-240), scope 'full' ou 'readonly'
  → PWA guarda token do admin em localStorage (keys `_imp_token`, `_imp_user`)
  → troca token ativo pelo do alvo + reload
  → Banner laranja/vermelho no topo: "Acessando como X ...Voltar pra admin"
  → Clicar Voltar: restaura token do admin, reload
```

**scope=readonly** (view_only=true): middleware em `app.py::_readonly_scope_guard` bloqueia qualquer mutacao — inclusive GETs legados como `/relay`, `/capture`, `/save-config`.

---

## Compliance LGPD (v4.1.20)

O Cultivee atende aos requisitos basicos da LGPD (Lei 13.709/2018):

**Consentimento:**
- Cadastro exige checkbox "Aceito Termos de Uso e Politica de Privacidade"
- Timestamp de aceite armazenado em `users.terms_accepted_at`
- Paginas publicas: `/termos` e `/privacidade` (templates em `server/templates/terms.html`, `privacy.html`)

**Direitos do titular (Art. 18):**
- **Confirmacao e acesso:** `GET /api/profile/` retorna tudo (sem hash)
- **Correcao:** `PUT /api/profile/` com whitelist
- **Portabilidade:** `GET /api/profile/export` → JSON com dados pessoais + modulos pareados + alertas recebidos
- **Exclusao:** `DELETE /api/profile/` → cascade (remove user, tokens, subs; despareia modulos; preserva historico anonimizado em audit_log/alert_log)
- **Revogacao:** user pode remover consentimento deletando a conta
- **Oposicao ao tratamento:** desativar notificacoes no profile (`notification_email=""`)

**Verificacao de email** (v4.1.20):
- Novos cadastros recebem email com link `/?verify=TOKEN`
- Coluna `users.email_verified_at` marca quando confirmou
- Banner azul na UI pede pra confirmar (com botao "Reenviar")
- Users antigos (pre-v4.1.20) foram marcados como verificados no bootstrap da migracao

---

## Seguranca (v4.1.12-4.1.22)

**Rate limiting** (in-memory por IP+endpoint em `usuario/auth.py`):
- `/register` — 5 req / 5 min
- `/login` — 10 req / 1 min (anti brute-force)
- `/forgot-password` — 3 req / 15 min
- `/reset-password` — 5 req / 5 min
- `/resend-verification` — 3 req / 10 min
- `impersonate`, `role change`, admin actions — sem rate limit (assume trust)

**2FA TOTP** (v4.1.22) — opt-in por user. Quando ativo, login exige `totp_code` no segundo request.

**Session management** (v4.1.22) — user ve todos os seus tokens (`user_agent`, `ip`, `last_used_at`) em "Meus dispositivos" e pode revogar individualmente ou em massa.

**CAPTCHA Turnstile** (v4.1.22 scaffolding) — implementacao completa que se auto-desativa se `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET` nao estiverem no env. Admin ativa quando quiser — sem necessidade de mudanca de codigo.

**Anti-enumeration:** `/forgot-password` sempre retorna 200 pra emails invalidos ou inexistentes. Evita que atacante descubra quais emails estao cadastrados.

**Impersonation audit:** toda impersonation gera entrada no `audit_log` + email pra outros admins (transparencia multi-admin).

**Security headers** (v4.1.23) — todas as respostas HTML tem headers defensivos aplicados por `@app.after_request` em `app.py`:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (so em HTTPS — navegador ignora via HTTP)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`: desativa camera/mic/geolocation/payment/usb/accelerometer/gyroscope/magnetometer do browser (nao usamos)
- `Content-Security-Policy`: `default-src 'self'`; libera `'unsafe-inline'` + `'unsafe-eval'` pra scripts (scripts inline no template + Turnstile), `fonts.googleapis.com`/`fonts.gstatic.com` (Google Fonts), `challenges.cloudflare.com` (CAPTCHA), `api.qrserver.com` (QR do 2FA)

Headers sao pulados em endpoints do ESP32 (register, poll, firmware GET, upload-capture, live-frame POST) pra economizar banda — ESP32 ignora mesmo e cada header custa ~500 bytes/poll. CSP so em respostas `text/html` (nao em JSON/imagens).

**ProxyFix do Werkzeug** (v4.1.23) — aplicado em `app.wsgi_app` pra honrar headers `X-Forwarded-*` do Traefik (scheme, host, IP real). Sem isso, `request.scheme` sempre voltaria `"http"` mesmo atras de HTTPS, e HSTS nao funcionaria. Tambem corrige `request.remote_addr` pra IP real do cliente (importante pra rate limiting e audit log).

---

## Infraestrutura

### VPS
- **IP:** 129.121.50.168
- **SSH:** `ssh -i "D:/01-projetos-claude/.credentials/id_rsa" -p 22022 root@129.121.50.168`
- **SO:** Ubuntu 24.04
- **Stack:** Docker + Traefik + Let's Encrypt

### Containers

| Container | Servico | Porta interna | Dominios |
|-----------|---------|---------------|----------|
| `cultivee-app` | Servidor unificado (Flask/Gunicorn 2w x 4t) | 5002 | `app.cultivee.com.br` |

**Duas entradas Traefik no mesmo container** (labels em [`docker-compose.yml`](./docker-compose.yml)):
- `cultivee-app` em `websecure` (HTTPS via Let's Encrypt) → usuarios acessando o PWA no navegador
- `cultivee-app-http` em `web` (HTTP puro, **sem redirect para HTTPS**) → ESP32 fazendo `POST /api/modules/register`, upload de fotos, poll de comandos

Esse split e intencional: o Traefik global tem middleware `https-redirect@file` que redireciona HTTP→HTTPS para todos os outros sites, mas **nao** e aplicado no router `cultivee-app-http`. ESP32 nao faz TLS, e forcar HTTPS quebraria todo o fluxo de registro do hardware.

**Volume externo:** `cultivee_cultivee-data` (declarado como `external: true` no compose) — persiste `/app/data/cultivee.db` e `/app/data/captures/`, `/app/data/thumbs/`, `/app/data/live/`. Criar uma vez com `docker volume create cultivee_cultivee-data` no primeiro deploy.

**Rede externa:** `web` (tambem `external: true`) — compartilhada com os outros containers da VPS (Traefik, outros sites).

> Site (cultivee.com.br) — codigo em [`../Site/`](../Site/), roda em container separado `cultivee-site` com proprio `docker-compose.yml`. Ver [`../Site/CLAUDE.md`](../Site/CLAUDE.md).

### Deploy

Duas formas de disparar:

1. **Automatico via GitHub Actions** (preferido) — push para `main` dispara [`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml), filtrado por paths (`server/**`, `docker-compose.yml`, `.github/workflows/**`). Pushes so em `firmware/**` ou `products/**` **nao** deploy — firmware e gravado local via USB/OTA, nunca pela pipeline. A action usa `appleboy/ssh-action@v1` com secret `VPS_SSH_KEY`, clona o repo na VPS, `rsync` para `/opt/sites/cultivee-platform/`, para containers antigos e roda `docker compose build --no-cache && docker compose up -d`. Tambem suporta `workflow_dispatch` para disparo manual.

2. **Manual via `deploy.sh`** (fallback) — do diretorio local:
    ```bash
    cd "D:/01-projetos-claude/00-Sites/site-cultivee.com.br/cultivee-platform"
    bash deploy.sh
    ```
    Empacota `app.py`, `config.py`, `notifications.py`, os pacotes `models/`, `hardware/`, `usuario/`, `admin/`, `requirements.txt`, `Dockerfile`, `static/`, `templates/` + `docker-compose.yml`, envia via `scp`, para containers antigos e rebuilda. Nao envia firmware nem arquivos de dados. Tudo numa unica sessao SSH (respeita a regra de `fail2ban`).

3. **OTA Remoto** (firmware, v4.0.15+) — envia .bin compilado localmente ao servidor, ESP32 baixa no proximo poll:
    ```bash
    # Compilar sem upload
    bash compile.sh                  # Hidro
    bash compile-hidrofarm.sh        # Hidro-Farm

    # Enviar ao servidor (requer token de usuario autenticado)
    bash ota-remote.sh <chip_id> build/firmware.ino.bin <token>

    # Cancelar OTA pendente
    curl -X DELETE -H "Authorization: Bearer <token>" https://app.cultivee.com.br/api/modules/<chip_id>/firmware
    ```
    O ESP32 recebe `firmware_url` na proxima resposta de `/api/modules/register` e faz OTA automaticamente. Requer firmware >=v4.0.15 ja gravado (bootstrap via USB ou OTA local).

Verificar logs/status:
```bash
ssh -p 22022 -i "D:/01-projetos-claude/.credentials/id_rsa" root@129.121.50.168 "docker logs cultivee-app --tail 50"
ssh -p 22022 -i "D:/01-projetos-claude/.credentials/id_rsa" root@129.121.50.168 "docker ps --filter name=cultivee-app"
```

### DNS (Cloudflare)
- **Conta:** mardo.abc@gmail.com
- `cultivee.com.br` + `www.cultivee.com.br` → proxied (Cloudflare CDN + SSL na borda) — servido pelo container do subprojeto [`../Site/`](../Site/)
- `app.cultivee.com.br` → **DNS only** (nao proxied — precisa ser DNS-only porque ESP32 acessa HTTP puro e Cloudflare forcaria HTTPS)
- `mail.cultivee.com.br` → **DNS only** (proxy Cloudflare DESATIVADO — SMTP nao funciona com proxy). Aponta para IP da HostGator `162.241.61.84`

### Email (SMTP)
- **Remetente:** `contato@cultivee.com.br` (caixa na HostGator)
- **SMTP:** SSL porta 465, host `mail.cultivee.com.br` (IP direto `162.241.61.84`)
- **SPF:** TXT record no Cloudflare: `v=spf1 include:_spf.hostgator.com.br a:162.241.61.84 ~all`
- **Headers obrigatorios** (RFC 5322, exigido pelo Gmail): `Message-ID` e `Date`
- **Credenciais:** no `.env` da VPS (SMTP_USER, SMTP_PASS) — NAO no repo
- **Proxy Cloudflare:** DEVE estar desativado para `mail.cultivee.com.br` — SMTP nao passa por proxy HTTP

### VAPID Keys (Web Push)
- Geradas via `pywebpush` e configuradas no `.env` da VPS (VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS_EMAIL)
- **NUNCA commitar no repo** — GitGuardian detectou vazamento quando estavam no `docker-compose.yml`; keys foram rotacionadas
- A public key e injetada no template `index.html` via config do Flask para o `pushManager.subscribe()`

### Desenvolvimento local

```bash
cd server/

# Servidor unificado (preferido — cobre todos os prefixos)
python run-app.py                   # porta 5002

# Alternativa: servidor dedicado para testes de Hidro (DB separado)
python run-hidro.py                 # porta 5002, DB em data/cultivee-hidro.db

# Simuladores de hardware (em terminais separados — dev sem ESP32)
python -u sim_esp32.py hidro        # hidro      — codigo de pareamento: SH01
python -u sim_esp32.py hidro-farm   # hidro-farm — codigo de pareamento: HF01
python -u sim_esp32.py cam          # cam        — codigo de pareamento: CA01

# Smoke tests HTTP
python test_routes.py
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

### Atualizar firmware remotamente (OTA remoto, v4.0.15+)
1. Ajustar `config.h` (produto + ambiente = `ENV_PRODUCTION`)
2. Compilar sem upload: `bash compile.sh` (Hidro) ou `bash compile-hidrofarm.sh` (Hidro-Farm)
3. Obter token de usuario autenticado (login via API ou copiar do localStorage do PWA)
4. Enviar: `bash ota-remote.sh <chip_id> build/firmware.ino.bin <token>`
5. Aguardar proximo poll do ESP32 (ate `poll_interval` segundos, default 30s)
6. ESP32 reinicia automaticamente apos OTA — verificar nova versao no PWA
7. Se precisar cancelar: `curl -X DELETE -H "Authorization: Bearer <token>" https://app.cultivee.com.br/api/modules/<chip_id>/firmware`

**Pre-requisito:** firmware >=v4.0.15 ja gravado no ESP32 (primeira vez sempre via USB ou OTA local).
**Cam suporta desde v4.1.8** — migrou de `no_ota` para `min_spiffs`. Primeira gravacao pos-migracao exige USB (muda partition table); depois disso, OTA remoto funciona igual aos outros produtos.

### Alterar docker-compose.yml
1. Editar no REPOSITORIO (nunca no servidor)
2. `bash deploy.sh` envia automaticamente

---

## Adicionar Novo Modulo

Exemplo: modulo "sensor":

### Firmware (3 arquivos)
1. `firmware/mod_sensor.h` — `sensor_setup()`, `sensor_loop()`, `sensor_register_routes()`, `sensor_dashboard_html()`, `sensor_dashboard_js()`, `sensor_process_command()`, `sensor_status_json()`, `sensor_register_json()`
2. `products/sensor.h` — `#define MOD_SENSOR`, MODULE_TYPE, pinos, SERVER_URL, APP_URL
3. `firmware/firmware.ino` — adicionar `#ifdef MOD_SENSOR` nos pontos de integracao. Se o novo modulo reusa variaveis globais de outro (ex: compartilhar `struct Phase` com hidro), expandir os guards existentes de `#ifdef MOD_HIDRO` para `#if defined(MOD_HIDRO) || defined(MOD_SENSOR)` E declarar exclusao mutua com `#if defined(MOD_HIDRO) && defined(MOD_SENSOR) #error`.

### ⚠ Codigo compartilhado em `core_*.h`
Se o modulo usa hardware ja implementado nos cores (RTC DS3231 em `core_wifi.h`, LED em `core_server.h`, etc.), **atualizar os guards `#ifdef` nesses arquivos** para incluir o novo `MOD_*`. Foi a causa raiz do bug de compilacao ao adicionar o hidro-farm — 3 blocos em `core_wifi.h:75,157,169` estavam em `#ifdef MOD_HIDRO` e precisaram virar `#if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)`. O compilador vai falhar com `'rtcAvailable' was not declared in this scope` se esquecer disso.

Regra geral: **se o recurso de hardware nao pertence exclusivamente a um produto**, use `defined(MOD_A) || defined(MOD_B)`. O guard so deve ser `#ifdef MOD_X` sozinho quando o recurso e **realmente unico** daquele produto (ex: camera em `mod_cam.h`).

### Servidor (2 arquivos)
4. `server/bp_sensor.py` — Flask Blueprint com rotas do sensor (valida capability `"sensor"`)
5. `server/app.py` — registrar blueprint: `app.register_blueprint(sensor_bp, url_prefix="/api/sensor", name="sensor")`

### PWA (1 registro + eventual ajuste no `loadCtrlStatus`)
6. `server/static/app.js` — adicionar no registry:
```javascript
moduleRenderers.sensor = {
    label: 'Sensor',
    renderContent: renderModule_sensor,
    getStatusText: (data) => ...
};
function renderModule_sensor(container, mod) { ... }
```
Se a capability tiver prefixo comum a outra ja existente (ex: `"hidro-sensor"` vs `"hidro"`), atualizar o helper `getCtrlContainer()` e evitar seletores `[id^="..."]` que capturam por prefixo.

### Infra (2 configs)
7. DNS: `sensor.cultivee.com.br` → DNS only no Cloudflare
8. `docker-compose.yml`: adicionar subdominio nos labels do Traefik

**OTA remoto e herdado automaticamente** por qualquer modulo novo que use `core_register.h` (todos usam). Nao precisa de codigo adicional — `registerOnServer()` ja checa `firmware_url` e `performRemoteOTA()` e generico. Desde v4.1.8, todos os produtos (Hidro, Hidro-Farm, Cam) usam particao `min_spiffs` e suportam OTA nativamente. Se criar um produto novo, usar `min_spiffs` — nunca `no_ota`.

**Total: ~4 arquivos novos, ~15 linhas em existentes. Verificar SEMPRE os guards em `core_*.h`.**

---

## Informacoes do Desenvolvedor
- **Git:** Mardoqueu Costa (mardo.abc@gmail.com)
- **Arduino CLI:** `C:/Users/user/arduino-cli/arduino-cli.exe`
- **WiFi teste:** Mardo-Dri / mardodri1609

---

## Changelog

Historico de versoes significativas. Formato: **`vX.Y.Z`** — `feat`/`fix`/`refactor`: descricao.

### v4.1.x — Commercial-grade (2026-04)

- **v4.1.33** — `feat`(monitoring): incidentes da plataforma marcam retroativamente quedas dos modulos como `reason='server_down'` e ficam excluidos do `uptime_pct` (mas somados em `uptime_pct_raw`). Webhook HMAC-SHA256 (`POST /api/platform-incident`, anti-replay 5min) recebe do CF Worker quando abre/fecha incidente; handler faz `upsert_platform_incident(webhook_id, ...)` idempotente + `mark_module_events_as_server_down(start, end)` UPDATE retroativo. `get_module_uptime_summary` agora suporta `exclude_server_down=True` (default) e retorna ambos os calculos (`uptime_pct` filtrado + `uptime_pct_raw` bruto + `offline_count_raw` + `server_down_seconds`). Frontend: badge cinza "SERVIDOR" em vez de "OFFLINE" nos eventos marcados, aviso azul no topo do modal ("N quedas excluidas... uptime bruto: X%"), aviso laranja v4.1.32 continua mostrando os incidentes do Worker em paralelo. CF Worker: `postIncidentToVPS(incident)` em `openIncident`/`closeIncident` usa Web Crypto (`crypto.subtle.sign` HMAC-SHA256) — best-effort com log em caso de falha. Secret `PLATFORM_INCIDENT_SECRET` provisionado via `bash deploy.sh` (envia como env secret do Worker via API CF) + `.env` da VPS (requer `docker compose up -d --force-recreate app` — `restart` sozinho nao re-le env_file). Nova tabela `platform_incidents` (webhook_id UNIQUE + start_at, end_at, reason). Endpoint fica silenciosamente desativado (401 `webhook_disabled`) se `PLATFORM_INCIDENT_SECRET` nao estiver no env.
- **v4.1.32** — `feat`(monitoring): card "Status da plataforma" no topo do painel admin + cruzamento com uptime dos modulos. Card consome direto `status.cultivee.com.br/check` (sem proxy pela VPS — nao depende dela pra ver se ela caiu); mostra estado por componente (healthy/latency/uptime 7d), ultima checagem e incidentes em curso. No modal de uptime (user+admin), aviso laranja listando incidentes do servidor que coincidem com o periodo exibido. Backend: `/check` do Worker agora retorna snapshot consolidado do KV (overall + components + uptime + incidents) com `Access-Control-Allow-Origin: *` + `Cache-Control: public, max-age=30`; `?live=1` mantem o probe ao vivo antigo. `snapshotToJson` + `buildStatusSnapshot` compartilhados entre HTML e JSON. CSP da VPS libera `connect-src https://status.cultivee.com.br`. Fix de infra: cron Worker `*/2` -> `*/5` + acumulador diario in-place dentro de `current:` pra caber no free tier KV (1k writes/dia, antes estourava com 2.880/dia).
- **v4.1.31** — `feat`(monitoring): historico persistente online/offline dos modulos (retencao 90 dias). Nova tabela `module_status_events` guarda cada transicao como linha (status, occurred_at, duration_seconds, reason, rssi). Helpers em `models/modules.py`: `record_module_status` (transicao ao register), `compute_module_status_lazy` (detecta offline silencioso quando `last_seen > 120s`), `get_module_uptime_summary` (agrega uptime%, quedas, maior offline) e `get_module_status_events` (timeline). Integrado em `register_module` (grava online) + `list_modules` (dispara compute_lazy pra capturar offline silencioso). Cleanup lazy: init_db + 1 a cada 1000 registers. Endpoints novos: `GET /api/modules/<chip>/uptime?days=N` (dono) e `GET /api/admin/modules/<chip>/uptime?days=N` (admin). Frontend: card do modulo do usuario ganha linha "Uptime 7d: 99.2% · 1 queda" com link "Ver historico" que abre modal (7d/30d/60d toggle, stats + lista de 20 eventos recentes). Tabela admin ganha coluna "Uptime 7d" + botao "Historico" (usa o mesmo modal via flag `isAdmin`). Cache de 60s no fetch inline pra nao bater no endpoint a cada poll.
- **v4.1.30** — `fix`(profile): botao "Salvar dados fiscais" proprio no card (saveProfile() ja enviava esses campos no payload, mas a UX confundia sem botao visivel). Feedback agora escreve nos 2 <p> (profile-save-msg + profile-fiscal-save-msg) pra confirmar perto do botao clicado.
- **v4.1.29** — `feat`(auth): 2FA por **email** como alternativa ao TOTP. Usuario que nao quer instalar app authenticator pode ativar 2FA com codigo enviado por email a cada login (6 digitos, valido 10min, single-use, plain no DB seguindo padrao de password_reset_tokens). Mutuamente exclusivo com TOTP (UI desabilita botao do outro quando um ja esta ativo). Backend: tabela `email_2fa_codes`, coluna `users.email_2fa_enabled`, helpers `create_email_2fa_code`/`verify_email_2fa_code`/`enable_email_2fa`/`disable_email_2fa` em `models/users.py`, 3 rotas em `usuario/profile.py` (`/2fa/email/setup`, `/enable`, `/disable`), integracao no `usuario/auth.py` login (`email_otp_required: true` na 1a chamada, valida na 2a), template de email em `notifications.py` (`send_email_2fa_code`). Frontend: nova secao no perfil (Seguranca) abaixo do TOTP, 2 modais (setup com 2 etapas + disable com senha+codigo), input dinamico no login com botao "Reenviar codigo". Schema: `email_2fa_enabled` em `users` + tabela `email_2fa_codes`. Rota `/api/auth/me` agora expoe `totp_enabled` e `email_2fa_enabled` pra UI sincronizar estado.
- **v4.1.28** — `refactor`: migracao do legado `MODULE_TYPE="ctrl"` para `"hidro"`. Antes, o produto Hidro reportava `type="ctrl"` e as rotas eram `/api/ctrl/*` — inconsistente com Hidro-Farm e Cam que ja usam `MODULE_TYPE == capability`. Migracao backward-compatible em 3 commits: (1) backend normaliza `ctrl->hidro` + blueprint duplo `/api/hidro` (novo) + `/api/ctrl` (alias deprecated com log) + migracao idempotente do DB via `UPDATE modules SET type='hidro' WHERE type='ctrl'` no `init_db`; (2) firmware Hidro `products/hidro.h` passa a reportar `MODULE_TYPE="hidro"` + `MDNS_NAME="cultivee-hidro"` (legado `cultivee-ctrl.local` deixou de existir); (3) renomeia `server/run-ctrl.py` -> `server/run-hidro.py` (git mv preserva historico), `sim_esp32.py` aceita "hidro" como produto primario (chip_id `SIM_HIDRO_0001`/short `SH01`) + alias "ctrl" deprecated, `test_routes.py` usa `/api/hidro` por padrao. Sem `ctrl_data` (nome de campo legitimo) nem APIs `esp_camera` (`set_exposure_ctrl`, etc.) foram tocadas. Alias `/api/ctrl/*` mantido por ~1 semana pra nao quebrar PWAs cacheados; remover em v4.1.29 se logs `[deprecated]` pararem.
- **v4.1.27** — `feat`(admin): OTA remoto direto no painel admin. Novo botao "Firmware" na tabela de modulos abre modal que calcula SHA-256 client-side (crypto.subtle), faz upload multipart para `POST /api/admin/modules/<chip>/firmware` (exige role=admin), grava `.bin + .sha256` e registra em `audit_log` com action `module.firmware_upload`. GET e DELETE tambem expostos (status + cancelar). Elimina a fricao de precisar do token do dono via `ota-remote.sh` (legacy, mantido). Limite 3MB por upload.
- **v4.1.26** — `feat`+`fix`: rodada completa de hardening pre-comercial. **Segurança:** path traversal corrigido em `hardware/cam.py` (helper `_safe_join`), `MAX_CONTENT_LENGTH=6MB` global + `MAX_UPLOAD_BYTES=5MB` por request, senha migra para `bcrypt` (rounds=12) transparentemente no login (rehash automatico), escape HTML em todos os `innerHTML` de dados (lista de modulos, fases, admin users/modules). **LGPD:** `delete_user_cascade` agora purga `captures/`, `thumbs/`, `live/` e firmware pendente do usuario excluido. **Firmware:** brownout detector nivel 4 (~2.7V), telemetria + protecao de heap com `min_free_heap` (restart <5kB), timeout 30min em `MODE_SETUP`, validacao SHA-256 obrigatoria no OTA remoto (firmware aborta e preserva versao anterior se hash nao bater), rollback A/B manual por NVS + `esp_ota_set_boot_partition` se 3 boots consecutivos falharem self-test. **Ops:** `sync-version.sh` alinha `FIRMWARE_VERSION` ao `APP_VERSION`, `backup-vps.sh` com `.backup` online + manifest SHA-256 e fluxo `--restore`. **Docs:** [`docs/manual-usuario.md`](./docs/manual-usuario.md) consumidor final, [`docs/operacao.md`](./docs/operacao.md) Uptime Robot + incidente, [`docs/lgpd-aipd.md`](./docs/lgpd-aipd.md) AIPD draft, [`docs/termos-uso.md`](./docs/termos-uso.md) minuta legal, [`docs/license-gate.md`](./docs/license-gate.md) modelo de monetizacao.
- **v4.1.25** — `feat`(admin): modal custom com dropdown pra alterar nivel do user (antes era `prompt()` do navegador — feio, permitia digitacao livre, ruim em mobile). Segue o mesmo padrao visual do modal de impersonation (header + botao fechar + Cancelar + acao primaria). Cada opcao do select tem descricao curta do que o nivel faz.
- **v4.1.24** — `i18n`(admin): traducao completa da area administrativa pra PT. Botoes ("Role"→"Nivel", "Reset pwd"→"Resetar senha"), colunas ("Mods"→"Modulos"), badges de nivel ("Support"→"Suporte"), Audit Log→"Registro de Acoes", mapper visual dos action types (`impersonate`→"Acesso como", `user.role_change`→"Mudanca de nivel", etc.). Valores internos da API continuam em ingles (chaves tecnicas, nao quebra filtros nem historico).
- **v4.1.23** — `feat`(security): Rodada 1 de infra comercial. Adiciona security headers completos (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy) via `@app.after_request` — pulados em endpoints do ESP32 pra economizar banda. Aplica `ProxyFix` do Werkzeug pra honrar `X-Forwarded-*` do Traefik (necessario pra HSTS detectar HTTPS, e pra IP real em rate limit/audit).
- **v4.1.22** — `feat`: 2FA TOTP (Google Auth/Authy) + session management ("Meus dispositivos") + CAPTCHA scaffolding (Turnstile, auto-desativado sem env keys). Novas colunas: `users.totp_secret/totp_enabled`, `tokens.user_agent/ip/last_used_at`. Depends `pyotp`.
- **v4.1.21** — `feat`: admin operacional — promover/rebaixar role (`POST /api/admin/users/<id>/role`), forcar reset de senha (`/force-password-reset`), transferir modulo (`/modules/<chip>/transfer`), audit log com filtros (action, admin_id, from, to).
- **v4.1.20** — `feat`: compliance LGPD + NF-e + verificacao de email + termos. Campos fiscais (PF/PJ, CPF/CNPJ, razao social). Endpoints `DELETE /api/profile/` e `GET /api/profile/export`. Paginas publicas `/termos` e `/privacidade`. Aceite obrigatorio no cadastro.
- **v4.1.19** — `feat`: admin entra direto no painel de admin apos login (padrao SaaS).
- **v4.1.18** — `fix`: `loadModules` travava em "Carregando..." pra users com 0 modulos (`_lastModulesKey=''` colidia com chave vazia).
- **v4.1.17** — `refactor`: split blueprints por camada (`hardware/`, `usuario/`, `admin/`). Zero breaking change — git mv preserva historico.
- **v4.1.16** — `feat`: area de perfil completa (nome, telefone, endereco BR com ViaCEP, dados fiscais) + troca de senha com verificacao de senha atual + menu dropdown na navbar. Refactor `models.py` -> pacote `models/` (db, users, modules, push, audit).
- **v4.1.15** — `feat`: admin Fase 3 — audit_log persistido no banco, modo readonly com middleware `@before_request`, duracao configuravel de impersonation (5-240min), notificacao email pra outros admins.
- **v4.1.14** — `feat`: admin Fase 2 — impersonation completa com banner fixo no topo, restauracao de sessao original.
- **v4.1.13** — `feat`: admin Fase 1 — painel de admin (stats, users, modules, audit). Coluna `users.role` + bootstrap automatico do user id=1 como admin.
- **v4.1.12** — `feat`: modulo de autenticacao separado (`bp_auth.py`) + recuperacao de senha completa (forgot-password + reset-password com email) + rate limiting + validacao de email.
- **v4.1.11** — `fix`: PUT `/api/user/prefs` salvava `{}` em vez do payload (body era string ja-stringificada mas o helper `api()` so setava Content-Type quando body era objeto).
- **v4.1.10** — `feat`: persistencia de ordem+selecao de modulos no servidor (antes era so localStorage). Coluna `users.module_prefs`. Migracao automatica.
- **v4.1.9** — `feat`: persistencia do botao "Ao Vivo" da camera apos reload do browser (`cam_live_mode` em ctrl_data + sync servidor).

### v4.1.8 — WiFi telemetry + OTA no Cam

- **v4.1.10 (Cam)** — `feat`: LIVE_MAX_DURATION aumentado de 2min pra 10min.
- **v4.1.9** — `fix` + sync de `cam_live_mode` no register do ESP32.
- **v4.1.8** — `feat`: telemetria WiFi (`wifi_last_error`, `wifi_last_connected_ms`, `wifi_disconnect_count`) + callback `WiFi.onEvent()` + `setAutoReconnect(true)`. Cam migrado de `no_ota` pra `min_spiffs` (agora suporta OTA remoto). Fix: server auto-deleta `.bin` apos download pra evitar loop infinito de OTA.

### v4.1.0-4.1.7 — Alertas push + email

- **v4.1.7** — `fix`: threshold configuravel de alerta (1-120 min), timer persistido em `ctrl_data.low_since`, email SMTP via HostGator.
- **v4.1.0** — `feat`: sistema de alertas completo. Push notifications (VAPID + pywebpush), email SMTP (Message-ID + Date RFC 5322), AlertManager integrado ao register do ESP32.

### v4.0.x — Refactor PWA + OTA Remoto

- **v4.0.16-v4.0.23** — `refactor`: `localStates` Map per-chipId (elimina vazamento de estado entre modulos), `renderSelectedContent` so recria DOM quando selecao muda, headers de modulo (Controle Hidro / Farm / Cam).
- **v4.0.14-v4.0.15** — `feat`: OTA remoto via servidor (ESP32 baixa `.bin` no proximo poll). Flag `otaRemoteAttempted` pra evitar loop.
- **v4.0.11-v4.0.13** — `fix`: estado per-chipId (antes vazava entre modulos no cooldown de 35s), merge de server_keys no register (phases/start_date saem da protecao — ESP32 e fonte de verdade).

---

## Historico do projeto — tres fontes

Se precisar entender "o que mudou quando" ou "por que isso esta assim":

1. **[`CHANGELOG.md`](./CHANGELOG.md)** — changelog formal por versao (Keep a Changelog). Atualize aqui **junto com o commit de bump de `APP_VERSION`**.
2. **[`docs/sessoes/YYYY-MM-DD.md`](./docs/sessoes/)** — log detalhado por rodada de trabalho. Em rodadas longas (varias releases no mesmo dia, decisoes arquiteturais, incidentes operacionais), crie um arquivo novo com: TL;DR, linha do tempo dos commits, decisoes tomadas + alternativas descartadas, erros encontrados + correcoes, licoes aprendidas.
3. **`git log --oneline`** — fonte tecnica "quem mudou qual arquivo". Use quando os outros nao tem o detalhe.

**Regra operacional pra agentes**: ao abrir um PR / fazer release, atualize `CHANGELOG.md` **na mesma rodada** — e, se foi rodada longa, crie tambem o log de sessao. Nao deixe pra depois — depois nao existe.

---

## Quando editar este arquivo?

Sempre que adicionar ou modificar:
- Novo produto (novo `MOD_*` + `products/*.h`)
- Novo blueprint ou camada (adicionar em "Servidor: Blueprints")
- Novos endpoints importantes (adicionar em "Servidor: API")
- Mudanca de schema do banco (migracao + comentario da versao)
- Fluxo critico novo (push, OTA, impersonation, etc.)
- Convencao operacional nova (ex: `docker compose up --force-recreate` pra re-ler env_file)

**Nao editar pra:**
- Bug fixes pequenos/pontuais (vai no commit message)
- Refactors internos que nao mudam interface publica
- Ajustes de UX que nao mudam contrato da API

> Historico de releases vive em [`CHANGELOG.md`](./CHANGELOG.md), nao aqui. A secao "Changelog" acima e mantida por compatibilidade com sessoes antigas e sera esvaziada quando o `CHANGELOG.md` estiver estabilizado.
