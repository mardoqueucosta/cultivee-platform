// =====================================================================
// Cultivee PWA — Registry Pattern + Lista de Modulos
// Versao definida em config.py (fonte unica), injetada via window.CULTIVEE
// =====================================================================

const C = window.CULTIVEE || {};
const APP_VERSION = C.version || '3.1.0';
const STORAGE_PREFIX = C.storagePrefix || 'cultivee';
const PRODUCT_NAME = C.productName || 'Cultivee';
const DEFAULT_NAME = C.defaultName || 'Dispositivo';

// Migracao de token: prefix antigo → novo (1x)
if (!localStorage.getItem(`${STORAGE_PREFIX}_token`)) {
    for (const old of ['cultivee_ctrl', 'cultivee_cam']) {
        const t = localStorage.getItem(`${old}_token`);
        if (t) {
            localStorage.setItem(`${STORAGE_PREFIX}_token`, t);
            const u = localStorage.getItem(`${old}_user`);
            if (u) localStorage.setItem(`${STORAGE_PREFIX}_user`, u);
            break;
        }
    }
}

let token = localStorage.getItem(`${STORAGE_PREFIX}_token`);
let user = JSON.parse(localStorage.getItem(`${STORAGE_PREFIX}_user`) || "null");
let modules = [];

// v4.1.26: escape de texto inserido em HTML via innerHTML / template literal
// Usar sempre que o valor venha do banco (nome de modulo, fase, user, email) ou
// de resposta de API. Nao preciso escapar chipId (formato hex controlado), nem
// numeros, nem constantes do proprio app.
function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}
// Variante para atributos onclick='...' — escapa tambem backslash e quebra de linha
function escapeAttr(s) {
    if (s === null || s === undefined) return '';
    return escapeHtml(s).replaceAll('\\', '&#92;').replaceAll('\n', ' ').replaceAll('\r', ' ');
}

// API prefix por tipo de modulo
function apiFor(moduleType) {
    return `/api/${moduleType}`;
}

// =====================================================================
// Module Registry — cada capability registra seu renderer
// =====================================================================

const moduleRenderers = {
    hidro: {
        label: 'Controle Hidro',
        renderContent: renderModule_hidro,
        getStatusText: (data) => {
            if (!data) return '';
            const l = data.light ? 'Luz ON' : 'Luz OFF';
            const p = data.pump ? 'Bomba ON' : 'Bomba OFF';
            const v = data.ventilation ? 'Vent ON' : 'Vent OFF';
            const a = data.aeration ? 'Aera ON' : 'Aera OFF';
            return `${l} · ${p} · ${v} · ${a}`;
        }
    },
    'hidro-farm': {
        label: 'Controle Farm',
        renderContent: renderModule_hidrofarm,
        getStatusText: (data) => {
            if (!data) return '';
            const l = data.light ? 'Luz ON' : 'Luz OFF';
            const p = data.pump ? 'Bomba ON' : 'Bomba OFF';
            const v = data.ventilation ? 'Vent ON' : 'Vent OFF';
            const a = data.aeration ? 'Aera ON' : 'Aera OFF';
            // Reservatorio: prioriza estado logico (cheio/enchendo/vazio/erro) sobre valvula
            const stateMap = { full: 'Cheio', filling: 'Baixo', empty: 'Vazio', error: 'ERRO' };
            const r = data.reservoir_state ? `Res: ${stateMap[data.reservoir_state] || '?'}` : '';
            const h = data.bomba_homo ? 'Hom ON' : 'Hom OFF';
            // Ambiente: temperatura/umidade quando disponiveis
            const amb = data.dht_valid && data.temperature !== undefined ? `${data.temperature}°C/${data.humidity}%` : '';
            return [l, p, v, a, r, h, amb].filter(Boolean).join(' · ');
        }
    },
    cam: {
        label: 'Câmera',
        renderContent: renderModule_cam,
        getStatusText: (data) => data && data.camera_ready ? 'Pronta' : 'Offline'
    }
};

// =====================================================================
// Module Prefs (selecao + ordem) — v4.1.10
// Persistido no servidor (sobrevive a limpeza de cache + sync cross-device).
// localStorage continua como cache local pra fallback offline e inicializacao
// rapida antes do fetch assincrono terminar.
// =====================================================================

let _modulePrefsCache = null;       // {selected: [...], order: [...]}
let _modulePrefsSaveTimer = null;   // debouncer pra nao bombardear o servidor

function _readLocalPrefs() {
    try {
        return JSON.parse(localStorage.getItem(`${STORAGE_PREFIX}_module_prefs`) || '{}');
    } catch (e) { return {}; }
}

function _writeLocalPrefs(prefs) {
    try { localStorage.setItem(`${STORAGE_PREFIX}_module_prefs`, JSON.stringify(prefs)); } catch (e) {}
}

// Fetch inicial — chamado uma vez no boot (apos login)
// Faz migracao de localStorage -> servidor se for o primeiro acesso
async function fetchModulePrefs() {
    try {
        const server = await api('/api/user/prefs');
        const serverEmpty = !(server.selected?.length) && !(server.order?.length);
        const local = _readLocalPrefs();
        const localHasData = !!(local.selected?.length) || !!(local.order?.length);
        if (serverEmpty && localHasData) {
            // Primeira sincronizacao: migra localStorage -> servidor
            _modulePrefsCache = local;
            try {
                // body como OBJETO (nao string) — api() helper faz stringify e seta Content-Type
                await api('/api/user/prefs', { method: 'PUT', body: local });
                console.log('[prefs] migrado localStorage -> servidor');
            } catch (e) { /* ok, tenta denovo depois */ }
        } else {
            _modulePrefsCache = server || {};
            _writeLocalPrefs(_modulePrefsCache);
        }
    } catch (e) {
        // Sem rede/erro: cai pro cache local
        _modulePrefsCache = _readLocalPrefs();
        console.warn('[prefs] fallback offline (localStorage)', e.message);
    }
}

function loadModulePrefs() {
    // Se ainda nao buscou do servidor (chamado antes do fetch), devolve localStorage
    if (_modulePrefsCache === null) _modulePrefsCache = _readLocalPrefs();
    return _modulePrefsCache;
}

function saveModulePrefs(prefs) {
    _modulePrefsCache = prefs;
    _writeLocalPrefs(prefs);  // cache local (instantaneo)
    // Debounce: espera 500ms sem novas mudancas antes de enviar ao servidor
    clearTimeout(_modulePrefsSaveTimer);
    _modulePrefsSaveTimer = setTimeout(() => {
        // body como OBJETO — api() helper faz stringify e seta Content-Type: application/json
        api('/api/user/prefs', { method: 'PUT', body: prefs })
            .catch(e => console.warn('[prefs] falha ao salvar no servidor:', e.message));
    }, 500);
}

function getSelectedChips() {
    const prefs = loadModulePrefs();
    return prefs.selected || [];
}

function getOrderedChips() {
    const prefs = loadModulePrefs();
    return prefs.order || [];
}

function toggleModuleSelected(chipId) {
    const prefs = loadModulePrefs();
    const sel = prefs.selected || [];
    const idx = sel.indexOf(chipId);
    if (idx >= 0) sel.splice(idx, 1);
    else sel.push(chipId);
    prefs.selected = sel;
    saveModulePrefs(prefs);
    renderModuleList();
    renderSelectedContent();
}

function moveModuleUp(chipId) {
    const prefs = loadModulePrefs();
    const order = prefs.order || modules.map(m => m.chip_id);
    // Defesa: se o chip nao estava na ordem salva (modulo adicionado depois), inclui no fim antes de mover
    if (order.indexOf(chipId) < 0) order.push(chipId);
    const idx = order.indexOf(chipId);
    if (idx > 0) { [order[idx - 1], order[idx]] = [order[idx], order[idx - 1]]; }
    prefs.order = order;
    saveModulePrefs(prefs);
    renderModuleList();
    renderSelectedContent();
}

function moveModuleDown(chipId) {
    const prefs = loadModulePrefs();
    const order = prefs.order || modules.map(m => m.chip_id);
    // Defesa: se o chip nao estava na ordem salva (modulo adicionado depois), inclui no fim antes de mover
    if (order.indexOf(chipId) < 0) order.push(chipId);
    const idx = order.indexOf(chipId);
    if (idx >= 0 && idx < order.length - 1) { [order[idx], order[idx + 1]] = [order[idx + 1], order[idx]]; }
    prefs.order = order;
    saveModulePrefs(prefs);
    renderModuleList();
    renderSelectedContent();
}

function getModulesInOrder() {
    const order = getOrderedChips();
    const ordered = [];
    // Primeiro os que tem ordem definida
    for (const chipId of order) {
        const m = modules.find(mod => mod.chip_id === chipId);
        if (m) ordered.push(m);
    }
    // Depois os novos (sem ordem definida)
    for (const m of modules) {
        if (!ordered.find(o => o.chip_id === m.chip_id)) ordered.push(m);
    }
    return ordered;
}

// =====================================================================
// API helper
// =====================================================================

async function api(path, options = {}) {
    const headers = { ...options.headers };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (options.body && typeof options.body === "object") {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(options.body);
    }
    const res = await fetch(path, { ...options, headers });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Erro desconhecido");
    return data;
}

// =====================================================================
// Auth
// =====================================================================

// v4.1.12: usa classe interna pra esconder/mostrar painel de auth ativo
function _switchAuthPanel(activeId) {
    ['auth-login', 'auth-register', 'auth-forgot', 'auth-reset'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.toggle('hidden', id !== activeId);
    });
    document.getElementById('auth-error').classList.add('hidden');
    const ok = document.getElementById('auth-success');
    if (ok) ok.classList.add('hidden');
}

function showLogin()    { _switchAuthPanel('auth-login'); }
function showRegister() { _switchAuthPanel('auth-register'); }
function showForgot()   { _switchAuthPanel('auth-forgot'); }
function showReset()    { _switchAuthPanel('auth-reset'); }

function togglePass(inputId, el) {
    const input = document.getElementById(inputId);
    if (input.type === "password") { input.type = "text"; el.textContent = "ocultar"; }
    else { input.type = "password"; el.textContent = "mostrar"; }
}

function showAuthError(msg) {
    const el = document.getElementById("auth-error");
    const ok = document.getElementById("auth-success");
    if (ok) ok.classList.add("hidden");
    el.textContent = msg;
    el.classList.remove("hidden");
}

function showAuthSuccess(msg) {
    const err = document.getElementById("auth-error");
    const ok = document.getElementById("auth-success");
    err.classList.add("hidden");
    if (ok) { ok.textContent = msg; ok.classList.remove("hidden"); }
}

async function doLogin() {
    const body = {
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-pass").value,
    };
    // v4.1.22: se campo TOTP estiver visivel, inclui
    const totpCode = document.getElementById("login-totp")?.value.trim();
    if (totpCode) body.totp_code = totpCode;
    // v4.1.29: se campo email_code estiver visivel, inclui
    const emailCode = document.getElementById("login-email-code")?.value.trim();
    if (emailCode) body.email_code = emailCode;

    try {
        // Faz request manual pra capturar o JSON de erro (com email_otp_required)
        const resp = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            // v4.1.29: 2FA por email — servidor mandou codigo, mostra campo
            if (data.email_otp_required) {
                const row = document.getElementById("login-email-code-row");
                if (row) row.classList.remove("hidden");
                showAuthError(data.email_otp_sent
                    ? "Enviamos um codigo pro seu email. Digite-o aqui pra concluir o login."
                    : (data.error || "Codigo invalido"));
                document.getElementById("login-email-code")?.focus();
                return;
            }
            // v4.1.22: TOTP fallback existente
            if (data.totp_required || (data.error && /2FA|totp/i.test(data.error))) {
                const row = document.getElementById("login-totp-row");
                if (row && row.classList.contains("hidden")) {
                    row.classList.remove("hidden");
                    showAuthError("Digite o codigo do seu app autenticador");
                    document.getElementById("login-totp")?.focus();
                    return;
                }
            }
            showAuthError(data.error || `HTTP ${resp.status}`);
            return;
        }
        token = data.token; user = data.user;
        localStorage.setItem(`${STORAGE_PREFIX}_token`, token);
        localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
        enterApp();
    } catch (e) {
        showAuthError(e.message);
    }
}

// v4.1.29: reenvia codigo de email 2FA (botao "Reenviar")
async function resendEmail2faLogin() {
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-pass").value;
    if (!email || !password) {
        showAuthError("Preencha email e senha pra receber novo codigo");
        return;
    }
    try {
        // Bate no /login sem email_code -> servidor reenvia
        await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        showAuthSuccess("Novo codigo enviado pro seu email.");
        document.getElementById("login-email-code")?.focus();
    } catch (e) {
        showAuthError("Erro ao reenviar: " + e.message);
    }
}

async function doRegister() {
    // v4.1.20: valida aceite de termos no cliente (duplicado no server)
    const acceptedTerms = document.getElementById("reg-accept-terms")?.checked || false;
    if (!acceptedTerms) {
        showAuthError("Voce precisa aceitar os Termos de Uso e a Politica de Privacidade");
        return;
    }
    // v4.1.22: le token do Turnstile (se widget estiver presente)
    let captchaToken = "";
    const turnstileEl = document.querySelector(".cf-turnstile");
    if (turnstileEl) {
        captchaToken = turnstileEl.querySelector('input[name="cf-turnstile-response"]')?.value || "";
        if (!captchaToken) {
            showAuthError("Complete a verificacao anti-bot");
            return;
        }
    }
    try {
        const data = await api("/api/auth/register", {
            method: "POST",
            body: {
                name: document.getElementById("reg-name").value,
                email: document.getElementById("reg-email").value,
                password: document.getElementById("reg-pass").value,
                accepted_terms: true,
                captcha_token: captchaToken,
            }
        });
        token = data.token; user = data.user;
        localStorage.setItem(`${STORAGE_PREFIX}_token`, token);
        localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
        enterApp();
    } catch (e) { showAuthError(e.message); }
}

// v4.1.12: recuperacao de senha
async function doForgot() {
    const email = document.getElementById("forgot-email").value.trim();
    if (!email) { showAuthError("Digite seu email"); return; }
    try {
        const resp = await api("/api/auth/forgot-password", {
            method: "POST",
            body: { email }
        });
        // Servidor sempre retorna sucesso (anti-enumeration) — mensagem e generica
        showAuthSuccess(resp.message || "Se o email estiver cadastrado, voce recebera instrucoes em instantes.");
        document.getElementById("forgot-email").value = "";
    } catch (e) { showAuthError(e.message); }
}

let _resetToken = null;
async function doReset() {
    const pass = document.getElementById("reset-pass").value;
    if (!pass || pass.length < 6) { showAuthError("Senha deve ter pelo menos 6 caracteres"); return; }
    if (!_resetToken) { showAuthError("Token invalido — solicite um novo link"); return; }
    try {
        await api("/api/auth/reset-password", {
            method: "POST",
            body: { token: _resetToken, password: pass }
        });
        // Limpa URL (remove o ?reset=TOKEN) e volta pro login
        try { history.replaceState(null, "", window.location.pathname); } catch (e) {}
        _resetToken = null;
        showLogin();
        showAuthSuccess("Senha alterada com sucesso. Entre com sua nova senha.");
    } catch (e) { showAuthError(e.message); }
}

// Detecta ?reset=TOKEN na URL e mostra tela de reset automaticamente
function _checkResetLink() {
    try {
        const params = new URLSearchParams(window.location.search);
        const t = params.get("reset");
        if (t && t.length > 10) {
            _resetToken = t;
            showReset();
            return true;
        }
    } catch (e) {}
    return false;
}

function doLogout() {
    api("/api/auth/logout", { method: "POST" }).catch(() => {});
    token = null; user = null;
    localStorage.removeItem(`${STORAGE_PREFIX}_token`);
    localStorage.removeItem(`${STORAGE_PREFIX}_user`);
    document.getElementById("auth-screen").classList.remove("hidden");
    document.getElementById("app-screen").classList.add("hidden");
}

// =====================================================================
// App Init
// =====================================================================

async function enterApp() {
    document.getElementById("auth-screen").classList.add("hidden");
    document.getElementById("app-screen").classList.remove("hidden");
    // v4.1.16: dropdown do usuario na navbar (nome + avatar + chevron)
    _renderUserMenu();
    // v4.1.14: banner de impersonation (se estiver ativo)
    renderImpersonationBanner();
    // v4.1.20: banner de email nao verificado
    renderEmailVerificationBanner();
    // v4.1.10: carrega prefs do servidor ANTES do loadModules pra evitar
    // flash visual de "ordem errada" -> "ordem certa"
    await fetchModulePrefs();
    loadModules();

    // v4.1.19: admin entra direto no painel de admin (padrao SaaS — GitLab,
    // WordPress, Linear, etc.). Client "user comum" continua caindo em modulos.
    // Se admin estiver impersonando outro user, ignora (ve como o user veria).
    if (user && user.role === "admin" && !isImpersonating()) {
        showAdminPanel();
    }

    setTimeout(checkPendingCode, 500);
    // Push notifications — pede permissao apos login (nao-bloqueante)
    setTimeout(setupPushNotifications, 2000);
}

// =====================================================================
// Helpers
// =====================================================================

function getRssiBar(rssi) {
    let filled = 0;
    if (rssi >= -50) filled = 4;
    else if (rssi >= -60) filled = 3;
    else if (rssi >= -70) filled = 2;
    else if (rssi >= -80) filled = 1;
    let html = '<span class="rssi-bars">';
    for (let i = 0; i < 4; i++) html += `<span class="rssi-bar ${i < filled ? 'filled' : ''}"></span>`;
    return html + '</span>';
}

function getRssiLabel(rssi) {
    if (rssi >= -50) return "Excelente";
    if (rssi >= -60) return "Bom";
    if (rssi >= -70) return "Regular";
    if (rssi >= -80) return "Fraco";
    return "Muito fraco";
}

function formatUptime(seconds) {
    if (!seconds) return "0min";
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}min`;
    if (m > 0) return `${m}min`;
    return `${seconds}s`;
}

// =====================================================================
// Historico online/offline (v4.1.31)
// =====================================================================
// Compartilhado entre user (modal a partir do card do modulo) e admin
// (modal a partir da tabela de modulos). Endpoint difere apenas em prefixo:
//   /api/modules/<chip>/uptime          (dono)
//   /api/admin/modules/<chip>/uptime    (admin)

let _uptimeCtx = { chipId: null, name: null, isAdmin: false, days: 7 };

function formatHumanDuration(seconds) {
    seconds = Math.max(0, Math.round(seconds || 0));
    if (seconds < 60) return `${seconds}s`;
    const min = Math.floor(seconds / 60);
    if (min < 60) return `${min}min`;
    const h = Math.floor(min / 60);
    const remMin = min % 60;
    if (h < 24) return remMin > 0 ? `${h}h ${remMin}min` : `${h}h`;
    const d = Math.floor(h / 24);
    const remH = h % 24;
    return remH > 0 ? `${d}d ${remH}h` : `${d}d`;
}

function formatRelativeShort(iso) {
    if (!iso) return '—';
    try {
        const dt = new Date(iso);
        const now = new Date();
        const diff = (now - dt) / 1000;
        if (diff < 60) return 'agora ha pouco';
        if (diff < 3600) return `ha ${Math.floor(diff / 60)}min`;
        if (diff < 86400) return `ha ${Math.floor(diff / 3600)}h`;
        const days = Math.floor(diff / 86400);
        if (days < 7) return `ha ${days}d`;
        return dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch (e) { return iso; }
}

function uptimeColor(pct) {
    if (pct === null || pct === undefined) return 'var(--text-dim)';
    if (pct >= 99) return 'var(--primary)';        // verde
    if (pct >= 95) return '#e67e22';                // laranja
    return '#e74c3c';                               // vermelho
}

function renderUptimeBadge(summary) {
    if (!summary) return '';
    const pct = summary.uptime_pct;
    const c = uptimeColor(pct);
    const txt = (pct === null || pct === undefined) ? '— sem dados' : `${pct}%`;
    return `<span style="color:${c};font-weight:700">${txt}</span>`;
}

async function loadUptimeData(chipId, days, isAdmin) {
    const prefix = isAdmin ? '/api/admin/modules' : '/api/modules';
    return await api(`${prefix}/${encodeURIComponent(chipId)}/uptime?days=${days}&events=20`);
}

function showUptimeModal(chipId, name, isAdmin) {
    _uptimeCtx = { chipId, name: name || chipId, isAdmin: !!isAdmin, days: 7 };
    document.getElementById('uptime-modal-subtitle').textContent =
        `Modulo: ${name || chipId} (${chipId})`;
    document.getElementById('uptime-modal').classList.remove('hidden');
    _setUptimePeriodButtons(7);
    _renderUptimeBody();  // Mostra "Carregando..." e dispara fetch
}

function closeUptimeModal() {
    document.getElementById('uptime-modal').classList.add('hidden');
    _uptimeCtx = { chipId: null, name: null, isAdmin: false, days: 7 };
}

function switchUptimePeriod(days) {
    if (!_uptimeCtx.chipId) return;
    _uptimeCtx.days = days;
    _setUptimePeriodButtons(days);
    _renderUptimeBody();
}

function _setUptimePeriodButtons(activeDays) {
    document.querySelectorAll('.uptime-period-btn').forEach(btn => {
        const d = parseInt(btn.dataset.days, 10);
        if (d === activeDays) {
            btn.style.background = 'var(--primary)';
            btn.style.color = '#fff';
            btn.style.border = 'none';
        } else {
            btn.style.background = 'transparent';
            btn.style.color = 'var(--text)';
            btn.style.border = '1px solid var(--border)';
        }
    });
}

async function _renderUptimeBody() {
    const body = document.getElementById('uptime-modal-body');
    body.innerHTML = '<p style="text-align:center;color:var(--text-dim)">Carregando...</p>';
    try {
        const data = await loadUptimeData(_uptimeCtx.chipId, _uptimeCtx.days, _uptimeCtx.isAdmin);
        const s = data.summary || {};
        const events = data.events || [];
        const pctTxt = (s.uptime_pct === null || s.uptime_pct === undefined) ? '—' : `${s.uptime_pct}%`;
        const pctColor = uptimeColor(s.uptime_pct);
        const lastOff = s.last_offline_at ? formatRelativeShort(s.last_offline_at) : '—';
        const longestOff = formatHumanDuration(s.longest_offline_seconds);
        const totalOff = formatHumanDuration(s.offline_seconds);

        // Stats grid
        let html = `
            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:14px">
                <div style="padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
                    <div style="font-size:0.7rem;color:var(--text-dim)">Uptime</div>
                    <div style="font-size:1.4rem;font-weight:700;color:${pctColor}">${escapeHtml(pctTxt)}</div>
                </div>
                <div style="padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
                    <div style="font-size:0.7rem;color:var(--text-dim)">Quedas no periodo</div>
                    <div style="font-size:1.4rem;font-weight:700">${s.offline_count || 0}</div>
                </div>
                <div style="padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
                    <div style="font-size:0.7rem;color:var(--text-dim)">Tempo offline total</div>
                    <div style="font-size:0.95rem;font-weight:600">${escapeHtml(totalOff)}</div>
                </div>
                <div style="padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
                    <div style="font-size:0.7rem;color:var(--text-dim)">Maior queda</div>
                    <div style="font-size:0.95rem;font-weight:600">${escapeHtml(longestOff)}</div>
                </div>
            </div>
            <div style="font-size:0.75rem;color:var(--text-dim);margin-bottom:8px">
                Ultima queda: ${escapeHtml(lastOff)} &middot; estado atual:
                <b style="color:${s.current_status === 'online' ? 'var(--primary)' : '#e74c3c'}">${escapeHtml(s.current_status || 'desconhecido')}</b>
            </div>`;

        // v4.1.33: aviso de exclusao — quando o uptime filtrado diverge do bruto,
        // mostra quantos eventos foram excluidos e o uptime bruto por transparencia.
        const rawCount = s.offline_count_raw || 0;
        const filtCount = s.offline_count || 0;
        const excluded = Math.max(0, rawCount - filtCount);
        if (excluded > 0 && s.uptime_pct_raw != null && s.uptime_pct_raw !== s.uptime_pct) {
            html += `<div style="margin:6px 0 10px;padding:8px 10px;background:rgba(52,152,219,0.08);border:1px solid rgba(52,152,219,0.30);border-radius:8px;font-size:0.72rem;color:var(--text)">
                <b>${excluded} queda${excluded>1?'s':''} excluida${excluded>1?'s':''}</b>
                por incidente da plataforma. Uptime bruto (incluindo): <b>${s.uptime_pct_raw}%</b>.
                <a href="https://status.cultivee.com.br" target="_blank" rel="noopener" style="color:var(--primary);text-decoration:none">Ver incidentes &#8599;</a>
            </div>`;
        }

        // v4.1.32: cruzamento com incidentes do servidor — se a plataforma esteve down
        // no periodo, quedas do modulo nessas janelas podem ser falsos positivos
        // (o ESP32 nao conseguiu fazer register, mas o problema era do servidor).
        html += await _renderServerIncidentsOverlap(_uptimeCtx.days);

        // Lista de eventos
        if (events.length === 0) {
            html += '<p style="color:var(--text-dim);font-size:0.8rem;text-align:center;margin-top:12px">Sem eventos no periodo.</p>';
        } else {
            html += '<h4 style="margin:14px 0 6px;font-size:0.85rem">Eventos recentes</h4>';
            html += '<div style="display:grid;gap:4px;font-size:0.78rem">';
            for (const e of events) {
                const isOffline = e.status === 'offline';
                // v4.1.33: eventos marcados como 'server_down' pelo webhook do CF Worker
                // (quedas causadas pela plataforma, nao pelo modulo) recebem badge cinza
                // e label "SERVIDOR" em vez de "OFFLINE" vermelho.
                const isServerDown = isOffline && e.reason === 'server_down';
                let dotColor, label, labelColor;
                if (isServerDown) {
                    dotColor = '#7d8a98';
                    label = 'SERVIDOR';
                    labelColor = '#7d8a98';
                } else if (isOffline) {
                    dotColor = '#e74c3c';
                    label = 'OFFLINE';
                    labelColor = '';
                } else {
                    dotColor = '#27ae60';
                    label = 'online';
                    labelColor = '';
                }
                const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${dotColor};margin-right:6px"></span>`;
                // v4.1.38: pra eventos em curso (sem duration_seconds), calcula
                // now - occurred_at pra mostrar quanto tempo ja passou. Antes so
                // mostrava "<i>em curso</i>" sem o tempo decorrido.
                let dur;
                if (e.duration_seconds != null) {
                    dur = formatHumanDuration(e.duration_seconds);
                } else {
                    const startedMs = new Date(e.occurred_at).getTime();
                    const elapsedSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
                    dur = `<i>em curso &middot; ${escapeHtml(formatHumanDuration(elapsedSec))}</i>`;
                }
                // Oculta o reason=server_down no texto (ja esta implicito no label cinza)
                const reasonTxt = (e.reason && !isServerDown) ? ` &middot; ${escapeHtml(e.reason)}` : '';
                const rssi = (e.rssi != null && e.status === 'online') ? ` &middot; ${e.rssi} dBm` : '';
                const bgStyle = isServerDown ? 'background:rgba(125,138,152,0.10);' : 'background:var(--bg);';
                const titleAttr = isServerDown ? ' title="Queda causada pela plataforma — nao conta no uptime do modulo"' : '';
                html += `<div style="padding:6px 8px;${bgStyle}border:1px solid var(--border);border-radius:6px;display:flex;justify-content:space-between;gap:8px;align-items:center"${titleAttr}>
                    <div>${dot}<b${labelColor ? ` style="color:${labelColor}"` : ''}>${label}</b>${reasonTxt}${rssi}</div>
                    <div style="color:var(--text-dim);white-space:nowrap">${escapeHtml(formatRelativeShort(e.occurred_at))} &middot; ${dur}</div>
                </div>`;
            }
            html += '</div>';
        }
        body.innerHTML = html;
    } catch (e) {
        body.innerHTML = `<p style="color:#e74c3c;font-size:0.85rem">Erro: ${escapeHtml(e.message)}</p>`;
    }
}

// v4.1.32: aviso de incidentes do servidor que coincidem com o periodo do modal
// de uptime. Resiliente — se o fetch ao Worker falhar, nao quebra o modal.
async function _renderServerIncidentsOverlap(days) {
    let data;
    try {
        data = await _fetchPlatformStatus(false);
    } catch (e) {
        return '';  // silencioso — modal continua funcionando sem o cruzamento
    }
    const cutoffMs = Date.now() - (days * 86400 * 1000);
    const incidents = (data.incidents || []).filter(function (i) {
        const startMs = new Date(i.start).getTime();
        const endMs = i.end ? new Date(i.end).getTime() : Date.now();
        // Sobrepoe se o incidente terminou depois do inicio do periodo
        return endMs >= cutoffMs;
    });
    if (incidents.length === 0) return '';

    const items = incidents.map(function (i) {
        const start = formatRelativeShort(i.start);
        const dur = i.duration_seconds != null ? formatHumanDuration(i.duration_seconds) : 'em curso';
        const reason = i.reason ? ` &middot; ${escapeHtml(i.reason)}` : '';
        const compName = escapeHtml(i.component_name || i.component || 'plataforma');
        return `<li style="margin-bottom:2px">${compName} &middot; ${escapeHtml(start)} &middot; ${escapeHtml(dur)}${reason}</li>`;
    }).join('');

    return `<div style="margin:6px 0 14px;padding:10px 12px;background:rgba(230,126,34,0.10);border:1px solid rgba(230,126,34,0.35);border-radius:8px;font-size:0.78rem;line-height:1.5">
        <div style="font-weight:600;color:#e67e22;margin-bottom:4px">&#9888; ${incidents.length} incidente${incidents.length>1?'s':''} da plataforma neste periodo</div>
        <ul style="margin:4px 0 6px 18px;padding:0;color:var(--text)">${items}</ul>
        <div style="font-size:0.7rem;color:var(--text-dim)">
            Quedas do modulo nessas janelas podem ser falsos positivos — o ESP32 nao conseguiu fazer register porque o servidor estava indisponivel.
            Detalhes em <a href="https://status.cultivee.com.br/" target="_blank" rel="noopener" style="color:var(--primary)">status.cultivee.com.br</a>.
        </div>
    </div>`;
}

// v4.1.8: pequena linha de telemetria WiFi exibida no fim de cada card de modulo
// Mostra estado ("OK" verde / erro vermelho), RSSI, quedas e tempo online
// v4.1.31: aceita chipId opcional pra incluir linha de uptime historico
function renderWifiTelemetry(data, chipId, modName) {
    if (!data) return '';
    const err = data.wifi_last_error;
    const rssi = data.rssi;
    const discCount = data.wifi_disconnect_count;
    const uptime = data.uptime || 0;
    const connectedMs = data.wifi_last_connected_ms;

    // Se nenhum campo novo existir (firmware < v4.1.8), nao renderiza nada
    if (err === undefined && connectedMs === undefined && discCount === undefined) return '';

    // Tempo online: uptime - wifi_last_connected_ms/1000
    let onlineText = '';
    if (typeof connectedMs === 'number' && typeof uptime === 'number' && connectedMs > 0) {
        const onlineSec = Math.max(0, uptime - Math.floor(connectedMs / 1000));
        onlineText = `ha ${formatUptime(onlineSec)}`;
    }

    const errLabel = (err === 'OK' || !err) ? 'OK' : err;
    const errColor = (err === 'OK' || !err) ? 'var(--primary)' : '#e74c3c';
    const dropColor = (discCount && discCount > 0) ? '#e74c3c' : 'var(--text-dim)';
    const rssiText = (typeof rssi === 'number' && rssi !== 0) ? `${rssi} dBm` : '--';

    // v4.1.31: link pra abrir modal de historico (so se chipId foi passado)
    let historyLink = '';
    if (chipId) {
        const safeChip = escapeAttr(chipId);
        const safeName = escapeAttr(modName || chipId);
        const uptimeSpanId = `uptime-inline-${chipId}`;
        historyLink = `<div style="text-align:center;font-size:0.7rem;color:var(--text-dim);margin-top:4px">
            <span id="${uptimeSpanId}">Uptime 7d: <i>carregando...</i></span>
            &middot; <a href="#" onclick="event.preventDefault();showUptimeModal('${safeChip}','${safeName}',false)" style="color:var(--primary);text-decoration:none">Ver historico</a>
        </div>`;
        // Dispara carregamento assincrono (so uma vez por render)
        setTimeout(() => loadInlineUptime(chipId, uptimeSpanId, false), 50);
    }

    return `<div style="text-align:center;font-size:0.7rem;color:var(--text-dim);margin:0.6rem 0 0;padding-top:0.5rem;border-top:1px dashed rgba(255,255,255,0.06);letter-spacing:0.2px">
        &#128246; <span style="color:${errColor};font-weight:600">${errLabel}</span>
        &middot; ${rssiText}
        &middot; <span style="color:${dropColor}">${discCount ?? 0} quedas</span>
        ${onlineText ? `&middot; online ${onlineText}` : ''}
    </div>${historyLink}`;
}

// v4.1.31: cache em memoria pra nao refazer fetch a cada poll (TTL 60s)
const _uptimeInlineCache = {};  // { chipId: { ts, html } }

async function loadInlineUptime(chipId, spanId, isAdmin) {
    const span = document.getElementById(spanId);
    if (!span) return;
    const cached = _uptimeInlineCache[chipId];
    if (cached && (Date.now() - cached.ts) < 60000) {
        span.innerHTML = cached.html;
        return;
    }
    try {
        const data = await loadUptimeData(chipId, 7, isAdmin);
        const s = data.summary || {};
        let html;
        // v4.1.38: se modulo esta offline AGORA, destaca em vermelho com tempo
        // decorrido em vez de mostrar "Uptime 7d: X%". Mais util operacionalmente
        // — admin/dono ve o estado critico imediatamente sem precisar abrir modal.
        if (s.current_status === 'offline' && s.last_offline_at) {
            const startedMs = new Date(s.last_offline_at).getTime();
            const elapsedSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
            const elapsedTxt = formatHumanDuration(elapsedSec);
            html = `<span style="color:#e74c3c;font-weight:700">&#9711; Offline ha ${escapeHtml(elapsedTxt)}</span>`;
        } else {
            const badge = renderUptimeBadge(s);
            const drops = s.offline_count || 0;
            const dropsTxt = drops === 0 ? 'sem quedas' : `${drops} queda${drops > 1 ? 's' : ''}`;
            html = `Uptime 7d: ${badge} &middot; ${dropsTxt}`;
        }
        _uptimeInlineCache[chipId] = { ts: Date.now(), html };
        span.innerHTML = html;
    } catch (e) {
        span.innerHTML = '<span style="color:var(--text-dim)">Uptime indisponivel</span>';
    }
}

function hasCap(mod, cap) {
    return (mod.capabilities || []).includes(cap);
}

// v4.1.37: nome de exibicao consistente entre barra de selecao e card expandido.
// Se o user nomeou ("Estufa Sala"), respeita. Senao, label + sufixo chip_id pra
// desambiguar modulos do mesmo capability (ex: 2 HIDROs aparecem
// "Controle Hidro · DBCC" e "Controle Hidro · 7000" em ambos os lugares).
function getDisplayName(chipId) {
    const m = modules.find(x => x.chip_id === chipId);
    if (!m) return chipId;
    const rawName = m.name && m.name !== DEFAULT_NAME ? m.name : '';
    if (rawName) return rawName;
    const baseLabel = getModuleLabel(m) || m.type || 'Modulo';
    const suffix = chipId ? chipId.slice(-4) : '';
    return suffix ? `${baseLabel} · ${suffix}` : baseLabel;
}

function getModuleLabel(mod) {
    const caps = mod.capabilities || [];
    for (const cap of caps) {
        if (moduleRenderers[cap]) return moduleRenderers[cap].label;
    }
    return 'Modulo';
}

// =====================================================================
// Load Modules
// =====================================================================

// v4.1.18: null (nao "") como sentinela inicial. Bug: modules=[] produzia
// chave "" que COINCIDIA com valor inicial "" -> loadModules retornava antes
// de renderizar, e a UI ficava presa em "Carregando..." pra usuarios com 0
// modulos (ex: admin recem-criado).
let _lastModulesKey = null;

function modulesVisualKey() {
    return modules.map(m => {
        const c = m.ctrl_data || {};
        return `${m.chip_id}:${m.online}:${m.name}:${c.light}:${c.pump}:${c.ventilation}:${c.aeration}:${c.mode}:${c.phase}:${c.camera_ready}`;
    }).join("|");
}

function forceFullRefresh() {
    _lastModulesKey = null;  // forca re-render na proxima chamada
    _lastCtrlKey = "";
    const mc = document.getElementById("module-content");
    if (mc) mc.dataset.structKey = "";  // Forca recriacao dos containers
    loadModules();
}

async function loadModules() {
    try {
        const data = await api("/api/modules");
        modules = data.modules;
        const key = modulesVisualKey();
        // v4.1.18: null e sentinela de "nunca renderizou" — sempre renderiza na primeira chamada
        if (_lastModulesKey !== null && key === _lastModulesKey) return;
        _lastModulesKey = key;

        // Sincroniza prefs com modulos existentes
        const prefs = loadModulePrefs();
        if (!prefs.order || prefs.order.length === 0) {
            prefs.order = modules.map(m => m.chip_id);
        } else {
            // Adiciona modulos pareados DEPOIS da inicializacao no fim da ordem
            // (sem isso, as setinhas ↑↓ no card novo ficam inertes — indexOf retorna -1)
            const existingOrder = new Set(prefs.order);
            for (const m of modules) {
                if (!existingOrder.has(m.chip_id)) prefs.order.push(m.chip_id);
            }
            // Remove da ordem modulos que foram despareados
            const currentIds = new Set(modules.map(m => m.chip_id));
            prefs.order = prefs.order.filter(id => currentIds.has(id));
        }
        // Auto-selecionar novos modulos
        if (!prefs.selected) prefs.selected = modules.map(m => m.chip_id);
        else {
            for (const m of modules) {
                if (!prefs.selected.includes(m.chip_id) && !prefs._seen?.includes(m.chip_id)) {
                    prefs.selected.push(m.chip_id);
                }
            }
        }
        prefs._seen = modules.map(m => m.chip_id);
        saveModulePrefs(prefs);

        // Sync capture state from cam module (config vive em ctrl_data)
        const camMod = modules.find(m => hasCap(m, 'cam'));
        if (camMod) {
            const cd = camMod.ctrl_data || {};
            cam_recording = !!cd.recording;
            cam_captureInterval = cd.capture_interval || 600;
            cam_captureFolder = cd.capture_folder || '';
            cam_resolution = cd.cam_resolution || 'UXGA';
            cam_quality = cd.cam_quality || 10;
        }

        renderModuleList();
        renderSelectedContent();
    } catch (e) {
        if (e.message === "Nao autenticado") doLogout();
    }
}

// =====================================================================
// Render Module List (checkbox + setas)
// =====================================================================

function renderModuleList() {
    const list = document.getElementById("modules-list");
    const ordered = getModulesInOrder();
    const selected = getSelectedChips();

    if (ordered.length === 0) {
        list.innerHTML = `<div class="empty-state">
            <p>Nenhum dispositivo vinculado</p>
            <p style="font-size:0.8rem;color:var(--text-dim);margin-top:0.5rem">Conecte seu ESP32 e vincule abaixo</p>
        </div>
        <div class="add-module-link" onclick="showPairModal()">+ Adicionar Modulo</div>`;
        return;
    }

    let html = ordered.map((m, i) => {
        // v4.1.37: usa helper getDisplayName pra ser consistente com o header
        // do card expandido (renderHidroCardHeader). Logica: nome custom se
        // houver, senao label + sufixo chip_id.
        const name = getDisplayName(m.chip_id);
        const isSelected = selected.includes(m.chip_id);
        const online = m.online;
        const caps = m.capabilities || [];
        let statusText = '';
        for (const cap of caps) {
            if (moduleRenderers[cap]) {
                const s = moduleRenderers[cap].getStatusText(m.ctrl_data);
                if (s) statusText += (statusText ? ' · ' : '') + s;
            }
        }
        if (!online) statusText = 'Offline';

        return `<div class="mod-item ${isSelected ? 'selected' : ''}" oncontextmenu="showModuleMenu('${m.chip_id}',event);return false">
            <label class="mod-check" onclick="event.stopPropagation()">
                <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleModuleSelected('${m.chip_id}')">
            </label>
            <div class="mod-info" onclick="toggleModuleSelected('${m.chip_id}')">
                <span class="status-dot ${online ? 'online' : 'offline'}"></span>
                <span class="mod-name">${escapeHtml(name)}</span>
                <span class="mod-status">${escapeHtml(statusText)}</span>
            </div>
            <div class="mod-arrows">
                <button onclick="moveModuleUp('${m.chip_id}');event.stopPropagation()" ${i === 0 ? 'disabled' : ''}>&#9650;</button>
                <button onclick="moveModuleDown('${m.chip_id}');event.stopPropagation()" ${i === ordered.length - 1 ? 'disabled' : ''}>&#9660;</button>
            </div>
        </div>`;
    }).join('');

    html += `<div class="add-module-link" onclick="showPairModal()">+ Adicionar Modulo</div>`;
    list.innerHTML = html;
}

// Long press / context menu → desvincular
function showModuleMenu(chipId, event) {
    event.preventDefault();
    if (confirm('Desvincular este modulo da sua conta?')) {
        api('/api/modules/unpair', { method: 'POST', body: { chip_id: chipId } })
            .then(() => forceFullRefresh())
            .catch(e => alert('Erro: ' + e.message));
    }
}

// =====================================================================
// Render Selected Content (por capabilities via registry)
// =====================================================================

function renderSelectedContent() {
    const container = document.getElementById("module-content");
    if (!container) return;

    const selected = getSelectedChips();
    const ordered = getModulesInOrder();
    const selectedOrdered = ordered.filter(m => selected.includes(m.chip_id));

    if (selectedOrdered.length === 0) {
        container.innerHTML = '';
        container.dataset.structKey = '';
        return;
    }

    // Chave estrutural: so recria containers se a SELECAO ou ORDEM de modulos mudou.
    // Atualizacoes de estado (reles, temp, modo) sao feitas pelo polling de 3s
    // via loadCtrlStatus() que atualiza o DOM sem destruir os containers.
    const structKey = selectedOrdered.map(m => m.chip_id).join(",");
    if (container.dataset.structKey === structKey) {
        // Mesmos modulos na mesma ordem — containers ja existem, nao destruir.
        // O polling de 3s (setInterval) cuida de atualizar os dados.
        return;
    }
    container.dataset.structKey = structKey;

    let html = '';
    for (const mod of selectedOrdered) {
        const caps = mod.capabilities || [];
        let hasRenderer = false;
        for (const cap of caps) {
            if (moduleRenderers[cap]) {
                hasRenderer = true;
                html += `<div id="mod-content-${mod.chip_id}-${cap}"></div>`;
            }
        }
        if (!hasRenderer) {
            html += `<div class="card"><div class="empty-state"><p>Modulo sem interface configurada</p><p style="font-size:0.8rem;color:var(--text-dim)">Capabilities: ${caps.join(', ') || 'nenhuma'}</p></div></div>`;
        }
    }
    container.innerHTML = html;

    // Chama os renderers para preencher cada container (so na primeira vez)
    for (const mod of selectedOrdered) {
        const caps = mod.capabilities || [];
        for (const cap of caps) {
            if (moduleRenderers[cap]) {
                const el = document.getElementById(`mod-content-${mod.chip_id}-${cap}`);
                if (el) moduleRenderers[cap].renderContent(el, mod);
            }
        }
    }
}

// =====================================================================
// Module Renderer: HIDRO (replica visual da versao offline)
// =====================================================================

let _lastCtrlKey = "";
// Map per-chipId: cada modulo tem seu proprio estado otimista isolado.
// Antes era singleton global — quando renderSelectedContent() renderizava 2 modulos,
// o segundo sobrescrevia o localState do primeiro e o optimistic update se perdia.
let localStates = {};
// Cooldown per-chipId: cada modulo tem seu proprio timer de "toggle recente".
// Antes era global — um click no farm bloqueava o polling do hidro por 35s.
let lastToggleTimes = {};
const TOGGLE_COOLDOWN = 35000;
let pendingCommands = new Set();

// Resolve o container do modulo de controle pelo moduleType.
// v4.1.28: migracao ctrl -> hidro finalizada. Mantido mapping defensivo ainda
// porque PWAs cacheados (SW) podem ter data antigo com type=ctrl ate o user
// recarregar. Apos ~1 semana sem chamadas /api/ctrl no log, remover este ramo.
function getCtrlContainer(chipId, moduleType) {
    const cap = moduleType === 'ctrl' ? 'hidro' : moduleType;
    return document.getElementById(`mod-content-${chipId}-${cap}`);
}

function renderModule_hidro(container, mod) {
    if (!mod.online) {
        container.innerHTML = `<div class="card"><div class="empty-state"><p>Controle offline</p></div></div>`;
        return;
    }
    // Carrega status e renderiza dashboard
    loadCtrlStatus(mod.chip_id, mod.type, container);
}

// Module Renderer: HIDRO-FARM (versao Premium — por ora reusa UI do hidro;
// vai divergir quando entradas/saidas extras forem ativadas).
function renderModule_hidrofarm(container, mod) {
    renderModule_hidro(container, mod);
}

async function loadCtrlStatus(chipId, moduleType, container) {
    const ct = container || getCtrlContainer(chipId, moduleType);
    if (!ct) return;
    try {
        const data = await api(`${apiFor(moduleType)}/${chipId}/status`);
        // Aplica estado otimista desse chip se cooldown ativo (per-chipId, isolado)
        const ls = localStates[chipId];
        if (ls && (Date.now() - (lastToggleTimes[chipId] || 0) < TOGGLE_COOLDOWN)) {
            data.light = ls.light;
            data.pump = ls.pump;
            data.ventilation = ls.ventilation;
            data.aeration = ls.aeration;
            data.valve_entrada = ls.valve_entrada;
            data.bomba_homo = ls.bomba_homo;
            data.valve_auto = ls.valve_auto;
            data.mode = ls.mode;
        }

        // Recalcula cycle_day e phase usando o relogio do NAVEGADOR (mais confiavel
        // que o ESP32, que pode ter NTP desincronizado / RTC com hora errada).
        // start_date e phases vem do banco (fonte de verdade via save-config).
        if (data.start_date && data.phases && data.phases.length > 0) {
            const start = new Date(data.start_date + 'T00:00:00');
            const now = new Date();
            const diffDays = Math.floor((now - start) / 86400000) + 1;
            if (diffDays > 0) data.cycle_day = diffDays;
            let dayCount = 0;
            for (let i = 0; i < data.phases.length; i++) {
                if (data.phases[i].days === 0) {
                    data.phase_index = i;
                    data.phase = data.phases[i].name;
                    break;
                }
                dayCount += data.phases[i].days;
                if (data.cycle_day <= dayCount) {
                    data.phase_index = i;
                    data.phase = data.phases[i].name;
                    break;
                }
                if (i === data.phases.length - 1) {
                    data.phase_index = i;
                    data.phase = data.phases[i].name;
                }
            }
        }

        const key = `${data.light}:${data.pump}:${data.ventilation}:${data.aeration}:${data.valve_entrada}:${data.bomba_homo}:${data.valve_auto}:${data.level_high}:${data.level_low}:${data.reservoir_state}:${data.low_since}:${data.temperature}:${data.humidity}:${data.dht_valid}:${data.mode}:${data.phase}:${data.phase_index}:${data.cycle_day}:${data.start_date}`;
        if (key === _lastCtrlKey && !container) return;
        _lastCtrlKey = key;
        renderDashboard(ct, chipId, moduleType, data);
    } catch (e) {
        ct.innerHTML = '<div class="card"><div class="empty-state"><p>Erro ao carregar status</p></div></div>';
    }
}

function renderDashboard(container, chipId, moduleType, data) {
    // Salva estado por chipId — cada modulo tem seu proprio localState isolado.
    localStates[chipId] = { ...data };

    // v4.1.37: nome de exibicao via helper compartilhado — consistente com a
    // barra de selecao. Inclui sufixo chip_id quando user nao nomeou
    // (ex: "Controle Hidro · DBCC" em vez de so "Controle Hidro").
    const _moduleLabel = getDisplayName(chipId);

    const cycleDay = data.cycle_day || 0;
    const phase = data.phase || "---";
    const phaseIndex = data.phase_index || 0;
    const lightOn = data.light || false;
    const pumpOn = data.pump || false;
    const ventOn = data.ventilation || false;
    const aerOn = data.aeration || false;
    const modeAuto = data.mode === "auto";
    const startDateRaw = data.start_date || "---";
    let startDate = startDateRaw;
    if (startDateRaw && startDateRaw.includes("-")) {
        const [y, m, d] = startDateRaw.split("-");
        startDate = `${d}/${m}/${y}`;
    }

    const ntpOk = data.ntp_synced || false;
    const rtcOk = data.rtc_available || false;
    const timeSource = ntpOk ? 'NTP' : (rtcOk ? 'RTC' : '--');
    const timeStr = data.time || '--:--';

    // Fases
    let phasesHtml = '';
    if (data.phases && data.phases.length) {
        let cumDays = 0;
        const phaseStartDays = [];
        data.phases.forEach(p => { phaseStartDays.push(cumDays); cumDays += (p.days > 0 ? p.days : 0); });

        phasesHtml = data.phases.map((p, i) => {
            const isActive = i === phaseIndex;
            const isPast = i < phaseIndex;
            const lOn = `${String(p.lightOnHour).padStart(2,'0')}:${String(p.lightOnMin).padStart(2,'0')}`;
            const lOff = `${String(p.lightOffHour).padStart(2,'0')}:${String(p.lightOffMin).padStart(2,'0')}`;
            let diasInfo = '', progressBar = '';
            if (p.days > 0) {
                if (isActive) {
                    const daysInPhase = cycleDay - phaseStartDays[i];
                    const clamped = Math.min(daysInPhase, p.days);
                    const pct = Math.round((clamped / p.days) * 100);
                    diasInfo = `<span class="phase-item-days">${clamped} de ${p.days} dias</span>`;
                    progressBar = `<div class="phase-mini-progress"><div class="phase-mini-bar" style="width:${pct}%"></div></div>`;
                } else if (isPast) { diasInfo = `<span class="phase-item-days phase-done">${p.days}/${p.days} dias &#10003;</span>`; }
                else { diasInfo = `<span class="phase-item-days">${p.days} dias</span>`; }
            } else { diasInfo = `<span class="phase-item-days">&#8734;</span>`; }
            return `<div class="phase-item ${isActive ? 'active' : ''} ${isPast ? 'past' : ''}">
                <div class="phase-item-header"><span class="phase-item-name">${escapeHtml(p.name)} ${isActive ? '<span class="phase-badge">ATIVA</span>' : ''}</span>${diasInfo}</div>
                ${progressBar}
                <div class="phase-item-details">&#128161; ${lOn} - ${lOff}<br>&#128167; Dia: ${p.pumpOnDay}/${p.pumpOffDay}min | Noite: ${p.pumpOnNight}/${p.pumpOffNight}min<br>&#127744; ${String(p.ventOnHour||0).padStart(2,'0')}:${String(p.ventOnMin||0).padStart(2,'0')} - ${String(p.ventOffHour||0).padStart(2,'0')}:${String(p.ventOffMin||0).padStart(2,'0')}<br>&#128168; Dia: ${p.aerOnDay||15}/${p.aerOffDay||15}min | Noite: ${p.aerOnNight||15}/${p.aerOffNight||45}min</div>
            </div>`;
        }).join("");
    }

    // Pendings com keys compostas chipId:device para evitar vazamento entre modulos
    const lightPending = pendingCommands.has(`${chipId}:light`);
    const pumpPending = pendingCommands.has(`${chipId}:pump`);
    const ventPending = pendingCommands.has(`${chipId}:ventilation`);
    const aerPending = pendingCommands.has(`${chipId}:aeration`);
    const modePending = pendingCommands.has(`${chipId}:mode`);

    // Hidro-Farm: reles extras, reservatorio e ambiente (DHT11)
    // Detectados pelos proprios campos no data — compatibilidade retroativa com o hidro legado.
    const hasFarmControls = data.bomba_homo !== undefined;
    const hasReservoir = data.level_high !== undefined || data.level_low !== undefined;
    const hasAmbient = data.temperature !== undefined || data.humidity !== undefined || data.dht_valid !== undefined;
    const valveOn = data.valve_entrada || false;
    const homoOn = data.bomba_homo || false;
    const valveAutoOn = data.valve_auto !== false; // default true (retrocompat)
    const levelHigh = data.level_high || false;
    const levelLow = data.level_low || false;
    const reservoirState = data.reservoir_state || 'unknown';
    const dhtValid = data.dht_valid === true;
    const temperature = data.temperature;
    const humidity = data.humidity;
    const homoPending = pendingCommands.has(`${chipId}:bomba_homo`);
    const valvePending = pendingCommands.has(`${chipId}:valve_entrada`);
    const valveAutoPending = pendingCommands.has(`${chipId}:valve_auto`);

    let controlsHtml = '';
    if (!modeAuto) {
        controlsHtml = `<div class="controls-row">
            <button class="ctrl-btn ${lightOn ? 'on' : 'off'} ${lightPending ? 'pending' : ''}" onclick="toggleRelay('${chipId}','${moduleType}','light')" ${lightPending ? 'disabled' : ''}>
                ${lightPending ? '<span class="btn-spinner"></span>' : `<span class="ctrl-btn-icon">${lightOn ? '&#128161;' : '&#9899;'}</span>`}
                <span>${lightPending ? 'Enviando...' : `LUZ ${lightOn ? 'ON' : 'OFF'}`}</span>
            </button>
            <button class="ctrl-btn ${pumpOn ? 'on pump-on' : 'off'} ${pumpPending ? 'pending' : ''}" onclick="toggleRelay('${chipId}','${moduleType}','pump')" ${pumpPending ? 'disabled' : ''}>
                ${pumpPending ? '<span class="btn-spinner"></span>' : `<span class="ctrl-btn-icon">${pumpOn ? '&#128167;' : '&#9899;'}</span>`}
                <span>${pumpPending ? 'Enviando...' : `BOMBA ${pumpOn ? 'ON' : 'OFF'}`}</span>
            </button>
        </div>
        <div class="controls-row">
            <button class="ctrl-btn ${ventOn ? 'on' : 'off'} ${ventPending ? 'pending' : ''}" style="${ventOn ? 'border-color:#2ecc71;background:rgba(46,204,113,0.1)' : ''}" onclick="toggleRelay('${chipId}','${moduleType}','ventilation')" ${ventPending ? 'disabled' : ''}>
                ${ventPending ? '<span class="btn-spinner"></span>' : `<span class="ctrl-btn-icon">${ventOn ? '&#127744;' : '&#9899;'}</span>`}
                <span>${ventPending ? 'Enviando...' : `VENT ${ventOn ? 'ON' : 'OFF'}`}</span>
            </button>
            <button class="ctrl-btn ${aerOn ? 'on' : 'off'} ${aerPending ? 'pending' : ''}" style="${aerOn ? 'border-color:#00bcd4;background:rgba(0,188,212,0.1)' : ''}" onclick="toggleRelay('${chipId}','${moduleType}','aeration')" ${aerPending ? 'disabled' : ''}>
                ${aerPending ? '<span class="btn-spinner"></span>' : `<span class="ctrl-btn-icon">${aerOn ? '&#128168;' : '&#9899;'}</span>`}
                <span>${aerPending ? 'Enviando...' : `AERA ${aerOn ? 'ON' : 'OFF'}`}</span>
            </button>
        </div>`;
    }

    // Card "Controles Extras" — HOMOG sempre visivel, independente do modeAuto global
    // (separado do bloco manual das fases porque nao faz parte da automacao por fase)
    let extrasHtml = '';
    if (hasFarmControls) {
        extrasHtml = `<div class="card">
            <div class="card-header"><div class="card-title"><h2>Controles Extras</h2></div></div>
            <div class="controls-row">
                <button class="ctrl-btn ${homoOn ? 'on' : 'off'} ${homoPending ? 'pending' : ''}" style="flex: 1 1 100%; ${homoOn ? 'border-color:#9b59b6;background:rgba(155,89,182,0.15);color:#9b59b6' : ''}" onclick="toggleRelay('${chipId}','${moduleType}','bomba_homo')" ${homoPending ? 'disabled' : ''}>
                    ${homoPending ? '<span class="btn-spinner"></span>' : `<span class="ctrl-btn-icon">${homoOn ? '&#128260;' : '&#9899;'}</span>`}
                    <span>${homoPending ? 'Enviando...' : `HOMOG ${homoOn ? 'ON' : 'OFF'}`}</span>
                </button>
            </div>
        </div>`;
    }

    // Card "Ambiente" — DHT11 (temperatura + umidade)
    let ambientHtml = '';
    if (hasAmbient) {
        const tempDisplay = dhtValid && temperature !== undefined ? `${temperature} &deg;C` : '--';
        const humidDisplay = dhtValid && humidity !== undefined ? `${humidity} %` : '--';
        const statusMsg = dhtValid ? 'atualizado agora' : 'sensor offline';
        const statusColor = dhtValid ? 'var(--text-muted)' : '#e74c3c';

        ambientHtml = `<div class="card ambient-card">
            <div class="card-header"><div class="card-title"><h2>&#127777; Ambiente</h2></div></div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="label">&#127777; Temperatura</div>
                    <div class="value" style="color:#e67e22">${tempDisplay}</div>
                </div>
                <div class="stat-card">
                    <div class="label">&#128167; Umidade</div>
                    <div class="value" style="color:#4ba3ff">${humidDisplay}</div>
                </div>
            </div>
            <div class="ambient-status" style="color:${statusColor}">${statusMsg}</div>
        </div>`;
    }

    // Card "Reservatorio" — sempre visivel quando o modulo tem boias (hidro-farm)
    // Tem seu proprio modo auto/manual independente do modeAuto global
    let reservoirHtml = '';
    if (hasReservoir) {
        let stateLabel, stateColor, waterH, waterT;
        if (reservoirState === 'full')        { stateLabel = 'CHEIO';    stateColor = '#27ae60'; waterH = '92%'; waterT = '8%';  }
        else if (reservoirState === 'filling'){ stateLabel = 'BAIXO';    stateColor = '#e67e22'; waterH = '30%'; waterT = '70%'; }
        else if (reservoirState === 'empty')  { stateLabel = 'VAZIO';    stateColor = '#e74c3c'; waterH = '8%';  waterT = '92%'; }
        else                                  { stateLabel = 'ERRO';     stateColor = '#e74c3c'; waterH = '50%'; waterT = '50%'; }

        // Reservatorio 100% automatico pela UI — sem botao de modo ou controle manual.
        // A logica do valveAuto continua no firmware (default true) e ainda pode ser
        // alterada via comando serial (VA0/VA1) ou comando remoto (device=valve_auto).
        // Threshold de alerta (configuravel pelo usuario, default 10 min)
        const alertThreshold = data.alert_threshold_min || 10;

        // Contador de tempo — inicia quando boia baixa NAO detecta agua (level_low = false)
        let lowTimerHtml = '';
        const lowSince = data.low_since;
        if (!levelLow && lowSince) {
            const sinceDate = new Date(lowSince);
            const diffMs = Math.max(0, Date.now() - sinceDate.getTime());
            const diffMin = Math.floor(diffMs / 60000);
            const diffSec = Math.floor((diffMs % 60000) / 1000);
            const timeStr = diffMin > 0 ? `${diffMin}min ${diffSec}s` : `${diffSec}s`;
            const isAlert = diffMin >= alertThreshold;
            lowTimerHtml = `<div class="reservoir-timer ${isAlert ? 'alert' : ''}">${isAlert ? '&#9888;' : '&#9201;'} Nivel baixo ha ${timeStr}</div>`;
        }

        // Detecta se push esta ativo pra esse usuario
        const pushEnabled = Notification.permission === 'granted';
        const pushDenied = Notification.permission === 'denied';
        const pushAvailable = 'Notification' in window && 'PushManager' in window;

        reservoirHtml = `<div class="card reservoir-card">
            <div class="reservoir-header">
                <h2>&#128167; Reservatorio</h2>
            </div>
            <div class="reservoir-body">
                <div class="reservoir-tank">
                    <div class="tank-outline">
                        <div class="tank-water ${reservoirState}" style="height:${waterH};top:${waterT}"></div>
                        <div class="tank-mark-high"></div>
                        <div class="tank-mark-low"></div>
                    </div>
                </div>
                <div class="reservoir-info">
                    <div class="level-indicator ${levelHigh ? 'active' : ''}">
                        <span class="dot"></span><span>Alto: ${levelHigh ? 'ATIVO' : 'inativo'}</span>
                    </div>
                    <div class="level-indicator ${levelLow ? 'active' : ''}">
                        <span class="dot"></span><span>Baixo: ${levelLow ? 'ATIVO' : 'inativo'}</span>
                    </div>
                    <div class="reservoir-state"><b>Estado:</b> <span style="color:${stateColor}">${stateLabel}</span></div>
                    <div class="reservoir-valve"><b>Valvula:</b> <span style="color:${valveOn ? '#4ba3ff' : '#888'}">${valveOn ? 'ABERTA' : 'FECHADA'}</span></div>
                </div>
            </div>
            ${lowTimerHtml}
            ${pushAvailable ? `
            <div class="reservoir-notify">
                <label class="notify-toggle">
                    <span class="notify-icon">${pushEnabled ? '&#128276;' : '&#128277;'}</span>
                    <span class="notify-label">Alertas de nivel</span>
                    <span class="notify-switch ${pushEnabled ? 'on' : ''} ${pushDenied ? 'blocked' : ''}" onclick="togglePushNotifications(this)">
                        <span class="notify-slider"></span>
                    </span>
                </label>
                ${pushDenied ? '<div class="notify-hint">Bloqueado pelo navegador. Acesse configuracoes do site para permitir.</div>' : ''}
                ${!pushEnabled && !pushDenied ? '<div class="notify-hint">Receba alertas quando o nivel ficar baixo.</div>' : ''}
            </div>` : ''}
            <div class="reservoir-threshold">
                <label>
                    <span>&#9201; Alerta apos</span>
                    <input type="number" min="1" max="120" value="${alertThreshold}"
                        onchange="saveAlertThreshold('${chipId}','${moduleType}',this.value)">
                    <span>min</span>
                </label>
            </div>
        </div>`;
    }

    const now = new Date();
    const dateStr = `${String(now.getDate()).padStart(2,'0')}/${String(now.getMonth()+1).padStart(2,'0')}/${now.getFullYear()}`;

    container.innerHTML = `
        <div class="card">
            <div class="module-inline-title"><span class="mch-dot online"></span><b>${_moduleLabel}</b></div>
            <div class="stats-grid">
                <div class="stat-card"><div class="label">Ciclo</div><div class="value">Dia ${cycleDay}</div></div>
                <div class="stat-card"><div class="label">Fase</div><div class="value small">${phase}</div></div>
                <div class="stat-card"><div class="label">Inicio</div><div class="value small">${startDate}</div></div>
                <div class="stat-card"><div class="label">Hoje</div><div class="value small">${dateStr}</div></div>
            </div>
            <div style="text-align:center;font-size:0.75rem;color:var(--text-dim);margin:0.25rem 0">
                ${timeStr} <span style="color:${ntpOk ? 'var(--primary)' : (rtcOk ? '#e67e22' : '#e74c3c')}">${timeSource}</span>${rtcOk ? ' <span style="color:#888">| RTC &#10003;</span>' : ''}
            </div>
            <div class="status-indicators">
                <div class="status-indicator ${lightOn ? 'status-on' : 'status-off'}"><span class="status-indicator-dot"></span><span>Luz ${lightOn ? 'Ligada' : 'Desligada'}</span></div>
                <div class="status-indicator ${pumpOn ? 'status-on pump' : 'status-off'}"><span class="status-indicator-dot"></span><span>Bomba ${pumpOn ? 'Ligada' : 'Desligada'}</span></div>
                <div class="status-indicator ${ventOn ? 'status-on' : 'status-off'}" style="${ventOn ? 'border-color:#2ecc71;color:#2ecc71' : ''}"><span class="status-indicator-dot" style="${ventOn ? 'background:#2ecc71' : ''}"></span><span>Vent ${ventOn ? 'Ligada' : 'Desligada'}</span></div>
                <div class="status-indicator ${aerOn ? 'status-on' : 'status-off'}" style="${aerOn ? 'border-color:#00bcd4;color:#00bcd4' : ''}"><span class="status-indicator-dot" style="${aerOn ? 'background:#00bcd4' : ''}"></span><span>Aera ${aerOn ? 'Ligada' : 'Desligada'}</span></div>
            </div>
            <button class="ctrl-btn-mode ${modeAuto ? 'auto' : 'manual'} ${modePending ? 'pending' : ''}" onclick="toggleRelay('${chipId}','${moduleType}','mode')" ${modePending ? 'disabled' : ''}>
                ${modePending ? '<span class="btn-spinner"></span> Alterando...' : (modeAuto ? '&#9881; Modo Automatico' : '&#9995; Modo Manual')}
            </button>
            ${controlsHtml}
        </div>
        ${phasesHtml ? `<div class="card">
            <div class="card-header">
                <div class="card-title"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg><h2>Fases</h2></div>
                <button class="btn-config" onclick="showConfigModal('${chipId}','${moduleType}')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> Config</button>
            </div>
            ${phasesHtml}
        </div>` : ''}
        ${ambientHtml}
        ${reservoirHtml}
        ${extrasHtml}
        ${renderNotificationCard(chipId, data)}
        ${renderWifiTelemetry(data, chipId, data && data.name)}`;
}

async function toggleRelay(chipId, moduleType, device) {
    const ls = localStates[chipId];
    if (ls) {
        if (device === "light") ls.light = !ls.light;
        else if (device === "pump") ls.pump = !ls.pump;
        else if (device === "ventilation") ls.ventilation = !ls.ventilation;
        else if (device === "aeration") ls.aeration = !ls.aeration;
        else if (device === "valve_entrada") ls.valve_entrada = !ls.valve_entrada;
        else if (device === "bomba_homo") ls.bomba_homo = !ls.bomba_homo;
        else if (device === "valve_auto") ls.valve_auto = !(ls.valve_auto !== false);
        else if (device === "mode") ls.mode = ls.mode === "auto" ? "manual" : "auto";
        lastToggleTimes[chipId] = Date.now();
        pendingCommands.add(`${chipId}:${device}`);
        const ct = getCtrlContainer(chipId, moduleType);
        if (ct) renderDashboard(ct, chipId, moduleType, ls);
    }
    try {
        await api(`${apiFor(moduleType)}/${chipId}/relay?device=${device}&action=toggle`);
    } catch (e) { console.error("Erro relay:", e); }

    let confirmed = false;
    for (let i = 0; i < 10; i++) {
        await new Promise(r => setTimeout(r, 1500));
        try {
            const data = await api(`${apiFor(moduleType)}/${chipId}/status`);
            if (device === "light" && data.light === ls.light) { confirmed = true; break; }
            if (device === "pump" && data.pump === ls.pump) { confirmed = true; break; }
            if (device === "ventilation" && data.ventilation === ls.ventilation) { confirmed = true; break; }
            if (device === "aeration" && data.aeration === ls.aeration) { confirmed = true; break; }
            if (device === "valve_entrada" && data.valve_entrada === ls.valve_entrada) { confirmed = true; break; }
            if (device === "bomba_homo" && data.bomba_homo === ls.bomba_homo) { confirmed = true; break; }
            if (device === "valve_auto" && data.valve_auto === ls.valve_auto) { confirmed = true; break; }
            if (device === "mode" && data.mode === ls.mode) {
                // Ao trocar modo, sincroniza estados reais dos reles
                ls.light = data.light;
                ls.pump = data.pump;
                ls.ventilation = data.ventilation;
                ls.aeration = data.aeration;
                confirmed = true; break;
            }
        } catch (e) { break; }
    }
    pendingCommands.delete(`${chipId}:${device}`);
    _lastCtrlKey = "";
    const ct = getCtrlContainer(chipId, moduleType);
    if (confirmed && ct && localStates[chipId]) {
        renderDashboard(ct, chipId, moduleType, localStates[chipId]);
    } else {
        loadCtrlStatus(chipId, moduleType);
    }
}

// =====================================================================
// Config Modal (hidro)
// =====================================================================

let configChipId = null;
let configModuleType = null;

async function showConfigModal(chipId, moduleType) {
    configChipId = chipId;
    configModuleType = moduleType;
    try {
        let data;
        try { data = await api(`${apiFor(moduleType)}/${chipId}/phases?live=1`); }
        catch (e) { data = await api(`${apiFor(moduleType)}/${chipId}/status`); }
        renderConfigModal(data);
        document.getElementById("config-modal").classList.remove("hidden");
    } catch (e) { alert("Erro ao carregar configuracao: " + e.message); }
}

function closeConfigModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById("config-modal").classList.add("hidden");
}

function renderConfigModal(data) {
    const container = document.getElementById("config-content");
    const today = new Date().toISOString().split('T')[0];
    const startDate = data.start_date || today;
    const phases = data.phases || [];

    let phasesHtml = phases.map((p, i) => {
        const lOn = `${String(p.lightOnHour||6).padStart(2,'0')}:${String(p.lightOnMin||0).padStart(2,'0')}`;
        const lOff = `${String(p.lightOffHour||18).padStart(2,'0')}:${String(p.lightOffMin||0).padStart(2,'0')}`;
        const vOn = `${String(p.ventOnHour||0).padStart(2,'0')}:${String(p.ventOnMin||0).padStart(2,'0')}`;
        const vOff = `${String(p.ventOffHour||0).padStart(2,'0')}:${String(p.ventOffMin||0).padStart(2,'0')}`;
        return `<div class="config-phase">
            <div class="config-phase-header"><span class="config-phase-title">Fase ${i+1}</span>${phases.length > 1 ? `<button class="config-remove" onclick="removePhase(${i})">&#10005;</button>` : ''}</div>
            <div class="config-grid">
                <div class="config-field"><label>Nome</label><input type="text" id="cfg-n${i}" value="${escapeHtml(p.name||`Fase ${i+1}`)}"></div>
                <div class="config-field"><label>Dias</label><input type="number" id="cfg-d${i}" value="${p.days!=null?p.days:7}" min="0"></div>
            </div>
            <div class="config-section-label sec-light">&#128161; Iluminacao</div>
            <div class="config-grid">
                <div class="config-field"><label>Liga</label><input type="time" id="cfg-lon${i}" value="${lOn}"></div>
                <div class="config-field"><label>Desliga</label><input type="time" id="cfg-loff${i}" value="${lOff}"></div>
            </div>
            <div class="config-section-label sec-pump">&#128167; Irrigacao Dia</div>
            <div class="config-grid">
                <div class="config-field"><label>ON (min)</label><input type="number" id="cfg-pod${i}" value="${p.pumpOnDay||15}" min="1"></div>
                <div class="config-field"><label>OFF (min)</label><input type="number" id="cfg-pfd${i}" value="${p.pumpOffDay||15}" min="1"></div>
            </div>
            <div class="config-section-label sec-pump">&#127769; Irrigacao Noite</div>
            <div class="config-grid">
                <div class="config-field"><label>ON (min)</label><input type="number" id="cfg-pon${i}" value="${p.pumpOnNight||15}" min="1"></div>
                <div class="config-field"><label>OFF (min)</label><input type="number" id="cfg-pfn${i}" value="${p.pumpOffNight||45}" min="1"></div>
            </div>
            <div class="config-section-label sec-vent">&#127744; Ventilacao</div>
            <div class="config-grid">
                <div class="config-field"><label>Liga</label><input type="time" id="cfg-von${i}" value="${vOn}"></div>
                <div class="config-field"><label>Desliga</label><input type="time" id="cfg-voff${i}" value="${vOff}"></div>
            </div>
            <div class="config-section-label sec-aer">&#128168; Aeracao Dia</div>
            <div class="config-grid">
                <div class="config-field"><label>ON (min)</label><input type="number" id="cfg-aod${i}" value="${p.aerOnDay||15}" min="1"></div>
                <div class="config-field"><label>OFF (min)</label><input type="number" id="cfg-afd${i}" value="${p.aerOffDay||15}" min="1"></div>
            </div>
            <div class="config-section-label sec-aer">&#127769; Aeracao Noite</div>
            <div class="config-grid">
                <div class="config-field"><label>ON (min)</label><input type="number" id="cfg-aon${i}" value="${p.aerOnNight||15}" min="1"></div>
                <div class="config-field"><label>OFF (min)</label><input type="number" id="cfg-afn${i}" value="${p.aerOffNight||45}" min="1"></div>
            </div>
        </div>`;
    }).join("");

    container.innerHTML = `
        <div class="config-field" style="margin-bottom:1rem"><label>Data de Inicio</label><input type="date" id="cfg-start-date" value="${startDate}"></div>
        <div id="config-phases">${phasesHtml}</div>
        <div class="config-actions"><button class="btn-primary" onclick="saveConfig()">Salvar</button></div>
        <div class="config-actions" style="margin-top:0.5rem">
            <button class="btn-secondary" onclick="addPhase()">+ Adicionar Fase</button>
            <button class="btn-danger-outline" onclick="resetPhases()">Restaurar Padrao</button>
        </div>`;
}

async function saveConfig() {
    const phases = document.querySelectorAll('.config-phase');
    const data = { start_date: document.getElementById('cfg-start-date').value, num_phases: phases.length };
    phases.forEach((_, i) => {
        data[`n${i}`] = document.getElementById(`cfg-n${i}`).value;
        data[`d${i}`] = document.getElementById(`cfg-d${i}`).value;
        data[`lon${i}`] = document.getElementById(`cfg-lon${i}`).value;
        data[`loff${i}`] = document.getElementById(`cfg-loff${i}`).value;
        data[`pod${i}`] = document.getElementById(`cfg-pod${i}`).value;
        data[`pfd${i}`] = document.getElementById(`cfg-pfd${i}`).value;
        data[`pon${i}`] = document.getElementById(`cfg-pon${i}`).value;
        data[`pfn${i}`] = document.getElementById(`cfg-pfn${i}`).value;
        data[`von${i}`] = document.getElementById(`cfg-von${i}`).value;
        data[`voff${i}`] = document.getElementById(`cfg-voff${i}`).value;
        data[`aod${i}`] = document.getElementById(`cfg-aod${i}`).value;
        data[`afd${i}`] = document.getElementById(`cfg-afd${i}`).value;
        data[`aon${i}`] = document.getElementById(`cfg-aon${i}`).value;
        data[`afn${i}`] = document.getElementById(`cfg-afn${i}`).value;
    });
    try {
        await api(`${apiFor(configModuleType)}/${configChipId}/save-config`, { method: "POST", body: data });
        closeConfigModal();
        lastToggleTimes[configChipId] = Date.now();
        setTimeout(forceFullRefresh, 500);
    } catch (e) { alert("Erro ao salvar: " + e.message); }
}

async function addPhase() {
    try { await api(`${apiFor(configModuleType)}/${configChipId}/add-phase`); showConfigModal(configChipId, configModuleType); }
    catch (e) { alert("Erro: " + e.message); }
}

async function removePhase(idx) {
    if (!confirm('Remover esta fase?')) return;
    try { await api(`${apiFor(configModuleType)}/${configChipId}/remove-phase?idx=${idx}`); showConfigModal(configChipId, configModuleType); }
    catch (e) { alert("Erro: " + e.message); }
}

async function resetPhases() {
    if (!confirm('Restaurar fases padrao?')) return;
    try { await api(`${apiFor(configModuleType)}/${configChipId}/reset-phases`); showConfigModal(configChipId, configModuleType); }
    catch (e) { alert("Erro: " + e.message); }
}

// =====================================================================
// Module Renderer: CAMERA (replica visual da versao offline)
// =====================================================================

let cam_pending = false;
let cam_imageUrl = null;
let cam_liveOn = false;
let cam_liveChipId = null;
let cam_liveType = null;
let cam_liveLastTs = 0;
let cam_captureOpen = true;
let cam_recordOpen = false;
let cam_recording = false;
let cam_captureInterval = 600;
let cam_captureFolder = '';
let cam_resolution = 'SVGA';
let cam_quality = 8;
let cam_galleryImages = [];
let cam_galleryPage = 1;
let cam_countdownTimer = null;
let cam_countdownRemaining = 0;
const CAM_GALLERY_PER_PAGE = 20;

function renderModule_cam(container, mod) {
    const chipId = mod.chip_id;
    const moduleType = mod.type;
    const ctrlData = mod.ctrl_data || {};
    const camReady = mod.online && ctrlData.camera_ready;

    // v4.1.9: sincroniza estado live do servidor apos reload do browser.
    // Servidor eh fonte de verdade (ESP32 reporta cam_live_mode no register,
    // start-live/stop-live escrevem otimisticamente). Se o PWA nao tem sessao
    // live tracked (cam_liveChipId=null) e o servidor diz que esta live, adota.
    const serverSaysLive = ctrlData.cam_live_mode === true && mod.online;
    if (!cam_liveChipId && serverSaysLive && camReady) {
        cam_liveOn = true;
        cam_liveChipId = chipId;
        cam_liveType = moduleType;
        cam_liveLastTs = 0;
        // Dispara pollLoop pra retomar frames (nao precisa chamar start-live de novo)
        setTimeout(() => cam_pollLoop(chipId, moduleType), 300);
    } else if (cam_liveChipId === chipId && !serverSaysLive && mod.online) {
        // Servidor diz off mas PWA acha que ta on — corrige (ex: auto-timeout do ESP32)
        cam_liveOn = false;
        cam_liveChipId = null;
        cam_liveType = null;
    }

    const statusColor = camReady ? '#27ae60' : '#e74c3c';
    const statusText = camReady ? 'Pronta' : 'Offline';
    const btnDisabled = !camReady || cam_pending;
    const liveActive = cam_liveOn && cam_liveChipId === chipId;
    const chevronSvg = (id, open) => `<svg id="${id}" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2" style="transition:transform 0.25s;${open ? 'transform:rotate(180deg)' : ''}"><polyline points="6 9 12 15 18 9"/></svg>`;

    container.innerHTML = `
        <div class="card" style="padding:0;overflow:hidden">
            <!-- Header Camera (mesma classe dos outros modulos) -->
            <div class="module-inline-title" style="margin:0;padding:14px;border-bottom:1px solid var(--border, hsl(210,15%,20%))">
                <span class="mch-dot" style="background:${statusColor};box-shadow:0 0 6px ${statusColor}40"></span>
                <b>${escapeHtml(getDisplayName(chipId))}</b>
            </div>

            <!-- Dropdown: Captura -->
            <div class="cam-dropdown">
                <div class="cam-dropdown-header" onclick="cam_toggleSection('capture')">
                    <span>Captura</span>
                    ${chevronSvg('chv-capture', cam_captureOpen)}
                </div>
                <div class="cam-dropdown-body" id="cam-section-capture" style="display:${cam_captureOpen ? 'block' : 'none'}">
                    <div id="cam-img" style="background:var(--bg);border-radius:8px;min-height:120px;display:flex;align-items:center;justify-content:center;overflow:hidden">
                        ${cam_imageUrl
                            ? `<img src="${cam_imageUrl}&token=${token}" style="width:100%;border-radius:8px" alt="Captura" />`
                            : `<span style="color:#555;font-size:0.85rem">${camReady ? 'Toque em Capturar' : 'Camera nao conectada'}</span>`
                        }
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px">
                        <button id="cam-btn" onclick="cam_capture('${chipId}','${moduleType}')" style="flex:1;padding:10px;border-radius:10px;border:1px solid var(--border);background:var(--bg-card);color:var(--text-muted);font-weight:600;font-size:0.85rem;cursor:pointer" ${btnDisabled || liveActive ? 'disabled' : ''}>
                            ${cam_pending ? '&#9203; Capturando...' : '&#128247; Capturar'}
                        </button>
                        <button id="live-btn" onclick="cam_liveToggle('${chipId}','${moduleType}')" style="flex:1;padding:10px;border-radius:10px;border:1px solid ${liveActive ? '#e74c3c' : 'var(--border)'};background:${liveActive ? 'rgba(231,76,60,0.1)' : 'var(--bg-card)'};color:${liveActive ? '#e74c3c' : 'var(--text-muted)'};font-weight:600;font-size:0.85rem;cursor:pointer" ${!camReady ? 'disabled' : ''}>
                            ${liveActive ? '&#9632; Parar' : '&#127909; Ao Vivo'}
                        </button>
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px">
                        <div style="flex:1">
                            <label style="font-size:0.7rem;color:var(--text-dim)">Resolucao</label>
                            <select class="config-select" onchange="cam_setResolution('${chipId}','${moduleType}',this.value)">
                                <option value="VGA" ${cam_resolution=='VGA'?'selected':''}>640x480</option>
                                <option value="SVGA" ${cam_resolution=='SVGA'?'selected':''}>800x600</option>
                                <option value="UXGA" ${cam_resolution=='UXGA'?'selected':''}>1600x1200</option>
                            </select>
                        </div>
                        <div style="flex:1">
                            <label style="font-size:0.7rem;color:var(--text-dim)">Qualidade</label>
                            <select class="config-select" onchange="cam_setQuality('${chipId}','${moduleType}',this.value)">
                                <option value="8" ${cam_quality==8?'selected':''}>Alta (q8)</option>
                                <option value="10" ${cam_quality==10?'selected':''}>Boa (q10)</option>
                                <option value="15" ${cam_quality==15?'selected':''}>Normal (q15)</option>
                            </select>
                        </div>
                    </div>
                    <button onclick="showCamSensorConfig('${chipId}','${moduleType}')" style="width:100%;margin-top:8px;padding:8px;border-radius:var(--radius);border:1px solid var(--border);background:transparent;color:var(--text-dim);font-size:0.8rem;cursor:pointer">&#9881; Configuracoes do Sensor</button>
                </div>
            </div>

            <!-- Dropdown: Gravacao + Galeria -->
            <div class="cam-dropdown">
                <div class="cam-dropdown-header" onclick="cam_toggleSection('record')">
                    <div style="display:flex;align-items:center;gap:8px">
                        <span>Gravacao</span>
                        ${cam_recording ? '<span class="scheduled-badge"><span class="rec-dot-green"></span> Gravando</span>' : ''}
                    </div>
                    ${chevronSvg('chv-record', cam_recordOpen)}
                </div>
                <div class="cam-dropdown-body" id="cam-section-record" style="display:${cam_recordOpen ? 'block' : 'none'}">
                    <div style="margin-bottom:8px">
                        <label style="font-size:0.75rem;color:var(--text-dim)">Pasta</label>
                        <input type="text" id="cam-folder" class="config-input" placeholder="Ex: Tomate Semana 3" value="${cam_captureFolder || ''}" ${cam_recording ? 'disabled' : ''} style="width:100%;padding:8px;border:1px solid var(--border);border-radius:var(--radius);font-size:0.85rem;background:var(--bg-input);color:var(--text)">
                    </div>
                    <div style="margin-bottom:8px">
                        <label style="font-size:0.75rem;color:var(--text-dim)">Intervalo</label>
                        <select id="cam-interval" class="config-select" onchange="cam_setInterval('${chipId}','${moduleType}',this.value)" ${cam_recording ? 'disabled' : ''}>
                            <option value="30" ${cam_captureInterval==30?'selected':''}>30 segundos</option>
                            <option value="60" ${cam_captureInterval==60?'selected':''}>1 minuto</option>
                            <option value="300" ${cam_captureInterval==300?'selected':''}>5 minutos</option>
                            <option value="600" ${cam_captureInterval==600?'selected':''}>10 minutos</option>
                            <option value="1800" ${cam_captureInterval==1800?'selected':''}>30 minutos</option>
                            <option value="3600" ${cam_captureInterval==3600?'selected':''}>1 hora</option>
                        </select>
                    </div>
                    ${cam_recording ? `<div id="cam-countdown" style="margin-bottom:8px">
                        <span style="font-size:0.75rem;color:var(--text-dim)" id="cam-countdown-label">Proxima captura em --:--</span>
                        <div class="progress-scheduled"><div class="progress-fill-scheduled" id="cam-countdown-bar"></div></div>
                    </div>` : ''}
                    <button class="btn-scheduled ${cam_recording ? 'recording' : ''}" onclick="cam_toggleRecording('${chipId}','${moduleType}')" ${!camReady ? 'disabled' : ''}>
                        <span>${cam_recording ? '&#9632;' : '&#9654;'}</span>
                        <span>${cam_recording ? 'Parar Gravacao' : 'Iniciar Gravacao'}</span>
                    </button>

                    <!-- Galeria carrossel -->
                    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                            <b style="font-size:0.85rem;color:var(--text)">Galeria</b>
                            <span id="cam-gallery-counter" style="font-size:0.7rem;color:var(--text-dim)"></span>
                        </div>
                        <div style="position:relative">
                            <div id="cam-gallery-track" style="display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;scrollbar-width:none;padding:4px 0">
                                <span style="color:var(--text-dim);font-size:0.8rem;text-align:center;padding:1rem;width:100%">Carregando...</span>
                            </div>
                            <button id="cam-gallery-prev" onclick="cam_scrollGallery(-1)" style="position:absolute;left:0;top:50%;transform:translateY(-50%);width:28px;height:28px;border-radius:50%;border:none;background:rgba(0,0,0,0.6);color:#fff;font-size:14px;cursor:pointer;display:none;z-index:2">&lt;</button>
                            <button id="cam-gallery-next" onclick="cam_scrollGallery(1)" style="position:absolute;right:0;top:50%;transform:translateY(-50%);width:28px;height:28px;border-radius:50%;border:none;background:rgba(0,0,0,0.6);color:#fff;font-size:14px;cursor:pointer;display:none;z-index:2">&gt;</button>
                        </div>
                        <button onclick="openGallery('${chipId}','${moduleType}')" style="width:100%;margin-top:8px;padding:10px;border-radius:var(--radius);border:1px solid var(--border);background:transparent;color:var(--text);font-weight:600;font-size:0.85rem;cursor:pointer">&#128193; Abrir Galeria</button>
                    </div>
                </div>
            </div>
        </div>
        ${renderNotificationCard(chipId, mod.ctrl_data || {})}
        ${renderWifiTelemetry({ ...(mod.ctrl_data || {}), rssi: mod.rssi, uptime: mod.uptime }, mod.chip_id, mod.name)}`;

    if (cam_captureOpen && !cam_imageUrl && camReady) cam_loadLast(chipId, moduleType);
    if (cam_recordOpen) {
        cam_loadGallery(chipId, moduleType);
        if (cam_recording) cam_startCountdown(cam_captureInterval);
    }
}

function cam_toggleSection(section) {
    if (section === 'capture') {
        cam_captureOpen = !cam_captureOpen;
        const body = document.getElementById('cam-section-capture');
        const chv = document.getElementById('chv-capture');
        if (body) body.style.display = cam_captureOpen ? 'block' : 'none';
        if (chv) chv.style.transform = cam_captureOpen ? 'rotate(180deg)' : '';
    } else if (section === 'record') {
        cam_recordOpen = !cam_recordOpen;
        const body = document.getElementById('cam-section-record');
        const chv = document.getElementById('chv-record');
        if (body) body.style.display = cam_recordOpen ? 'block' : 'none';
        if (chv) chv.style.transform = cam_recordOpen ? 'rotate(180deg)' : '';
        if (cam_recordOpen) {
            const camMod = modules.find(m => hasCap(m, 'cam'));
            if (camMod) cam_loadGallery(camMod.chip_id, camMod.type);
        }
    }
}

async function cam_capture(chipId, moduleType) {
    if (!chipId || cam_pending) return;
    cam_pending = true;
    const btn = document.getElementById('cam-btn');
    const img = document.getElementById('cam-img');
    if (btn) { btn.disabled = true; btn.innerHTML = '&#9203; Capturando...'; }
    if (img) img.innerHTML = '<div style="padding:20px;text-align:center"><div style="width:24px;height:24px;border:3px solid #333;border-top-color:#27ae60;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto"></div><p style="color:#555;margin-top:8px;font-size:0.8rem">Aguardando imagem...</p></div>';

    const prevBase = cam_imageUrl ? cam_imageUrl.split("?")[0] : "";
    try {
        await api(`${apiFor(moduleType)}/${chipId}/capture`);
        for (let i = 0; i < 12; i++) {
            await new Promise(r => setTimeout(r, 1200));
            try {
                const data = await api(`${apiFor(moduleType)}/${chipId}/last-capture`);
                if (data.status === "ok" && data.url && data.url !== prevBase) {
                    cam_imageUrl = data.url + "?t=" + Date.now();
                    if (img) {
                        // v4.1.26: createElement + setAttribute evita injecao via URL com aspas
                        img.replaceChildren();
                        const el = document.createElement('img');
                        el.src = cam_imageUrl + "&token=" + encodeURIComponent(token);
                        el.style.cssText = "width:100%;border-radius:8px";
                        el.alt = "Captura";
                        img.appendChild(el);
                    }
                    break;
                }
            } catch (e) { break; }
        }
    } catch (e) {
        if (img) img.innerHTML = '<span style="color:#e74c3c;font-size:0.85rem">Erro ao capturar</span>';
    }
    cam_pending = false;
    if (btn) { btn.disabled = false; btn.innerHTML = '&#128247; Capturar'; }
    // Refresh galeria apos captura
    if (cam_recordOpen) cam_loadGallery(chipId, moduleType);
}

async function cam_liveToggle(chipId, moduleType) {
    if (cam_liveOn) cam_stopLive(); else cam_startLive(chipId, moduleType);
}

async function cam_startLive(chipId, moduleType) {
    if (!chipId || cam_liveOn) return;
    cam_liveOn = true; cam_liveChipId = chipId; cam_liveType = moduleType; cam_liveLastTs = 0;
    const btn = document.getElementById('live-btn');
    if (btn) { btn.innerHTML = '&#9632; Parar'; btn.style.borderColor = '#e74c3c'; btn.style.background = 'rgba(231,76,60,0.1)'; btn.style.color = '#e74c3c'; }
    const camBtn = document.getElementById('cam-btn');
    if (camBtn) camBtn.disabled = true;
    try { await api(`${apiFor(moduleType)}/${chipId}/start-live`); } catch (e) { console.error("Erro live:", e); }
    cam_pollLoop(chipId, moduleType);
}

async function cam_stopLive() {
    cam_liveOn = false;
    if (cam_liveChipId && cam_liveType) {
        try { await api(`${apiFor(cam_liveType)}/${cam_liveChipId}/stop-live`); } catch (e) {}
    }
    cam_liveChipId = null; cam_liveType = null; cam_liveLastTs = 0;
    const btn = document.getElementById('live-btn');
    if (btn) { btn.innerHTML = '&#127909; Ao Vivo'; btn.style.borderColor = ''; btn.style.background = ''; btn.style.color = ''; }
    const camBtn = document.getElementById('cam-btn');
    if (camBtn) camBtn.disabled = false;
    const img = document.getElementById('cam-img');
    if (img) img.innerHTML = '<span style="color:#555;font-size:0.85rem">Toque em Capturar</span>';
}

async function cam_pollLoop(chipId, moduleType) {
    while (cam_liveOn && cam_liveChipId === chipId) {
        try {
            const res = await fetch(`${apiFor(moduleType)}/${chipId}/live-frame?token=${token}&after=${cam_liveLastTs}`);
            if (!cam_liveOn) break;
            if (res.ok && res.headers.get("content-type")?.includes("image/jpeg")) {
                const ts = res.headers.get("x-frame-ts");
                if (ts) cam_liveLastTs = parseFloat(ts);
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const img = document.getElementById("cam-img");
                if (img) {
                    const oldImg = img.querySelector("img");
                    if (oldImg && oldImg.src.startsWith("blob:")) URL.revokeObjectURL(oldImg.src);
                    img.innerHTML = `<img src="${url}" style="width:100%;border-radius:8px" alt="Live" />`;
                }
                continue;
            }
            await new Promise(r => setTimeout(r, 400));
        } catch (e) { if (cam_liveOn) await new Promise(r => setTimeout(r, 1000)); }
    }
}

async function cam_loadLast(chipId, moduleType) {
    try {
        const data = await api(`${apiFor(moduleType)}/${chipId}/last-capture`);
        if (data.status === "ok" && data.url) {
            cam_imageUrl = data.url + "?t=" + Date.now();
            const img = document.getElementById("cam-img");
            if (img) {
                // v4.1.26: createElement evita injecao via URL (mesmo fluxo do cam_capture)
                img.replaceChildren();
                const el = document.createElement('img');
                el.src = cam_imageUrl + "&token=" + encodeURIComponent(token);
                el.style.cssText = "width:100%;border-radius:8px";
                el.alt = "Captura";
                img.appendChild(el);
            }
        }
    } catch (e) {}
}

// --- Captura Agendada ---

async function cam_toggleRecording(chipId, moduleType) {
    const newState = !cam_recording;
    const body = { recording: newState };
    if (newState) {
        const folderInput = document.getElementById('cam-folder');
        const folder = folderInput ? folderInput.value.trim() : '';
        body.capture_folder = folder;
        cam_captureFolder = folder;
    }
    try {
        await api(`${apiFor(moduleType)}/${chipId}/config`, { method: 'POST', body });
        cam_recording = newState;
        if (!newState) cam_stopCountdown();
        forceFullRefresh();
    } catch (e) { alert('Erro: ' + e.message); }
}

async function cam_setResolution(chipId, moduleType, value) {
    try {
        await api(`${apiFor(moduleType)}/${chipId}/config`, { method: 'POST', body: { cam_resolution: value } });
        cam_resolution = value;
    } catch (e) { alert('Erro: ' + e.message); }
}

async function cam_setQuality(chipId, moduleType, value) {
    try {
        await api(`${apiFor(moduleType)}/${chipId}/config`, { method: 'POST', body: { cam_quality: parseInt(value) } });
        cam_quality = parseInt(value);
    } catch (e) { alert('Erro: ' + e.message); }
}

async function cam_setInterval(chipId, moduleType, value) {
    const interval = parseInt(value);
    try {
        await api(`${apiFor(moduleType)}/${chipId}/config`, {
            method: 'POST', body: { capture_interval: interval }
        });
        cam_captureInterval = interval;
    } catch (e) { alert('Erro: ' + e.message); }
}

function cam_startCountdown(intervalSeconds) {
    cam_stopCountdown();
    cam_countdownRemaining = intervalSeconds;
    cam_countdownTimer = setInterval(() => {
        cam_countdownRemaining--;
        if (cam_countdownRemaining <= 0) {
            cam_countdownRemaining = intervalSeconds;
            // Aguarda imagem chegar e atualiza galeria
            const camMod = modules.find(m => hasCap(m, 'cam'));
            if (camMod && cam_recordOpen) cam_waitAndRefreshGallery(camMod.chip_id, camMod.type);
        }
        const bar = document.getElementById('cam-countdown-bar');
        const label = document.getElementById('cam-countdown-label');
        if (bar) bar.style.width = ((intervalSeconds - cam_countdownRemaining) / intervalSeconds * 100) + '%';
        if (label) {
            const m = Math.floor(cam_countdownRemaining / 60);
            const s = String(cam_countdownRemaining % 60).padStart(2, '0');
            label.textContent = `Proxima captura em ${m}:${s}`;
        }
    }, 1000);
}

async function cam_waitAndRefreshGallery(chipId, moduleType) {
    // Pega contagem atual
    const prevTotal = cam_galleryImages.length > 0 ? cam_galleryImages[0].filename : '';
    // Tenta ate 5x com 3s entre cada (max 15s de espera)
    for (let i = 0; i < 5; i++) {
        await new Promise(r => setTimeout(r, 3000));
        try {
            const data = await api(`${apiFor(moduleType)}/${chipId}/images?page=1&per_page=${CAM_GALLERY_PER_PAGE}`);
            const newFirst = (data.images && data.images.length > 0) ? data.images[0].filename : '';
            if (newFirst !== prevTotal) {
                cam_galleryImages = data.images || [];
                cam_renderGallery(data);
                return;
            }
        } catch (e) { break; }
    }
}

function cam_stopCountdown() {
    if (cam_countdownTimer) { clearInterval(cam_countdownTimer); cam_countdownTimer = null; }
}

// --- Galeria ---

async function cam_loadGallery(chipId, moduleType) {
    try {
        const data = await api(`${apiFor(moduleType)}/${chipId}/images?page=${cam_galleryPage}&per_page=${CAM_GALLERY_PER_PAGE}`);
        cam_galleryImages = data.images || [];
        cam_renderGallery(data);
    } catch (e) {
        const track = document.getElementById('cam-gallery-track');
        if (track) track.innerHTML = '<span style="color:var(--text-dim);font-size:0.8rem;text-align:center;padding:1rem;width:100%">Erro ao carregar</span>';
    }
}

function cam_renderGallery(data) {
    const track = document.getElementById('cam-gallery-track');
    const counter = document.getElementById('cam-gallery-counter');
    if (!track) return;

    if (!data.images || data.images.length === 0) {
        track.innerHTML = '<span style="color:var(--text-dim);font-size:0.8rem;text-align:center;padding:1rem;width:100%">Nenhuma captura salva</span>';
        if (counter) counter.textContent = '';
        return;
    }

    if (counter) counter.textContent = `${data.total} fotos`;

    track.innerHTML = data.images.map(img => {
        const sizeStr = img.size_kb >= 1024 ? (img.size_kb/1024).toFixed(1)+' MB' : Math.round(img.size_kb)+' KB';
        let dateStr = '';
        let ago = '';
        if (img.created_at) {
            try {
                const d = new Date(img.created_at + '-03:00');
                dateStr = `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
                const diff = Math.floor((Date.now() - d.getTime()) / 1000);
                if (diff > 0 && diff < 60) ago = `${diff}s`;
                else if (diff >= 60 && diff < 3600) ago = `${Math.floor(diff/60)}min`;
                else if (diff >= 3600 && diff < 86400) ago = `${Math.floor(diff/3600)}h`;
                else if (diff >= 86400) ago = `${Math.floor(diff/86400)}d`;
            } catch(e) {}
        }
        const thumbSrc = img.thumb_url || img.url;
        return `<div style="flex:0 0 calc(50% - 4px);scroll-snap-align:start;border-radius:8px;overflow:hidden;position:relative;background:var(--bg-card);cursor:pointer" onclick="cam_openImage('${img.url}')">
            <img src="${thumbSrc}?token=${token}" alt="Captura" loading="lazy" style="width:100%;aspect-ratio:4/3;object-fit:cover;display:block" />
            ${ago ? `<span style="position:absolute;top:4px;right:4px;font-size:0.6rem;font-weight:700;color:#fff;background:rgba(231,76,60,0.85);padding:1px 6px;border-radius:99px">${ago}</span>` : ''}
            <div style="padding:4px 6px;font-size:0.65rem;color:var(--text-dim)">${dateStr} · ${sizeStr}</div>
        </div>`;
    }).join('');

    const prevBtn = document.getElementById('cam-gallery-prev');
    const nextBtn = document.getElementById('cam-gallery-next');
    if (prevBtn && nextBtn && data.images.length > 2) {
        prevBtn.style.display = 'block';
        nextBtn.style.display = 'block';
    }
    cam_updateGalleryBtns();
    track.addEventListener('scroll', cam_updateGalleryBtns, {passive: true});
}

function cam_updateGalleryBtns() {
    const track = document.getElementById('cam-gallery-track');
    const prevBtn = document.getElementById('cam-gallery-prev');
    const nextBtn = document.getElementById('cam-gallery-next');
    if (!track || !prevBtn || !nextBtn) return;
    prevBtn.style.opacity = track.scrollLeft > 10 ? '1' : '0.3';
    nextBtn.style.opacity = track.scrollLeft < track.scrollWidth - track.clientWidth - 10 ? '1' : '0.3';
}

function cam_scrollGallery(dir) {
    const track = document.getElementById('cam-gallery-track');
    if (!track) return;
    const step = track.clientWidth;
    track.scrollBy({left: dir * step, behavior: 'smooth'});
}

function cam_openImage(url) {
    window.open(url + '?token=' + token, '_blank');
}

// Sync recording state from modules data
function cam_syncState(mod) {
    if (!mod || !mod.ctrl_data) return;
    const cfg = mod.ctrl_data;
    if (cfg.capture_interval) cam_captureInterval = cfg.capture_interval;
    if (cfg.recording !== undefined) cam_recording = !!cfg.recording;
    if (cfg.cam_resolution) cam_resolution = cfg.cam_resolution;
    if (cfg.cam_quality) cam_quality = cfg.cam_quality;
    if (cfg.capture_folder !== undefined) cam_captureFolder = cfg.capture_folder || '';
}

// --- Sensor Config ---
let sensorChipId = null, sensorModuleType = null;

async function showCamSensorConfig(chipId, moduleType) {
    sensorChipId = chipId;
    sensorModuleType = moduleType;
    try {
        const resp = await api('/api/modules');
        const mod = (resp.modules || []).find(m => m.chip_id === chipId);
        const data = mod && mod.ctrl_data ? mod.ctrl_data : {};
        renderCamSensorConfig(data);
        document.getElementById("config-modal").classList.remove("hidden");
    } catch (e) { alert("Erro: " + e.message); }
}

function renderCamSensorConfig(data) {
    const c = document.getElementById("config-content");
    const wb = data.cam_wb_mode || 0;
    const bri = data.cam_brightness || 0;
    const con = data.cam_contrast || 0;
    const sat = data.cam_saturation || 0;
    const ae = data.cam_ae_level || 0;
    const gc = data.cam_gainceiling != null ? data.cam_gainceiling : 2;
    const fx = data.cam_special_effect || 0;
    const hm = data.cam_hmirror || 0;
    const vf = data.cam_vflip || 0;
    const ec = data.cam_exposure_ctrl != null ? data.cam_exposure_ctrl : 1;
    const wbal = data.cam_whitebal != null ? data.cam_whitebal : 1;

    c.innerHTML = `
        <div class="config-section-label" style="color:var(--primary);background:var(--primary-glow);padding:0.3rem 0.6rem;border-radius:0.5rem;display:inline-block;font-weight:700;font-size:0.8rem">&#127909; Balanco de Branco</div>
        <div class="config-field" style="margin-bottom:0.5rem">
            <label>Modo</label>
            <select id="sc-wb" class="config-select" style="width:100%">
                <option value="0" ${wb==0?'selected':''}>Auto</option>
                <option value="1" ${wb==1?'selected':''}>Sunny</option>
                <option value="2" ${wb==2?'selected':''}>Cloudy</option>
                <option value="3" ${wb==3?'selected':''}>Office</option>
                <option value="4" ${wb==4?'selected':''}>Home</option>
            </select>
        </div>

        <div class="config-section-label" style="color:hsl(210,80%,55%);background:hsla(210,80%,55%,0.12);padding:0.3rem 0.6rem;border-radius:0.5rem;display:inline-block;font-weight:700;font-size:0.8rem">&#127912; Ajustes de Imagem</div>
        <div class="config-field" style="margin-bottom:0.5rem">
            <label>Brilho <span id="sc-bri-val">${bri}</span></label>
            <input type="range" id="sc-bri" min="-2" max="2" value="${bri}" oninput="document.getElementById('sc-bri-val').textContent=this.value" style="width:100%">
        </div>
        <div class="config-field" style="margin-bottom:0.5rem">
            <label>Contraste <span id="sc-con-val">${con}</span></label>
            <input type="range" id="sc-con" min="-2" max="2" value="${con}" oninput="document.getElementById('sc-con-val').textContent=this.value" style="width:100%">
        </div>
        <div class="config-field" style="margin-bottom:0.5rem">
            <label>Saturacao <span id="sc-sat-val">${sat}</span></label>
            <input type="range" id="sc-sat" min="-2" max="2" value="${sat}" oninput="document.getElementById('sc-sat-val').textContent=this.value" style="width:100%">
        </div>
        <div class="config-field" style="margin-bottom:0.5rem">
            <label>Compensacao Exposicao <span id="sc-ae-val">${ae}</span></label>
            <input type="range" id="sc-ae" min="-2" max="2" value="${ae}" oninput="document.getElementById('sc-ae-val').textContent=this.value" style="width:100%">
        </div>

        <div class="config-section-label" style="color:#e67e22;background:rgba(230,126,34,0.12);padding:0.3rem 0.6rem;border-radius:0.5rem;display:inline-block;font-weight:700;font-size:0.8rem">&#9881; Avancado</div>
        <div class="config-grid">
            <div class="config-field">
                <label>Teto de Ganho</label>
                <select id="sc-gc" class="config-select" style="width:100%">
                    <option value="0" ${gc==0?'selected':''}>2x</option>
                    <option value="1" ${gc==1?'selected':''}>4x</option>
                    <option value="2" ${gc==2?'selected':''}>8x</option>
                    <option value="3" ${gc==3?'selected':''}>16x</option>
                    <option value="4" ${gc==4?'selected':''}>32x</option>
                    <option value="5" ${gc==5?'selected':''}>64x</option>
                    <option value="6" ${gc==6?'selected':''}>128x</option>
                </select>
            </div>
            <div class="config-field">
                <label>Efeito</label>
                <select id="sc-fx" class="config-select" style="width:100%">
                    <option value="0" ${fx==0?'selected':''}>Nenhum</option>
                    <option value="1" ${fx==1?'selected':''}>Negativo</option>
                    <option value="2" ${fx==2?'selected':''}>P&B</option>
                    <option value="3" ${fx==3?'selected':''}>Vermelho</option>
                    <option value="4" ${fx==4?'selected':''}>Verde</option>
                    <option value="5" ${fx==5?'selected':''}>Azul</option>
                    <option value="6" ${fx==6?'selected':''}>Sepia</option>
                </select>
            </div>
        </div>

        <div style="margin-top:0.75rem;display:flex;flex-direction:column;gap:0.5rem">
            <label style="display:flex;align-items:center;gap:8px;font-size:0.85rem;color:var(--text);cursor:pointer">
                <input type="checkbox" id="sc-ec" ${ec?'checked':''} style="width:18px;height:18px"> Auto Exposicao
            </label>
            <label style="display:flex;align-items:center;gap:8px;font-size:0.85rem;color:var(--text);cursor:pointer">
                <input type="checkbox" id="sc-wbal" ${wbal?'checked':''} style="width:18px;height:18px"> Auto Balanco de Branco
            </label>
            <label style="display:flex;align-items:center;gap:8px;font-size:0.85rem;color:var(--text);cursor:pointer">
                <input type="checkbox" id="sc-hm" ${hm?'checked':''} style="width:18px;height:18px"> Espelhar Horizontal
            </label>
            <label style="display:flex;align-items:center;gap:8px;font-size:0.85rem;color:var(--text);cursor:pointer">
                <input type="checkbox" id="sc-vf" ${vf?'checked':''} style="width:18px;height:18px"> Inverter Vertical
            </label>
        </div>

        <div class="config-actions" style="margin-top:1rem">
            <button class="btn-primary" onclick="saveCamSensorConfig()">Salvar</button>
        </div>
        <div class="config-actions" style="margin-top:0.5rem">
            <button class="btn-secondary" onclick="resetCamSensorConfig()">Restaurar Padrao</button>
        </div>
    `;
}

async function saveCamSensorConfig() {
    const body = {
        cam_wb_mode: parseInt(document.getElementById('sc-wb').value),
        cam_brightness: parseInt(document.getElementById('sc-bri').value),
        cam_contrast: parseInt(document.getElementById('sc-con').value),
        cam_saturation: parseInt(document.getElementById('sc-sat').value),
        cam_ae_level: parseInt(document.getElementById('sc-ae').value),
        cam_gainceiling: parseInt(document.getElementById('sc-gc').value),
        cam_special_effect: parseInt(document.getElementById('sc-fx').value),
        cam_hmirror: document.getElementById('sc-hm').checked ? 1 : 0,
        cam_vflip: document.getElementById('sc-vf').checked ? 1 : 0,
        cam_exposure_ctrl: document.getElementById('sc-ec').checked ? 1 : 0,
        cam_whitebal: document.getElementById('sc-wbal').checked ? 1 : 0,
    };
    try {
        await api(`${apiFor(sensorModuleType)}/${sensorChipId}/config`, { method: 'POST', body });
        closeConfigModal();
    } catch (e) { alert('Erro: ' + e.message); }
}

async function resetCamSensorConfig() {
    const body = {
        cam_wb_mode: 0, cam_brightness: 0, cam_contrast: 0, cam_saturation: 0,
        cam_ae_level: 0, cam_gainceiling: 2, cam_special_effect: 0,
        cam_hmirror: 0, cam_vflip: 0, cam_exposure_ctrl: 1, cam_whitebal: 1,
    };
    try {
        await api(`${apiFor(sensorModuleType)}/${sensorChipId}/config`, { method: 'POST', body });
        closeConfigModal();
    } catch (e) { alert('Erro: ' + e.message); }
}

// =====================================================================
// Pair Modal
// =====================================================================

function showPairModal() {
    document.getElementById("pair-modal").classList.remove("hidden");
    wizardShowStep(0);
}

function closePairModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById("pair-modal").classList.add("hidden");
}

function wizardShowStep(n) {
    ["0", "1", "2"].forEach(id => {
        const el = document.getElementById("wizard-step-" + id);
        if (el) el.classList.toggle("hidden", id != n);
    });
    if (n === 2 || n === "2") {
        document.getElementById("pair-code").value = "";
        document.getElementById("pair-name").value = "";
        document.getElementById("pair-error").classList.add("hidden");
        setTimeout(() => document.getElementById("pair-code").focus(), 100);
    }
}

function wizardStart(mode) { wizardShowStep(mode === "new" ? 1 : 2); }
function wizardNext(step) { wizardShowStep(step); }
function wizardBack(step) { wizardShowStep(step); }

async function doPair() {
    try {
        await api("/api/modules/pair", { method: "POST", body: {
            short_id: document.getElementById("pair-code").value,
            name: document.getElementById("pair-name").value
        }});
        closePairModal();
        forceFullRefresh();
    } catch (e) {
        const el = document.getElementById("pair-error");
        el.textContent = e.message;
        el.classList.remove("hidden");
    }
}

// =====================================================================
// Auto-pair
// =====================================================================

let autoPairRetries = 0;

function checkPendingCode() {
    const params = new URLSearchParams(window.location.search);
    let code = params.get("code");
    if (!code) code = localStorage.getItem(`${STORAGE_PREFIX}_pending_code`);
    if (code && token) {
        localStorage.removeItem(`${STORAGE_PREFIX}_pending_code`);
        window.history.replaceState({}, "", window.location.pathname);
        doAutoPair(code);
    }
}

async function doAutoPair(code) {
    const list = document.getElementById("modules-list");
    list.innerHTML = `<div class="auto-pair-status"><div class="spinner"></div><p>Conectando modulo <strong>${code}</strong>...</p></div>`;
    try {
        await api("/api/modules/pair", { method: "POST", body: { short_id: code, name: DEFAULT_NAME } });
        autoPairRetries = 0;
        forceFullRefresh();
    } catch (e) {
        if ((e.message || "").includes("vinculado")) { autoPairRetries = 0; forceFullRefresh(); return; }
        autoPairRetries++;
        if (autoPairRetries < 20) {
            list.innerHTML = `<div class="auto-pair-status"><div class="spinner"></div><p>Conectando <strong>${code}</strong>... (${autoPairRetries}/20)</p></div>`;
            setTimeout(() => doAutoPair(code), 3000);
        } else { autoPairRetries = 0; forceFullRefresh(); }
    }
}

// =====================================================================
// Init
// =====================================================================

async function initApp() {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    if (code) localStorage.setItem(`${STORAGE_PREFIX}_pending_code`, code);

    // v4.1.20: ?verify=TOKEN (link de confirmacao de email) — consome antes de tudo
    await _checkVerifyLink();

    // v4.1.12: se URL tem ?reset=TOKEN, vai direto pra tela de reset
    // (mesmo se o usuario estiver logado — ele clicou no link intencionalmente)
    const hasResetLink = _checkResetLink();
    if (hasResetLink) {
        // Desloga caso esteja logado (seguranca: so quem tem o token do email acessa)
        if (token) {
            token = null; user = null;
            localStorage.removeItem(`${STORAGE_PREFIX}_token`);
            localStorage.removeItem(`${STORAGE_PREFIX}_user`);
        }
        document.getElementById("auth-screen").classList.remove("hidden");
        return;
    }

    const serverOnline = await checkServerConnection();
    if (token && user && serverOnline) { enterApp(); }
    else if (!serverOnline) { showOfflineScreen(); }
    else { document.getElementById("auth-screen").classList.remove("hidden"); }
}

async function checkServerConnection() {
    try { await fetch("/api/modules/register", { method: "HEAD", signal: AbortSignal.timeout(3000) }); return true; }
    catch (e) { return false; }
}

function showOfflineScreen() {
    document.getElementById("offline-screen").classList.remove("hidden");
    document.getElementById("auth-screen").classList.add("hidden");
    document.getElementById("app-screen").classList.add("hidden");
}

window.addEventListener("online", () => {
    if (!document.getElementById("offline-screen").classList.contains("hidden")) location.reload();
});

initApp();

// =====================================================================
// Admin Panel (v4.1.13) — so funciona se user.role === 'admin'
// Rotas /api/admin/* retornam 403 pra nao-admins, entao mesmo que alguem
// force o HTML a aparecer no dev-tools, os dados nao vem.
// =====================================================================

function showAdminPanel() {
    if (!user || user.role !== "admin") return;  // guard no cliente tambem
    _hideAllMainViews();
    document.getElementById("admin-view").classList.remove("hidden");
    loadAdminStats();
    loadAdminPlatformStatus();  // v4.1.32: status do servidor (CF Worker externo)
    loadAdminUsers();
    loadAdminModules();
    loadAdminAudit();  // v4.1.15
}

function hideAdminPanel() {
    document.getElementById("admin-view").classList.add("hidden");
    document.getElementById("module-view").classList.remove("hidden");
}

// v4.1.16: helper compartilhado — esconde todas as views de "main" pra ativar uma
function _hideAllMainViews() {
    const ids = ["module-view", "admin-view", "profile-view"];
    for (const id of ids) {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
    }
}

// =====================================================================
// User menu dropdown (v4.1.16) — nome + avatar + dropdown com Perfil/Admin/Sair
// Padrao SaaS: click no nome abre dropdown; click fora ou em item fecha.
// =====================================================================

function _renderUserMenu() {
    if (!user) return;
    // Nome + email no trigger e no header do dropdown
    document.getElementById("nav-user").textContent = user.name || user.email || "Usuario";
    document.getElementById("user-menu-name").textContent = user.name || "Usuario";
    document.getElementById("user-menu-email").textContent = user.email || "";
    // Avatar = primeira letra do nome (maiuscula)
    const avatar = document.getElementById("user-avatar");
    if (avatar) {
        const letter = ((user.name || user.email || "?").trim()[0] || "?").toUpperCase();
        avatar.textContent = letter;
    }
    // Badge de role no header do dropdown
    const roleEl = document.getElementById("user-menu-role");
    if (roleEl) {
        const roleColor = user.role === "admin" ? "#e67e22" : (user.role === "support" ? "#3498db" : "#888");
        const roleLabel = user.role === "admin" ? "Admin" : (user.role === "support" ? "Suporte" : "Usuario");
        roleEl.innerHTML = `<span style="background:${roleColor}22;color:${roleColor};padding:2px 8px;border-radius:10px;font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.5px">${roleLabel}</span>`;
    }
    // Mostra item "Admin" no dropdown so se role === 'admin'
    const adminItem = document.getElementById("nav-admin-link");
    if (adminItem) {
        if (user.role === "admin") adminItem.classList.remove("hidden");
        else adminItem.classList.add("hidden");
    }
}

function toggleUserMenu(event) {
    if (event) event.stopPropagation();
    const dd = document.getElementById("user-menu-dropdown");
    if (!dd) return;
    dd.classList.toggle("hidden");
}

function closeUserMenu() {
    const dd = document.getElementById("user-menu-dropdown");
    if (dd) dd.classList.add("hidden");
}

// Click fora fecha o dropdown
document.addEventListener("click", function(e) {
    const menu = document.getElementById("user-menu");
    const dd = document.getElementById("user-menu-dropdown");
    if (!menu || !dd || dd.classList.contains("hidden")) return;
    if (!menu.contains(e.target)) closeUserMenu();
});

// ESC fecha
document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") closeUserMenu();
});

// =====================================================================
// Profile Panel (v4.1.16) — "Meu perfil" na navbar
// =====================================================================

function showProfilePanel() {
    if (!user) return;
    _hideAllMainViews();
    document.getElementById("profile-view").classList.remove("hidden");
    loadProfile();
}

function hideProfilePanel() {
    document.getElementById("profile-view").classList.add("hidden");
    document.getElementById("module-view").classList.remove("hidden");
}

async function loadProfile() {
    // v4.1.22: carrega em paralelo — perfil + sessoes
    loadProfileSessions();
    // v4.1.43: notificacoes saem do perfil — agora ficam consolidadas no card
    // de cada modulo (renderNotificationCard). Nao carrega aqui.
    try {
        const p = await api("/api/profile/");
        // Header info (read-only)
        document.getElementById("profile-email").textContent = p.email || "";
        const roleBadge = p.role === "admin" ? "Admin" : (p.role === "support" ? "Suporte" : "Usuario");
        const roleColor = p.role === "admin" ? "#e67e22" : (p.role === "support" ? "#3498db" : "#888");
        document.getElementById("profile-role").innerHTML =
            `<span style="background:${roleColor}22;color:${roleColor};padding:2px 6px;border-radius:4px;font-size:0.7rem;font-weight:600">${roleBadge}</span>`;
        document.getElementById("profile-created").textContent = p.created_at || "—";

        // Editable fields
        document.getElementById("prof-name").value = p.name || "";
        document.getElementById("prof-phone").value = p.phone || "";
        document.getElementById("prof-birth").value = p.birth_date || "";
        document.getElementById("prof-notif-email").value = p.notification_email || "";
        document.getElementById("prof-cep").value = p.cep || "";
        document.getElementById("prof-street").value = p.street || "";
        document.getElementById("prof-number").value = p.number || "";
        document.getElementById("prof-complement").value = p.complement || "";
        document.getElementById("prof-neighborhood").value = p.neighborhood || "";
        document.getElementById("prof-city").value = p.city || "";
        document.getElementById("prof-state").value = p.state || "";
        // v4.1.20: dados fiscais
        const ptype = p.person_type || "pf";
        document.getElementById("prof-ptype-pf").checked = ptype === "pf";
        document.getElementById("prof-ptype-pj").checked = ptype === "pj";
        document.getElementById("prof-tax-id").value = p.tax_id || "";
        document.getElementById("prof-company").value = p.company_name || "";
        onPersonTypeChange();  // ajusta label + visibilidade de razao social
        // v4.1.22: status 2FA TOTP
        const statusEl = document.getElementById("prof-2fa-status");
        const btnEl = document.getElementById("prof-2fa-btn");
        if (statusEl && btnEl) {
            const enabled = !!p.totp_enabled;
            _totpEnabled = enabled;
            if (enabled) {
                statusEl.innerHTML = '<span style="color:var(--primary)">&#10003; Ativo</span>';
                btnEl.textContent = "Desativar";
                btnEl.style.background = "transparent";
                btnEl.style.color = "#e74c3c";
                btnEl.style.border = "1px solid #e74c3c";
            } else {
                statusEl.textContent = "Inativo — codigo gerado pelo app, sem precisar de email";
                btnEl.textContent = "Ativar";
                btnEl.style.background = "var(--primary)";
                btnEl.style.color = "#fff";
                btnEl.style.border = "none";
            }
        }
        // v4.1.29: status 2FA Email
        const e2faStatusEl = document.getElementById("prof-email2fa-status");
        const e2faBtnEl = document.getElementById("prof-email2fa-btn");
        if (e2faStatusEl && e2faBtnEl) {
            const enabled = !!p.email_2fa_enabled;
            _email2faEnabled = enabled;
            if (enabled) {
                e2faStatusEl.innerHTML = '<span style="color:var(--primary)">&#10003; Ativo</span>';
                e2faBtnEl.textContent = "Desativar";
                e2faBtnEl.style.background = "transparent";
                e2faBtnEl.style.color = "#e74c3c";
                e2faBtnEl.style.border = "1px solid #e74c3c";
            } else {
                e2faStatusEl.textContent = "Inativo — codigo enviado por email a cada login";
                e2faBtnEl.textContent = "Ativar";
                e2faBtnEl.style.background = "var(--primary)";
                e2faBtnEl.style.color = "#fff";
                e2faBtnEl.style.border = "none";
            }
            // Mutua exclusao com TOTP — desabilita botao se outro ativo
            if (_totpEnabled && !enabled) {
                e2faBtnEl.disabled = true;
                e2faBtnEl.style.opacity = "0.4";
                e2faBtnEl.title = "Desative o TOTP primeiro";
            } else {
                e2faBtnEl.disabled = false;
                e2faBtnEl.style.opacity = "1";
                e2faBtnEl.title = "";
            }
            if (enabled && !_totpEnabled) {
                btnEl.disabled = true;
                btnEl.style.opacity = "0.4";
                btnEl.title = "Desative o 2FA por Email primeiro";
            } else {
                btnEl.disabled = false;
                btnEl.style.opacity = "1";
                btnEl.title = "";
            }
        }
    } catch (e) {
        alert("Erro ao carregar perfil: " + e.message);
    }
}

// =====================================================================
// 2FA TOTP (v4.1.22)
// =====================================================================

let _totpEnabled = false;

function toggle2FA() {
    if (_totpEnabled) {
        // Abre modal de desativar
        document.getElementById("totp-disable-pass").value = "";
        document.getElementById("totp-disable-code").value = "";
        document.getElementById("totp-disable-msg").classList.add("hidden");
        document.getElementById("totp-disable-modal").classList.remove("hidden");
    } else {
        // Inicia setup
        setup2FA();
    }
}

async function setup2FA() {
    try {
        const r = await api("/api/profile/2fa/setup", { method: "POST" });
        // Mostra QR (via API externa gratuita) + secret + input
        const qrUrl = "https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=" + encodeURIComponent(r.uri);
        document.getElementById("totp-qr-container").innerHTML = `<img src="${qrUrl}" width="220" height="220" alt="QR Code 2FA" style="display:block">`;
        document.getElementById("totp-secret-text").textContent = r.secret;
        document.getElementById("totp-code-input").value = "";
        document.getElementById("totp-msg").classList.add("hidden");
        document.getElementById("totp-modal").classList.remove("hidden");
        setTimeout(() => document.getElementById("totp-code-input")?.focus(), 200);
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

function close2FAModal() {
    document.getElementById("totp-modal").classList.add("hidden");
}

async function confirmEnable2FA() {
    const code = document.getElementById("totp-code-input").value.trim();
    const msg = document.getElementById("totp-msg");
    msg.classList.add("hidden");
    if (!code || code.length !== 6) {
        msg.textContent = "Codigo deve ter 6 digitos";
        msg.classList.remove("hidden");
        return;
    }
    try {
        await api("/api/profile/2fa/enable", { method: "POST", body: { code } });
        alert("2FA ativado com sucesso. Proximos logins vao exigir o codigo do app.");
        close2FAModal();
        loadProfile();
    } catch (e) {
        msg.textContent = e.message;
        msg.classList.remove("hidden");
    }
}

function close2FADisableModal() {
    document.getElementById("totp-disable-modal").classList.add("hidden");
}

async function confirmDisable2FA() {
    const password = document.getElementById("totp-disable-pass").value;
    const code = document.getElementById("totp-disable-code").value.trim();
    const msg = document.getElementById("totp-disable-msg");
    msg.classList.add("hidden");
    if (!password || !code) {
        msg.textContent = "Senha e codigo obrigatorios";
        msg.classList.remove("hidden");
        return;
    }
    try {
        await api("/api/profile/2fa/disable", { method: "POST", body: { password, code } });
        alert("2FA desativado");
        close2FADisableModal();
        loadProfile();
    } catch (e) {
        msg.textContent = e.message;
        msg.classList.remove("hidden");
    }
}

// =====================================================================
// 2FA por Email (v4.1.29) — alternativa ao TOTP
// =====================================================================

let _email2faEnabled = false;

function toggleEmail2FA() {
    if (_email2faEnabled) {
        // Desativar — abre modal que dispara envio de codigo
        document.getElementById("email2fa-disable-pass").value = "";
        document.getElementById("email2fa-disable-code").value = "";
        document.getElementById("email2fa-disable-msg").classList.add("hidden");
        document.getElementById("email2fa-disable-modal").classList.remove("hidden");
    } else {
        // Setup — abre modal e mostra etapa de envio
        document.getElementById("email2fa-step-intro").style.display = "block";
        document.getElementById("email2fa-step-confirm").style.display = "none";
        document.getElementById("email2fa-code-input").value = "";
        document.getElementById("email2fa-msg").classList.add("hidden");
        document.getElementById("email2fa-modal").classList.remove("hidden");
    }
}

function closeEmail2FAModal() {
    document.getElementById("email2fa-modal").classList.add("hidden");
}

function closeEmail2FADisableModal() {
    document.getElementById("email2fa-disable-modal").classList.add("hidden");
}

async function email2faSetup() {
    const msg = document.getElementById("email2fa-msg");
    msg.classList.add("hidden");
    try {
        await api("/api/profile/2fa/email/setup", { method: "POST" });
        document.getElementById("email2fa-step-intro").style.display = "none";
        document.getElementById("email2fa-step-confirm").style.display = "block";
        setTimeout(() => document.getElementById("email2fa-code-input")?.focus(), 200);
    } catch (e) {
        msg.textContent = e.message;
        msg.classList.remove("hidden");
    }
}

async function email2faConfirmEnable() {
    const code = document.getElementById("email2fa-code-input").value.trim();
    const msg = document.getElementById("email2fa-msg");
    msg.classList.add("hidden");
    if (!code || code.length !== 6) {
        msg.textContent = "Codigo deve ter 6 digitos";
        msg.classList.remove("hidden");
        return;
    }
    try {
        await api("/api/profile/2fa/email/enable", { method: "POST", body: { code } });
        alert("2FA por email ativado. Proximos logins vao receber codigo no seu email.");
        closeEmail2FAModal();
        loadProfile();
    } catch (e) {
        msg.textContent = e.message;
        msg.classList.remove("hidden");
    }
}

async function confirmDisableEmail2FA() {
    const password = document.getElementById("email2fa-disable-pass").value;
    const code = document.getElementById("email2fa-disable-code").value.trim();
    const msg = document.getElementById("email2fa-disable-msg");
    msg.classList.add("hidden");
    if (!password) {
        msg.textContent = "Senha obrigatoria";
        msg.classList.remove("hidden");
        return;
    }
    try {
        const resp = await fetch("/api/profile/2fa/email/disable", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
            body: JSON.stringify({ password, code }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            // Servidor mandou novo codigo? Mostra msg amigavel
            if (data.code_sent) {
                msg.textContent = data.error || "Codigo enviado pro seu email";
            } else {
                msg.textContent = data.error || "Erro";
            }
            msg.classList.remove("hidden");
            return;
        }
        alert("2FA por email desativado");
        closeEmail2FADisableModal();
        loadProfile();
    } catch (e) {
        msg.textContent = e.message;
        msg.classList.remove("hidden");
    }
}

// =====================================================================
// Session management (v4.1.22) — Meus dispositivos
// =====================================================================

async function loadProfileSessions() {
    const el = document.getElementById("prof-sessions");
    if (!el) return;
    try {
        const data = await api("/api/profile/sessions");
        if (!data.sessions || !data.sessions.length) {
            el.innerHTML = '<p class="empty-state" style="padding:10px">Nenhuma sessao ativa.</p>';
            return;
        }
        const rows = data.sessions.map(s => {
            // Detecta tipo de device do user-agent
            const ua = s.user_agent || "";
            let deviceIcon = "&#128241;"; // mobile default
            let deviceName = "Dispositivo";
            if (/Windows/i.test(ua)) { deviceIcon = "&#128187;"; deviceName = "Windows"; }
            else if (/Macintosh|Mac OS/i.test(ua)) { deviceIcon = "&#128187;"; deviceName = "Mac"; }
            else if (/Linux/i.test(ua) && !/Android/i.test(ua)) { deviceIcon = "&#128187;"; deviceName = "Linux"; }
            else if (/iPad/i.test(ua)) { deviceName = "iPad"; }
            else if (/iPhone/i.test(ua)) { deviceName = "iPhone"; }
            else if (/Android/i.test(ua)) { deviceName = "Android"; }
            let browser = "";
            if (/Chrome/i.test(ua) && !/Edg/i.test(ua)) browser = "Chrome";
            else if (/Firefox/i.test(ua)) browser = "Firefox";
            else if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) browser = "Safari";
            else if (/Edg/i.test(ua)) browser = "Edge";

            const lastUsed = s.last_used_at || s.created_at || "";
            const current = s.is_current
                ? '<span style="background:rgba(39,174,96,0.15);color:var(--primary);padding:2px 6px;border-radius:4px;font-size:0.65rem;font-weight:600;margin-left:6px">ATUAL</span>'
                : '';
            const revokeBtn = s.is_current
                ? ''
                : `<button onclick="revokeSession(${s.id})" style="background:transparent;border:1px solid #e74c3c;color:#e74c3c;padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem">Revogar</button>`;
            return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:6px">
                <div>
                    <div style="font-size:0.85rem;font-weight:600">${deviceIcon} ${deviceName}${browser ? ' \u00b7 ' + browser : ''}${current}</div>
                    <div style="font-size:0.7rem;color:var(--text-dim);margin-top:2px">IP ${s.ip || '—'} \u00b7 Ultimo uso: ${lastUsed}</div>
                </div>
                ${revokeBtn}
            </div>`;
        }).join("");
        el.innerHTML = rows;
    } catch (e) {
        el.innerHTML = `<p style="color:#e74c3c;padding:10px;font-size:0.8rem">Erro: ${e.message}</p>`;
    }
}

async function revokeSession(sessionId) {
    if (!confirm("Revogar essa sessao? O outro dispositivo sera deslogado.")) return;
    try {
        await api(`/api/profile/sessions/${sessionId}`, { method: "DELETE" });
        loadProfileSessions();
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

async function revokeOtherSessions() {
    if (!confirm("Deslogar de TODOS os outros dispositivos? Essa sessao continua ativa.")) return;
    try {
        await api("/api/profile/sessions/revoke-others", { method: "POST" });
        alert("Outras sessoes foram revogadas");
        loadProfileSessions();
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

// v4.1.20: Alterna entre PF e PJ (muda label do campo + mostra/esconde razao social)
function onPersonTypeChange() {
    const isPj = document.getElementById("prof-ptype-pj")?.checked;
    const label = document.getElementById("prof-tax-label");
    const input = document.getElementById("prof-tax-id");
    const companyRow = document.getElementById("prof-company-row");
    if (!label || !input || !companyRow) return;
    if (isPj) {
        label.textContent = "CNPJ";
        input.placeholder = "00.000.000/0000-00";
        input.maxLength = 18;
        companyRow.classList.remove("hidden");
    } else {
        label.textContent = "CPF";
        input.placeholder = "000.000.000-00";
        input.maxLength = 14;
        companyRow.classList.add("hidden");
    }
}

async function saveProfile() {
    // v4.1.30: feedback em ambos os botoes (Meus dados + Dados fiscais)
    const msgs = [
        document.getElementById("profile-save-msg"),
        document.getElementById("profile-fiscal-save-msg"),
    ].filter(Boolean);
    msgs.forEach(m => m.classList.add("hidden"));
    const isPj = document.getElementById("prof-ptype-pj").checked;
    const payload = {
        name: document.getElementById("prof-name").value.trim(),
        phone: document.getElementById("prof-phone").value.trim(),
        birth_date: document.getElementById("prof-birth").value,
        notification_email: document.getElementById("prof-notif-email").value.trim().toLowerCase(),
        cep: document.getElementById("prof-cep").value.replace(/\D/g, ""),
        street: document.getElementById("prof-street").value.trim(),
        number: document.getElementById("prof-number").value.trim(),
        complement: document.getElementById("prof-complement").value.trim(),
        neighborhood: document.getElementById("prof-neighborhood").value.trim(),
        city: document.getElementById("prof-city").value.trim(),
        state: document.getElementById("prof-state").value.trim().toUpperCase().slice(0, 2),
        // v4.1.20: dados fiscais
        person_type: isPj ? "pj" : "pf",
        tax_id: document.getElementById("prof-tax-id").value.replace(/\D/g, ""),
        company_name: isPj ? document.getElementById("prof-company").value.trim() : "",
    };
    try {
        const r = await api("/api/profile/", { method: "PUT", body: payload });
        msgs.forEach(m => {
            m.textContent = "Dados salvos com sucesso.";
            m.style.color = "var(--primary)";
            m.classList.remove("hidden");
        });
        // Atualiza user object + navbar (se nome mudou)
        if (payload.name && user) {
            user.name = payload.name;
            localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
            _renderUserMenu();  // re-renderiza avatar + nome + header do dropdown
        }
        setTimeout(() => msgs.forEach(m => m.classList.add("hidden")), 3500);
    } catch (e) {
        msgs.forEach(m => {
            m.textContent = "Erro: " + e.message;
            m.style.color = "#e74c3c";
            m.classList.remove("hidden");
        });
    }
}

async function fetchCep() {
    const raw = document.getElementById("prof-cep").value.replace(/\D/g, "");
    const status = document.getElementById("prof-cep-status");
    if (raw.length !== 8) {
        status.textContent = "Digite o CEP pra auto-preencher";
        return;
    }
    status.textContent = "Buscando CEP...";
    try {
        const r = await api(`/api/profile/cep/${raw}`);
        document.getElementById("prof-street").value = r.street || document.getElementById("prof-street").value;
        document.getElementById("prof-neighborhood").value = r.neighborhood || document.getElementById("prof-neighborhood").value;
        document.getElementById("prof-city").value = r.city || document.getElementById("prof-city").value;
        document.getElementById("prof-state").value = r.state || document.getElementById("prof-state").value;
        status.textContent = `${r.city}/${r.state} ✓`;
        status.style.color = "var(--primary)";
        setTimeout(() => document.getElementById("prof-number").focus(), 100);
    } catch (e) {
        status.textContent = "CEP nao encontrado";
        status.style.color = "#e74c3c";
    }
}

async function changePasswordProfile() {
    const cur = document.getElementById("prof-pwd-current").value;
    const n1 = document.getElementById("prof-pwd-new").value;
    const n2 = document.getElementById("prof-pwd-confirm").value;
    const msg = document.getElementById("profile-pwd-msg");
    msg.classList.add("hidden");

    if (!cur || !n1) { _pwdMsg("Preencha todos os campos", "#e74c3c"); return; }
    if (n1.length < 6) { _pwdMsg("Nova senha deve ter pelo menos 6 caracteres", "#e74c3c"); return; }
    if (n1 !== n2) { _pwdMsg("As senhas nao conferem", "#e74c3c"); return; }

    try {
        const r = await api("/api/profile/password", {
            method: "POST",
            body: { current_password: cur, new_password: n1 },
        });
        _pwdMsg(r.message || "Senha alterada com sucesso.", "var(--primary)");
        document.getElementById("prof-pwd-current").value = "";
        document.getElementById("prof-pwd-new").value = "";
        document.getElementById("prof-pwd-confirm").value = "";
    } catch (e) {
        _pwdMsg("Erro: " + e.message, "#e74c3c");
    }
}

function _pwdMsg(text, color) {
    const msg = document.getElementById("profile-pwd-msg");
    msg.textContent = text;
    msg.style.color = color;
    msg.classList.remove("hidden");
}

// =====================================================================
// LGPD (v4.1.20) — exportar meus dados + deletar conta
// =====================================================================

async function exportMyData() {
    try {
        // Usa fetch direto pra tratar o blob (api() espera JSON)
        const res = await fetch("/api/profile/export", {
            headers: token ? { "Authorization": `Bearer ${token}` } : {}
        });
        if (!res.ok) throw new Error("Falha ao exportar: " + res.status);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `cultivee-dados-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

function showDeleteAccountModal() {
    document.getElementById("delete-pass").value = "";
    document.getElementById("delete-msg").classList.add("hidden");
    document.getElementById("delete-account-modal").classList.remove("hidden");
}

function closeDeleteAccountModal() {
    document.getElementById("delete-account-modal").classList.add("hidden");
}

async function deleteMyAccount() {
    const pwd = document.getElementById("delete-pass").value;
    const msg = document.getElementById("delete-msg");
    msg.classList.add("hidden");
    if (!pwd) {
        msg.textContent = "Senha obrigatoria";
        msg.classList.remove("hidden");
        return;
    }
    try {
        await api("/api/profile/", { method: "DELETE", body: { password: pwd } });
        // Sucesso — limpa tudo e volta pra tela de login
        alert("Conta excluida. Ate mais!");
        localStorage.clear();
        location.href = "/";
    } catch (e) {
        msg.textContent = e.message;
        msg.classList.remove("hidden");
    }
}

// =====================================================================
// Email verification (v4.1.20) — banner + reenvio + consumir token do URL
// =====================================================================

function renderEmailVerificationBanner() {
    const banner = document.getElementById("email-verification-banner");
    if (!banner) return;
    // Banner so aparece pra usuario logado + email nao verificado + nao impersonando
    if (user && user.email_verified === false && !isImpersonating()) {
        banner.classList.remove("hidden");
    } else {
        banner.classList.add("hidden");
    }
}

async function resendVerification() {
    try {
        const r = await api("/api/auth/resend-verification", { method: "POST" });
        alert(r.message || "Email de verificacao reenviado.");
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

// Detecta ?verify=TOKEN na URL (link do email) e consome
async function _checkVerifyLink() {
    try {
        const params = new URLSearchParams(window.location.search);
        const t = params.get("verify");
        if (!t || t.length < 10) return false;
        try {
            await api("/api/auth/verify-email?token=" + encodeURIComponent(t));
            alert("Email confirmado com sucesso! Faca login pra continuar.");
            // Atualiza user object se estiver logado
            if (user) {
                user.email_verified = true;
                localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
            }
        } catch (e) {
            alert("Nao foi possivel confirmar o email: " + e.message);
        }
        // Limpa URL independente de sucesso/erro
        try { history.replaceState(null, "", window.location.pathname); } catch (e) {}
        return true;
    } catch (e) { return false; }
}

async function loadAdminStats() {
    const el = document.getElementById("admin-stats");
    try {
        const s = await api("/api/admin/stats");
        const byType = Object.entries(s.modules.by_type || {})
            .map(([t, c]) => `${t}:${c}`).join(" · ") || "-";
        el.innerHTML = `
            <div class="stat-card"><div class="label">Usuarios</div><div class="value">${s.users.total}</div><div class="label" style="margin-top:4px;font-size:0.6rem">${s.users.admins} admin(s)</div></div>
            <div class="stat-card"><div class="label">Modulos</div><div class="value">${s.modules.total}</div><div class="label" style="margin-top:4px;font-size:0.6rem">${s.modules.paired} pareados</div></div>
            <div class="stat-card"><div class="label">Online agora</div><div class="value" style="color:${s.modules.online_now>0?'#27ae60':'#888'}">${s.modules.online_now}</div><div class="label" style="margin-top:4px;font-size:0.6rem">${byType}</div></div>
            <div class="stat-card"><div class="label">Alertas 24h</div><div class="value">${s.alerts_24h}</div><div class="label" style="margin-top:4px;font-size:0.6rem">${s.push_subscriptions} push subs</div></div>
        `;
    } catch (e) {
        el.innerHTML = `<p style="color:#e74c3c;font-size:0.8rem">Erro: ${e.message}</p>`;
    }
}

// =====================================================================
// v4.1.32 — Status da plataforma (CF Worker externo em status.cultivee.com.br)
// Endpoint /check ja tem CORS aberto + cache 30s na borda CF.
// Cache local de 60s pra nao bater no Worker a cada modal aberto.
// =====================================================================

const _PLATFORM_STATUS_URL = "https://status.cultivee.com.br/check";
let _platformStatusCache = null;  // { ts, data }

async function _fetchPlatformStatus(force) {
    if (!force && _platformStatusCache && (Date.now() - _platformStatusCache.ts) < 60000) {
        return _platformStatusCache.data;
    }
    const r = await fetch(_PLATFORM_STATUS_URL, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    _platformStatusCache = { ts: Date.now(), data };
    return data;
}

async function loadAdminPlatformStatus() {
    const el = document.getElementById("admin-platform-status");
    if (!el) return;
    try {
        const data = await _fetchPlatformStatus(false);
        const overallOk = !!(data.overall && data.overall.healthy);
        const headerColor = overallOk ? "#27ae60" : "#e74c3c";
        const headerBg = overallOk ? "rgba(39,174,96,0.12)" : "rgba(231,76,60,0.12)";
        const headerIcon = overallOk ? "&#10003;" : "&#9888;";
        const headerLabel = overallOk ? "Operacional" : "Com problemas";

        const rows = (data.components || []).map(function (c) {
            const cur = c.current || {};
            const ok = cur.healthy === true;
            const dotColor = ok ? "#27ae60" : (cur.healthy === false ? "#e74c3c" : "#7d8a98");
            const stateTxt = ok ? "operacional" : (cur.healthy === false ? (cur.reason || "indisponivel") : "sem dados");
            const lat = (cur.latency_ms != null) ? `${cur.latency_ms}ms` : "—";
            const up7 = (c.uptime && c.uptime.pct_7d != null) ? `${c.uptime.pct_7d}%` : "—";
            const lastSeen = cur.last_check_at ? formatRelativeShort(cur.last_check_at) : "—";
            return `
                <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:8px">
                    <div style="display:flex;align-items:center;gap:8px;min-width:0">
                        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${dotColor};flex-shrink:0"></span>
                        <div style="min-width:0">
                            <div style="font-size:0.82rem;font-weight:600">${escapeHtml(c.name)}</div>
                            <div style="font-size:0.68rem;color:var(--text-dim)">${escapeHtml(stateTxt)} &middot; ${escapeHtml(lat)} &middot; uptime 7d: ${escapeHtml(up7)}</div>
                        </div>
                    </div>
                    <div style="font-size:0.65rem;color:var(--text-dim);text-align:right;white-space:nowrap">verificado ${escapeHtml(lastSeen)}</div>
                </div>`;
        }).join("");

        const incidents = data.incidents || [];
        const ongoing = incidents.filter(function (i) { return i.ongoing; });
        let incidentsHtml = "";
        if (ongoing.length > 0) {
            incidentsHtml = `<div style="margin-top:10px;padding:8px 10px;background:rgba(231,76,60,0.10);border:1px solid rgba(231,76,60,0.35);border-radius:8px;font-size:0.78rem">
                &#9888; <b>${ongoing.length} incidente${ongoing.length>1?'s':''} em curso</b> &middot;
                ${ongoing.map(function(i){return escapeHtml(i.component_name||i.component);}).join(", ")}
            </div>`;
        } else if (incidents.length > 0) {
            incidentsHtml = `<div style="margin-top:8px;font-size:0.7rem;color:var(--text-dim)">
                ${incidents.length} incidente${incidents.length>1?'s':''} nos ultimos 30 dias
                (mais recente: ${escapeHtml(formatRelativeShort(incidents[0].start))}).
            </div>`;
        } else {
            incidentsHtml = `<div style="margin-top:8px;font-size:0.7rem;color:var(--text-dim)">
                Sem incidentes nos ultimos 30 dias.
            </div>`;
        }

        el.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
                <span style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:${headerBg};color:${headerColor};font-size:0.95rem">${headerIcon}</span>
                <div>
                    <div style="font-size:0.92rem;font-weight:700;color:${headerColor}">${headerLabel}</div>
                    <div style="font-size:0.65rem;color:var(--text-dim)">Monitorado por Cloudflare Worker externo &middot; checagem a cada 5min</div>
                </div>
            </div>
            <div style="display:grid;gap:6px">${rows || '<div class="empty-state"><p>Sem componentes configurados.</p></div>'}</div>
            ${incidentsHtml}`;
    } catch (e) {
        el.innerHTML = `<p style="color:var(--text-dim);font-size:0.78rem">
            Nao foi possivel carregar (${escapeHtml(e.message)}).
            Veja diretamente em <a href="https://status.cultivee.com.br/" target="_blank" rel="noopener" style="color:var(--primary)">status.cultivee.com.br</a>.
        </p>`;
    }
}

async function loadAdminUsers() {
    const el = document.getElementById("admin-users");
    try {
        const data = await api("/api/admin/users");
        _adminUsersCache = data.users || [];  // cache pra usar no modal de transfer
        if (!data.users || !data.users.length) {
            el.innerHTML = '<p class="empty-state">Nenhum usuario.</p>';
            return;
        }
        const myId = user && user.id;
        const rows = data.users.map(u => {
            const roleColor = u.role === 'admin' ? '#e67e22' : (u.role === 'support' ? '#3498db' : '#888');
            const roleBadge = `<span style="background:${roleColor}22;color:${roleColor};padding:2px 6px;border-radius:4px;font-size:0.65rem;font-weight:600;text-transform:uppercase">${escapeHtml(u.role||'user')}</span>`;
            // v4.1.26: safeLabel vai pra atributo onclick='...' — usar escapeAttr
            const safeLabel = escapeAttr(u.name || u.email);
            // v4.1.14 + v4.1.21: menu de acoes
            const canImpersonate = u.role !== 'admin' && u.id !== myId;
            const actions = [];
            if (canImpersonate) {
                actions.push(`<button onclick="impersonateUser(${u.id}, '${safeLabel}')" style="background:transparent;border:1px solid var(--border);color:var(--primary);padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem;font-weight:600">Acessar</button>`);
            }
            if (u.id !== myId) {
                actions.push(`<button onclick="showRoleModal(${u.id}, '${safeLabel}', '${escapeAttr(u.role||'user')}')" style="background:transparent;border:1px solid var(--border);color:#e67e22;padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem;font-weight:600">Nivel</button>`);
            }
            actions.push(`<button onclick="forceResetPwd(${u.id}, '${safeLabel}')" style="background:transparent;border:1px solid var(--border);color:#3498db;padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem;font-weight:600">Resetar senha</button>`);
            const actionBtn = actions.length ? actions.join(" ") : '<span style="color:var(--text-dim);font-size:0.7rem">—</span>';
            return `<tr>
                <td style="padding:6px 4px;font-family:monospace;font-size:0.75rem">#${u.id}</td>
                <td style="padding:6px 4px">${escapeHtml(u.name||'—')}</td>
                <td style="padding:6px 4px;font-size:0.75rem;color:var(--text-dim)">${escapeHtml(u.email)}</td>
                <td style="padding:6px 4px;text-align:center">${roleBadge}</td>
                <td style="padding:6px 4px;text-align:center;font-size:0.75rem">${u.module_count}</td>
                <td style="padding:6px 4px;text-align:center;white-space:nowrap">${actionBtn}</td>
            </tr>`;
        }).join("");
        el.innerHTML = `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:0.8rem">
            <thead><tr style="border-bottom:1px solid var(--border);color:var(--text-dim);text-align:left">
                <th style="padding:6px 4px">ID</th>
                <th style="padding:6px 4px">Nome</th>
                <th style="padding:6px 4px">Email</th>
                <th style="padding:6px 4px;text-align:center">Nivel</th>
                <th style="padding:6px 4px;text-align:center">Modulos</th>
                <th style="padding:6px 4px;text-align:center">Acoes</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
    } catch (e) {
        el.innerHTML = `<p style="color:#e74c3c;font-size:0.8rem">Erro: ${e.message}</p>`;
    }
}

// v4.1.21: cache de users pra uso em outros modais (ex: transfer de modulo)
let _adminUsersCache = [];

// =====================================================================
// R2 admin actions (v4.1.21) — alterar role + forcar reset + transferir modulo
// =====================================================================

// v4.1.25: showRoleModal agora abre modal custom com dropdown
// (antes era prompt() do navegador — feio e permitia digitacao livre)
let _roleTargetId = null;
let _roleTargetName = null;
let _roleCurrent = null;

function showRoleModal(userId, userLabel, currentRole) {
    _roleTargetId = userId;
    _roleTargetName = userLabel;
    _roleCurrent = (currentRole || "user").toLowerCase();
    document.getElementById("role-target-name").textContent = userLabel;
    const currentLabel = _roleCurrent === "admin" ? "Admin" : (_roleCurrent === "support" ? "Suporte" : "Usuario");
    document.getElementById("role-current").textContent = currentLabel;
    document.getElementById("role-new").value = _roleCurrent;
    document.getElementById("role-modal").classList.remove("hidden");
}

function closeRoleModal() {
    document.getElementById("role-modal").classList.add("hidden");
    _roleTargetId = null;
}

function doChangeRole() {
    if (!_roleTargetId) return;
    const newRole = document.getElementById("role-new").value;
    if (!["user", "support", "admin"].includes(newRole)) {
        alert("Nivel invalido");
        return;
    }
    if (newRole === _roleCurrent) {
        closeRoleModal();
        return;
    }
    const targetId = _roleTargetId;
    closeRoleModal();
    _setUserRole(targetId, newRole);
}

async function _setUserRole(userId, role) {
    try {
        const r = await api(`/api/admin/users/${userId}/role`, {
            method: "POST", body: { role }
        });
        alert(r.message || "Nivel alterado");
        loadAdminUsers();
        loadAdminAudit();
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

async function forceResetPwd(userId, userLabel) {
    if (!confirm(`Forçar reset de senha de "${userLabel}"?\n\n- Email sera enviado ao usuario com link de reset (valido 1h)\n- TODAS as sessoes ativas desse user serao revogadas\n- Acao registrada no audit log\n\nContinuar?`)) return;
    try {
        const r = await api(`/api/admin/users/${userId}/force-password-reset`, { method: "POST" });
        alert(r.message);
        loadAdminAudit();
    } catch (e) {
        alert("Erro: " + e.message);
    }
}

function transferModule(chipId, currentOwnerEmail) {
    // Monta lista de candidatos (users != atual dono)
    const candidates = _adminUsersCache.filter(u => u.email !== currentOwnerEmail);
    if (!candidates.length) {
        alert("Nenhum outro usuario disponivel");
        return;
    }
    const options = candidates.map(u => `${u.id}: ${u.email} (${u.role})`).join("\n");
    const input = prompt(
        `Transferir modulo ${chipId}\n\nDono atual: ${currentOwnerEmail || '(sem dono)'}\n\nDigite o ID do novo dono:\n\n${options}`
    );
    if (!input) return;
    const newUserId = parseInt(input.trim(), 10);
    if (!newUserId || !candidates.find(u => u.id === newUserId)) {
        alert("ID invalido");
        return;
    }
    if (!confirm(`Confirma transferir ${chipId} pro user #${newUserId}?`)) return;
    _transferModule(chipId, newUserId);
}

async function _transferModule(chipId, newUserId) {
    try {
        const r = await api(`/api/admin/modules/${encodeURIComponent(chipId)}/transfer`, {
            method: "POST", body: { new_user_id: newUserId }
        });
        alert(r.message);
        loadAdminUsers();
        loadAdminModules();
        loadAdminAudit();
    } catch (e) {
        alert("Erro: " + e.message);
    }
}


// =====================================================================
// Firmware upload modal (v4.1.27) — admin envia .bin OTA sem precisar
// do token do dono. Calcula SHA-256 client-side pra conferir antes de subir.
// =====================================================================

let _firmwareTargetChip = null;
let _firmwareSelectedFile = null;
let _firmwareClientSha = null;

function showFirmwareModal(chipId, moduleName, moduleType) {
    _firmwareTargetChip = chipId;
    _firmwareSelectedFile = null;
    _firmwareClientSha = null;
    document.getElementById("firmware-target-chip").textContent = chipId;
    document.getElementById("firmware-target-name").textContent = moduleName || chipId;
    document.getElementById("firmware-target-type").textContent = moduleType || '—';
    // Reset do formulario
    const fileInput = document.getElementById("firmware-file");
    if (fileInput) fileInput.value = "";
    document.getElementById("firmware-preview").style.display = "none";
    document.getElementById("firmware-step-pick").style.display = "block";
    document.getElementById("firmware-step-result").style.display = "none";
    const btn = document.getElementById("firmware-upload-btn");
    btn.disabled = true;
    btn.style.opacity = "0.5";
    btn.textContent = "Enviar OTA";
    document.getElementById("firmware-modal").classList.remove("hidden");
}

function closeFirmwareModal() {
    document.getElementById("firmware-modal").classList.add("hidden");
    _firmwareTargetChip = null;
    _firmwareSelectedFile = null;
    _firmwareClientSha = null;
}

function _fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

async function _sha256Hex(arrayBuffer) {
    const digest = await crypto.subtle.digest("SHA-256", arrayBuffer);
    return Array.from(new Uint8Array(digest))
        .map(b => b.toString(16).padStart(2, "0")).join("");
}

async function onFirmwareFileChange(event) {
    const file = event.target.files && event.target.files[0];
    const preview = document.getElementById("firmware-preview");
    const btn = document.getElementById("firmware-upload-btn");
    if (!file) {
        _firmwareSelectedFile = null;
        _firmwareClientSha = null;
        preview.style.display = "none";
        btn.disabled = true;
        btn.style.opacity = "0.5";
        return;
    }
    const MAX = 3 * 1024 * 1024;
    if (file.size > MAX) {
        alert(`Arquivo grande demais (${_fmtBytes(file.size)}). Limite 3MB.`);
        event.target.value = "";
        return;
    }
    _firmwareSelectedFile = file;
    document.getElementById("firmware-size").textContent = _fmtBytes(file.size);
    document.getElementById("firmware-sha").textContent = "calculando...";
    preview.style.display = "block";
    btn.disabled = true;
    btn.style.opacity = "0.5";
    try {
        const buf = await file.arrayBuffer();
        _firmwareClientSha = await _sha256Hex(buf);
        document.getElementById("firmware-sha").textContent = _firmwareClientSha;
        btn.disabled = false;
        btn.style.opacity = "1";
    } catch (e) {
        document.getElementById("firmware-sha").textContent = "erro ao calcular hash";
        _firmwareClientSha = null;
    }
}

async function doUploadFirmware() {
    if (!_firmwareTargetChip || !_firmwareSelectedFile) return;
    const btn = document.getElementById("firmware-upload-btn");
    btn.disabled = true;
    btn.style.opacity = "0.5";
    btn.textContent = "Enviando...";

    const fd = new FormData();
    fd.append("firmware", _firmwareSelectedFile);
    try {
        const resp = await fetch(`/api/admin/modules/${encodeURIComponent(_firmwareTargetChip)}/firmware`, {
            method: "POST",
            headers: { "Authorization": "Bearer " + token },
            body: fd,
        });
        const data = await resp.json();
        const box = document.getElementById("firmware-result-box");
        if (resp.ok) {
            const shaMatch = data.sha256 && _firmwareClientSha && (data.sha256.toLowerCase() === _firmwareClientSha.toLowerCase());
            const shaLine = shaMatch
                ? `<div style="color:#27ae60;margin-top:6px">SHA-256 do servidor bate com o local: OK</div>`
                : `<div style="color:#e67e22;margin-top:6px">Aviso: SHA-256 divergente. Verifique o arquivo.</div>`;
            box.style.background = "rgba(39,174,96,0.1)";
            box.style.border = "1px solid #27ae60";
            box.innerHTML = `
                <div style="font-weight:700;color:#27ae60;margin-bottom:6px">Firmware pendente no servidor</div>
                <div style="font-family:monospace;font-size:0.7rem;color:var(--text-dim);word-break:break-all">
                    Tamanho: ${_fmtBytes(data.size)}<br>
                    SHA-256: ${escapeHtml(data.sha256 || '—')}
                </div>
                ${shaLine}
                <div style="color:var(--text-dim);font-size:0.78rem;margin-top:10px">
                    ${escapeHtml(data.message || 'ESP32 vai baixar no proximo poll.')}
                </div>`;
        } else {
            box.style.background = "rgba(231,76,60,0.1)";
            box.style.border = "1px solid #e74c3c";
            box.innerHTML = `<div style="color:#e74c3c;font-weight:700">Erro HTTP ${resp.status}</div>
                <div style="margin-top:6px">${escapeHtml(data.error || JSON.stringify(data))}</div>`;
        }
        document.getElementById("firmware-step-pick").style.display = "none";
        document.getElementById("firmware-step-result").style.display = "block";
        if (resp.ok) {
            loadAdminAudit();
            loadAdminModules();
        }
    } catch (e) {
        alert("Erro no upload: " + e.message);
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.textContent = "Enviar OTA";
    }
}

// =====================================================================
// Impersonation (v4.1.14) — admin entra como outro user
// Guarda token+user do admin em localStorage separado, troca pelo do target.
// Banner no topo permite voltar. Token do target expira em 30min.
// =====================================================================

function isImpersonating() {
    return !!localStorage.getItem(`${STORAGE_PREFIX}_imp_token`);
}

function renderImpersonationBanner() {
    const banner = document.getElementById("impersonation-banner");
    if (!banner) return;
    if (isImpersonating() && user) {
        const label = document.getElementById("impersonation-label");
        const scope = localStorage.getItem(`${STORAGE_PREFIX}_imp_scope`) || "full";
        const readonly = scope === "readonly";
        if (label) {
            label.textContent = `Acessando como ${user.name} (${user.email})`
                              + (readonly ? " · SOMENTE LEITURA" : "");
        }
        // Banner vermelho pra readonly (alerta), laranja pra full (alerta ameno)
        banner.style.background = readonly ? "#c0392b" : "#e67e22";
        banner.classList.remove("hidden");
    } else {
        banner.classList.add("hidden");
    }
}

// v4.1.15: abre modal pra escolher opcoes (minutes + view_only) antes de impersonar
let _impTargetId = null;
let _impTargetName = null;
function impersonateUser(targetId, targetName) {
    _impTargetId = targetId;
    _impTargetName = targetName;
    document.getElementById("imp-target-name").textContent = targetName;
    document.getElementById("imp-minutes").value = "30";
    document.getElementById("imp-view-only").checked = false;
    document.getElementById("impersonate-modal").classList.remove("hidden");
}

function closeImpersonateModal() {
    document.getElementById("impersonate-modal").classList.add("hidden");
    _impTargetId = null;
}

async function doImpersonate() {
    if (!_impTargetId) return;
    const minutes = parseInt(document.getElementById("imp-minutes").value, 10) || 30;
    const viewOnly = document.getElementById("imp-view-only").checked;
    try {
        const data = await api(`/api/admin/users/${_impTargetId}/impersonate`, {
            method: "POST",
            body: { minutes, view_only: viewOnly },
        });
        // Salva sessao admin pra restaurar depois
        localStorage.setItem(`${STORAGE_PREFIX}_imp_token`, token);
        localStorage.setItem(`${STORAGE_PREFIX}_imp_user`, JSON.stringify(user));
        localStorage.setItem(`${STORAGE_PREFIX}_imp_scope`, data.scope || "full");
        // Troca pra sessao do target
        token = data.token;
        user = data.user;
        localStorage.setItem(`${STORAGE_PREFIX}_token`, token);
        localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
        location.reload();
    } catch (e) {
        alert("Erro ao impersonar: " + e.message);
    }
}

function stopImpersonating() {
    const impToken = localStorage.getItem(`${STORAGE_PREFIX}_imp_token`);
    const impUser = localStorage.getItem(`${STORAGE_PREFIX}_imp_user`);
    if (!impToken || !impUser) {
        location.reload();
        return;
    }
    localStorage.setItem(`${STORAGE_PREFIX}_token`, impToken);
    localStorage.setItem(`${STORAGE_PREFIX}_user`, impUser);
    localStorage.removeItem(`${STORAGE_PREFIX}_imp_token`);
    localStorage.removeItem(`${STORAGE_PREFIX}_imp_user`);
    localStorage.removeItem(`${STORAGE_PREFIX}_imp_scope`);
    location.reload();
}

// v4.1.15 + v4.1.21: Audit Log panel com filtros
async function loadAdminAudit() {
    const el = document.getElementById("admin-audit");
    if (!el) return;
    try {
        // Le filtros da UI (se existirem)
        const fAction = document.getElementById("audit-filter-action")?.value.trim() || "";
        const fAdmin = document.getElementById("audit-filter-admin")?.value.trim() || "";
        const fFrom = document.getElementById("audit-filter-from")?.value || "";
        const fTo = document.getElementById("audit-filter-to")?.value || "";
        const qs = new URLSearchParams();
        qs.set("limit", "100");
        if (fAction) qs.set("action", fAction);
        if (fAdmin) qs.set("admin_id", fAdmin);
        if (fFrom) qs.set("from", fFrom);
        if (fTo) qs.set("to", fTo);
        const data = await api("/api/admin/audit?" + qs.toString());
        if (!data.entries || !data.entries.length) {
            el.innerHTML = '<p class="empty-state">Nenhuma acao administrativa registrada.</p>';
            return;
        }
        // Mapper visual das acoes internas -> labels PT
        const actionLabels = {
            'impersonate': 'Acesso como',
            'user.role_change': 'Mudanca de nivel',
            'user.force_password_reset': 'Reset de senha',
            'module.transfer': 'Transferencia de modulo',
            'module.firmware_upload': 'Upload de firmware',
            'module.firmware_cancel': 'Cancelamento de firmware',
        };
        const rows = data.entries.map(e => {
            const ts = e.created_at || '—';
            const admin = e.admin_email || `id=${e.admin_id}`;
            const target = e.target_label ? `${e.target_type||''} ${e.target_label}` : (e.target_id || '—');
            const dtx = e.details && Object.keys(e.details).length ? JSON.stringify(e.details) : '';
            const actColor = e.action === 'impersonate' ? '#e67e22' : 'var(--primary)';
            const actLabel = actionLabels[e.action] || e.action;
            return `<tr>
                <td style="padding:6px 4px;font-family:monospace;font-size:0.7rem;color:var(--text-dim);white-space:nowrap">${ts}</td>
                <td style="padding:6px 4px;font-size:0.75rem">${admin}</td>
                <td style="padding:6px 4px"><span style="background:${actColor}22;color:${actColor};padding:2px 6px;border-radius:4px;font-size:0.7rem;font-weight:600">${actLabel}</span></td>
                <td style="padding:6px 4px;font-size:0.75rem">${target}</td>
                <td style="padding:6px 4px;font-size:0.7rem;color:var(--text-dim);font-family:monospace;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${dtx.replace(/"/g,'&quot;')}">${dtx}</td>
                <td style="padding:6px 4px;font-size:0.7rem;color:var(--text-dim);font-family:monospace">${e.ip||'—'}</td>
            </tr>`;
        }).join("");
        el.innerHTML = `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:0.8rem">
            <thead><tr style="border-bottom:1px solid var(--border);color:var(--text-dim);text-align:left">
                <th style="padding:6px 4px">Quando</th>
                <th style="padding:6px 4px">Admin</th>
                <th style="padding:6px 4px">Acao</th>
                <th style="padding:6px 4px">Alvo</th>
                <th style="padding:6px 4px">Detalhes</th>
                <th style="padding:6px 4px">IP</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
    } catch (e) {
        el.innerHTML = `<p style="color:#e74c3c;font-size:0.8rem">Erro: ${e.message}</p>`;
    }
}

async function loadAdminModules() {
    const el = document.getElementById("admin-modules");
    try {
        const data = await api("/api/admin/modules");
        if (!data.modules || !data.modules.length) {
            el.innerHTML = '<p class="empty-state">Nenhum modulo cadastrado.</p>';
            return;
        }
        const rows = data.modules.map(m => {
            const onlineDot = m.online
                ? '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#27ae60"></span>'
                : '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#555"></span>';
            const owner = m.user_email
                ? `${escapeHtml(m.user_name||'—')} <span style="color:var(--text-dim);font-size:0.7rem">${escapeHtml(m.user_email)}</span>`
                : '<span style="color:var(--text-dim)">nao pareado</span>';
            const safeEmail = escapeAttr(m.user_email || '');
            const safeChip = escapeAttr(m.chip_id);
            const safeName = escapeAttr(m.name || m.chip_id);
            // v4.1.28: normaliza legado ctrl -> hidro na coluna Tipo (safety net
            // ate todos os ESP32 + PWAs cacheados estarem em >= v4.1.28).
            const displayType = m.type === 'ctrl' ? 'hidro' : m.type;
            // v4.1.21: botao Transferir + v4.1.27: botao Firmware + v4.1.31: botao Historico
            const transferBtn = `<button onclick="transferModule('${safeChip}', '${safeEmail}')" style="background:transparent;border:1px solid var(--border);color:var(--primary);padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem;font-weight:600">Transferir</button>`;
            const firmwareBtn = `<button onclick="showFirmwareModal('${safeChip}', '${safeName}', '${escapeAttr(m.type||'')}')" style="background:transparent;border:1px solid var(--border);color:#3498db;padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem;font-weight:600">Firmware</button>`;
            const historyBtn = `<button onclick="showUptimeModal('${safeChip}', '${safeName}', true)" style="background:transparent;border:1px solid var(--border);color:#9b59b6;padding:3px 8px;border-radius:6px;cursor:pointer;font-size:0.7rem;font-weight:600">Historico</button>`;
            const actionBtns = `${historyBtn} ${firmwareBtn} ${transferBtn}`;
            // v4.1.31: span que carrega uptime 7d async
            const uptimeSpanId = `admin-uptime-${m.chip_id}`;
            setTimeout(() => loadInlineUptime(m.chip_id, uptimeSpanId, true), 50);
            return `<tr>
                <td style="padding:6px 4px;text-align:center">${onlineDot}</td>
                <td style="padding:6px 4px;font-family:monospace;font-size:0.7rem">${escapeHtml(m.chip_id)}</td>
                <td style="padding:6px 4px">${escapeHtml(displayType)}</td>
                <td style="padding:6px 4px">${escapeHtml(m.name||'—')}</td>
                <td style="padding:6px 4px">${owner}</td>
                <td style="padding:6px 4px;font-size:0.7rem;color:var(--text-dim)">${escapeHtml(m.ip||'—')}</td>
                <td style="padding:6px 4px;text-align:center;font-size:0.72rem"><span id="${uptimeSpanId}"><i style="color:var(--text-dim)">...</i></span></td>
                <td style="padding:6px 4px;text-align:center;white-space:nowrap">${actionBtns}</td>
            </tr>`;
        }).join("");
        el.innerHTML = `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:0.8rem">
            <thead><tr style="border-bottom:1px solid var(--border);color:var(--text-dim);text-align:left">
                <th style="padding:6px 4px;text-align:center">•</th>
                <th style="padding:6px 4px">Chip ID</th>
                <th style="padding:6px 4px">Tipo</th>
                <th style="padding:6px 4px">Nome</th>
                <th style="padding:6px 4px">Dono</th>
                <th style="padding:6px 4px">IP</th>
                <th style="padding:6px 4px;text-align:center">Uptime 7d</th>
                <th style="padding:6px 4px;text-align:center">Acao</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
    } catch (e) {
        el.innerHTML = `<p style="color:#e74c3c;font-size:0.8rem">Erro: ${e.message}</p>`;
    }
}

// Polling
setInterval(() => { if (token) loadModules(); }, 5000);
setInterval(() => {
    if (!token || !modules.length) return;
    const selected = getSelectedChips();
    for (const m of modules) {
        if (!selected.includes(m.chip_id)) continue;
        if (!(hasCap(m, 'hidro') || hasCap(m, 'hidro-farm'))) continue;
        if (!m.online) continue;
        // Cooldown PER-CHIP: so pula o polling desse chip se ELE teve toggle recente.
        // Antes era global — toggle no farm bloqueava polling do hidro por 35s inteiros.
        if (Date.now() - (lastToggleTimes[m.chip_id] || 0) < TOGGLE_COOLDOWN) continue;
        loadCtrlStatus(m.chip_id, m.type);
    }
}, 3000);

// =====================================================================
// PWA
// =====================================================================

let deferredPrompt = null;

if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
        .then(reg => {
            setInterval(() => reg.update(), 30 * 60 * 1000);
            reg.addEventListener('updatefound', () => {
                const nw = reg.installing;
                nw.addEventListener('statechange', () => {
                    if (nw.state === 'installed' && navigator.serviceWorker.controller) showUpdateBanner();
                });
            });
        }).catch(() => {});
    navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data.type === 'APP_UPDATED') showUpdateBanner(event.data.version);
    });
}

// =====================================================================
// Push Notifications — permissao + subscribe
// =====================================================================

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}

async function setupPushNotifications() {
    const vapidKey = C.vapidPublicKey;
    if (!vapidKey || !('Notification' in window) || !('PushManager' in window)) return;
    if (!('serviceWorker' in navigator)) return;
    if (Notification.permission === 'denied') return;

    // Se ja tem permissao, re-subscribe silenciosamente (garante subscription valida)
    if (Notification.permission === 'granted') {
        await _subscribePush(vapidKey);
        return;
    }

    // Primeira vez: pede permissao
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
        await _subscribePush(vapidKey);
    }
}

async function _subscribePush(vapidKey) {
    try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidKey)
        });
        await api('/api/push/subscribe', {
            method: 'POST',
            body: { subscription: sub.toJSON() }
        });
    } catch (e) {
        console.error('Push subscribe error:', e);
    }
}

async function saveAlertThreshold(chipId, moduleType, value) {
    const min = Math.max(1, Math.min(120, parseInt(value) || 10));
    try {
        await api(`${apiFor(moduleType)}/${chipId}/save-config`, {
            method: 'POST',
            body: { alert_threshold_min: min }
        });
    } catch (e) { console.error('Erro ao salvar threshold:', e); }
}

// =====================================================================
// v4.1.43 — Helper consolidado de Notificacoes (per-modulo + globais + historico)
// =====================================================================
// Tudo num unico card no dashboard de cada modulo, organizado em 3 sections:
//   1. ESTE MODULO  (per-modulo): toggle offline + threshold (v4.1.39)
//   2. GLOBAIS      (per-user): silent_hours + canais por tipo (afeta TODOS os modulos)
//   3. HISTORICO    (per-user): timeline de alertas com ack inline (collapsed por default)
//
// Helper REUSAVEL — pode ser movido pra outro lugar (perfil, header, pagina dedicada)
// trocando o caller. Mantem o nome `renderNotificationCard` pra back-compat.
//
// IDs sao sufixados por chipId pra permitir N cards na tela sem colisao.
// =====================================================================

function renderNotificationCard(chipId, ctrlData) {
    const cd = ctrlData || {};
    const enabled = cd.offline_alert_enabled !== false;
    const threshold = parseInt(cd.offline_alert_threshold_min) || 15;
    const safeChip = escapeAttr(chipId);
    const sufx = chipId.replace(/[^a-zA-Z0-9]/g, '');  // sufixo seguro pra IDs

    // v4.1.50: anti-flash. loadCtrlStatus polla a cada ~5s e o key inclui
    // temperature/humidity (DHT11) — entao renderDashboard reescreve o
    // container.innerHTML (e o card de notificacoes junto) toda vez que a temp
    // varia. Antes, isso destruia o catalog ja carregado, mostrava placeholder
    // por 50ms ate o setTimeout repintar do cache. Agora: se cache valido,
    // renderiza HTML completo direto. Sem cache, mantem placeholder + carrega.
    const cacheValid = _notifCardCache.catalog && (Date.now() - _notifCardCache.ts) < 60000;
    let catalogHtml, silentHtml, historyHtml;
    if (cacheValid) {
        catalogHtml = _buildCatalogHtml(_notifCardCache.catalog.catalog || []);
        silentHtml = _buildSilentHtml(_notifCardCache.catalog.silent_hours || {}, sufx);
        historyHtml = _buildHistoryHtml(_notifCardCache.history.alerts || [], _notifCardCache.catalog.catalog || []);
    } else {
        catalogHtml = `<div class="empty-state"><p style="font-size:0.75rem">Carregando tipos...</p></div>`;
        silentHtml = `<div class="empty-state"><p style="font-size:0.75rem">Carregando silencio...</p></div>`;
        historyHtml = `<div class="empty-state"><p style="font-size:0.75rem">Carregando historico...</p></div>`;
        // Dispara fetch async pra preencher cache (so a 1a vez ou apos TTL expirar)
        setTimeout(() => loadCardNotifications(chipId, sufx), 50);
    }

    return `<div class="card" style="padding:14px">
        <h2 style="margin:0 0 10px;font-size:0.95rem;display:flex;align-items:center;gap:6px">
            <span>${enabled ? '&#128276;' : '&#128277;'}</span>
            <span>Notificacoes</span>
        </h2>

        <!-- SECTION 1: ESTE MODULO -->
        <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-dim);margin:6px 0 4px">Este modulo</div>
        <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed var(--border)">
            <span style="font-size:0.82rem">Alertar quando offline</span>
            <span class="notify-switch ${enabled ? 'on' : ''}" onclick="toggleOfflineAlert('${safeChip}',this)">
                <span class="notify-slider"></span>
            </span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;font-size:0.82rem">
            <label style="display:flex;align-items:center;gap:6px;color:var(--text-dim)">
                <span>&#9201; Alertar apos</span>
                <input type="number" min="1" max="1440" value="${threshold}"
                    style="width:70px;padding:4px 6px;border-radius:4px;border:1px solid var(--border);background:var(--bg);color:var(--text);text-align:center"
                    onchange="saveOfflineThreshold('${safeChip}',this.value)">
                <span>min</span>
            </label>
        </div>

        <!-- SECTION 2: TIPOS GLOBAIS (canais por tipo de alerta) -->
        <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-dim);margin:14px 0 4px">
            Tipos de alerta <span style="text-transform:none;font-weight:normal;color:var(--text-dim);font-size:0.65rem">(globais — afeta todos os modulos)</span>
        </div>
        <div id="card-catalog-${sufx}" style="font-size:0.78rem">${catalogHtml}</div>

        <!-- SECTION 3: HISTORICO (collapsed por default) -->
        <details style="margin-top:14px">
            <summary style="cursor:pointer;font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-dim);padding:4px 0">
                Historico (30 dias)
            </summary>
            <div id="card-history-${sufx}" style="margin-top:8px;font-size:0.75rem">${historyHtml}</div>
        </details>

        <!-- SECTION 4: JANELA DE SILENCIO (no fim, com explicacao) -->
        <details style="margin-top:14px">
            <summary style="cursor:pointer;font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-dim);padding:4px 0">
                &#128564; Janela de silencio
            </summary>
            <div style="margin-top:8px;font-size:0.72rem;color:var(--text-dim);line-height:1.5;padding:0 4px 8px">
                Pausa as notificacoes em uma faixa de horario, util quando voce sabe que <b>nao podera reagir agora</b> ou esta <b>fazendo manutencao</b>:
                <ul style="margin:6px 0 6px 18px;padding:0">
                    <li>Madrugada (alerta P1 pode esperar a manha — voce vai tratar de manha mesmo)</li>
                    <li>Reuniao com cliente (celular tocando atrapalha)</li>
                    <li>Bench / teste (mexer nos modulos sem ser bombardeado)</li>
                    <li>Viagem / ferias curta (alguem mais cuida)</li>
                </ul>
                <div style="padding:6px 8px;background:rgba(231,76,60,0.08);border:1px solid rgba(231,76,60,0.25);border-radius:4px;margin-top:6px;color:var(--text)">
                    &#9888; <b>Alertas P0 (emergencia) sempre passam</b>, mesmo na janela de silencio. Isso garante que falhas criticas (vazamento, modulo offline >24h) nao sao perdidas.
                </div>
            </div>
            <div id="card-silent-${sufx}" style="padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:6px;margin-top:8px;font-size:0.78rem">${silentHtml}</div>
        </details>
    </div>`;
}

// Cache compartilhado entre todos os cards (TTL 60s — evita N requests por poll)
const _notifCardCache = { ts: 0, catalog: null, history: null };

async function loadCardNotifications(chipId, sufx) {
    // Carrega so se cache expirou ou e a primeira vez
    const now = Date.now();
    const cacheValid = _notifCardCache.catalog && (now - _notifCardCache.ts) < 60000;

    if (!cacheValid) {
        try {
            const [catalogResp, historyResp] = await Promise.all([
                api('/api/profile/alerts/catalog'),
                api('/api/profile/alerts/history?days=30'),
            ]);
            _notifCardCache.catalog = catalogResp;
            _notifCardCache.history = historyResp;
            _notifCardCache.ts = now;
        } catch (e) {
            console.warn('Erro ao carregar notificacoes:', e);
            // Mostra erro nos cards
            const errEl = document.getElementById(`card-catalog-${sufx}`);
            if (errEl) errEl.innerHTML = `<p style="color:#e74c3c;font-size:0.75rem">Erro: ${escapeHtml(e.message)}</p>`;
            return;
        }
    }

    _renderCardSilentHours(sufx, _notifCardCache.catalog.silent_hours || {});
    _renderCardCatalog(sufx, _notifCardCache.catalog.catalog || []);
    _renderCardHistory(sufx, _notifCardCache.history.alerts || [], _notifCardCache.catalog.catalog || []);
}

// v4.1.50: builders puros (retornam string) — usados tanto pelo
// renderNotificationCard (renderiza inline quando cache valido) quanto pelos
// _renderCardXxx (escrevem em el.innerHTML apos fetch). Evita duplicacao.
function _buildSilentHtml(sh, sufx) {
    const hasWindow = sh.start && sh.end;
    return `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-weight:600">&#128564; Janela de silencio</span>
            <span style="font-size:0.7rem;color:var(--text-dim)">${hasWindow ? `${sh.start} → ${sh.end}` : 'desativada'}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <input type="time" id="sh-start-${sufx}" value="${sh.start || ''}" style="padding:3px 6px;border-radius:4px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:0.75rem">
            <span style="font-size:0.7rem">→</span>
            <input type="time" id="sh-end-${sufx}" value="${sh.end || ''}" style="padding:3px 6px;border-radius:4px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:0.75rem">
            <button onclick="saveCardSilentHours('${sufx}')" style="padding:3px 10px;background:var(--primary);color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:0.7rem">Salvar</button>
            <button onclick="clearCardSilentHours('${sufx}')" style="padding:3px 10px;background:transparent;color:var(--text-dim);border:1px solid var(--border);border-radius:4px;cursor:pointer;font-size:0.7rem">Off</button>
        </div>`;
}

function _renderCardSilentHours(sufx, sh) {
    const el = document.getElementById(`card-silent-${sufx}`);
    if (!el) return;
    el.innerHTML = _buildSilentHtml(sh, sufx);
}

function _buildCatalogHtml(items) {
    // v4.1.45: header explicativo + texto completo nos toggles (eram "P"/"E"
    // — opaco demais, ninguem advinha sem ver o codigo). Agora "Push"/"Email"
    // com icones, e o header explica que sao canais de entrega do alerta.
    const header = `
        <div style="font-size:0.7rem;color:var(--text-dim);margin:0 2px 6px;line-height:1.4">
            Marque por onde quer <b>receber</b> cada tipo de alerta:
            <b>&#128241; Push</b> (notificacao no celular/browser) e/ou
            <b>&#9993; Email</b>. Desmarcar desliga o canal so pra esse tipo
            (cooldown e demais regras continuam valendo).
        </div>`;
    const rows = items.map(item => {
        const sev = item.severity_default;
        const safeType = escapeAttr(item.alert_type);
        // v4.1.49: removido flex-wrap (checkboxes nao caem mais pra linha de baixo);
        // align-items:flex-start pra badge/checkboxes ficarem na 1a linha quando o
        // label longo (P2 "Sensor com leitura invalida" etc.) wrap em 2 linhas;
        // overflow-wrap:anywhere garante quebra agressiva sem estourar o container.
        return `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:6px 8px;background:var(--bg);border:1px solid var(--border);border-radius:5px;margin-bottom:3px;font-size:0.72rem;gap:8px">
            <div style="display:flex;align-items:flex-start;gap:5px;min-width:0;flex:1 1 auto;line-height:1.35">
                ${_sevBadge(sev)}
                <span style="overflow-wrap:anywhere">${escapeHtml(item.name)}</span>
            </div>
            <div style="display:flex;gap:10px;flex-shrink:0;align-items:center;padding-top:1px">
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer" title="Push: notificacao no celular/browser via Service Worker">
                    <input type="checkbox" ${item.enabled_push ? 'checked' : ''} onchange="saveCardAlertPref('${safeType}','push',this.checked)">
                    <span>&#128241; Push</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer" title="Email: enviado pra seu notification_email (ou email de login se vazio)">
                    <input type="checkbox" ${item.enabled_email ? 'checked' : ''} onchange="saveCardAlertPref('${safeType}','email',this.checked)">
                    <span>&#9993; Email</span>
                </label>
            </div>
        </div>`;
    }).join('');
    return header + rows;
}

function _renderCardCatalog(sufx, items) {
    const el = document.getElementById(`card-catalog-${sufx}`);
    if (!el) return;
    el.innerHTML = _buildCatalogHtml(items);
}

function _buildHistoryHtml(alerts, catalog) {
    if (alerts.length === 0) {
        return `<p style="color:var(--text-dim);font-size:0.72rem;text-align:center;padding:10px">Sem alertas nos ultimos 30 dias.</p>`;
    }
    const nameMap = {};
    catalog.forEach(c => { nameMap[c.alert_type] = c.name; });
    return alerts.slice(0, 20).map(a => {
        const sev = a.severity || 'P1';
        const name = nameMap[a.alert_type] || a.alert_type;
        const when = formatRelativeShort(a.sent_at);
        const isAcked = !!a.ack_at;
        const ackHtml = isAcked
            ? `<span style="font-size:0.65rem;color:var(--text-dim)">&#10003;</span>`
            : `<button onclick="ackCardAlert(${a.id})" style="background:transparent;color:var(--primary);border:1px solid var(--border);border-radius:3px;padding:1px 6px;font-size:0.65rem;cursor:pointer">&#10003;</button>`;
        return `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 6px;background:var(--bg);border:1px solid var(--border);border-radius:4px;margin-bottom:2px;${isAcked ? 'opacity:0.55' : ''}">
            <div style="display:flex;align-items:center;gap:5px;min-width:0">
                ${_sevBadge(sev)}
                <div style="min-width:0">
                    <div style="font-weight:600">${escapeHtml(name)}</div>
                    <div style="color:var(--text-dim);font-size:0.65rem">${escapeHtml(a.chip_id)} &middot; ${escapeHtml(when)}</div>
                </div>
            </div>
            ${ackHtml}
        </div>`;
    }).join('');
}

function _renderCardHistory(sufx, alerts, catalog) {
    const el = document.getElementById(`card-history-${sufx}`);
    if (!el) return;
    el.innerHTML = _buildHistoryHtml(alerts, catalog);
}

// --- Handlers (invalida cache + reload todos os cards visiveis) ---

function _invalidateAndReloadAll() {
    _notifCardCache.ts = 0;
    // Reload todos os cards visiveis
    document.querySelectorAll('[id^="card-catalog-"]').forEach(el => {
        const sufx = el.id.replace('card-catalog-', '');
        loadCardNotificationsBySufx(sufx);
    });
}

async function loadCardNotificationsBySufx(sufx) {
    // Helper pra reload sem precisar do chipId — usa o cache global
    const cards = document.querySelectorAll(`#card-catalog-${sufx}`);
    if (!cards.length) return;
    try {
        const [catalogResp, historyResp] = await Promise.all([
            api('/api/profile/alerts/catalog'),
            api('/api/profile/alerts/history?days=30'),
        ]);
        _notifCardCache.catalog = catalogResp;
        _notifCardCache.history = historyResp;
        _notifCardCache.ts = Date.now();
        _renderCardSilentHours(sufx, catalogResp.silent_hours || {});
        _renderCardCatalog(sufx, catalogResp.catalog || []);
        _renderCardHistory(sufx, historyResp.alerts || [], catalogResp.catalog || []);
    } catch (e) {
        console.warn('reload card:', e);
    }
}

async function saveCardSilentHours(sufx) {
    const start = document.getElementById(`sh-start-${sufx}`).value;
    const end = document.getElementById(`sh-end-${sufx}`).value;
    if (!start || !end) { alert('Preencha ambas as horas, ou clique em Off'); return; }
    try {
        await api('/api/profile/alert-silent-hours', { method: 'PUT', body: { start, end } });
        _invalidateAndReloadAll();
    } catch (e) { alert('Erro: ' + e.message); }
}

async function clearCardSilentHours(sufx) {
    try {
        await api('/api/profile/alert-silent-hours', { method: 'PUT', body: { start: '', end: '' } });
        _invalidateAndReloadAll();
    } catch (e) { alert('Erro: ' + e.message); }
}

async function saveCardAlertPref(alertType, channel, enabled) {
    try {
        const body = {};
        if (channel === 'push') body.enabled_push = enabled;
        if (channel === 'email') body.enabled_email = enabled;
        await api(`/api/profile/alert-prefs/${encodeURIComponent(alertType)}`, { method: 'PUT', body });
        // v4.1.50: atualiza cache local pra proximas re-renderizacoes (a cada
        // poll do dashboard, ~5s) refletirem o novo estado. Antes, o cache
        // ficava com o valor antigo por ate 60s — o checkbox no DOM mantinha
        // o estado correto, mas se renderNotificationCard fosse chamado, o
        // template gerado vinha com `checked` baseado no cache antigo,
        // revertendo visualmente o toggle.
        if (_notifCardCache.catalog && Array.isArray(_notifCardCache.catalog.catalog)) {
            const item = _notifCardCache.catalog.catalog.find(i => i.alert_type === alertType);
            if (item) {
                if (channel === 'push') item.enabled_push = enabled;
                else if (channel === 'email') item.enabled_email = enabled;
            }
        }
    } catch (e) {
        console.error('Erro ao salvar pref:', e);
        _invalidateAndReloadAll();  // recarrega pra reverter UI
    }
}

async function ackCardAlert(alertId) {
    try {
        await api(`/api/profile/alerts/${alertId}/ack`, { method: 'POST' });
        _invalidateAndReloadAll();  // re-renderiza todos os cards (alerta vira ackd em todos)
    } catch (e) { alert('Erro ao marcar: ' + e.message); }
}

async function toggleOfflineAlert(chipId, el) {
    const willEnable = !el.classList.contains('on');
    // Atualizacao otimista da UI
    el.classList.toggle('on', willEnable);
    const icon = el.closest('.card')?.querySelector('h2 span:first-child');
    if (icon) icon.innerHTML = willEnable ? '&#128276;' : '&#128277;';
    try {
        await api(`/api/modules/${encodeURIComponent(chipId)}/notification-prefs`, {
            method: 'POST',
            body: { offline_alert_enabled: willEnable }
        });
    } catch (e) {
        console.error('Erro ao salvar pref offline:', e);
        // Reverte UI em caso de erro
        el.classList.toggle('on', !willEnable);
        if (icon) icon.innerHTML = !willEnable ? '&#128276;' : '&#128277;';
    }
}

async function saveOfflineThreshold(chipId, value) {
    const min = Math.max(1, Math.min(1440, parseInt(value) || 15));
    try {
        await api(`/api/modules/${encodeURIComponent(chipId)}/notification-prefs`, {
            method: 'POST',
            body: { offline_alert_threshold_min: min }
        });
    } catch (e) { console.error('Erro ao salvar threshold offline:', e); }
}

async function togglePushNotifications(el) {
    if (Notification.permission === 'denied') {
        alert('Notificacoes estao bloqueadas pelo navegador.\n\nPara ativar:\n1. Clique no cadeado/icone ao lado da URL\n2. Em "Notificacoes", selecione "Permitir"\n3. Recarregue a pagina');
        return;
    }
    if (Notification.permission === 'granted') {
        // Desativar
        await unsubscribePush();
        el.classList.remove('on');
        const icon = el.parentElement.querySelector('.notify-icon');
        if (icon) icon.innerHTML = '&#128277;';
    } else {
        // Ativar — pede permissao
        const perm = await Notification.requestPermission();
        if (perm === 'granted') {
            await _subscribePush(C.vapidPublicKey);
            el.classList.add('on');
            const icon = el.parentElement.querySelector('.notify-icon');
            if (icon) icon.innerHTML = '&#128276;';
        }
    }
}

async function unsubscribePush() {
    try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
            await api('/api/push/unsubscribe', {
                method: 'POST',
                body: { endpoint: sub.endpoint }
            });
            await sub.unsubscribe();
        }
    } catch (e) {
        console.error('Push unsubscribe error:', e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const footer = document.getElementById('app-footer');
    if (footer) footer.textContent = `${PRODUCT_NAME} v${APP_VERSION}`;
});

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault(); deferredPrompt = e;
    const d = localStorage.getItem('pwa_dismissed');
    if (d && Date.now() - parseInt(d) < 7 * 24 * 60 * 60 * 1000) return;
    showPwaBanner();
});

window.addEventListener('appinstalled', () => { hidePwaBanner(); deferredPrompt = null; });
function showPwaBanner() { const b = document.getElementById('pwa-banner'); if (b) b.classList.remove('hidden'); }
function hidePwaBanner() { const b = document.getElementById('pwa-banner'); if (b) b.classList.add('hidden'); }

function pwaInstall() {
    if (!deferredPrompt) {
        alert(/iPhone|iPad|iPod/.test(navigator.userAgent)
            ? 'Para instalar:\n1. Toque em compartilhar\n2. Adicionar a Tela de Inicio'
            : 'Para instalar:\n1. Menu do navegador (3 pontos)\n2. Instalar aplicativo');
        return;
    }
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => { deferredPrompt = null; hidePwaBanner(); });
}
function pwaDismiss() { hidePwaBanner(); localStorage.setItem('pwa_dismissed', Date.now().toString()); }

function showUpdateBanner(v) {
    let b = document.getElementById('update-banner'); if (b) b.remove();
    b = document.createElement('div'); b.id = 'update-banner'; b.className = 'update-banner';
    b.innerHTML = `<div class="update-banner-inner"><div class="update-banner-info"><strong>Nova versao${v ? ' v'+v : ''}</strong></div><div class="update-banner-actions"><button class="pwa-btn-install" onclick="doAppUpdate()">Atualizar</button><button class="pwa-btn-dismiss" onclick="dismissUpdate()">Depois</button></div></div>`;
    document.body.appendChild(b);
}
function doAppUpdate() {
    navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload());
    navigator.serviceWorker.ready.then(reg => { if (reg.waiting) reg.waiting.postMessage('SKIP_WAITING'); else caches.keys().then(k => Promise.all(k.map(c => caches.delete(c))).then(() => location.reload())); });
    setTimeout(() => caches.keys().then(k => Promise.all(k.map(c => caches.delete(c))).then(() => location.reload())), 3000);
}
function dismissUpdate() { const b = document.getElementById('update-banner'); if (b) b.remove(); }
document.addEventListener("keydown", e => { if (e.key === "Escape") closePairModal(); });

// =====================================================================
// v4.1.41 — Notificacoes (catalogo + historico + prefs + silent hours)
// =====================================================================

const SEV_META = {
    P0: { color: '#e74c3c', label: 'P0', icon: '&#128293;' },  // emergencia
    P1: { color: '#e67e22', label: 'P1', icon: '&#9888;' },     // alta
    P2: { color: '#f1c40f', label: 'P2', icon: '&#9888;' },     // media
    P3: { color: '#3498db', label: 'P3', icon: '&#8505;' },     // info
};

function _sevBadge(sev) {
    const m = SEV_META[sev] || SEV_META.P2;
    return `<span style="display:inline-block;padding:2px 6px;border-radius:4px;background:${m.color}22;color:${m.color};font-size:0.65rem;font-weight:700;letter-spacing:0.04em">${m.label}</span>`;
}

function _formatCooldown(sec) {
    if (sec < 3600) return `${Math.round(sec/60)}min`;
    const h = Math.round(sec/3600);
    if (h < 24) return `${h}h`;
    return `${Math.round(h/24)}d`;
}

// v4.1.43: removidas as funcoes loadAlertCatalog/loadAlertsHistory/saveAlertPref/
// saveSilentHours/clearSilentHours/ackAlert — eram da v4.1.41 (perfil), agora
// substituidas pelos handlers do card consolidado: loadCardNotifications +
// _renderCardSilentHours/_renderCardCatalog/_renderCardHistory + saveCardSilentHours/
// clearCardSilentHours/saveCardAlertPref/ackCardAlert (definidos perto de
// renderNotificationCard).
