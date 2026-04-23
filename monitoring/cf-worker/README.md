# Cultivee — Uptime Monitor (Cloudflare Worker)

Worker que verifica `https://app.cultivee.com.br/` a cada 2 minutos e
envia email se cair. Externo ao servidor — sobrevive a falhas dele.

**Status page publica:** <https://status.cultivee.com.br/>
**Endpoint JSON:** <https://status.cultivee.com.br/check>

Estilo Atlassian Statuspage / status.claude.com:
- Multiplos componentes monitorados (App + Site)
- Barrinhas de uptime de 90 dias por componente (verde/amarelo/vermelho)
- Uptime % por janela: 24h / 7d / 30d / 90d
- Historico de incidentes auto-detectados (ultimos 30 dias)
- Persistencia em Cloudflare KV (free tier)

## Arquitetura

```
┌──────────────────┐  fetch/2min   ┌──────────────────────┐
│ Cloudflare Edge  │ ────────────▶ │ app.cultivee.com.br  │
│ (Worker + Cron)  │ ◀──── 200 ── │ (VPS, container app) │
└──────┬───────────┘               └──────────────────────┘
       │ se status != 200
       │ ou body sem "Cultivee"
       ▼
┌──────────────────┐  Mailchannels  ┌──────────────────┐
│ Cooldown 30 min  │ ─────────────▶ │ mardo.abc@gmail  │
│ (Cache API)      │                │ + recovery email │
└──────────────────┘                └──────────────────┘
```

## Componentes monitorados

Editar a constante `COMPONENTS` em `uptime.js`. Cada item tem:
- `id`, `name`, `description` (mostrados no card)
- `url` (alvo do GET)
- `expectStatus` (default 200)
- `expectBody` (string que precisa estar no body — opcional)

Atualmente:
1. **App Cultivee** — `app.cultivee.com.br/` valida HTTP 200 + palavra "Cultivee"
2. **Site institucional** — `cultivee.com.br/` valida apenas HTTP 200

Pra adicionar componente novo, append na lista + redeploy.

## Persistencia (Cloudflare KV)

Namespace: `cultivee_status` (id `3c4314b3fd394c6b8af6d31bf44678a2`)
Bind no Worker: `STATUS_KV`

Chaves:
- `current:{component_id}` — snapshot atual (TTL 24h)
- `daily:{component_id}:{YYYY-MM-DD}` — agregado diario (TTL 100 dias)
- `incident:{component_id}:{start_iso}` — incidentes (TTL 100 dias)
- `cooldown:{component_id}:{down|up}` — cooldown email 30min

Uso esperado: ~720 writes/dia (cron 2min × 2 components × 1 write daily +
poucos writes em transicoes), bem dentro do free tier de 1.000 writes/dia.

## Detecao automatica de incidentes

- Abre incidente: 2 checks DOWN consecutivos do mesmo componente
- Fecha incidente: 2 checks UP consecutivos
- Email de alerta: 1 vez por transicao (cooldown 30min)

Editavel em `INCIDENT_OPEN_THRESHOLD` / `INCIDENT_CLOSE_THRESHOLD` no JS.

## Caracteristicas

- **Cadencia:** 2 minutos (cron `*/2 * * * *`) — 720 execucoes/dia,
  bem dentro dos 100k requests/dia do free tier.
- **Cooldown:** 30min entre emails de mesmo estado (sem spam se cair por horas).
- **Email de recovery:** quando volta, voce recebe segundo email automatico.
- **Sem dependencia interna:** roda na borda Cloudflare, nao usa o servidor
  Cultivee — detecta exatamente quando ele NAO responde.
- **Logs:** retencao 7 dias no plano free, viewable em
  Dashboard CF > Workers & Pages > cultivee-uptime > Logs.

## Deploy

### Primeira vez

Use o script `deploy.sh` (na mesma pasta):

```bash
cd monitoring/cf-worker
bash deploy.sh
```

O script:
1. Le `cloudflare-cultivee.env` (pega `CF_API_TOKEN` + `CF_ACCOUNT_ID`)
2. PUT do JS via API Cloudflare Workers Scripts
3. Configura Cron Trigger
4. Imprime URL do dashboard pra acompanhar logs

Pre-requisitos:
- `CF_API_TOKEN` em `D:/01-projetos-claude/.credentials/cloudflare-cultivee.env`
  com escopos `Account.Workers Scripts:Edit` + `Account.Account Settings:Read`

### Atualizar (depois de mudar uptime.js)

Mesmo comando: `bash deploy.sh`. Idempotente — atualiza in-place.

## Email de alerta — configuracao do remetente

Mailchannels e gratis pra Workers, MAS o email pode cair em spam se o
SPF do dominio remetente nao estiver configurado.

**Setup recomendado** (uma vez):

1. No Cloudflare DNS de `cultivee.com.br`, adicionar TXT record:
   ```
   _mailchannels.cultivee.com.br  TXT  v=mc1 cfid=cultivee.workers.dev
   ```
   (substitui `cultivee.workers.dev` pelo seu subdominio Workers — apos primeiro deploy)

2. SPF record existente em `cultivee.com.br` ja inclui o HostGator. Pra
   incluir Mailchannels tambem, atualizar:
   ```
   cultivee.com.br  TXT  "v=spf1 include:_spf.hostgator.com.br include:relay.mailchannels.net ~all"
   ```

Sem essa config, o email ainda chega mas pode cair em "spam" do Gmail.

## Mudar destinatario

Editar `uptime.js`, linhas:
```javascript
const NOTIFY_TO = 'mardo.abc@gmail.com';
const NOTIFY_FROM = 'monitor@cultivee.com.br';
```

E rodar `bash deploy.sh` de novo.

## Verificar status agora

3 formas:

1. **Status page publica (visual):** <https://status.cultivee.com.br/>
2. **API JSON:** <https://status.cultivee.com.br/check> -> `{"healthy": true|false, "reason": "..."}`
3. **Forca fluxo completo (envia email se DOWN):** <https://status.cultivee.com.br/trigger>

Logs em tempo real:
- Dashboard CF > Workers & Pages > `cultivee-uptime` > **Logs (live)** (retencao 7 dias)

## Custom domain

Configuracao atual (criada via API durante setup):
- DNS record: `status.cultivee.com.br` CNAME proxied -> `cultivee.workers.dev`
- Worker Route: `status.cultivee.com.br/*` -> script `cultivee-uptime`

Pra mudar o subdomain (ex: pra `monitor.cultivee.com.br`):
1. Criar novo DNS record proxied no Cloudflare
2. Criar nova Worker Route com novo padrao
3. Opcional: deletar DNS + Route antigos

## Custo / limites do plano free

| Recurso | Limite free | Uso real esperado |
|---|---|---|
| Worker requests | 100k/dia | ~720/dia (cron 2min) |
| CPU per request | 10ms | Bem abaixo (so fetch + parse) |
| Cron Triggers | 5 por conta | Usamos 1 |
| Cache API | Free, sem limite explicito | ~720 reads + ~720 writes/dia |
| Mailchannels emails | 1.200/mes | ~5/mes em condicao normal |

## Remover

Pra desativar (sem deletar):
- Dashboard CF > Workers > `cultivee-uptime` > Triggers > deletar Cron

Pra deletar tudo:
```bash
bash teardown.sh
```
