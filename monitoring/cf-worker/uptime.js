/**
 * Cultivee — Uptime Monitor (Cloudflare Worker)
 *
 * Roda a cada 2 minutos via Cron Trigger (configurado fora deste arquivo).
 * Faz GET em app.cultivee.com.br, valida que retornou 200 e que o body
 * contem a palavra "Cultivee" (sanity check basico — se a app crashou e
 * voltou pagina default, ainda detectamos).
 *
 * Se falhar, envia email via Mailchannels (gratis pra Workers no
 * Cloudflare). Cooldown de 30min entre emails iguais usando Cache API
 * (sem precisar de Workers KV — fica no free tier).
 *
 * Logs ficam disponiveis no dashboard Cloudflare > Workers > este script
 * > "Logs" (Tail Workers, retencao 7 dias no plano free).
 */

const CHECK_URL = 'https://app.cultivee.com.br/';
const NOTIFY_TO = 'mardo.abc@gmail.com';
const NOTIFY_FROM = 'monitor@cultivee.com.br';
const NOTIFY_FROM_NAME = 'Cultivee Monitor';
const FETCH_TIMEOUT_MS = 10000;
const COOLDOWN_SECONDS = 1800; // 30 min entre emails de mesmo estado

// Chave fake-URL pra cache (Cache API exige Request com URL valida)
const CACHE_KEY_DOWN = new Request('https://internal.cultivee/uptime/last-alert-down');
const CACHE_KEY_UP = new Request('https://internal.cultivee/uptime/last-alert-up');

export default {
  // GET / -> retorna status; GET /trigger -> dispara verificacao + email pra testar
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/trigger') {
      await this.scheduled(null, env, ctx);
      return new Response('triggered (veja logs do Worker)\n', { status: 200 });
    }
    if (url.pathname === '/check') {
      // Apenas verifica sem alertar/cooldown — util pra status simples
      const r = await checkOnce();
      return new Response(JSON.stringify(r, null, 2), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(
      'Cultivee Uptime Monitor\n\n' +
      'Endpoints:\n' +
      '  GET /check    -> verifica app.cultivee.com.br agora (sem alertar)\n' +
      '  GET /trigger  -> dispara fluxo completo (com email se down)\n\n' +
      'Cron: */2 * * * * (auto)\n',
      { status: 200, headers: { 'Content-Type': 'text/plain' } }
    );
  },

  async scheduled(event, env, ctx) {
    const result = await checkOnce();
    const ts = new Date().toISOString();

    if (result.healthy) {
      console.log(`[OK] ${ts} status=200 body~Cultivee`);
      // Se estavamos em estado "down" anteriormente (cooldown_down ativo),
      // significa que o site VOLTOU. Avisa e limpa o cooldown.
      const cache = caches.default;
      const wasDown = await cache.match(CACHE_KEY_DOWN);
      if (wasDown) {
        ctx.waitUntil(announceRecovery(cache));
      }
      return;
    }

    console.error(`[DOWN] ${ts} ${result.reason}`);

    // Cooldown — se ja avisamos sobre um down nos ultimos 30min, pula
    const cache = caches.default;
    const cooldown = await cache.match(CACHE_KEY_DOWN);
    if (cooldown) {
      console.log(`[DOWN] alerta ja enviado recentemente — cooldown ativo`);
      return;
    }

    ctx.waitUntil(announceDown(cache, result.reason));
  },
};

async function checkOnce() {
  try {
    const r = await fetch(CHECK_URL, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: {
        'User-Agent': 'Cultivee-Uptime-Monitor/1.0 (Cloudflare Worker)',
        'Accept': 'text/html',
      },
      cf: { cacheTtl: 0, cacheEverything: false }, // sem cache do CF
    });
    if (!r.ok) {
      return { healthy: false, reason: `HTTP ${r.status}` };
    }
    const body = await r.text();
    if (!body.includes('Cultivee')) {
      return { healthy: false, reason: `body inesperado (sem palavra "Cultivee")` };
    }
    return { healthy: true };
  } catch (e) {
    return { healthy: false, reason: `fetch error: ${e.name}: ${e.message}` };
  }
}

async function announceDown(cache, reason) {
  const ts = new Date().toISOString();
  const subject = `[Cultivee] ⚠ Servidor offline detectado`;
  const body = `Cultivee Uptime Monitor

Quando:    ${ts}
URL:       ${CHECK_URL}
Motivo:    ${reason}

O monitor continua verificando a cada 2 minutos. Voce recebera outro
email automaticamente quando o servico voltar.

Logs do Worker:
https://dash.cloudflare.com/  (Workers & Pages > cultivee-uptime > Logs)

Comandos uteis (SSH na VPS):
  docker logs cultivee-app --tail 50
  docker ps --filter name=cultivee-app
  systemctl status docker

--
Cultivee Monitor (Cloudflare Worker)
`;
  try {
    await sendMail(subject, body);
    // Marca cooldown — nao reenvia email DOWN nos proximos 30min
    await cache.put(
      CACHE_KEY_DOWN,
      new Response(JSON.stringify({ alerted_at: ts, reason }), {
        headers: { 'Cache-Control': `max-age=${COOLDOWN_SECONDS}` },
      })
    );
    console.log(`[DOWN] email enviado pra ${NOTIFY_TO}`);
  } catch (e) {
    console.error(`[DOWN] falha ao enviar email: ${e.message}`);
  }
}

async function announceRecovery(cache) {
  const ts = new Date().toISOString();
  const subject = `[Cultivee] ✓ Servidor de volta online`;
  const body = `Cultivee Uptime Monitor

O servidor https://app.cultivee.com.br/ voltou a responder normalmente.

Confirmado em: ${ts}

Recomendado: revisar os logs pra entender o que aconteceu.

--
Cultivee Monitor (Cloudflare Worker)
`;
  try {
    await sendMail(subject, body);
    await cache.delete(CACHE_KEY_DOWN);
    console.log(`[UP] email de recovery enviado`);
  } catch (e) {
    console.error(`[UP] falha ao enviar recovery: ${e.message}`);
  }
}

async function sendMail(subject, plainBody) {
  const r = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [
        { to: [{ email: NOTIFY_TO }] },
      ],
      from: { email: NOTIFY_FROM, name: NOTIFY_FROM_NAME },
      subject,
      content: [{ type: 'text/plain', value: plainBody }],
    }),
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`Mailchannels HTTP ${r.status}: ${txt.slice(0, 200)}`);
  }
}
