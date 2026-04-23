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
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/trigger') {
      await this.scheduled(null, env, ctx);
      return new Response('triggered (veja logs do Worker)\n', { status: 200 });
    }
    if (url.pathname === '/check') {
      const r = await checkOnce();
      return new Response(JSON.stringify(r, null, 2), {
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
      });
    }
    // GET / -> status page HTML (visual)
    return await renderStatusPage();
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

async function renderStatusPage() {
  const result = await checkOnce();
  const ts = new Date();
  const isOk = result.healthy;

  // Le ultimo alerta DOWN do cache (se ativo, mostramos "indisponivel desde X")
  let downSince = null;
  try {
    const cache = caches.default;
    const cached = await cache.match(CACHE_KEY_DOWN);
    if (cached) {
      const data = await cached.json();
      downSince = data.alerted_at;
    }
  } catch (_) {}

  const statusColor = isOk ? '#27ae60' : '#e74c3c';
  const statusBg = isOk ? 'rgba(39,174,96,0.12)' : 'rgba(231,76,60,0.12)';
  const statusIcon = isOk ? '&#10003;' : '&#9888;';
  const statusTitle = isOk ? 'Tudo operacional' : 'Servico indisponivel';
  const statusSubtitle = isOk
    ? 'Plataforma Cultivee respondendo normalmente.'
    : (result.reason ? `Detectado: ${escapeHtml(result.reason)}` : 'Detectamos um problema na ultima verificacao.');

  const downBanner = (!isOk && downSince)
    ? `<div class="alert">Indisponivel desde <b>${escapeHtml(formatBR(downSince))}</b>.</div>`
    : '';

  const tsBR = formatBR(ts.toISOString());

  const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Status Cultivee${isOk ? '' : ' — Indisponivel'}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1923;color:#e8e8e8;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:40px 16px}
  .wrap{max-width:560px;width:100%}
  .brand{display:flex;align-items:center;gap:10px;margin-bottom:32px}
  .logo{width:36px;height:36px;background:#27ae60;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:1.1rem}
  .brand-name{font-size:1.05rem;font-weight:600;color:#e8e8e8}
  .brand-sub{font-size:0.75rem;color:#7d8a98}
  .card{background:#1a2530;border:1px solid #2a3946;border-radius:14px;padding:28px;text-align:center}
  .status-icon{display:inline-flex;align-items:center;justify-content:center;width:64px;height:64px;border-radius:50%;background:${statusBg};color:${statusColor};font-size:1.8rem;margin-bottom:14px;font-weight:700}
  .status-title{font-size:1.5rem;font-weight:700;color:${statusColor};margin-bottom:6px}
  .status-sub{color:#9ca7b3;font-size:0.9rem;line-height:1.5}
  .alert{background:rgba(231,76,60,0.1);border:1px solid #e74c3c;color:#fcd0c8;border-radius:8px;padding:10px 14px;margin-top:14px;font-size:0.85rem}
  .meta{margin-top:24px;padding-top:18px;border-top:1px solid #2a3946;font-size:0.75rem;color:#7d8a98;display:grid;gap:6px}
  .meta b{color:#c8d3df}
  .links{margin-top:18px;display:flex;justify-content:center;gap:16px;font-size:0.78rem}
  .links a{color:#27ae60;text-decoration:none}
  .links a:hover{text-decoration:underline}
  .footer{margin-top:24px;font-size:0.7rem;color:#5a6878;text-align:center}
  .footer a{color:#7d8a98;text-decoration:none}
  @media (max-width: 480px){.card{padding:20px}.status-title{font-size:1.25rem}}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">
    <div class="logo">C</div>
    <div>
      <div class="brand-name">Cultivee</div>
      <div class="brand-sub">Status do servico</div>
    </div>
  </div>
  <div class="card">
    <div class="status-icon">${statusIcon}</div>
    <div class="status-title">${statusTitle}</div>
    <div class="status-sub">${statusSubtitle}</div>
    ${downBanner}
    <div class="meta">
      <div>Verificado em: <b>${escapeHtml(tsBR)}</b></div>
      <div>Verificacoes automaticas: <b>a cada 2 minutos</b></div>
      <div>Endereco monitorado: <b>app.cultivee.com.br</b></div>
    </div>
    <div class="links">
      <a href="/check">Verificar agora (JSON)</a>
      <span style="color:#5a6878">&middot;</span>
      <a href="https://app.cultivee.com.br/" target="_blank" rel="noopener">Abrir app</a>
    </div>
  </div>
  <div class="footer">
    Pagina atualizada a cada acesso &middot;
    <a href="https://cultivee.com.br" target="_blank" rel="noopener">cultivee.com.br</a>
  </div>
</div>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    },
  });
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatBR(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'medium' });
  } catch (_) { return iso; }
}

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
