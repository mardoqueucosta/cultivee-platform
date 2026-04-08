// =====================================================================
// Cultivee PWA v3.0 — Registry Pattern + Lista de Modulos
// Config injetada pelo servidor via window.CULTIVEE
// =====================================================================

const APP_VERSION = '3.0.0';
const C = window.CULTIVEE || {};
const STORAGE_PREFIX = C.storagePrefix || 'cultivee';
const PRODUCT_NAME = C.productName || 'Cultivee';
const DEFAULT_NAME = C.defaultName || 'Dispositivo';

// Migracao de token: prefix antigo → novo (1x)
if (!localStorage.getItem(`${STORAGE_PREFIX}_token`)) {
    for (const old of ['cultivee_ctrl', 'cultivee_hidro_cam', 'cultivee_cam']) {
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

// API prefix por tipo de modulo
function apiFor(moduleType) {
    return `/api/${moduleType}`;
}

// =====================================================================
// Module Registry — cada capability registra seu renderer
// =====================================================================

const moduleRenderers = {
    hidro: {
        label: 'Controle',
        renderContent: renderModule_hidro,
        getStatusText: (data) => {
            if (!data) return '';
            const l = data.light ? 'Luz ON' : 'Luz OFF';
            const p = data.pump ? 'Bomba ON' : 'Bomba OFF';
            return `${l} · ${p}`;
        }
    },
    cam: {
        label: 'Camera',
        renderContent: renderModule_cam,
        getStatusText: (data) => data && data.camera_ready ? 'Pronta' : 'Offline'
    }
};

// =====================================================================
// Module Prefs (selecao + ordem — localStorage)
// =====================================================================

function loadModulePrefs() {
    try {
        return JSON.parse(localStorage.getItem(`${STORAGE_PREFIX}_module_prefs`) || '{}');
    } catch (e) { return {}; }
}

function saveModulePrefs(prefs) {
    localStorage.setItem(`${STORAGE_PREFIX}_module_prefs`, JSON.stringify(prefs));
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

function showLogin() {
    document.getElementById("auth-login").classList.remove("hidden");
    document.getElementById("auth-register").classList.add("hidden");
    document.getElementById("auth-error").classList.add("hidden");
}

function showRegister() {
    document.getElementById("auth-login").classList.add("hidden");
    document.getElementById("auth-register").classList.remove("hidden");
    document.getElementById("auth-error").classList.add("hidden");
}

function togglePass(inputId, el) {
    const input = document.getElementById(inputId);
    if (input.type === "password") { input.type = "text"; el.textContent = "ocultar"; }
    else { input.type = "password"; el.textContent = "mostrar"; }
}

function showAuthError(msg) {
    const el = document.getElementById("auth-error");
    el.textContent = msg;
    el.classList.remove("hidden");
}

async function doLogin() {
    try {
        const data = await api("/api/auth/login", {
            method: "POST",
            body: { email: document.getElementById("login-email").value, password: document.getElementById("login-pass").value }
        });
        token = data.token; user = data.user;
        localStorage.setItem(`${STORAGE_PREFIX}_token`, token);
        localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
        enterApp();
    } catch (e) { showAuthError(e.message); }
}

async function doRegister() {
    try {
        const data = await api("/api/auth/register", {
            method: "POST",
            body: { name: document.getElementById("reg-name").value, email: document.getElementById("reg-email").value, password: document.getElementById("reg-pass").value }
        });
        token = data.token; user = data.user;
        localStorage.setItem(`${STORAGE_PREFIX}_token`, token);
        localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
        enterApp();
    } catch (e) { showAuthError(e.message); }
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

function enterApp() {
    document.getElementById("auth-screen").classList.add("hidden");
    document.getElementById("app-screen").classList.remove("hidden");
    document.getElementById("nav-user").textContent = user.name;
    loadModules();
    setTimeout(checkPendingCode, 500);
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

function hasCap(mod, cap) {
    return (mod.capabilities || []).includes(cap);
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

let _lastModulesKey = "";

function modulesVisualKey() {
    return modules.map(m => {
        const c = m.ctrl_data || {};
        return `${m.chip_id}:${m.online}:${m.name}:${c.light}:${c.pump}:${c.mode}:${c.phase}:${c.camera_ready}`;
    }).join("|");
}

function forceFullRefresh() {
    _lastModulesKey = "";
    _lastCtrlKey = "";
    loadModules();
}

async function loadModules() {
    try {
        const data = await api("/api/modules");
        modules = data.modules;
        const key = modulesVisualKey();
        if (key === _lastModulesKey) return;
        _lastModulesKey = key;

        // Sincroniza prefs com modulos existentes
        const prefs = loadModulePrefs();
        if (!prefs.order || prefs.order.length === 0) {
            prefs.order = modules.map(m => m.chip_id);
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
        const rawName = m.name && m.name !== DEFAULT_NAME ? m.name : '';
        const name = rawName || getModuleLabel(m) || m.type || 'Modulo';
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
                <span class="mod-name">${name}</span>
                <span class="mod-status">${statusText}</span>
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
        return;
    }

    let html = '';
    for (const mod of selectedOrdered) {
        const caps = mod.capabilities || [];
        let hasRenderer = false;
        for (const cap of caps) {
            if (moduleRenderers[cap]) {
                hasRenderer = true;
                // Cria div container por modulo/capability
                html += `<div id="mod-content-${mod.chip_id}-${cap}"></div>`;
            }
        }
        if (!hasRenderer) {
            html += `<div class="card"><div class="empty-state"><p>Modulo sem interface configurada</p><p style="font-size:0.8rem;color:var(--text-dim)">Capabilities: ${caps.join(', ') || 'nenhuma'}</p></div></div>`;
        }
    }
    container.innerHTML = html;

    // Agora chama os renderers para preencher cada container
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
let localState = null;
let lastToggleTime = 0;
const TOGGLE_COOLDOWN = 35000;
let pendingCommands = new Set();

function renderModule_hidro(container, mod) {
    if (!mod.online) {
        container.innerHTML = `<div class="card"><div class="empty-state"><p>Controle offline</p></div></div>`;
        return;
    }
    // Carrega status e renderiza dashboard
    loadCtrlStatus(mod.chip_id, mod.type, container);
}

async function loadCtrlStatus(chipId, moduleType, container) {
    const ct = container || document.querySelector(`[id^="mod-content-${chipId}-hidro"]`);
    if (!ct) return;
    try {
        const data = await api(`${apiFor(moduleType)}/${chipId}/status`);
        if (localState && (Date.now() - lastToggleTime < TOGGLE_COOLDOWN)) {
            data.light = localState.light;
            data.pump = localState.pump;
            data.mode = localState.mode;
        }
        const key = `${data.light}:${data.pump}:${data.mode}:${data.phase}:${data.phase_index}:${data.cycle_day}:${data.start_date}`;
        if (key === _lastCtrlKey && !container) return;
        _lastCtrlKey = key;
        renderDashboard(ct, chipId, moduleType, data);
    } catch (e) {
        ct.innerHTML = '<div class="card"><div class="empty-state"><p>Erro ao carregar status</p></div></div>';
    }
}

function renderDashboard(container, chipId, moduleType, data) {
    localState = { ...data };
    const cycleDay = data.cycle_day || 0;
    const phase = data.phase || "---";
    const phaseIndex = data.phase_index || 0;
    const lightOn = data.light || false;
    const pumpOn = data.pump || false;
    const modeAuto = data.mode === "auto";
    const startDateRaw = data.start_date || "---";
    let startDate = startDateRaw;
    if (startDateRaw && startDateRaw.includes("-")) {
        const [y, m, d] = startDateRaw.split("-");
        startDate = `${d}/${m}/${y}`;
    }

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
                <div class="phase-item-header"><span class="phase-item-name">${p.name} ${isActive ? '<span class="phase-badge">ATIVA</span>' : ''}</span>${diasInfo}</div>
                ${progressBar}
                <div class="phase-item-details">&#128161; ${lOn} - ${lOff}<br>&#128167; Dia: ${p.pumpOnDay}/${p.pumpOffDay}min | Noite: ${p.pumpOnNight}/${p.pumpOffNight}min</div>
            </div>`;
        }).join("");
    }

    const lightPending = pendingCommands.has('light');
    const pumpPending = pendingCommands.has('pump');
    const modePending = pendingCommands.has('mode');

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
        </div>`;
    }

    const now = new Date();
    const dateStr = `${String(now.getDate()).padStart(2,'0')}/${String(now.getMonth()+1).padStart(2,'0')}/${now.getFullYear()}`;

    container.innerHTML = `
        <div class="card">
            <div class="stats-grid">
                <div class="stat-card"><div class="label">Ciclo</div><div class="value">Dia ${cycleDay}</div></div>
                <div class="stat-card"><div class="label">Fase</div><div class="value small">${phase}</div></div>
                <div class="stat-card"><div class="label">Inicio</div><div class="value small">${startDate}</div></div>
                <div class="stat-card"><div class="label">Hoje</div><div class="value small">${dateStr}</div></div>
            </div>
            <div class="status-indicators">
                <div class="status-indicator ${lightOn ? 'status-on' : 'status-off'}"><span class="status-indicator-dot"></span><span>Luz ${lightOn ? 'Ligada' : 'Desligada'}</span></div>
                <div class="status-indicator ${pumpOn ? 'status-on pump' : 'status-off'}"><span class="status-indicator-dot"></span><span>Bomba ${pumpOn ? 'Ligada' : 'Desligada'}</span></div>
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
        </div>` : ''}`;
}

async function toggleRelay(chipId, moduleType, device) {
    if (localState) {
        if (device === "light") localState.light = !localState.light;
        else if (device === "pump") localState.pump = !localState.pump;
        else if (device === "mode") localState.mode = localState.mode === "auto" ? "manual" : "auto";
        lastToggleTime = Date.now();
        pendingCommands.add(device);
        const ct = document.querySelector(`[id^="mod-content-${chipId}-hidro"]`);
        if (ct) renderDashboard(ct, chipId, moduleType, localState);
    }
    try {
        await api(`${apiFor(moduleType)}/${chipId}/relay?device=${device}&action=toggle`);
    } catch (e) { console.error("Erro relay:", e); }

    let confirmed = false;
    for (let i = 0; i < 10; i++) {
        await new Promise(r => setTimeout(r, 1500));
        try {
            const data = await api(`${apiFor(moduleType)}/${chipId}/status`);
            if (device === "light" && data.light === localState.light) { confirmed = true; break; }
            if (device === "pump" && data.pump === localState.pump) { confirmed = true; break; }
            if (device === "mode" && data.mode === localState.mode) { confirmed = true; break; }
        } catch (e) { break; }
    }
    pendingCommands.delete(device);
    _lastCtrlKey = "";
    const ct = document.querySelector(`[id^="mod-content-${chipId}-hidro"]`);
    if (confirmed && ct) renderDashboard(ct, chipId, moduleType, localState);
    else loadCtrlStatus(chipId, moduleType);
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
        return `<div class="config-phase">
            <div class="config-phase-header"><span class="config-phase-title">Fase ${i+1}</span>${phases.length > 1 ? `<button class="config-remove" onclick="removePhase(${i})">&#10005;</button>` : ''}</div>
            <div class="config-grid">
                <div class="config-field"><label>Nome</label><input type="text" id="cfg-n${i}" value="${p.name||`Fase ${i+1}`}"></div>
                <div class="config-field"><label>Dias</label><input type="number" id="cfg-d${i}" value="${p.days!=null?p.days:7}" min="0"></div>
            </div>
            <div class="config-section-label">&#128161; Iluminacao</div>
            <div class="config-grid">
                <div class="config-field"><label>Liga</label><input type="time" id="cfg-lon${i}" value="${lOn}"></div>
                <div class="config-field"><label>Desliga</label><input type="time" id="cfg-loff${i}" value="${lOff}"></div>
            </div>
            <div class="config-section-label">&#128167; Irrigacao Dia</div>
            <div class="config-grid">
                <div class="config-field"><label>ON (min)</label><input type="number" id="cfg-pod${i}" value="${p.pumpOnDay||15}" min="1"></div>
                <div class="config-field"><label>OFF (min)</label><input type="number" id="cfg-pfd${i}" value="${p.pumpOffDay||15}" min="1"></div>
            </div>
            <div class="config-section-label">&#127769; Irrigacao Noite</div>
            <div class="config-grid">
                <div class="config-field"><label>ON (min)</label><input type="number" id="cfg-pon${i}" value="${p.pumpOnNight||15}" min="1"></div>
                <div class="config-field"><label>OFF (min)</label><input type="number" id="cfg-pfn${i}" value="${p.pumpOffNight||45}" min="1"></div>
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
    });
    try {
        await api(`${apiFor(configModuleType)}/${configChipId}/save-config`, { method: "POST", body: data });
        closeConfigModal();
        lastToggleTime = Date.now();
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
    const camReady = mod.online && mod.ctrl_data && mod.ctrl_data.camera_ready;
    const statusColor = camReady ? '#27ae60' : '#e74c3c';
    const statusText = camReady ? 'Pronta' : 'Offline';
    const btnDisabled = !camReady || cam_pending;
    const liveActive = cam_liveOn && cam_liveChipId === chipId;
    const chevronSvg = (id, open) => `<svg id="${id}" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2" style="transition:transform 0.25s;${open ? 'transform:rotate(180deg)' : ''}"><polyline points="6 9 12 15 18 9"/></svg>`;

    container.innerHTML = `
        <div class="card" style="padding:0;overflow:hidden">
            <!-- Header Camera -->
            <div style="display:flex;align-items:center;gap:8px;padding:14px">
                <span style="width:8px;height:8px;border-radius:50%;background:${statusColor}"></span>
                <b style="font-size:0.9rem">Camera</b>
                <span style="color:#888;font-size:0.8rem">${statusText}</span>
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
                    </div>
                </div>
            </div>
        </div>`;

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
                    if (img) img.innerHTML = `<img src="${cam_imageUrl}&token=${token}" style="width:100%;border-radius:8px" alt="Captura" />`;
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
            if (img) img.innerHTML = `<img src="${cam_imageUrl}&token=${token}" style="width:100%;border-radius:8px" alt="Captura" />`;
        }
    } catch (e) {}
}

// --- Captura Agendada ---

async function cam_toggleRecording(chipId, moduleType) {
    const newState = !cam_recording;
    try {
        await api(`${apiFor(moduleType)}/${chipId}/config`, {
            method: 'POST', body: { recording: newState }
        });
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

// Polling
setInterval(() => { if (token) loadModules(); }, 5000);
setInterval(() => {
    if (!token || !modules.length) return;
    if (Date.now() - lastToggleTime < TOGGLE_COOLDOWN) return;
    const selected = getSelectedChips();
    for (const m of modules) {
        if (selected.includes(m.chip_id) && hasCap(m, 'hidro') && m.online) {
            loadCtrlStatus(m.chip_id, m.type);
        }
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
