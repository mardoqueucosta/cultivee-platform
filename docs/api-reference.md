# Cultivee API Reference

Compilação de todos os endpoints da API REST. Para a arquitetura + fluxos, ver [CLAUDE.md](../CLAUDE.md).

**Base URL:** `https://app.cultivee.com.br`
**Autenticação:** header `Authorization: Bearer <token>` (obtido via `/api/auth/login`). Exceções: endpoints públicos (registro, login, recuperação) e endpoints do ESP32 (register, poll, firmware).

---

## 📁 Organização por camada

| Prefixo | Camada | Arquivo |
|---|---|---|
| `/api/auth/*` | Usuário (público + autenticado) | `server/usuario/auth.py` |
| `/api/profile/*` | Usuário (só próprio) | `server/usuario/profile.py` |
| `/api/admin/*` | Admin (role='admin') | `server/admin/admin.py` |
| `/api/ctrl/*` | Hardware Hidro | `server/hardware/hidro.py` |
| `/api/hidro-farm/*` | Hardware Hidro-Farm | `server/hardware/hidrofarm.py` |
| `/api/cam/*` | Hardware Cam | `server/hardware/cam.py` |
| `/api/gallery/*` | Hardware (galeria de fotos) | `server/hardware/gallery.py` |
| `/api/modules/*` | Sistema (ESP32 + user) | `server/app.py` |
| `/api/push/*` | PWA (notificações) | `server/app.py` |
| `/api/user/prefs` | PWA (UI state) | `server/app.py` |

---

## 🔐 Autenticação (`/api/auth/*`)

| Método | Rota | Body | Descrição |
|---|---|---|---|
| POST | `/register` | `{name, email, password, accepted_terms: true, captcha_token?}` | Cadastro. Dispara email de verificação. Rate-limit 5/5min |
| POST | `/login` | `{email, password, totp_code?}` | Login. Se 2FA ativo, 1ª tentativa → 401 `{totp_required: true}`. Rate-limit 10/1min |
| GET | `/me` | — | Dados do user logado (id, email, name, role, email_verified) |
| POST | `/logout` | — | Invalida token atual |
| POST | `/forgot-password` | `{email}` | Envia link de reset. Anti-enumeration. Rate-limit 3/15min |
| POST | `/reset-password` | `{token, password}` | Valida token + troca senha (one-shot) |
| GET/POST | `/verify-email` | `?token=XXX` ou `{token}` | Consome token de verificação |
| POST | `/resend-verification` | — | Reenvia email de verificação. Rate-limit 3/10min |

---

## 👤 Perfil pessoal (`/api/profile/*`)

Todos exigem auth. Operam apenas na própria conta.

### Dados do usuário

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Perfil completo (sem `password_hash`) |
| PUT | `/` | Atualiza campos da whitelist (nome, telefone, endereço, dados fiscais, notification_email) |
| DELETE | `/` | Deleta conta com `{password}`. Cascade + protege último admin |
| POST | `/password` | Troca senha: `{current_password, new_password}` |
| GET | `/export` | Download JSON com todos os dados (LGPD — portabilidade) |
| GET | `/cep/<cep>` | Proxy pra ViaCEP (auto-preenchimento de endereço) |

### 2FA TOTP

| Método | Rota | Body | Descrição |
|---|---|---|---|
| POST | `/2fa/setup` | — | Gera secret + URI pra QR code |
| POST | `/2fa/enable` | `{code}` | Ativa 2FA com o 1º código de confirmação |
| POST | `/2fa/disable` | `{password, code}` | Desativa 2FA |

### Session management

| Método | Rota | Descrição |
|---|---|---|
| GET | `/sessions` | Lista tokens ativos (user_agent, ip, last_used_at) |
| DELETE | `/sessions/<id>` | Revoga sessão específica |
| POST | `/sessions/revoke-others` | Revoga todas exceto a atual |

---

## 👑 Admin (`/api/admin/*`)

Todos protegidos por `@require_admin` (401 sem auth, 403 sem role=admin).

### Dashboard + visualização

| Método | Rota | Descrição |
|---|---|---|
| GET | `/stats` | Contadores: users, modules (total/paired/online/by_type), alerts_24h, push_subscriptions |
| GET | `/users` | Lista todos os usuários com `module_count` + `last_token_at` |
| GET | `/users/<id>` | Detalhes + módulos pareados do user |
| GET | `/modules` | Todos os módulos com dono (JOIN user_email) |
| GET | `/audit` | Audit log paginado. Query: `limit`, `offset`, `action`, `admin_id`, `from`, `to` |

### Ações administrativas

| Método | Rota | Body | Descrição |
|---|---|---|---|
| POST | `/users/<id>/role` | `{role: 'user'/'support'/'admin'}` | Altera role. Protege último admin |
| POST | `/users/<id>/force-password-reset` | — | Gera reset token + email ao user + revoga todos os tokens |
| POST | `/users/<id>/impersonate` | `{minutes?: 5-240, view_only?: bool}` | Gera token de impersonation. Audit + notifica outros admins |
| POST | `/modules/<chip_id>/transfer` | `{new_user_id, new_name?}` | Transfere módulo entre users |

---

## 🔩 Hardware (ESP32)

### Módulos core (`/api/modules/*`)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| POST | `/register` | — (ESP32) | Poll principal do ESP32 — envia ctrl_data, recebe commands + `firmware_url` |
| GET | `/poll` | — (ESP32) | Polling rápido (1s) pra detectar comandos de relé novos |
| POST | `/pair` | Token | Vincular módulo via `short_id` |
| POST | `/unpair` | Token | Desvincular módulo |
| GET | `/` (lista) | Token | Lista módulos do user logado |
| POST | `/<chip_id>/firmware` | Token (admin) | Upload `.bin` pro OTA remoto (multipart) |
| GET | `/<chip_id>/firmware` | — (ESP32) | Download `.bin`. Auto-deletado após download (previne loop) |
| DELETE | `/<chip_id>/firmware` | Token (admin) | Cancela OTA pendente |

### Hidro (`/api/ctrl/*`)

Todas exigem auth + validam capability `"hidro"` + ownership.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/<chip>/status` | Status completo (light, pump, vent, aer, mode, phases) |
| GET | `/<chip>/relay?device=X&action=toggle` | Controle de relé. Proxy direto ou fila |
| GET | `/<chip>/phases?live=1` | Fases (live=1 força proxy ao ESP32) |
| POST | `/<chip>/save-config` | Salvar configuração de fases |
| GET | `/<chip>/add-phase` | Adicionar fase |
| GET | `/<chip>/remove-phase?idx=N` | Remover fase N |
| GET | `/<chip>/reset-phases` | Reset pro default |
| GET | `/<chip>/reset-wifi` | Reset do WiFi do ESP32 |

### Hidro-Farm (`/api/hidro-farm/*`)

Mesmas rotas do Hidro + suporte aos relés adicionais (`valve_entrada`, `bomba_homo`). Capability exigida: `"hidro-farm"`.

### Cam (`/api/cam/*`)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/<chip>/capture` | Token | Enfileira captura |
| POST | `/<chip>/upload-capture` | — (ESP32) | ESP32 envia foto |
| GET | `/<chip>/image/<file>` | Token | Serve imagem |
| GET | `/<chip>/start-live` / `/stop-live` | Token | Live mode |
| GET/POST | `/<chip>/live-frame` | Token/— | GET: PWA poll frame. POST: ESP32 push frame |
| GET | `/<chip>/last-capture` | Token | URL da última captura |

### Galeria (`/api/gallery/*`)

Gerencia organização por pastas (listar, mover entre pastas, excluir em lote). Auth obrigatória.

---

## 📱 PWA utils

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/push/subscribe` | Registra push subscription `{endpoint, keys: {p256dh, auth}}` |
| POST | `/api/push/unsubscribe` | Remove subscription |
| GET | `/api/push/status` | `{subscribed: bool}` |
| GET | `/api/user/prefs` | Ordem + seleção de módulos `{selected, order}` |
| PUT | `/api/user/prefs` | Salva prefs |

---

## 📄 Páginas públicas (não-JSON)

| Rota | Descrição |
|---|---|
| `/` | PWA app (template `index.html`) |
| `/manifest.json` | Manifest do PWA (gerado dinamicamente) |
| `/sw.js` | Service Worker (gerado dinamicamente — cache busting por APP_VERSION) |
| `/termos` | Termos de Uso |
| `/privacidade` | Política de Privacidade (LGPD) |
| `/?reset=TOKEN` | Deep link pra reset de senha (PWA abre tela) |
| `/?verify=TOKEN` | Deep link pra verificação de email |
| `/?code=XXXX` | Deep link pra pairing rápido de módulo |

---

## 🛡️ Guards & Middlewares

**`@require_auth`** (`app.py`): valida Bearer token, popula `request.user`. 401 se inválido.

**`@require_admin`** (`usuario/auth.py`): exige `role='admin'`. 401 sem token, 403 se não-admin.

**`@rate_limit(max, window)`** (`usuario/auth.py`): in-memory por IP+endpoint.

**`@before_request _readonly_scope_guard`** (`app.py`): bloqueia mutações (POST/PUT/DELETE + GETs legados como `/relay`, `/capture`) em tokens com `scope='readonly'` (usado pelo modo "Ver como" do admin).

---

## 📊 Status HTTP padronizados

| Código | Quando |
|---|---|
| **200** | OK |
| **400** | Body/params inválidos, validação falhou |
| **401** | Não autenticado ou token inválido/expirado |
| **403** | Autenticado mas sem permissão (role, scope readonly, capability errada, ownership errado) |
| **404** | Recurso não encontrado (user, módulo) |
| **409** | Conflito (email já cadastrado) |
| **429** | Rate limit excedido — mensagem tem o tempo de espera |
| **502** | Falha de proxy (SMTP, ViaCEP) |

---

## 🧪 Testing / dev

Smoke tests locais: `python server/test_routes.py` (cobertura parcial).

Simuladores de hardware (rodam sem ESP32 físico):
```bash
python server/sim_esp32.py ctrl         # Hidro, código SC01
python server/sim_esp32.py hidro-farm   # Hidro-Farm, código HF01
python server/sim_esp32.py cam          # Cam, código CA01
```

Dev server local: `python server/run-app.py` (porta 5002).
