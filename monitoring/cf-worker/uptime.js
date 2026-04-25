/**
 * Cultivee — Status Page (Cloudflare Worker)
 *
 * Estilo Atlassian Statuspage / status.claude.com:
 *   - Multiplos componentes monitorados
 *   - Persistencia em KV (cultivee_status namespace)
 *   - Barrinhas de 90 dias por componente
 *   - Uptime % por janela (24h / 7d / 30d / 90d)
 *   - Historico de incidentes auto-detectados
 *
 * Dispara via:
 *   - Cron Trigger (a cada 5 minutos) — checa todos os componentes
 *   - GET /trigger             — manual (com email)
 *   - GET /check               — JSON do snapshot persistido (overall + components + uptime + incidents)
 *   - GET /check?c=app         — JSON apenas do componente "app"
 *   - GET /check?live=1        — JSON de probe ao vivo (sem KV, util pra health check simples)
 *
 * Renderiza:
 *   - GET /                    — HTML status page
 */

// ====== CONFIG ======

const COMPONENTS = [
  {
    id: 'app',
    name: 'App Cultivee',
    description: 'PWA + API REST — onde voce controla seus dispositivos',
    url: 'https://app.cultivee.com.br/',
    expectStatus: 200,
    expectBody: 'Cultivee',
  },
  {
    id: 'site',
    name: 'Site institucional',
    description: 'cultivee.com.br — landing, blog, conteudo publico',
    url: 'https://cultivee.com.br/',
    expectStatus: 200,
    // Sem expectBody — site institucional pode renderizar JS-first; valida so HTTP 200
  },
];

const NOTIFY_TO = 'mardo.abc@gmail.com';
const NOTIFY_FROM = 'monitor@cultivee.com.br';
const NOTIFY_FROM_NAME = 'Cultivee Monitor';
const FETCH_TIMEOUT_MS = 10000;
const ALERT_COOLDOWN_SECONDS = 1800;     // 30min entre emails do mesmo componente
const INCIDENT_OPEN_THRESHOLD = 2;       // 2 checks DOWN consecutivos = abre incidente
const INCIDENT_CLOSE_THRESHOLD = 2;      // 2 checks UP consecutivos = fecha incidente
const HISTORY_DAYS_VISUAL = 90;          // barrinhas mostradas
const KV_TTL_DAILY = 100 * 24 * 3600;    // 100 dias (folga sobre 90)
const KV_TTL_INCIDENT = 100 * 24 * 3600;

// v4.1.51: bug do detector de incidentes corrigido em 2026-04-25 ~22h UTC.
// Antes dessa data, openIncident() nunca disparava (condicao impossivel),
// entao quedas reais afetavam o uptime mas nao apareciam na lista. A nota
// abaixo informa visitantes desse gap. Auto-desativa 30 dias apos o fix
// (ate la, qualquer queda anterior cai fora da janela de 30d e o gap fica
// implicito). Nao precisa redeploy pra remover.
const INCIDENT_DETECTOR_FIXED_AT = '2026-04-25T22:00:00Z';
const INCIDENT_DETECTOR_NOTE_TTL_MS = 30 * 24 * 3600 * 1000;
// TTL 7d — `current:` carrega o acumulador in-place do dia (today_*),
// precisa sobreviver a eventuais pausas do cron sem perder o streak.
const KV_TTL_CURRENT = 7 * 24 * 3600;

// ====== ENTRYPOINT ======

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/trigger') {
      await this.scheduled(null, env, ctx);
      return new Response('triggered\n', { status: 200 });
    }
    if (url.pathname === '/check') {
      // ?live=1 — probe ao vivo (sem KV) — util pra health check simples
      if (url.searchParams.get('live') === '1') {
        const cid = url.searchParams.get('c');
        if (cid) {
          const c = COMPONENTS.find(x => x.id === cid);
          if (!c) return jsonResp({ error: 'unknown component' }, 404);
          return jsonResp(await checkComponent(c));
        }
        const all = await Promise.all(COMPONENTS.map(checkComponent));
        return jsonResp(Object.fromEntries(COMPONENTS.map((c, i) => [c.id, all[i]])));
      }
      // Default: snapshot consolidado do KV (mesmo que a pagina HTML usa)
      const snap = await buildStatusSnapshot(env);
      const json = snapshotToJson(snap);
      const cid = url.searchParams.get('c');
      // Cache 30s — admin/integradores nao precisam de tempo real e isso
      // protege contra refresh agressivo + bate com TTL da pagina HTML
      const cacheHeaders = { 'Cache-Control': 'public, max-age=30' };
      if (cid) {
        const comp = json.components.find(c => c.id === cid);
        if (!comp) return jsonResp({ error: 'unknown component' }, 404);
        return jsonResp({
          generated_at: json.generated_at,
          ...comp,
          incidents: json.incidents.filter(i => i.component === cid),
        }, 200, cacheHeaders);
      }
      return jsonResp(json, 200, cacheHeaders);
    }
    return await renderStatusPage(env);
  },

  async scheduled(event, env, ctx) {
    if (!env.STATUS_KV) {
      console.error('STATUS_KV binding ausente — Worker nao consegue persistir');
      return;
    }
    for (const comp of COMPONENTS) {
      ctx.waitUntil(processComponent(comp, env));
    }
  },
};

// ====== CORE: 1 ciclo de check + persistencia + alerta ======

// Design de writes (importante pro free tier KV = 1000 writes/dia):
// - `current:{id}` carrega o acumulador do DIA ATUAL in-place (today_checks,
//   today_healthy, etc.). 1 write por check (normal). 2 writes no primeiro
//   check de um dia novo (flush do dia anterior pra daily:YYYY-MM-DD).
// - `daily:{id}:{YYYY-MM-DD}` so e escrito 1x por componente por dia, na virada.
// Com cron `*/5`: 288 checks/dia × 2 componentes × 1 write = ~576 writes/dia.
async function processComponent(comp, env) {
  const result = await checkComponent(comp);
  const ts = new Date();
  const today = ymd(ts);

  const prev = await readJSON(env.STATUS_KV, `current:${comp.id}`);

  // 1) Se virou o dia, congela o acumulador anterior em `daily:{id}:{prevDay}`
  //    antes de resetar. Write extra — so acontece 1x por dia por componente.
  if (prev?.day && prev.day !== today) {
    await writeJSON(env.STATUS_KV, `daily:${comp.id}:${prev.day}`, {
      checks: prev.today_checks || 0,
      healthy: prev.today_healthy || 0,
      total_latency_ms: prev.today_total_latency_ms || 0,
      max_latency_ms: prev.today_max_latency_ms || 0,
    }, KV_TTL_DAILY);
  }

  // 2) Acumulador do dia atual (reset se virou o dia)
  const sameDay = prev?.day === today;
  const today_checks = (sameDay ? (prev.today_checks || 0) : 0) + 1;
  const today_healthy = (sameDay ? (prev.today_healthy || 0) : 0) + (result.healthy ? 1 : 0);
  const today_total_latency_ms = (sameDay ? (prev.today_total_latency_ms || 0) : 0)
    + (result.latency_ms || 0);
  const today_max_latency_ms = Math.max(
    sameDay ? (prev.today_max_latency_ms || 0) : 0,
    result.latency_ms || 0
  );

  // 3) Streaks + estado
  const fail_streak = result.healthy ? 0 : ((prev?.fail_streak || 0) + 1);
  const ok_streak = result.healthy ? ((prev?.ok_streak || 0) + 1) : 0;
  const current = {
    healthy: result.healthy,
    reason: result.reason || null,
    latency_ms: result.latency_ms || null,
    last_check_at: ts.toISOString(),
    fail_streak,
    ok_streak,
    last_down_at: result.healthy ? (prev?.last_down_at || null) : ts.toISOString(),
    last_up_at: result.healthy ? ts.toISOString() : (prev?.last_up_at || null),
    // Acumulador in-place (evita write separado em daily:{id}:{today})
    day: today,
    today_checks,
    today_healthy,
    today_total_latency_ms,
    today_max_latency_ms,
  };
  await writeJSON(env.STATUS_KV, `current:${comp.id}`, current, KV_TTL_CURRENT);

  // 4) Transicoes de incidente
  //
  // BUG corrigido (rodada 2026-04-25): a versao anterior usava
  //   `wasHealthy && !result.healthy && fail_streak >= INCIDENT_OPEN_THRESHOLD`
  // que NUNCA disparava. Trace: no 1o check de falha, `wasHealthy=true` mas
  // `fail_streak=1` (< 2). No 2o check de falha, `fail_streak=2` mas
  // `wasHealthy=false` (porque o `prev.healthy` ja virou false no ciclo
  // anterior). Resultado: nenhum incidente foi aberto desde o deploy
  // inicial do worker, mesmo com quedas reais (uptime caia mas a lista
  // de incidentes ficava vazia — visivel na pagina status.cultivee.com.br).
  //
  // Fix: detectar a TRANSICAO via `prev_streak < threshold && new_streak
  // >= threshold` — disparado exatamente uma vez quando o contador cruza
  // o threshold de baixo pra cima. Independe do flag `healthy` anterior.
  const prevFails = prev?.fail_streak || 0;
  const prevOks = prev?.ok_streak || 0;
  if (!result.healthy && prevFails < INCIDENT_OPEN_THRESHOLD && fail_streak >= INCIDENT_OPEN_THRESHOLD) {
    await openIncident(env, comp, current, result.reason);
    await sendAlertWithCooldown(env, comp, 'down', result.reason);
  } else if (result.healthy && prevOks < INCIDENT_CLOSE_THRESHOLD && ok_streak >= INCIDENT_CLOSE_THRESHOLD) {
    await closeIncident(env, comp, current);
    await sendAlertWithCooldown(env, comp, 'up', null);
  }
}

async function checkComponent(comp) {
  const t0 = Date.now();
  try {
    const r = await fetch(comp.url, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: {
        'User-Agent': 'Cultivee-Status-Monitor/1.0 (Cloudflare Worker)',
        'Accept': 'text/html',
      },
      cf: { cacheTtl: 0, cacheEverything: false },
    });
    const latency = Date.now() - t0;
    if (r.status !== comp.expectStatus) {
      return { healthy: false, reason: `HTTP ${r.status}`, latency_ms: latency };
    }
    if (comp.expectBody) {
      const body = await r.text();
      if (!body.includes(comp.expectBody)) {
        return { healthy: false, reason: `body sem "${comp.expectBody}"`, latency_ms: latency };
      }
    }
    return { healthy: true, latency_ms: latency };
  } catch (e) {
    return { healthy: false, reason: `${e.name || 'error'}: ${e.message}`, latency_ms: Date.now() - t0 };
  }
}

// ====== INCIDENTES ======

async function openIncident(env, comp, current, reason) {
  const start = current.last_down_at || new Date().toISOString();
  const key = `incident:${comp.id}:${start}`;
  const existing = await readJSON(env.STATUS_KV, key);
  if (existing) return;  // ja aberto
  const incident = {
    component: comp.id,
    component_name: comp.name,
    start, end: null, reason,
  };
  await writeJSON(env.STATUS_KV, key, incident, KV_TTL_INCIDENT);
  console.log(`[INCIDENT_OPEN] ${comp.id} reason=${reason}`);
  // v4.1.33: posta pra VPS pra marcar eventos dos modulos (best-effort)
  await postIncidentToVPS(env, incident);
}

async function closeIncident(env, comp, current) {
  // Acha o ultimo incidente aberto desse componente
  const list = await env.STATUS_KV.list({ prefix: `incident:${comp.id}:` });
  let openOne = null;
  for (const k of list.keys) {
    const inc = await readJSON(env.STATUS_KV, k.name);
    if (inc && !inc.end) { openOne = { key: k.name, data: inc }; break; }
  }
  if (!openOne) return;
  openOne.data.end = current.last_up_at || new Date().toISOString();
  await writeJSON(env.STATUS_KV, openOne.key, openOne.data, KV_TTL_INCIDENT);
  console.log(`[INCIDENT_CLOSE] ${comp.id}`);
  // v4.1.33: posta pra VPS (agora com end preenchido) — mark retroativo acontece la
  await postIncidentToVPS(env, openOne.data);
}

// ====== WEBHOOK VPS (v4.1.33) ======

// URL do endpoint da VPS. Sobrescrivivel via env pra permitir dev/local.
const VPS_WEBHOOK_URL_DEFAULT = 'https://app.cultivee.com.br/api/platform-incident';

/**
 * Posta o incidente pra VPS. Autentica via HMAC-SHA256 de `{ts}.{body}`.
 * Best-effort: log de erro se falhar, nao rethrowa pra nao quebrar o ciclo.
 */
async function postIncidentToVPS(env, incident) {
  const secret = env.PLATFORM_INCIDENT_SECRET;
  if (!secret) {
    console.log('[WEBHOOK skip] PLATFORM_INCIDENT_SECRET nao configurado');
    return;
  }
  const url = env.VPS_WEBHOOK_URL || VPS_WEBHOOK_URL_DEFAULT;
  const body = JSON.stringify({
    webhook_id: `${incident.component}:${incident.start}`,
    component: incident.component,
    component_name: incident.component_name,
    start: incident.start,
    end: incident.end,
    reason: incident.reason,
  });
  const ts = Math.floor(Date.now() / 1000);
  const sig = await hmacSha256Hex(secret, `${ts}.${body}`);
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Platform-Timestamp': String(ts),
        'X-Platform-Signature': sig,
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) {
      const txt = await r.text();
      console.error(`[WEBHOOK fail] ${incident.component} HTTP ${r.status}: ${txt.slice(0, 200)}`);
      return;
    }
    const resp = await r.json();
    console.log(`[WEBHOOK ok] ${incident.component} ${resp.status} events_marked=${resp.events_marked}`);
  } catch (e) {
    console.error(`[WEBHOOK error] ${incident.component}: ${e.message}`);
  }
}

/**
 * HMAC-SHA256 em hex. Usa Web Crypto (disponivel em Workers), pois
 * `crypto.createHmac` do Node nao existe aqui.
 */
async function hmacSha256Hex(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function listRecentIncidents(env, days = 30) {
  const cutoff = new Date(Date.now() - days * 86400e3).toISOString();
  const all = [];
  for (const comp of COMPONENTS) {
    const list = await env.STATUS_KV.list({ prefix: `incident:${comp.id}:` });
    for (const k of list.keys) {
      const inc = await readJSON(env.STATUS_KV, k.name);
      if (inc && inc.start >= cutoff) all.push(inc);
    }
  }
  all.sort((a, b) => b.start.localeCompare(a.start));
  return all;
}

// ====== ALERTAS POR EMAIL (cooldown) ======

async function sendAlertWithCooldown(env, comp, kind, reason) {
  const ckey = `cooldown:${comp.id}:${kind}`;
  const existing = await env.STATUS_KV.get(ckey);
  if (existing) {
    console.log(`[ALERT skip] ${kind} ${comp.id} — cooldown ativo`);
    return;
  }
  try {
    const subject = kind === 'down'
      ? `[Cultivee] ⚠ ${comp.name} indisponivel`
      : `[Cultivee] ✓ ${comp.name} de volta`;
    const body = kind === 'down'
      ? `${comp.name} (${comp.url}) parou de responder.\n\n` +
        `Detectado em: ${new Date().toISOString()}\n` +
        `Motivo: ${reason || 'desconhecido'}\n\n` +
        `Pagina de status: https://status.cultivee.com.br/\n`
      : `${comp.name} (${comp.url}) voltou a responder.\n\n` +
        `Confirmado em: ${new Date().toISOString()}\n\n` +
        `Pagina de status: https://status.cultivee.com.br/\n`;
    await sendMail(subject, body);
    await env.STATUS_KV.put(ckey, '1', { expirationTtl: ALERT_COOLDOWN_SECONDS });
    console.log(`[ALERT sent] ${kind} ${comp.id}`);
  } catch (e) {
    console.error(`[ALERT fail] ${kind} ${comp.id}: ${e.message}`);
  }
}

async function sendMail(subject, plainBody) {
  const r = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: NOTIFY_TO }] }],
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

// ====== KV HELPERS ======

async function readJSON(kv, key) {
  if (!kv) return null;
  const raw = await kv.get(key);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

async function writeJSON(kv, key, value, ttlSec) {
  if (!kv) return;
  await kv.put(key, JSON.stringify(value), ttlSec ? { expirationTtl: ttlSec } : undefined);
}

// ====== SNAPSHOT (compartilhado entre HTML e JSON) ======

/**
 * Le o estado consolidado do KV de todos os componentes.
 * Usado tanto pela pagina HTML (renderStatusPage) quanto pelo JSON (/check).
 */
async function buildStatusSnapshot(env) {
  const generatedAt = new Date().toISOString();
  const components = await Promise.all(
    COMPONENTS.map(async (c) => {
      const current = env.STATUS_KV ? await readJSON(env.STATUS_KV, `current:${c.id}`) : null;
      const days = await getDailySeries(env.STATUS_KV, c.id, HISTORY_DAYS_VISUAL);
      const stats = computeStats(days);
      return { ...c, current, days, stats };
    })
  );
  const incidents = env.STATUS_KV ? await listRecentIncidents(env, 30) : [];
  const allOk = components.every((c) => c.current?.healthy !== false);
  return { generatedAt, components, incidents, allOk };
}

/**
 * Converte o snapshot em JSON leve (sem o array `days` pesado).
 * Forma de saida estavel — ok pra clientes externos consumirem.
 */
function snapshotToJson(snap) {
  return {
    generated_at: snap.generatedAt,
    overall: {
      healthy: snap.allOk,
      status: snap.allOk ? 'operational' : 'incident',
    },
    components: snap.components.map((c) => ({
      id: c.id,
      name: c.name,
      description: c.description,
      url: c.url,
      current: c.current
        ? {
            healthy: c.current.healthy,
            reason: c.current.reason || null,
            latency_ms: c.current.latency_ms || null,
            last_check_at: c.current.last_check_at || null,
            last_down_at: c.current.last_down_at || null,
            last_up_at: c.current.last_up_at || null,
            fail_streak: c.current.fail_streak || 0,
            ok_streak: c.current.ok_streak || 0,
          }
        : null,
      uptime: {
        pct_24h: c.stats.pct_24h,
        pct_7d: c.stats.pct_7d,
        pct_30d: c.stats.pct_30d,
        pct_90d: c.stats.overall_pct,
      },
    })),
    incidents: snap.incidents.map((inc) => ({
      component: inc.component,
      component_name: inc.component_name || null,
      start: inc.start,
      end: inc.end || null,
      reason: inc.reason || null,
      duration_seconds: inc.end
        ? Math.round((new Date(inc.end) - new Date(inc.start)) / 1000)
        : null,
      ongoing: !inc.end,
    })),
  };
}

// ====== STATUS PAGE HTML ======

async function renderStatusPage(env) {
  const snap = await buildStatusSnapshot(env);
  const html = renderHTML({
    components: snap.components,
    incidents: snap.incidents,
    allOk: snap.allOk,
  });
  return new Response(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'public, max-age=30',  // cache leve evita carga
    },
  });
}

async function getDailySeries(kv, compId, days) {
  if (!kv) return [];
  const keys = [];
  const now = new Date();
  const today = ymd(now);
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setUTCDate(d.getUTCDate() - i);
    keys.push({ day: ymd(d), key: `daily:${compId}:${ymd(d)}` });
  }
  // Dia atual nao tem chave em daily:{today} — esta no acumulador in-place
  // dentro de current:{id} (today_checks, today_healthy, etc.). So leitura.
  const current = await readJSON(kv, `current:${compId}`);
  const values = await Promise.all(
    keys.map(({ day, key }) => {
      if (day === today) {
        // Materializa o dia atual a partir do current: (sem I/O extra)
        if (!current || current.day !== today) return null;
        return {
          checks: current.today_checks || 0,
          healthy: current.today_healthy || 0,
          total_latency_ms: current.today_total_latency_ms || 0,
          max_latency_ms: current.today_max_latency_ms || 0,
        };
      }
      return readJSON(kv, key);
    })
  );
  return keys.map(({ day }, i) => {
    const v = values[i];
    if (!v || !v.checks) return { day, status: 'no-data', checks: 0, healthy: 0 };
    const pct = v.healthy / v.checks;
    let status = 'ok';
    if (pct < 0.95) status = 'major';
    else if (pct < 0.999) status = 'minor';
    return { day, status, checks: v.checks, healthy: v.healthy, pct };
  });
}

function computeStats(days) {
  const totalChecks = days.reduce((a, d) => a + (d.checks || 0), 0);
  const totalHealthy = days.reduce((a, d) => a + (d.healthy || 0), 0);
  const last24 = days.slice(-1).reduce((a, d) => ({ c: a.c + (d.checks || 0), h: a.h + (d.healthy || 0) }), { c: 0, h: 0 });
  const last7 = days.slice(-7).reduce((a, d) => ({ c: a.c + (d.checks || 0), h: a.h + (d.healthy || 0) }), { c: 0, h: 0 });
  const last30 = days.slice(-30).reduce((a, d) => ({ c: a.c + (d.checks || 0), h: a.h + (d.healthy || 0) }), { c: 0, h: 0 });
  return {
    overall_pct: totalChecks ? round2(100 * totalHealthy / totalChecks) : null,
    pct_24h: last24.c ? round2(100 * last24.h / last24.c) : null,
    pct_7d: last7.c ? round2(100 * last7.h / last7.c) : null,
    pct_30d: last30.c ? round2(100 * last30.h / last30.c) : null,
  };
}

function round2(n) { return Math.round(n * 100) / 100; }

function renderHTML({ components, incidents, allOk }) {
  const headerColor = allOk ? '#27ae60' : '#e74c3c';
  const headerBg = allOk ? 'rgba(39,174,96,0.12)' : 'rgba(231,76,60,0.12)';
  const headerIcon = allOk ? '&#10003;' : '&#9888;';
  const headerTitle = allOk ? 'Tudo operacional' : 'Estamos com problemas';
  const headerSub = allOk
    ? 'Todos os servicos da Cultivee estao respondendo normalmente.'
    : 'Detectamos um ou mais componentes com problema. Veja detalhes abaixo.';

  // Favicon SVG inline (sem fetch externo). Cor reflete o status:
  //   verde Cultivee (#27ae60) quando tudo ok, vermelho (#e74c3c) em incidente.
  // O '#' precisa ser URL-encoded como '%23' dentro do data URL.
  const faviconColor = allOk ? '%2327ae60' : '%23e74c3c';
  const favicon =
    `data:image/svg+xml;utf8,` +
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>` +
    `<rect width='100' height='100' rx='22' fill='${faviconColor}'/>` +
    `<text x='50' y='75' font-family='sans-serif' font-size='72' font-weight='900' ` +
    `fill='%23fff' text-anchor='middle'>C</text></svg>`;

  const componentsHTML = components.map(renderComponent).join('');
  const incidentsHTML = incidents.length > 0
    ? incidents.map(renderIncident).join('')
    : '<div class="empty">Nenhum incidente nos ultimos 30 dias.</div>';
  // Nota informativa sobre o gap historico (auto-desativa apos 30d do fix)
  const detectorNoteHTML = renderDetectorFixNote();

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<link rel="icon" type="image/svg+xml" href="${favicon}">
<link rel="apple-touch-icon" href="${favicon}">
<meta name="theme-color" content="${headerColor}">
<title>Status Cultivee${allOk ? '' : ' — Indisponivel'}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#0f1923;color:#e8e8e8;min-height:100vh;padding:32px 16px}
  .wrap{max-width:760px;margin:0 auto}
  .brand{display:flex;align-items:center;gap:12px;margin-bottom:28px}
  .logo{width:40px;height:40px;background:#27ae60;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:1.2rem}
  .brand-name{font-size:1.15rem;font-weight:700}
  .brand-sub{font-size:0.78rem;color:#7d8a98}
  .header-card{background:#1a2530;border:1px solid #2a3946;border-radius:14px;padding:28px;text-align:center;margin-bottom:24px}
  .header-icon{display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;border-radius:50%;background:${headerBg};color:${headerColor};font-size:1.5rem;margin-bottom:14px}
  .header-title{font-size:1.6rem;font-weight:700;color:${headerColor};margin-bottom:6px}
  .header-sub{color:#9ca7b3;font-size:0.92rem;line-height:1.5;max-width:480px;margin:0 auto}
  .section-title{font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:#7d8a98;margin:24px 12px 12px;font-weight:700}
  .comp{background:#1a2530;border:1px solid #2a3946;border-radius:12px;padding:18px;margin-bottom:12px}
  .comp-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}
  .comp-name{font-size:1.02rem;font-weight:700;color:#e8e8e8}
  .comp-desc{font-size:0.78rem;color:#7d8a98;margin-top:2px}
  .comp-status{font-size:0.78rem;font-weight:700;padding:4px 10px;border-radius:14px;white-space:nowrap}
  .status-ok{background:rgba(39,174,96,0.18);color:#27ae60}
  .status-down{background:rgba(231,76,60,0.18);color:#e74c3c}
  .status-unknown{background:rgba(125,138,152,0.18);color:#9ca7b3}
  .bars{display:flex;gap:2px;margin:12px 0 8px;height:34px;align-items:stretch}
  .bar{flex:1;border-radius:2px;cursor:default;min-width:2px}
  .bar-ok{background:#27ae60}
  .bar-minor{background:#e67e22}
  .bar-major{background:#e74c3c}
  .bar-no-data{background:#2a3946}
  .bar:hover{opacity:0.75}
  .bars-axis{display:flex;justify-content:space-between;font-size:0.65rem;color:#5a6878;margin-top:4px}
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid #2a3946}
  .stat{text-align:center}
  .stat-label{font-size:0.66rem;color:#7d8a98;text-transform:uppercase;letter-spacing:0.04em}
  .stat-value{font-size:0.95rem;font-weight:700;color:#e8e8e8;margin-top:2px}
  .pct-good{color:#27ae60}.pct-warn{color:#e67e22}.pct-bad{color:#e74c3c}
  .incidents{margin-top:8px}
  .incident{background:#1a2530;border:1px solid #2a3946;border-radius:10px;padding:14px;margin-bottom:10px;font-size:0.86rem}
  .incident-head{display:flex;justify-content:space-between;gap:10px;margin-bottom:6px}
  .incident-comp{font-weight:700;color:#e8e8e8}
  .incident-status{font-size:0.7rem;padding:2px 8px;border-radius:10px;font-weight:700}
  .inc-resolved{background:rgba(39,174,96,0.18);color:#27ae60}
  .inc-ongoing{background:rgba(231,76,60,0.18);color:#e74c3c;animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.55}}
  .incident-meta{font-size:0.75rem;color:#7d8a98;line-height:1.5}
  .empty{background:#1a2530;border:1px dashed #2a3946;border-radius:10px;padding:18px;text-align:center;color:#7d8a98;font-size:0.85rem}
  .detector-note{background:rgba(52,152,219,0.08);border:1px solid rgba(52,152,219,0.25);border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:0.78rem;color:#9cb3c7;line-height:1.5;display:flex;gap:8px;align-items:flex-start}
  .detector-note-icon{flex-shrink:0;color:#3498db;font-weight:700;font-size:0.95rem;line-height:1.3}
  .detector-note b{color:#bcd0e0}
  .footer{margin-top:32px;font-size:0.72rem;color:#5a6878;text-align:center;line-height:1.6}
  .footer a{color:#7d8a98;text-decoration:none}.footer a:hover{color:#27ae60}
  @media (max-width: 540px){
    body{padding:18px 10px}.stats{grid-template-columns:repeat(2,1fr)}.header-title{font-size:1.3rem}
  }
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

  <div class="header-card">
    <div class="header-icon">${headerIcon}</div>
    <div class="header-title">${headerTitle}</div>
    <div class="header-sub">${headerSub}</div>
  </div>

  <div class="section-title">Componentes</div>
  ${componentsHTML}

  <div class="section-title">Incidentes (ultimos 30 dias)</div>
  ${detectorNoteHTML}
  <div class="incidents">${incidentsHTML}</div>

  <div class="footer">
    Ultima atualizacao: ${escapeHtml(formatBR(new Date().toISOString()))}<br>
    Verificacoes a cada 5 minutos<br>
    <a href="https://cultivee.com.br" target="_blank" rel="noopener">cultivee.com.br</a> &middot;
    <a href="https://app.cultivee.com.br" target="_blank" rel="noopener">app.cultivee.com.br</a>
  </div>
</div>
</body>
</html>`;
}

function renderComponent(c) {
  const cur = c.current;
  let statusLabel = 'Sem dados', statusClass = 'status-unknown';
  if (cur?.healthy === true) { statusLabel = 'Operacional'; statusClass = 'status-ok'; }
  else if (cur?.healthy === false) { statusLabel = 'Indisponivel'; statusClass = 'status-down'; }

  const bars = c.days.map(d => {
    const cls = d.status === 'ok' ? 'bar-ok'
      : d.status === 'minor' ? 'bar-minor'
      : d.status === 'major' ? 'bar-major'
      : 'bar-no-data';
    const tip = d.checks > 0
      ? `${d.day}: ${d.healthy}/${d.checks} ok (${(d.pct * 100).toFixed(2)}%)`
      : `${d.day}: sem dados`;
    return `<div class="bar ${cls}" title="${escapeHtml(tip)}"></div>`;
  }).join('');

  const s = c.stats;
  return `
  <div class="comp">
    <div class="comp-head">
      <div>
        <div class="comp-name">${escapeHtml(c.name)}</div>
        <div class="comp-desc">${escapeHtml(c.description)}</div>
      </div>
      <div class="comp-status ${statusClass}">${statusLabel}</div>
    </div>
    <div class="bars">${bars}</div>
    <div class="bars-axis">
      <span>${HISTORY_DAYS_VISUAL} dias atras</span>
      <span>hoje</span>
    </div>
    <div class="stats">
      <div class="stat"><div class="stat-label">24h</div><div class="stat-value ${pctClass(s.pct_24h)}">${pctTxt(s.pct_24h)}</div></div>
      <div class="stat"><div class="stat-label">7 dias</div><div class="stat-value ${pctClass(s.pct_7d)}">${pctTxt(s.pct_7d)}</div></div>
      <div class="stat"><div class="stat-label">30 dias</div><div class="stat-value ${pctClass(s.pct_30d)}">${pctTxt(s.pct_30d)}</div></div>
      <div class="stat"><div class="stat-label">${HISTORY_DAYS_VISUAL} dias</div><div class="stat-value ${pctClass(s.overall_pct)}">${pctTxt(s.overall_pct)}</div></div>
    </div>
  </div>`;
}

function pctTxt(p) { return p === null ? '—' : `${p}%`; }
function pctClass(p) {
  if (p === null) return '';
  if (p >= 99.9) return 'pct-good';
  if (p >= 95) return 'pct-warn';
  return 'pct-bad';
}

function renderIncident(inc) {
  const ongoing = !inc.end;
  const startBR = formatBR(inc.start);
  const endBR = inc.end ? formatBR(inc.end) : null;
  const dur = inc.end
    ? humanDuration((new Date(inc.end) - new Date(inc.start)) / 1000)
    : 'em curso';
  return `
  <div class="incident">
    <div class="incident-head">
      <div class="incident-comp">${escapeHtml(inc.component_name || inc.component)}</div>
      <div class="incident-status ${ongoing ? 'inc-ongoing' : 'inc-resolved'}">${ongoing ? 'EM CURSO' : 'Resolvido'}</div>
    </div>
    <div class="incident-meta">
      Inicio: ${escapeHtml(startBR)}${endBR ? ` &middot; Fim: ${escapeHtml(endBR)}` : ''} &middot; Duracao: <b>${escapeHtml(dur)}</b>
      ${inc.reason ? `<br>Motivo: ${escapeHtml(inc.reason)}` : ''}
    </div>
  </div>`;
}

// v4.1.51: nota informativa sobre o gap historico de incidentes.
// O detector tinha bug que NUNCA disparava — quedas reais afetavam o uptime
// (calculado via daily: accumulator) mas nao apareciam na lista. A nota
// avisa o visitante. Auto-desativa apos `INCIDENT_DETECTOR_NOTE_TTL_MS` do
// fix — depois disso, qualquer queda anterior ao fix ja saiu da janela de
// 30d e o gap fica implicito.
function renderDetectorFixNote() {
  const fixedAt = new Date(INCIDENT_DETECTOR_FIXED_AT).getTime();
  const expiresAt = fixedAt + INCIDENT_DETECTOR_NOTE_TTL_MS;
  if (Date.now() > expiresAt) return '';
  const fixedAtBR = formatBR(INCIDENT_DETECTOR_FIXED_AT);
  return `
  <div class="detector-note">
    <span class="detector-note-icon">&#9432;</span>
    <span>
      <b>Detector de incidentes corrigido em ${escapeHtml(fixedAtBR)}.</b>
      Quedas anteriores a essa data afetam o calculo de uptime mas podem
      nao constar nesta lista (bug latente fazia o detector nunca abrir
      incidentes). Quedas posteriores sao registradas normalmente.
    </span>
  </div>`;
}

// ====== HELPERS ======

function jsonResp(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj, null, 2), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      // Endpoint publico (sem secrets) — libera qualquer origem.
      // Permite o admin do app.cultivee.com.br consumir direto, alem de outros
      // monitoramentos externos (Uptime Robot, etc.) que possam aparecer.
      'Access-Control-Allow-Origin': '*',
      ...extraHeaders,
    },
  });
}

function ymd(d) {
  // YYYY-MM-DD em UTC (consistente entre execucoes)
  return d.toISOString().slice(0, 10);
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function formatBR(iso) {
  try {
    return new Date(iso).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'medium' });
  } catch { return iso; }
}

function humanDuration(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  const remMin = min % 60;
  if (h < 24) return remMin > 0 ? `${h}h ${remMin}min` : `${h}h`;
  const d = Math.floor(h / 24);
  const remH = h % 24;
  return remH > 0 ? `${d}d ${remH}h` : `${d}d`;
}
