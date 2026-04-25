# Changelog

Todas as mudancas relevantes do projeto Cultivee Platform sao documentadas neste arquivo.

O formato segue [Keep a Changelog 1.1.0](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/).

Para contexto mais profundo de decisoes arquiteturais (por que foi feito assim, o que foi descartado), ver `docs/sessoes/YYYY-MM-DD.md` da rodada correspondente.

---

## [Nao lancado]

## [4.1.52] - 2026-04-25

### Mudado (BREAKING — refator de alertas pra independencia per-modulo)
- **Alertas agora sao POR MODULO, totalmente independentes** entre modulos
  do mesmo user. Antes (v4.1.41), prefs eram por (user, alert_type) e o
  catalogo era global — usuario com so Camera via alertas de "level_low"
  irrelevantes; nao dava pra silenciar 1 modulo problematico mantendo
  os outros. Refator alinha com a filosofia central do projeto: "modulos
  sao entidades independentes, servidor e router/storage, nao decisor".
- **`server/notifications.py`**: substituiu `ALERT_CATALOG` global por
  `UNIVERSAL_ALERTS` (4 alertas — todo modulo tem) + `PRODUCT_ALERTS`
  (especificos por module_type). Funcao pura nova `get_alerts_for_module(type)`
  retorna o catalogo aplicavel a UM modulo. Adicionar produto novo =
  adicionar entry em `PRODUCT_ALERTS["nome"]`, sem mexer endpoint/UI/banco.
- **Schema**: drop `user_alert_prefs` (sem migracao — user disse "estamos
  testando"); cria `module_alert_prefs (user_id, chip_id, alert_type, ...)`.
- **Helpers em `models/users.py`**: `get_user_alert_prefs/set_user_alert_pref`
  removidos; substituidos por `get_module_alert_prefs(user_id, chip_id)` e
  `set_module_alert_pref(user_id, chip_id, alert_type, ...)`.
- **Endpoints REMOVIDOS** (sem alias):
  - `GET /api/profile/alerts/catalog`
  - `PUT /api/profile/alert-prefs/<alert_type>`
- **Endpoints NOVOS** (em `app.py`, padrao per-chip):
  - `GET /api/modules/<chip_id>/alerts/catalog`
  - `PUT /api/modules/<chip_id>/alert-prefs/<alert_type>`
- **`_send_alert`**: usa `_user_wants_channel(user_id, chip_id, type, channel)` —
  prefs per-modulo. Severity tambem passa a olhar primeiro o catalogo do produto
  (precedencia: PRODUCT > UNIVERSAL).

### Mudado (UX)
- **Janela de silencio saiu do card de notificacoes** (era replicada N vezes,
  uma em cada card de modulo — confuso). Agora vive no **menu do usuario**
  com novo item "Janela de silencio" + modal dedicado. Continua sendo
  propriedade GLOBAL do user (faz sentido — "nao me incomode na madrugada"
  e do dono, nao do sensor).
- **Card de notificacoes**: secao "Tipos de alerta" agora diz "(deste modulo)"
  em vez de "(globais — afeta todos os modulos)". Reflete a nova realidade.
- **Endpoint novo** `GET /api/profile/alert-silent-hours` (antes vinha
  embutido no catalogo, que foi removido).

### Frontend (refator do `renderNotificationCard`)
- Cache `_notifCardCache` (singleton) -> `_notifCardCacheByChip[chipId]`
  (per-chip, TTL 60s). Historico continua global em `_notifHistoryCache`.
- Funcoes `loadCardNotifications/loadCardNotificationsBySufx` substituidas
  por `loadCardCatalog(chipId, sufx)` + `loadCardHistory(chipId, sufx)` —
  separadas pra refletir que catalogo e per-chip e historico e global.
- `saveCardAlertPref(alertType, channel, enabled)` -> `saveCardAlertPref(chipId, alertType, channel, enabled)`.
- `_buildCatalogHtml(items)` -> `_buildCatalogHtml(items, chipId)` — onchange
  precisa propagar chipId pra montar o endpoint correto.
- Removidas funcoes `_buildSilentHtml`, `_renderCardSilentHours`,
  `saveCardSilentHours`, `clearCardSilentHours` — janela de silencio agora
  e no modal do menu (`openSilentHoursModal/saveSilentHoursModal/clearSilentHoursModal`).

### Filosofia preservada
Adicionar produto novo no futuro: `PRODUCT_ALERTS["sensor-ph"] = {...}`.
Pronto. Zero mudanca em endpoint, schema, ou frontend. UI ja sabe consumir
o catalogo do modulo via Registry Pattern.

## [4.1.51] - 2026-04-25

### Corrigido (CRITICAL — bug latente desde o deploy do Worker)
- **Worker de monitoring `status.cultivee.com.br` NUNCA abria incidentes**
  (`monitoring/cf-worker/uptime.js` linhas 169-176). A condicao era:
  ```js
  if (wasHealthy && !result.healthy && fail_streak >= INCIDENT_OPEN_THRESHOLD)
  ```
  Trace: no 1o check de falha, `wasHealthy=true` mas `fail_streak=1` (< 2,
  threshold). No 2o check de falha, `fail_streak=2` mas `wasHealthy=false`
  (porque `prev.healthy` virou false no ciclo anterior). Resultado: **nenhum
  incidente foi aberto desde o deploy inicial do Worker** — o uptime caia
  corretamente (calculado via `daily:` acumulado, independente de incidents)
  mas a lista de "INCIDENTES" ficava sempre vazia.
- Sintoma visivel: pagina mostrava `App Cultivee 99.49%` mas
  "Nenhum incidente nos ultimos 30 dias" simultaneamente.
- Fix: detectar a TRANSICAO via `prevFails < THRESHOLD && fail_streak
  >= THRESHOLD`. Dispara exatamente uma vez quando o contador cruza o
  threshold. Mesma logica espelhada pra closeIncident.
- Roll-out: deploy via `bash monitoring/cf-worker/deploy.sh`. Validado
  com `/trigger` — proximo cron (`*/5min`) ja usa logica nova.

### Nao corrigido (escopo posterior)
- Quedas historicas (visiveis em `last_down_at` dos componentes) nao foram
  reconstituidas como incidentes sinteticos. Worker nao tem dados granulares
  pra inferir start/end de quedas passadas (so guarda o ultimo
  `last_down_at`/`last_up_at`). Quedas futuras serao registradas
  corretamente; o gap historico fica visivel apenas no calculo de uptime.

## [4.1.50] - 2026-04-25

### Corrigido
- **Card de notificacoes piscava entre "Carregando tipos..." e o conteudo**
  a cada ~5s (`server/static/app.js`). Causa: `loadCtrlStatus` polla o
  dashboard a cada poll do ESP32, e o `_lastCtrlKey` inclui `temperature` e
  `humidity` do DHT11 (mudam toda leitura). Sempre que a temp variava,
  `renderDashboard` reescrevia o `container.innerHTML` inteiro — incluindo
  o card de notificacoes — e o template gerado vinha com o placeholder
  "Carregando tipos...". 50ms depois o `setTimeout` re-renderizava do cache
  (TTL 60s, sem fetch novo) — daí o flash visual.
- Fix: `renderNotificationCard` agora consulta o cache (`_notifCardCache`)
  ANTES de gerar o template. Se cache valido, gera HTML completo dos 3
  blocos (catalogo + silencio + historico) inline — sem placeholder.
  Refatorado em 3 builders puros (`_buildCatalogHtml`, `_buildSilentHtml`,
  `_buildHistoryHtml`) reusados pelos `_renderCardXxx` que escrevem no DOM
  apos fetch.
- Bonus: `saveCardAlertPref` agora atualiza o cache local apos salvar (antes,
  o cache mantinha o valor antigo por ate 60s — bug latente: se o card
  fosse re-renderizado nesse intervalo, o checkbox revertia visualmente).

## [4.1.49] - 2026-04-25

### Corrigido
- **Layout inconsistente dos "Tipos de alerta" no card de notificacoes**
  (`server/static/app.js` `_renderCardCatalog`). Antes, labels longos (P2
  "Sensor com leitura invalida", "WiFi instavel (varias quedas)", "Memoria
  baixa no modulo") faziam os checkboxes Push/Email caerem pra linha de
  baixo via `flex-wrap:wrap`, enquanto labels curtos (P1/P3) ficavam tudo
  em 1 linha. Visual desigual entre os 6 itens.
- Fix: removido `flex-wrap:wrap`, label agora wrap em 2 linhas com
  `overflow-wrap:anywhere`, checkboxes ficam fixos a direita alinhados ao
  topo (`align-items:flex-start`). Layout uniforme nos 6 itens — nada de
  checkbox abandonando a linha.

## [4.1.48] - 2026-04-25

### Mudado
- **Largura maxima do dashboard de 1400px → 1600px** (`server/static/style.css`).
  Atualizado em 3 lugares: `main`, `#module-content` (grid de cards) e `.module-bar`
  (barra de selecao). Em telas widescreen (1920×1080+) reduz o espaco escuro nas
  laterais; com `grid-template-columns: repeat(auto-fill, minmax(300px, 1fr))`,
  agora cabem **5 cards** por linha em viewports >=1568px (antes 4). Em telas
  menores que 1600px o comportamento continua identico.
- Bump `APP_VERSION` em `server/config.py` (invalida cache do Service Worker).

### Nao alterado
- Dashboard offline do firmware (`mod_*.h`) — serve um unico modulo no IP local
  do ESP32, sem `<main>` nem `#module-content` com multiplos cards. Regra de sync
  online/offline nao se aplica.

## [4.1.47] - 2026-04-25

### Corrigido (CRITICAL latente — afetava silenciosamente Hidro-Farm)
- **JSON do `register` truncava silenciosamente em modulos com payload >1.5kB**
  (Hidro-Farm tem 3 fases × 18 campos = `phasesJson` ~1.5kB). Heap do ESP32
  fragmentava por reallocacoes do `String += String` em ~30 lugares no
  `core_register.h` + `mod_*_register_json()`. Ao chegar perto do fim, alocacoes
  falhavam silenciosamente e os ultimos 2 campos (`min_free_heap`,
  `firmware_version`) **simplesmente nao eram adicionados** ao JSON.
- Sintoma: Hidro-Farm reportava 31 campos em `ctrl_data` (faltavam 2). Hidros
  reportavam todos (33). Bug latente desde v4.1.26 (quando `min_free_heap`
  foi adicionado) — manifestava SO no Hidro-Farm porque tem JSON maior.
- Fix de 1 linha em `core_register.h`:
  ```cpp
  String json;
  json.reserve(3000);  // pre-aloca capacity, evita reallocacoes
  json += "{";
  ```
- Validado em producao: apos OTA do Farm, JSON volta com `total_keys=33`,
  `firmware_version=4.1.47`, `min_free_heap=198492`.

### Removido
- Log debug `REG-FARM-DEBUG` em `app.py` (era v4.1.46, ja cumpriu seu papel).

### Roll-out
- Hidro-Farm (`348257088304`): gravado USB (descoberta do bug)
- Hidro #2 (`50B525077000`), Hidro #1 (`E04730A7DBCC`), Cam (`704CAAF7C630`):
  OTA via SSH escrevendo `.bin` direto no volume Docker. Os 3 chips reportam
  agora `firmware_version=4.1.47`. Sem rollback A/B disparado.

---

## [4.1.46] - 2026-04-25 (debug — nao-release oficial)

### Adicionado (temporario)
- Log de debug `REG-FARM-DEBUG` em `register_module` que captura body cru
  + presenca/posicao de chaves criticas. Disparou apenas pra chip
  `348257088304` (Hidro-Farm). Removido na v4.1.47.
- Resultado da investigacao: confirmou que JSON chega ao servidor truncado
  em `..."wifi_disconnect_count":0}}` com 1511 bytes — bug e no firmware,
  nao no servidor.

---

## [4.1.45] - 2026-04-25

### Alterado
- Labels do catalogo de alertas: `P` / `E` -> `📱 Push` / `✉ Email`
  com texto cheio. Adicionado header explicativo acima da lista descrevendo
  os canais (push = notificacao no celular/browser, email = SMTP). Tooltips
  com detalhes tecnicos. Era opaco, ninguem adivinhava sem ver o codigo.

---

## [4.1.44] - 2026-04-25

### Alterado
- Reordena card de notificacoes — janela de silencio movida pro fim, dentro
  de um `<details>` collapsed (era 2a section). Adiciona explicacao expandida
  ao abrir, listando 4 casos de uso reais (madrugada, reuniao, bench, viagem)
  + aviso destacado: P0 sempre passa.
- Justificativa: feature e nicho (maioria nao usa). Esconder por default
  deixa o card menos cheio sem perder funcionalidade.

---

## [4.1.43] - 2026-04-25

### Alterado (consolidacao UX)
- **Notificacoes consolidadas em UM helper unico** `renderNotificationCard(chipId, ctrlData)`
  no card de cada modulo (era espalhado entre Perfil + card per-modulo desde v4.1.41).
  Estrutura em 3 sections num so card:
  1. **Este modulo** (per-modulo): toggle offline + threshold (v4.1.39)
  2. **Tipos de alerta** (globais): catalogo + checkboxes Push/Email
  3. **Historico** (collapsed `<details>`): timeline com ack inline
- IDs sufixados com `chipId` pra permitir N cards simultaneos sem colisao.
- Cache compartilhado de 60s (`_notifCardCache`) — fetch unico pra catalogo
  + historico, todos os cards leem do mesmo cache. Evita N requests por poll.
- Acoes globais (silent_hours, ack, toggle de canal) invalidam cache +
  re-renderizam **todos os cards visiveis** simultaneamente — estado sempre
  sincronizado entre cards.

### Removido
- Section `#profile-notifications-card` no `index.html` (era v4.1.41).
- 6 funcoes antigas no `app.js` (`loadAlertCatalog`, `loadAlertsHistory`,
  `saveAlertPref`, `saveSilentHours`, `clearSilentHours`, `ackAlert`).

---

## [4.1.42] - 2026-04-25

### Corrigido
- Cards de selecao (barra superior) estavam mais estreitos que cards de
  dashboard (5 colunas vs 4 em tela larga) — visualmente desencaixado.
  Causa: `.modules-list` usava `minmax(250px)` + `gap 0.5rem`,
  `#module-content` usava `minmax(300px)` + `gap 1rem`.
- Fix: igualar grid em ambos pra `minmax(300px, 1fr)` + `gap 1rem`. Cards
  agora alinhados verticalmente entre as duas linhas.

---

## [4.1.41] - 2026-04-25 (substituido pela v4.1.43)

### Adicionado (depois consolidado)
- Section "Notificacoes" no Perfil com catalogo + historico + prefs +
  silent_hours. **Movido pro card de cada modulo na v4.1.43** apos
  feedback do user de que "perfil nao e o lugar certo".
- Tabela `user_alert_prefs(user_id, alert_type, enabled_push, enabled_email)`.
- Colunas `users.alert_silent_hours_start/end`.
- Helpers em `models/users.py`: `get/set_user_alert_prefs`,
  `get/set_user_silent_hours`.
- 5 endpoints em `usuario/profile.py`: `/alerts/catalog`, `/alerts/history`,
  `/alerts/<id>/ack`, `/alert-prefs/<type>`, `/alert-silent-hours`.
- `_send_alert` respeita prefs do user: `_user_wants_channel(user_id, type, channel)`
  + `_is_in_silent_hours(user_id, severity)` (P0 sempre passa). Sempre
  loga em `alert_log` mesmo quando bloqueado por silent_hours/pref —
  user ve no historico que disparou.

---

## [4.1.40] - 2026-04-25

### Adicionado (catalogo P0-P3 formal — fecha item 3 do plano Mes 2)
- `alert_log` ganha 3 colunas: `severity` (P0-P3, default 'P1'),
  `ack_at`, `ack_by`. Migration aditiva idempotente.
- Catalogo INLINE `ALERT_CATALOG` em `notifications.py` (dict
  constante, em vez de tabela `alert_definitions` que seria
  over-engineering pra MVP). 6 tipos com `severity_default` +
  `cooldown_sec` + `name`.
- 3 checks novos no `AlertManager.check()` (cross-modulo via
  `register_module`):
  - `low_heap_warning` — P2, dispara se `min_free_heap < 10kB`. Cooldown 24h.
  - `sensor_invalid` — P2, streak 3x consecutivos de `dht_valid=false`.
    Cooldown 12h. Pra Hidro-Farm (DHT11). Hidro/Cam pulam.
  - `wifi_disconnect_burst` — P2, snapshot baseline + diff em janela de 1h.
    Threshold conservador (>=10 quedas) pra evitar fadiga em WiFi naturalmente
    ruim. Cooldown 6h.
- 3 server_keys novos em `models/modules.py` (protegem merge do ESP32):
  `sensor_invalid_streak`, `wifi_disconnect_baseline`,
  `wifi_disconnect_baseline_at`.

### Alterado
- `AlertManager._send_alert(severity)` agora aceita parametro opcional.
  Se `None`, usa default do catalogo. `offline_watcher` passa P0/P1 explicito.
- `models.log_alert(severity)` aceita parametro novo (default P1 pra back-compat).
- Log linha agora inclui sev: `ALERTA [P0] [module_offline] chip=...`

### Notas
- `firmware_update_failed`: deferred pra proxima rev de firmware (precisa
  reportar `ota_rollback_count` no register).
- Tabela `user_alert_prefs` + UI de preferencias por canal: feita em
  v4.1.41 (entrou na rodada seguinte).

---

## [4.1.39] - 2026-04-25

### Adicionado
- Alerta de offline agora **configuravel por modulo** via UI. Card novo "Notificacoes de offline" no dashboard de cada modulo (Hidro, Hidro-Farm e Cam), com:
  - Toggle "Alertar quando offline" (default ON pra modulos novos)
  - Input "Alertar apos N min" (range 1-1440 = 1min a 24h)
- Endpoint `POST /api/modules/<chip>/notification-prefs` (auth: dono ou admin). Body opcional: `{offline_alert_enabled?: bool, offline_alert_threshold_min?: int}`. Valida int 1-1440.
- `models/modules.py`: 2 campos novos em `server_keys` — `offline_alert_enabled`, `offline_alert_threshold_min`. Protege merge do ESP32 (so servidor escreve via endpoint).
- `static/app.js`: helper `renderNotificationCard(chipId, ctrlData)` reusavel entre Hidro/Hidro-Farm/Cam, mais `toggleOfflineAlert` + `saveOfflineThreshold` com atualizacao otimista da UI + revert em caso de erro.

### Alterado
- `jobs/offline_watcher.py`: default global `OFFLINE_ALERT_THRESHOLD_MIN` 60min → `DEFAULT_OFFLINE_THRESHOLD_MIN` 15min. Por modulo, le `ctrl_data.offline_alert_threshold_min` (fallback ao default). Skip do alerta se `offline_alert_enabled === false`.
- Padrao visual do novo card replica o do alerta de nivel do reservatorio (toggle + input numerico) — consistencia.
- Cam ganha alerta de offline pela primeira vez (antes nem tinha card de notificacoes — so HIDRO/Farm tinham via reservatorio).

### Corrigido (commit `facff77`)
- **Bug que cometi nesta mesma release** (entre commit principal `cb9ddbb` e fix): renomeei `OFFLINE_ALERT_THRESHOLD_MIN` → `DEFAULT_OFFLINE_THRESHOLD_MIN` mas esqueci 2 referencias:
  1. Log de startup do `_watcher_loop` — `NameError` imediato, thread crashou. Sistema ficou SEM detecao automatica de offline por ~25min (modulos continuaram registrando normal, mas nenhum alerta seria disparado).
  2. `_maybe_send_recovery_alert` — comparacao com constante inexistente, recovery alert nao disparava (silenciosamente).
- Fix usa `DEFAULT_OFFLINE_THRESHOLD_MIN` (log) e `_module_threshold_min(module)` (recovery — passa a respeitar config por modulo tambem).

### Notas operacionais
- Pra modulos pareados antes do upgrade, os campos novos sao **fallback ao default** (15min, ON) — nao precisa rodar migration nem POST manual. Quem quiser ajustar, abre o modulo no app e mexe.
- Padrao do bug recorrente: 4o caso seguido de "refatorei nome de simbolo sem grep por todas as ocorrencias". Documentado novamente em `docs/sessoes/2026-04-25.md` — proxima rodada DEVE rodar `grep -n PATTERN file` antes de commitar refator de constante/funcao.

---

## [4.1.38] - 2026-04-25

### Adicionado
- **Alerta proativo "modulo offline ha X min"** — thread daemon em `server/jobs/offline_watcher.py` roda a cada 60s. Pra cada modulo pareado:
  - Se offline >= 60min (default desta versao — alterado pra 15min na v4.1.39): dispara alerta P1 (push + email) via `AlertManager._send_alert` existente.
  - Se >= 24h: escala pra P0 (cooldown maior pra evitar spam — 12h).
  - Se voltou apos queda longa: alerta de recovery ("voltou apos Xmin").
- Lock distribuido — nova tabela `offline_watcher_state` (singleton id=1) + helper `try_acquire_offline_watcher_lock(min_interval_sec)`. UPDATE atomico no SQLite garante que so 1 worker do Gunicorn (de 2) execute o ciclo por intervalo.
- Cooldowns no `alert_log`:
  - `module_offline` P1: 4h
  - `module_offline` P0: 12h
  - `module_recovered`: 1h
- Iniciado em `app.py` apos init_db. Falha silenciosa se import quebrar (nao trava startup do servidor).

### Alterado
- Modal de uptime: evento offline ainda em aberto (sem `duration_seconds`) agora mostra "OFFLINE · em curso · 45min" (calcula `now - occurred_at`) em vez de so "em curso" sem o tempo.
- `loadInlineUptime`: quando modulo esta offline AGORA, substitui a linha "Uptime 7d: 99% · sem quedas" por `🔴 Offline ha 45min` em vermelho. Visivel imediatamente no card sem precisar abrir modal. Cache 60s mantido.

### Validacao em producao
- Primeiro alerta real disparado em 10:14:26 BRT — CAM (`704CAAF7C630`) ficou 72min offline antes do deploy. Thread detectou no primeiro ciclo, push entregue pra 7 endpoints + email pro `mardo.abc@gmail.com`. Deduplicacao via `alert_log` funcionou apesar dos 2 workers (sem alerta duplicado). 8 push subs antigas (410 Gone) foram removidas automaticamente pelo handler existente.

---

## [4.1.37] - 2026-04-25

### Alterado
- Novo helper `getDisplayName(chipId)` em `static/app.js` centraliza a logica de nome exibido pra modulo. Substitui codigo duplicado em 3 lugares (loadModules barra de selecao, loadCtrlStatus header card Hidro/Hidro-Farm, renderModule_cam header card Camera). Antes a barra mostrava "Controle Hidro · DBCC" mas o card aberto mostrava so "Controle Hidro" — inconsistente. Agora e `nome customizado se houver` ou `${label} · ${ultimos 4 chars do chip_id}` em todos os lugares.

### Corrigido
- Header da Camera tinha `<b>Câmera</b>` hardcoded literal. Agora usa o helper.

---

## [4.1.36] - 2026-04-25

### Corrigido
- Quando havia 4+ modulos no layout de 3 colunas, o 4o card ficava sozinho na 2a linha e **esticava pra ocupar a largura toda**. Causa: CSS usava `flex: 1 1 calc(33.333% - 0.67rem)` com `flex-grow: 1`. Em linhas cheias o grow distribuia espaco igualmente; em linha incompleta, o grow expandia o item solitario pra 100%.

### Alterado
- `style.css` `@media (min-width: 640px)`: troca Flex por CSS Grid em ambos os containers (`.modules-list` na barra superior e `#module-content` no dashboard de selecionados):
  ```css
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(NNNpx, 1fr));
  ```
  Com `auto-fill`, colunas vazias ficam reservadas — items mantem largura natural alinhados a esquerda. Mobile (sem @media) continua flex column.

---

## [4.1.35] - 2026-04-25

### Adicionado
- Firmware reporta `firmware_version` no register (`core_register.h`) — admin/dashboard passam a ver qual versao esta rodando em cada modulo via `ctrl_data.firmware_version` no banco, sem precisar abrir `/update` do ESP32 na rede local.
- PWA desambigua nomes de modulos do mesmo capability: quando 2+ HIDROs (ou Cams, ou Farms) estao pareados sem nome customizado, o card mostra `Controle Hidro · DBCC` e `Controle Hidro · 7000` em vez de dois "Controle Hidro" identicos. Se o user nomeia ("Estufa Sala"), respeita o nome custom sem sufixo.

### Corrigido
- **Bug introduzido neste mesmo commit (858e4b7)** e fixado em `8eafe4b`: a primeira tentativa colocou `firmware_version` na raiz do JSON do request. Mas o servidor (`app.py register_module`) so extrai chaves especificas da raiz e o resto desce para o sub-objeto `ctrl_data`. Resultado: campo nao era armazenado em lugar nenhum. Fix: mover a linha pra dentro do `"ctrl_data":{...}` no firmware, junto com as outras telemetrias cross-produto (wifi_last_error, min_free_heap). Validado: ambos HIDROs reportando fw=4.1.35 no banco apos OTA.

### Notas operacionais
- **Roll-out**: HIDRO #2 (chip novo `50B525077000`) gravado via USB no COM17. HIDRO #1 (E04730A7DBCC, em campo) atualizado via OTA — feito por SSH single-session subindo `.bin` direto no volume Docker (`/var/lib/docker/volumes/cultivee_cultivee-data/_data/firmware/`), sem precisar de token de admin. Servidor auto-deletou o `.bin` apos download (anti-loop, fix da v4.1.8). Modulo voltou online em ~31s (1 reboot, sem rollback A/B disparado).

---

## [4.1.34] - 2026-04-25

### Adicionado
- AP SSID + mDNS name agora ganham sufixo de 6 hex chars do MAC. Antes `Cultivee-Hidro` e `cultivee-hidro.local` colidiam quando 2 modulos do mesmo produto estavam na mesma rede WiFi (lista de redes do celular agregava SSIDs duplicados, mDNS resolvia pra um IP ou outro). Agora:
  - HIDRO MAC `E04730A7DBCC` → AP `Cultivee-Hidro-A7DBCC` + mDNS `cultivee-hidro-a7dbcc.local`
  - HIDRO MAC outro ESP32 → AP `Cultivee-Hidro-XXXXXX` + mDNS `cultivee-hidro-xxxxxx.local`
- Inicializacao em `firmware.ino setup()`: `dynamicApSsid` e `dynamicMdnsName` calculados a partir do `chipId` ja existente. Globais em `core_wifi.h`. Uppercase no SSID (visual), lowercase no mDNS (convencao).
- `core_wifi.h startAP()` e `MDNS.begin()` (em `core_wifi.h` + `firmware.ino`) usam as variaveis dinamicas com fallback defensivo ao define estatico.
- `core_server.h` captive portal mostra o SSID dinamico no HTML (em vez do literal `AP_SSID`).

### Alterado
- `compile.sh`: aceita `PORT` via env var (default `COM7`). Permite `PORT=COM17 bash compile.sh upload` pra gravar segundo HIDRO sem editar o script. Melhoria permanente, serve pra qualquer modulo novo no futuro.

### Notas operacionais
- **Descoberta**: `docker compose restart` **nao re-le** `env_file`. As env vars sao capturadas na CRIACAO do container. Pra re-ler apos editar `.env`, usar `docker compose up -d --force-recreate <service>`. Documentado em CLAUDE.md/memory.
- **Descoberta**: nome do service no docker-compose e `app`, nao `cultivee-app` (esse e o `container_name`). Comando correto: `docker compose restart app`.

---

## [4.1.33] - 2026-04-24

### Adicionado
- Webhook HMAC-SHA256 `POST /api/platform-incident` recebe do CF Worker (`status.cultivee.com.br`) quando abre/fecha um incidente da plataforma. Anti-replay 5min, silenciosamente desativado se `PLATFORM_INCIDENT_SECRET` nao estiver no env (retorna 401 `webhook_disabled`).
- Tabela `platform_incidents` (UNIQUE por `webhook_id` — idempotente em re-posts).
- Helpers `upsert_platform_incident`, `mark_module_events_as_server_down(start, end)` e `get_recent_platform_incidents(days)` em `models/modules.py`.
- CF Worker: `postIncidentToVPS(incident)` chamado em `openIncident`/`closeIncident`, HMAC via `crypto.subtle` (Web Crypto). Best-effort com log em caso de falha.
- Secret `PLATFORM_INCIDENT_SECRET` provisionado via `bash monitoring/cf-worker/deploy.sh` (API CF) + `.env` da VPS.
- Badge cinza "SERVIDOR" (em vez de vermelho "OFFLINE") em eventos com `reason='server_down'` no modal de uptime do modulo.
- Aviso azul no topo do modal: "N quedas excluidas... uptime bruto: X%" com link pra `status.cultivee.com.br`.

### Alterado
- `get_module_uptime_summary(chip_id, days)` agora aceita `exclude_server_down=True` (default) e retorna campos novos: `uptime_pct_raw`, `offline_count_raw`, `server_down_seconds`.
- Quando o CF Worker fecha um incidente, a VPS marca retroativamente os `module_status_events` cujo timestamp cai na janela como `reason='server_down'`. O calculo filtrado do `uptime_pct` passa a refletir so a saude do hardware.

### Corrigido
- `deploy.sh` do Worker aceita HTTP 200 OU 201 no PUT do secret (API CF retorna 201 na primeira criacao).

### Seguranca
- HMAC-SHA256 com `hmac.compare_digest` (constant-time) pra evitar timing attacks.
- Timestamp obrigatorio no payload (parte do HMAC) + janela de ±5min pra anti-replay.

---

## [4.1.32] - 2026-04-23

### Adicionado
- Card "Status da plataforma" no topo do painel admin — mostra healthy/latencia/uptime 7d por componente monitorado + incidentes em curso. Consome direto o `status.cultivee.com.br/check` via CORS (sem proxy pela VPS).
- `/check` do CF Worker agora retorna snapshot consolidado do KV (overall + components + uptime + incidents), em vez de probe ao vivo pobre.
- `?live=1` no `/check` mantem o comportamento antigo (probe simples — util pra Uptime Robot externo).
- `?c=<id>` filtra um componente unico + seus incidentes.
- Aviso laranja no modal de uptime do modulo listando incidentes do CF Worker que cruzam com o periodo exibido.
- Cache local de 60s (`_platformStatusCache`) pra nao bater no Worker a cada modal aberto.

### Alterado
- CSP da VPS libera `connect-src https://status.cultivee.com.br`.
- CF Worker: `Access-Control-Allow-Origin: *` + `Cache-Control: public, max-age=30` nas respostas JSON publicas.
- Cron do Worker `*/2 * * * *` → `*/5 * * * *` pra caber no free tier KV.
- Acumulador diario in-place dentro de `current:{id}` (campos `today_checks`, `today_healthy`, `today_total_latency_ms`, `today_max_latency_ms`) — `daily:{YYYY-MM-DD}` escrito 1x por dia por componente, na virada. `getDailySeries` materializa o dia atual direto do `current:`.

### Removido
- Link "JSON" do footer da status page publica — endpoint continua acessivel mas nao exposto visualmente (status page e B2C, ninguem consome API).

### Corrigido
- Writes de KV caiam de ~2.880/dia (estourava o free tier de 1.000/dia) pra ~578/dia (58% do limite).
- `deploy.sh`: pretty-print do cron tolera tanto string quanto objeto (API CF mudou formato).

---

## [4.1.31] - 2026-04-22

### Adicionado
- Historico persistente online/offline por modulo (retencao 90 dias).
- Nova tabela `module_status_events` (status, occurred_at, duration_seconds, reason, rssi) — cada transicao vira uma linha.
- Helpers em `models/modules.py`: `record_module_status`, `compute_module_status_lazy` (detecta offline silencioso quando `last_seen > 120s`), `get_module_uptime_summary` (agrega uptime%, quedas, maior offline), `get_module_status_events` (timeline), `purge_old_status_events` (retencao 90d).
- Endpoints: `GET /api/modules/<chip>/uptime?days=N` (dono) e `GET /api/admin/modules/<chip>/uptime?days=N` (admin).
- Card do modulo ganha linha "Uptime 7d: 99.2% · 1 queda · Ver historico" que abre modal com toggle 7d/30d/60d.
- Tabela admin ganha coluna "Uptime 7d" + botao "Historico" (reusa o mesmo modal com flag `isAdmin`).

### Alterado
- `register_module` dispara `record_module_status('online')` se o status anterior era diferente.
- `list_modules` dispara `compute_module_status_lazy` pra capturar offline silencioso.
- Cleanup lazy: `init_db` + 1 vez a cada 1000 registers (via `_REGISTER_COUNTER`).

---

## [4.1.30] - 2026-04-21

### Corrigido
- Botao "Salvar dados fiscais" agora aparece no card respectivo (antes estava orfao). Feedback escreve em ambos `profile-save-msg` e `profile-fiscal-save-msg`.

---

## [4.1.29] - 2026-04-21

### Adicionado
- 2FA por email como alternativa ao TOTP. Usuarios que nao querem instalar app authenticator recebem codigo 6-digitos por email a cada login (valido 10min, single-use).
- Tabela `email_2fa_codes` + coluna `users.email_2fa_enabled`.
- 3 rotas: `/api/profile/2fa/email/{setup,enable,disable}`.
- Login no `usuario/auth.py` detecta `email_2fa_enabled` e retorna `email_otp_required: true` na 1a chamada.
- Template de email `send_email_2fa_code` em `notifications.py`.
- Modais de setup + disable no frontend + input dinamico no login com botao "Reenviar codigo".
- `/api/auth/me` expoe `totp_enabled` e `email_2fa_enabled` pra UI sincronizar estado.

### Alterado
- TOTP e 2FA-email sao mutuamente exclusivos (UI desabilita botao do outro quando um ja esta ativo).

---

## [4.1.28] - 2026-04-21

### Alterado (migracao em 3 commits)
- `MODULE_TYPE` do produto Hidro: `"ctrl"` (legado) → `"hidro"`. Padrao `MODULE_TYPE == capability` agora vale pros 3 produtos.
- Backend normaliza `ctrl → hidro` no `register_module` (ESP32 com firmware antigo continua funcionando).
- Blueprint duplo: `/api/hidro/*` (novo) + `/api/ctrl/*` (alias deprecated com log).
- Migracao idempotente no `init_db`: `UPDATE modules SET type='hidro' WHERE type='ctrl'`.
- Firmware Hidro `products/hidro.h`: `MODULE_TYPE="hidro"` + `MDNS_NAME="cultivee-hidro"` (legado `cultivee-ctrl.local` removido).
- `git mv server/run-ctrl.py server/run-hidro.py` (preserva historico).
- `sim_esp32.py` aceita "hidro" primario + "ctrl" deprecated.
- `test_routes.py` usa `/api/hidro` por padrao.

### Notas
- Alias `/api/ctrl/*` mantido por ~1 semana pra nao quebrar PWAs cacheados. Remover em versao futura quando logs `[deprecated]` zerarem.

---

## [4.1.27] - 2026-04-21

### Adicionado
- Admin OTA direto no painel. Novo botao "Firmware" na tabela de modulos abre modal que calcula SHA-256 client-side (`crypto.subtle`) e faz upload multipart pra `POST /api/admin/modules/<chip>/firmware` (exige role=admin).
- Rotas `POST/GET/DELETE /api/admin/modules/<chip>/firmware` + audit log `module.firmware_upload` / `module.firmware_cancel`.
- Limite 3MB por upload.

### Alterado
- Elimina a fricao de precisar do token do dono via `ota-remote.sh` (legacy, mantido por compatibilidade).

---

## [4.1.26] - 2026-04-21

### Adicionado
- `sync-version.sh` — alinha `FIRMWARE_VERSION` ao `APP_VERSION` (fonte unica).
- `backup-vps.sh` — dump sqlite online + tarball + manifest SHA-256, modo `--restore`.
- `docs/manual-usuario.md`, `docs/operacao.md`, `docs/lgpd-aipd.md`, `docs/termos-uso.md`, `docs/license-gate.md`.

### Alterado (seguranca/hardening)
- `hardware/cam.py`: path traversal fix com `_safe_join`.
- `MAX_CONTENT_LENGTH=6MB` global + `MAX_UPLOAD_BYTES=5MB` por request.
- Escape HTML em todos os `innerHTML` de dados (lista de modulos, fases, admin users/modules) via `escapeHtml`/`escapeAttr`.
- Senhas migram pra `bcrypt` (rounds=12) transparentemente no login (`check_password_and_upgrade` rehash automatico do SHA-256 legado).
- `delete_user_cascade` purga `captures/`, `thumbs/`, `live/` e firmware pendente (LGPD).
- Firmware: brownout detector nivel 4 (~2.7V), telemetria + protecao de heap com `min_free_heap` (restart <5kB), timeout 30min em `MODE_SETUP`.
- OTA remoto: validacao SHA-256 obrigatoria (firmware aborta e preserva versao anterior se hash nao bater) + rollback A/B manual por NVS + `esp_ota_set_boot_partition` se 3 boots falharem self-test.

---

## [4.1.25] - 2026-04-21

### Alterado
- Modal custom com dropdown pra alterar nivel do user (antes era `prompt()` do navegador — feio, permitia digitacao livre). Cada opcao tem descricao curta.

---

## [4.1.24] - 2026-04-21

### Alterado
- Area admin traduzida pra portugues: "Role" → "Nivel", "Reset pwd" → "Resetar senha", "Mods" → "Modulos", "Support" → "Suporte", "Audit Log" → "Registro de Acoes". Mapper visual dos action types (`impersonate` → "Acesso como", etc.).
- Valores internos da API continuam em ingles (chaves tecnicas, nao quebra filtros).

---

## [4.1.23] - 2026-04-21

### Adicionado (seguranca)
- Security headers via `@app.after_request`: HSTS (so em HTTPS), CSP, X-Frame-Options SAMEORIGIN, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy (desativa camera/mic/geo/payment/usb/accelerometer).
- `ProxyFix` do Werkzeug pra honrar `X-Forwarded-*` do Traefik (HSTS + IP real em rate limit/audit).

### Notas
- Headers pulados em endpoints do ESP32 (register, poll, firmware, upload) pra economizar banda.
- CSP so em respostas `text/html` (nao em JSON/imagens).

---

## [4.1.22] - 2026-04-21

### Adicionado
- 2FA TOTP (`pyotp` — compativel com Google Authenticator, Authy, 1Password).
- Session management em "Meus dispositivos" — lista tokens com `user_agent`, `ip`, `last_used_at`, revogacao individual ou em massa.
- CAPTCHA Turnstile scaffolding (auto-desativado se `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET` nao estiverem no env).
- Colunas `users.totp_secret/totp_enabled`, `tokens.user_agent/ip/last_used_at`.

---

## [4.1.21] - 2026-04-21

### Adicionado
- Admin Fase 4 — operacoes: `POST /api/admin/users/<id>/role` (promover/rebaixar), `/force-password-reset` (reset forcado + revoga tokens), `/modules/<chip>/transfer` (muda dono).
- Audit log com filtros (`action`, `admin_id`, `from`, `to`, `limit`, `offset`).

---

## [4.1.20] - 2026-04-21

### Adicionado (compliance LGPD)
- Consentimento obrigatorio no cadastro (`accepted_terms: true` + `users.terms_accepted_at`).
- Paginas publicas `/termos` e `/privacidade`.
- Verificacao de email via link enviado apos cadastro (`email_verified_at`, `email_verification_token`).
- Dados fiscais: `person_type` (pf/pj), `tax_id` (CPF/CNPJ), `company_name` (razao social).
- Direitos LGPD Art. 18: `DELETE /api/profile/` (exclusao cascade), `GET /api/profile/export` (portabilidade — JSON).

### Alterado
- Bootstrap: usuarios antigos foram marcados `email_verified_at = created_at` + `terms_accepted_at = created_at`.

---

## [4.1.19] - 2026-04-21

### Alterado
- Admin entra direto no painel admin apos login (padrao SaaS, em vez da visao de modulos).

---

## [4.1.18] - 2026-04-21

### Corrigido
- `loadModules` travava em "Carregando..." pra usuarios com 0 modulos — `_lastModulesKey=''` colidia com chave inicial vazia.

---

## [4.1.17] - 2026-04-21

### Alterado (refactor)
- Split dos blueprints por camada: `server/hardware/` (hidro, hidrofarm, cam, gallery), `server/usuario/` (auth, profile), `server/admin/`. Zero breaking change — `git mv` preserva historico.

---

## [4.1.13] - [4.1.16] - 2026-04-21

### Adicionado (camadas de usuario + admin)
- **v4.1.13** — Admin Fase 1: painel com stats, users, modules, audit. Coluna `users.role` + bootstrap automatico do user id=1 como admin.
- **v4.1.14** — Admin Fase 2: impersonation completa com banner fixo no topo, restauracao de sessao.
- **v4.1.15** — Admin Fase 3: audit_log persistido no banco, modo readonly com middleware `@before_request`, duracao configuravel 5-240min, notificacao email pra outros admins.
- **v4.1.16** — Perfil completo: nome, telefone, endereco BR com ViaCEP, dados fiscais + troca de senha com verificacao + menu dropdown na navbar. Refactor `models.py` → pacote `models/` (db, users, modules, push, audit).

---

## [4.1.12] - 2026-04-20

### Adicionado
- Modulo de autenticacao separado (`bp_auth.py` → `usuario/auth.py` depois).
- Recuperacao de senha completa: `forgot-password` (email com token 1h, anti-enumeration) + `reset-password`.
- Rate limiting in-memory por IP+endpoint.
- Validacao de formato de email.

---

## [4.1.11] - 2026-04-20

### Corrigido
- `PUT /api/user/prefs` salvava `{}` em vez do payload — o body era string ja-stringificada mas o helper `api()` so setava `Content-Type` quando body era objeto.

---

## [4.1.10] - 2026-04-20

Nota: **dois bumps de versao no mesmo dia com o mesmo numero**. O commit `b44ed73` bumpou `FIRMWARE_VERSION` do Cam pra 4.1.10 (por `LIVE_MAX_DURATION`); o commit seguinte `8b22c08` bumpou `APP_VERSION` do servidor pra 4.1.10 (por `module_prefs`). O `sync-version.sh` ainda nao existia (chegou em v4.1.26) — por isso os dois ficaram desalinhados por algumas horas.

### Adicionado
- **Server (`APP_VERSION`)** — Persistencia de ordem + selecao de modulos no servidor (antes so localStorage). Coluna `users.module_prefs` JSON. Migracao automatica dos valores antigos.

### Alterado
- **Firmware Cam (`FIRMWARE_VERSION`)** — `LIVE_MAX_DURATION` aumentado de 2min pra 10min (stream ao vivo nao auto-encerra tao rapido).

---

## [4.1.9] - 2026-04-20

### Adicionado
- Persistencia do botao "Ao Vivo" da camera apos reload do browser (`cam_live_mode` em ctrl_data + sync servidor). `mod_cam.h` agora reporta `cam_live_mode` no `register_json`; `bp_cam.py` escreve em `ctrl_data` otimisticamente no `/start-live` e `/stop-live`. Elimina dessincronizacao UI ↔ hardware.

---

## [4.1.8] - 2026-04-20

### Adicionado
- Telemetria WiFi: `wifi_last_error`, `wifi_last_connected_ms`, `wifi_disconnect_count`, `WiFi.onEvent()` + `setAutoReconnect(true)`.
- Cam migrado de particao `no_ota` pra `min_spiffs` — agora suporta OTA remoto.

### Corrigido
- Server auto-deleta `.bin` apos download pelo ESP32 pra evitar loop infinito de OTA (bootstrap novo recebia firmware_url antigo no register).

---

## [4.1.0] - [4.1.7] - 2026-04-16

### Adicionado
- Sistema de alertas completo (reservatorio vazio).
- Push notifications com VAPID + `pywebpush` + subscribe automatico 2s apos login.
- Email SMTP SSL (porta 465 HostGator, `Message-ID` + `Date` RFC 5322 obrigatorios pelo Gmail).
- `AlertManager` integrado ao `register_module`.
- Tabelas `push_subscriptions` + `alert_log` (cooldown 1h).
- Service Worker com handlers `push` + `notificationclick`.
- Timer visual no card Reservatorio ("Nivel baixo ha Xmin Xs" — laranja < threshold, vermelho pulsante >= threshold).
- Coluna `users.notification_email` (email separado pra alertas).

### Alterado
- **v4.1.7** — Threshold configuravel de alerta (1-120 min, default 10). Timer persistido em `ctrl_data.low_since` (sobrevive a restart).

### Corrigido
- `AlertManager` fazia merge dos dados do ESP32 (level_low) com dados do banco (low_since, alert_threshold_min) antes de processar.
- `sqlite3.Row` nao tem `.get()` — substituido por `row["campo"]` direto.
- VAPID keys vazaram no `docker-compose.yml` (GitGuardian detectou). Keys rotacionadas e movidas pra `.env` da VPS.

---

## [4.0.x] - 2026-04-10 a 2026-04-16

### Refactor PWA
- **v4.0.16-v4.0.23** — `localStates` Map per-chipId (elimina vazamento de estado entre modulos no cooldown de 35s), `renderSelectedContent` so recria DOM quando selecao muda (elimina flash visual a cada poll), headers de modulo com icone colorido e label.

### Adicionado (OTA Remoto)
- **v4.0.14-v4.0.15** — OTA remoto via servidor. ESP32 baixa `.bin` no proximo poll quando servidor anexa `firmware_url` na resposta de `register`. Flag `otaRemoteAttempted` (RAM, nao NVS) evita loop infinito.

### Corrigido
- **v4.0.11** — Estado per-chipId: `localState`, `pendingCommands`, `lastToggleTimes` deixam de ser globais (antes clicar em um modulo afetava visualmente todos por 35s).
- **v4.0.13** — Merge de server_keys no register: `phases`, `num_phases`, `start_date` saem da protecao. ESP32 passa a ser fonte de verdade para fases/config.
- **v4.0.14** — PWA recalcula `cycle_day` e `phase` no navegador usando `Date()` do browser (relogio do ESP32 pode ter NTP desincronizado).

---

## [4.0.0] - 2026-04-10

### Adicionado
- **Galeria com pastas** — `bp_gallery.py` (7 endpoints: pastas, imagens, selecao, exclusao) + `gallery.js` modal com grid 3 colunas, selecao multipla, delete. Upload salva na pasta ativa (`capture_folder` em ctrl_data). Migracao automatica de fotos existentes pra `_sem-pasta`.
- **Sensor config OV2640** — modal com 11 parametros: WB mode, brilho, contraste, saturacao, compensacao de exposicao, teto de ganho, efeito especial, espelhar, inverter, auto-exposicao, auto-WB. Persistido em ctrl_data, enviado ao ESP32 via `set-camera`.
- **Camera otimizada em 2 estagios** — init UXGA q4 (buffer grande) + reduz para VGA (uso normal). Flush de 3 frames apos mudanca de resolucao pra AEC estabilizar. Resolucao/qualidade selecionavel pelo usuario.
- **Layout desktop** — cards lado a lado em telas >= 640px, `max-width: 1100px` pra aproveitar tela grande. Mobile continua em coluna unica.

---

## [3.6.0] - 2026-04-10

### Alterado
- `bump: v3.6.0 — forca refresh cache PWA` (commit `c2be03b`, 15:12 BRT — ~45min antes do v4.0.0). Bump minimo de `APP_VERSION` pra forcar o Service Worker a invalidar o cache e entregar a UI recem-atualizada. Tipicamente usado quando mudanca so em CSS/JS nao dispara o browser a recarregar o SW sozinho.

---

## [3.5.0] - 2026-04-10

### Alterado
- **Camera refatorada pra always-on** (init unico no boot, nunca `esp_camera_deinit()`). DMA estavel, captura instantanea, WiFi estavel com zero falhas DMA.
- XCLK **20 MHz → 8 MHz** — EMI minima, WiFi ping 35ms (antes 1435ms!).
- `fb_count` 1 → 2 — double buffering, DMA continuo.
- `jpeg_quality` init 12 → 10 — buffer maior previne truncamento.
- 4 frames descartados no boot — auto-exposure/AWB estabiliza.

### Adicionado
- `docs/guia-otimizacao-esp32-cam.md` — referencia completa de otimizacao da OV2640.

### Notas
- Historico de tentativas registrado no commit: on-demand (v3.4.0) falhava por DMA instavel com deinit repetido, `captureHighRes` tinha timeout, `send_P` falhava com binarios grandes. Always-on seguindo guia Espressif e a unica estrategia que funciona consistentemente.

---

## [3.4.0] - 2026-04-09

### Alterado
- **Cam**: XCLK 10 MHz, init SVGA, TX power 8.5 dBm, camera init **apos** WiFi.
- **Cam**: particao `no_ota` (2.0 MB), `FIRMWARE_VERSION` adicionado.
- **Hidro**: sync de estados dos reles ao trocar auto/manual na PWA.

### Notas
- Cam ainda em 60% flash (no_ota USB), Hidro em 62% (min_spiffs OTA).
- Proximo objetivo naquele momento era init on-demand (abandonado em v3.5.0 apos testar).

---

## [3.3.0] - 2026-04-09

### Adicionado
- **Web OTA** — pagina `/update` pra atualizar firmware via navegador (upload .bin).
- `compile.sh` — gera `build/firmware.ino.bin` pronto pra upload OTA.
- `FIRMWARE_VERSION` em `products/hidro.h` (mostrado na pagina de OTA).
- Footer do dashboard com links: WiFi | Firmware | versao.

### Alterado
- Particao firmware: `default (no_ota)` → `min_spiffs` — 1.9 MB por slot (62% usado, antes era 93% — espaco pra OTA).
- CLAUDE.md atualizado com novos comandos de compilacao.

---

## [3.2.0] - 2026-04-09

### Adicionado
- **RTC DS3231** como fallback de tempo (I2C GPIO21/22). Mantem hora mesmo sem WiFi/NTP.
- Seed automatico do RTC com data da compilacao no primeiro boot.
- Validacao de data do RTC (ignora ano < 2024 — data suja).
- NTP sincroniza e atualiza RTC automaticamente.
- Controle de **ventilacao (D18)** e **aeracao (D19)** — agora 4 reles (antes 2).
- Indicador de fonte de tempo no dashboard (NTP/RTC).

### Alterado
- WiFi scan: `WIFI_AP_STA` no setup + disconnect antes do scan (corrigia scan travado).
- Reconexao WiFi nao-bloqueante (60s background).
- Versionamento unificado em `server/config.py` (fonte unica — antes espalhado em varios lugares).

### Notas
- GPIO map: `D0=BOOT D2=LED D4=LUZ D5=BOMBA D18=VENT D19=AERA D21=SDA D22=SCL`.
- Flash em 93% (1.22 MB de 1.31 MB) — particao default ainda, sem espaco pra OTA. Proximo passo: trocar pra `min_spiffs` (aconteceu na v3.3.0).

---

## [Pre-split — monorepo cultivee] - 2026-03-20 14:43 BRT a 2026-04-08 19:00 BRT

Historico do repo unificado [`mardoqueucosta/cultivee`](https://github.com/mardoqueucosta/cultivee) (tag `v1.0-monorepo` = commit `a3ab34a`, 48 commits) que continha **site + servidor + firmware** antes do split em dois repos (`cultivee-platform` + `cultivee.com.br`). Datas em horario de Brasilia (UTC-3).

**Observacoes:**
- Monorepo **nao tem GitHub Releases** formais — so git tags. A tag `v1.0-monorepo` e a unica verdadeiramente pre-split; a tag `v1.1-4reles` (tambem no remote monorepo) foi criada **apos** o split e aponta pra commits que ja vivem no `cultivee-platform` (os primeiros da v3.1.0).
- Branch `claude/scheduled-image-capture-aVOiL` no monorepo tem 1 commit extra (`df55412`, 2026-03-29) com um implementation plan que nao foi mergeado — nao listado abaixo.
- Hidratacao rapida: **v1.0 → v1.8.0 todos em 2026-03-21** (uma tarde de iteracao no setup wizard, das 13:40 as 22:58). Versionamento da PWA, nao do firmware.

### Marcos arquiteturais (commits significativos, datas ISO + BRT)

- **2026-04-08 19:00:53** `a3ab34a` — Snapshot pre-split: estado completo do monorepo no ponto da separacao.
- **2026-03-30 14:29:33** `4b06575` — `PLANO-VISAO-GERAL-SOFTWARE.md` (arquitetura modular documentada).
- **2026-03-30 06:21:37** `36bc243` — Resolucao/qualidade de foto configuravel + thumbnails na galeria.
- **2026-03-29 20:52:12** `64d2e68` — Captura agendada + galeria de imagens.
- **2026-03-29 15:51:15** `9bbd294` — Remove produto `hidro-cam` (WROVER fica dedicado a camera).
- **2026-03-29 15:42:35** `aa33cda` — **Servidor unificado** Flask + produto `cam` standalone + **registry pattern** na PWA.
- **2026-03-29 09:47:39** `7897d6c` — **Refactor grande**: reorganizacao em estrutura modular unificada (`firmware/`, `products/`, `server/`).
- **2026-03-28 10:10:04** `58ac51f` — Site ganha pagina Aplicativos com cards dos 3 apps.
- **2026-03-28 10:09:42** `98f5937` — Hidro-cam completo: captura, stream ao vivo, card colapsavel.
- **2026-03-28 03:31:56** `4c41d57` — Projeto Hidro-cam: copia do Hidro pra ESP32-WROVER-DEV com camera (depois descontinuado na refactor de 2026-03-29).
- **2026-03-27 21:35:22** `9e2f200` — Subdominio `cam.cultivee.com.br` (descontinuado depois).
- **2026-03-27 21:18:47** `1dcf50c` — firmware-wrover: WiFi hibrido AP+STA, MJPEG stream.
- **2026-03-23 13:29:27** `f312aec` — firmware-ctrl: modo AP hibrido, formato data BR, dashboard local atualizado.
- **2026-03-23 07:07:21** `9b70b9f` — PWA Hidroponia + WiFi manager + polling adaptativo + **primeiro deploy VPS real**.
- **2026-03-22 08:06:54** `4579981` — Adicao do sistema de controle hidroponico (primeiro hardware ctrl — antes era so camera).

### Versoes marcadas no monorepo (bump de `APP_VERSION` da PWA)

- **v1.8.0** - 2026-03-21 22:58:25 `5eed4ee` — Recording toggle: imagens so salvas quando REC ativo.
- **v1.7.2** - 2026-03-21 15:43:06 `0d5632a` — Spacing ajustado entre navbar, module bar e live section.
- **v1.7.1** - 2026-03-21 15:37:44 `cba635e` — Module bar compacta: pill shape, menos padding, centralizada.
- **v1.7.0** - 2026-03-21 14:50:00 `aa66306` — Layout redesenhado: live stream no topo, module bar compacta.
- **v1.6.0** - 2026-03-21 14:38:50 `62fa8eb` — Offline module card simplificado com botao direto pra setup.
- **v1.5.0** - 2026-03-21 14:28:04 `4b472a5` — Setup wizard reduzido pra 2 steps + link direto pro portal.
- **v1.4.0** - 2026-03-21 14:18:06 `b5e45af` — Redesign do fluxo de setup: portal interativo + auto-pair.
- **v1.3.0** - 2026-03-21 14:04:36 `68fdebd` — Setup wizard simplificado pra 3 steps, fix info do AP.
- **v1.2.0** - 2026-03-21 13:47:34 `3005653` — Fix PWA update: clear caches antes de reload.
- **v1.1.0** - 2026-03-21 13:44:01 `be840d1` — In-app WiFi setup: scan e configurar ESP32 direto da PWA.
- **v1.0** - 2026-03-20 14:43:22 `7dc1eda` — Initial monorepo setup (site + server + firmware). **Primeiro commit do projeto.**

### Recuperando o historico pre-split localmente

Como o split foi feito sem `git subtree` (criamos `cultivee-platform` limpo a partir do monorepo), o historico acima **nao esta no repo atual**. Pra acessar:

```bash
# Fetch completo (tags + branches) do monorepo original como remote temporario
git remote add monorepo https://github.com/mardoqueucosta/cultivee.git
git fetch monorepo --tags "refs/heads/*:refs/remotes/monorepo/*"

# Listar os 48 commits pre-split com data/hora ISO
git log v1.0-monorepo --reverse --format="%ai | %h | %s"

# Detalhes de qualquer commit
git show <hash>

# Limpar quando terminar (nao deleta as refs fetchadas localmente, mas remove o remote)
git remote remove monorepo
git update-ref -d refs/tags/v1.0-monorepo  # opcional: remove tag local
```

**Nota**: o fetch traz ~185 objetos (48 commits da tag + branches). Numero enxuto — nao ocupa espaco significativo mesmo se mantido.
