# Changelog

Todas as mudancas relevantes do projeto Cultivee Platform sao documentadas neste arquivo.

O formato segue [Keep a Changelog 1.1.0](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/).

Para contexto mais profundo de decisoes arquiteturais (por que foi feito assim, o que foi descartado), ver `docs/sessoes/YYYY-MM-DD.md` da rodada correspondente.

---

## [Nao lancado]

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

## [4.1.9] - [4.1.11] - 2026-04-20

### Adicionado
- **v4.1.10** — Persistencia de ordem + selecao de modulos no servidor (antes so localStorage). Coluna `users.module_prefs` JSON.
- **v4.1.9** — Persistencia do botao "Ao Vivo" da camera apos reload (`cam_live_mode` em ctrl_data + sync servidor).

### Corrigido
- **v4.1.11** — `PUT /api/user/prefs` salvava `{}` em vez do payload (body era string ja-stringificada).

---

## [4.1.8] - 2026-04-20

### Adicionado
- Telemetria WiFi: `wifi_last_error`, `wifi_last_connected_ms`, `wifi_disconnect_count`, `WiFi.onEvent()` + `setAutoReconnect(true)`.
- Cam migrado de particao `no_ota` pra `min_spiffs` — agora suporta OTA remoto.
- **v4.1.10 (Cam)** — `LIVE_MAX_DURATION` subiu de 2min pra 10min.

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
- Galeria com pastas (`gallery.js`): grid, selecao multipla, exclusao em lote, mover entre pastas.
- Sensor config da camera (brightness, contrast, saturation, AE level, etc.).
- Layout desktop responsivo com ate 3 colunas.

---

## Versoes anteriores

Historico pre-v4.0.0 vive no monorepo original (`mardoqueucosta/cultivee` tag `v1.0-monorepo`) — antes do split em `cultivee-platform` + `cultivee.com.br`.
