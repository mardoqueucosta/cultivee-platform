# Cultivee — Uptime Monitor (Cloudflare Worker)

Worker que verifica `https://app.cultivee.com.br/` a cada 2 minutos e
envia email se cair. Externo ao servidor — sobrevive a falhas dele.

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

Forca 1 execucao manual (via API):
```bash
bash trigger-now.sh
```

Ou ver os ultimos logs:
- Dashboard CF > Workers & Pages > `cultivee-uptime` > **Logs (live)**

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
