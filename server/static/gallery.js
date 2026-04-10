// =====================================================================
// Cultivee Gallery — Modal de pastas e imagens da camera
// Depende de: api() global (app.js), token global, apiFor() global
// =====================================================================

// --- State ---
let gal_chipId = null;
let gal_moduleType = null;
let gal_currentFolder = null;
let gal_currentPage = 1;
let gal_totalImages = 0;
let gal_totalPages = 1;
let gal_selectMode = false;
let gal_selected = new Set();
let gal_allImages = [];
let gal_loading = false;

const GAL_PER_PAGE = 20;

// =====================================================================
// Modal lifecycle
// =====================================================================

function openGallery(chipId, moduleType) {
    gal_chipId = chipId;
    gal_moduleType = moduleType;
    gal_currentFolder = null;
    gal_selectMode = false;
    gal_selected.clear();

    // Create modal if not present
    let modal = document.getElementById('gallery-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'gallery-modal';
        modal.className = 'modal hidden';
        modal.innerHTML = `
            <div class="modal-content gallery-content">
                <div class="gallery-header">
                    <button class="gallery-back hidden" onclick="galleryBack()">&#8592;</button>
                    <h3 id="gallery-title">Galeria</h3>
                    <button class="gallery-select hidden" onclick="toggleSelectMode()">&#9745; Selecionar</button>
                    <button class="modal-close" onclick="closeGallery()">&#10005;</button>
                </div>
                <div id="gallery-body"></div>
                <div id="gallery-actions" class="gallery-actions hidden"></div>
            </div>`;
        document.body.appendChild(modal);
    }

    modal.classList.remove('hidden');
    document.getElementById('gallery-title').textContent = 'Galeria';
    document.querySelector('.gallery-back').classList.add('hidden');
    document.querySelector('.gallery-select').classList.add('hidden');
    document.getElementById('gallery-actions').classList.add('hidden');

    loadFolders();
}

function closeGallery() {
    const modal = document.getElementById('gallery-modal');
    if (modal) modal.classList.add('hidden');
    gal_selectMode = false;
    gal_selected.clear();
    gal_currentFolder = null;
}

function galleryBack() {
    if (gal_currentFolder) {
        gal_currentFolder = null;
        gal_selectMode = false;
        gal_selected.clear();
        document.querySelector('.gallery-back').classList.add('hidden');
        document.querySelector('.gallery-select').classList.add('hidden');
        document.getElementById('gallery-actions').classList.add('hidden');
        document.getElementById('gallery-title').textContent = 'Galeria';
        loadFolders();
    }
}

// =====================================================================
// Folders
// =====================================================================

async function loadFolders() {
    const body = document.getElementById('gallery-body');
    if (!body) return;
    body.innerHTML = gal_spinner('Carregando pastas...');

    try {
        const data = await api(`/api/gallery/${gal_chipId}/folders`);
        renderFolders(data.folders || []);
    } catch (e) {
        body.innerHTML = gal_errorMsg('Erro ao carregar pastas');
    }
}

function renderFolders(folders) {
    const body = document.getElementById('gallery-body');
    if (!body) return;

    if (folders.length === 0) {
        body.innerHTML = gal_emptyMsg('Nenhuma pasta encontrada');
        return;
    }

    let html = '<div class="gal-folders">';
    for (const f of folders) {
        const displayName = f.name === '_sem-pasta' ? 'Capturas anteriores' : f.name;
        const sizeText = gal_formatSize(f.total_size || 0);
        const countText = (f.count || 0) + ' foto' + ((f.count || 0) !== 1 ? 's' : '');

        // Thumbnails row
        let thumbsHtml = '';
        if (f.thumbnails && f.thumbnails.length > 0) {
            thumbsHtml = '<div class="gal-folder-thumbs">';
            const thumbs = f.thumbnails.slice(0, 3);
            for (const t of thumbs) {
                const src = `/api/gallery/${gal_chipId}/folders/${encodeURIComponent(f.name)}/thumb/${encodeURIComponent(t)}?token=${token}`;
                thumbsHtml += `<div class="gal-folder-thumb"><img src="${src}" alt="" loading="lazy"></div>`;
            }
            thumbsHtml += '</div>';
        }

        html += `
            <div class="gal-folder-card" onclick="openFolder('${gal_escAttr(f.name)}')">
                <div class="gal-folder-info">
                    <div class="gal-folder-name">&#128193; ${gal_escHtml(displayName)}</div>
                    <div class="gal-folder-meta">${countText} &middot; ${sizeText}</div>
                </div>
                ${thumbsHtml}
            </div>`;
    }
    html += '</div>';
    body.innerHTML = html;
}

// =====================================================================
// Folder view (images)
// =====================================================================

function openFolder(folderName) {
    gal_currentFolder = folderName;
    gal_currentPage = 1;
    gal_selectMode = false;
    gal_selected.clear();
    gal_allImages = [];

    const displayName = folderName === '_sem-pasta' ? 'Capturas anteriores' : folderName;
    document.getElementById('gallery-title').textContent = displayName;
    document.querySelector('.gallery-back').classList.remove('hidden');
    document.querySelector('.gallery-select').classList.remove('hidden');
    document.getElementById('gallery-actions').classList.add('hidden');

    loadImages(folderName, 1);
}

async function loadImages(folderName, page) {
    const body = document.getElementById('gallery-body');
    if (!body) return;
    if (gal_loading) return;
    gal_loading = true;

    if (page === 1) {
        body.innerHTML = gal_spinner('Carregando imagens...');
    }

    try {
        const data = await api(`/api/gallery/${gal_chipId}/folders/${encodeURIComponent(folderName)}/images?page=${page}&per_page=${GAL_PER_PAGE}`);
        gal_currentPage = page;
        gal_totalImages = data.total || 0;
        gal_totalPages = data.pages || 1;
        renderImages(data, page === 1);
    } catch (e) {
        if (page === 1) {
            body.innerHTML = gal_errorMsg('Erro ao carregar imagens');
        }
    }
    gal_loading = false;
}

function renderImages(data, replace) {
    const body = document.getElementById('gallery-body');
    if (!body) return;

    const images = data.images || [];

    if (replace) {
        gal_allImages = images;
    } else {
        gal_allImages = gal_allImages.concat(images);
    }

    if (gal_allImages.length === 0) {
        body.innerHTML = gal_emptyMsg('Nenhuma imagem nesta pasta');
        return;
    }

    let html = '<div class="gal-grid">';
    for (const img of gal_allImages) {
        const thumbSrc = `/api/gallery/${gal_chipId}/folders/${encodeURIComponent(gal_currentFolder)}/thumb/${encodeURIComponent(img.filename)}?token=${token}`;
        const fullSrc = `/api/gallery/${gal_chipId}/folders/${encodeURIComponent(gal_currentFolder)}/image/${encodeURIComponent(img.filename)}?token=${token}`;
        const timeText = gal_formatTime(img.timestamp || img.filename);
        const sizeText = gal_formatSize(img.size || 0);
        const isSelected = gal_selected.has(img.filename);

        html += `
            <div class="gal-thumb ${isSelected ? 'gal-thumb-selected' : ''}" data-filename="${gal_escAttr(img.filename)}">
                ${gal_selectMode ? `<div class="gal-checkbox ${isSelected ? 'checked' : ''}" onclick="event.stopPropagation();gal_toggleImage('${gal_escAttr(img.filename)}')">
                    ${isSelected ? '&#10003;' : ''}
                </div>` : ''}
                <img src="${thumbSrc}" alt="" loading="lazy" onclick="${gal_selectMode
                    ? `gal_toggleImage('${gal_escAttr(img.filename)}')`
                    : `gal_openFull('${gal_escAttr(fullSrc)}')`
                }">
                <div class="gal-thumb-info">
                    <span>${timeText}</span>
                    <span>${sizeText}</span>
                </div>
            </div>`;
    }
    html += '</div>';

    // Load more button
    if (gal_currentPage < gal_totalPages) {
        html += `<button class="gal-load-more" onclick="loadImages('${gal_escAttr(gal_currentFolder)}', ${gal_currentPage + 1})">Carregar mais</button>`;
    }

    // Counter
    html = `<div class="gal-counter">${gal_allImages.length} de ${gal_totalImages} fotos</div>` + html;

    body.innerHTML = html;
}

function gal_openFull(url) {
    window.open(url, '_blank');
}

// =====================================================================
// Selection mode
// =====================================================================

function toggleSelectMode() {
    gal_selectMode = !gal_selectMode;
    gal_selected.clear();

    const selectBtn = document.querySelector('.gallery-select');
    if (selectBtn) {
        selectBtn.textContent = gal_selectMode ? 'Cancelar' : '\u2611 Selecionar';
    }

    if (gal_selectMode) {
        gal_renderActions();
        document.getElementById('gallery-actions').classList.remove('hidden');
    } else {
        document.getElementById('gallery-actions').classList.add('hidden');
    }

    // Re-render grid to show/hide checkboxes
    if (gal_currentFolder && gal_allImages.length > 0) {
        renderImages({ images: [], total: gal_totalImages, pages: gal_totalPages }, false);
        // renderImages with replace=false and empty images just re-renders existing gal_allImages
        // Actually we need to re-render the full list. Let's just call it properly:
        gal_rerender();
    }
}

function gal_rerender() {
    renderImages({ images: gal_allImages, total: gal_totalImages, pages: gal_totalPages }, true);
}

function gal_toggleImage(filename) {
    if (gal_selected.has(filename)) {
        gal_selected.delete(filename);
    } else {
        gal_selected.add(filename);
    }
    gal_rerender();
    gal_updateActions();
}

function gal_selectAll() {
    if (gal_selected.size === gal_allImages.length) {
        gal_selected.clear();
    } else {
        gal_selected.clear();
        for (const img of gal_allImages) {
            gal_selected.add(img.filename);
        }
    }
    gal_rerender();
    gal_updateActions();
}

function gal_renderActions() {
    const actions = document.getElementById('gallery-actions');
    if (!actions) return;

    actions.innerHTML = `
        <div class="gal-action-bar">
            <label class="gal-select-all" onclick="gal_selectAll()">
                <span class="gal-checkbox-small ${gal_selected.size === gal_allImages.length && gal_allImages.length > 0 ? 'checked' : ''}">
                    ${gal_selected.size === gal_allImages.length && gal_allImages.length > 0 ? '&#10003;' : ''}
                </span>
                <span>Selecionar tudo</span>
            </label>
            <div class="gal-action-btns">
                <button class="gal-btn-delete" onclick="deleteSelected()" ${gal_selected.size === 0 ? 'disabled' : ''}>
                    Excluir ${gal_selected.size > 0 ? gal_selected.size + ' selecionada' + (gal_selected.size !== 1 ? 's' : '') : ''}
                </button>
                <button class="gal-btn-delete-folder" onclick="deleteFolder()">
                    Excluir pasta inteira
                </button>
            </div>
        </div>`;
}

function gal_updateActions() {
    if (gal_selectMode) gal_renderActions();
}

// =====================================================================
// Deletions
// =====================================================================

async function deleteSelected() {
    if (gal_selected.size === 0) return;
    const n = gal_selected.size;
    const confirmed = confirm(`Excluir ${n} foto${n !== 1 ? 's' : ''}?`);
    if (!confirmed) return;

    try {
        await api(`/api/gallery/${gal_chipId}/folders/${encodeURIComponent(gal_currentFolder)}/images`, {
            method: 'DELETE',
            body: { filenames: Array.from(gal_selected) }
        });
        gal_selected.clear();
        gal_selectMode = false;
        document.querySelector('.gallery-select').textContent = '\u2611 Selecionar';
        document.getElementById('gallery-actions').classList.add('hidden');
        loadImages(gal_currentFolder, 1);
    } catch (e) {
        alert('Erro ao excluir: ' + (e.message || 'Tente novamente'));
    }
}

async function deleteFolder() {
    if (!gal_currentFolder) return;
    const displayName = gal_currentFolder === '_sem-pasta' ? 'Capturas anteriores' : gal_currentFolder;
    const confirmed = confirm(`Excluir pasta '${displayName}' com ${gal_totalImages} fotos? Esta a\u00e7\u00e3o \u00e9 irrevers\u00edvel.`);
    if (!confirmed) return;

    try {
        await api(`/api/gallery/${gal_chipId}/folders/${encodeURIComponent(gal_currentFolder)}`, {
            method: 'DELETE'
        });
        gal_selectMode = false;
        gal_selected.clear();
        document.querySelector('.gallery-select').classList.add('hidden');
        document.getElementById('gallery-actions').classList.add('hidden');
        gal_currentFolder = null;
        document.getElementById('gallery-title').textContent = 'Galeria';
        document.querySelector('.gallery-back').classList.add('hidden');
        loadFolders();
    } catch (e) {
        alert('Erro ao excluir pasta: ' + (e.message || 'Tente novamente'));
    }
}

// =====================================================================
// Helpers
// =====================================================================

function gal_formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function gal_formatTime(timestampOrFilename) {
    // Try parsing as timestamp number first
    const ts = Number(timestampOrFilename);
    if (!isNaN(ts) && ts > 1000000000) {
        const d = new Date(ts * 1000);
        return gal_pad(d.getHours()) + ':' + gal_pad(d.getMinutes()) + ' ' +
               gal_pad(d.getDate()) + '/' + gal_pad(d.getMonth() + 1);
    }
    // Try extracting from filename pattern (e.g., 20240115_143022.jpg)
    const m = String(timestampOrFilename).match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/);
    if (m) {
        return m[4] + ':' + m[5] + ' ' + m[3] + '/' + m[2];
    }
    return '';
}

function gal_pad(n) {
    return n < 10 ? '0' + n : '' + n;
}

function gal_escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function gal_escAttr(s) {
    return String(s).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function gal_spinner(text) {
    return `<div class="gal-status">
        <div class="gal-spinner"></div>
        <span>${text}</span>
    </div>`;
}

function gal_errorMsg(text) {
    return `<div class="gal-status gal-status-error"><span>${text}</span></div>`;
}

function gal_emptyMsg(text) {
    return `<div class="gal-status"><span>${text}</span></div>`;
}

// =====================================================================
// Inject gallery styles
// =====================================================================

(function injectGalleryStyles() {
    if (document.getElementById('gallery-styles')) return;
    const style = document.createElement('style');
    style.id = 'gallery-styles';
    style.textContent = `

/* Gallery modal overrides */
.gallery-content {
    max-width: 520px;
    width: 100%;
    max-height: 92vh;
    padding: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.gallery-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid var(--border);
    position: relative;
    flex-shrink: 0;
}

.gallery-header h3 {
    flex: 1;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.gallery-back {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 1.3rem;
    cursor: pointer;
    padding: 0.15rem 0.4rem;
    border-radius: 6px;
    line-height: 1;
    transition: var(--transition);
}
.gallery-back:hover { color: var(--text); background: var(--bg-card-hover); }

.gallery-select {
    background: none;
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    padding: 0.3rem 0.65rem;
    border-radius: 6px;
    transition: var(--transition);
    white-space: nowrap;
}
.gallery-select:hover { border-color: var(--primary); color: var(--primary); }

.gallery-content .modal-close {
    position: static;
    flex-shrink: 0;
    padding: 0.15rem 0.4rem;
}

#gallery-body {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem;
    -webkit-overflow-scrolling: touch;
}

/* Folder cards */
.gal-folders {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.gal-folder-card {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.85rem;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
}
.gal-folder-card:hover {
    border-color: var(--primary);
    background: var(--bg-card-hover);
}
.gal-folder-card:active {
    transform: scale(0.98);
}

.gal-folder-info {
    flex: 1;
    min-width: 0;
}
.gal-folder-name {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.gal-folder-meta {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.15rem;
}

.gal-folder-thumbs {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
}
.gal-folder-thumb {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    overflow: hidden;
    background: var(--bg);
    border: 1px solid var(--border);
}
.gal-folder-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

/* Image grid */
.gal-counter {
    font-size: 0.7rem;
    color: var(--text-dim);
    margin-bottom: 0.5rem;
    text-align: right;
}

.gal-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
}

.gal-thumb {
    position: relative;
    aspect-ratio: 1;
    border-radius: 6px;
    overflow: hidden;
    background: var(--bg);
    border: 1px solid var(--border);
    cursor: pointer;
    transition: border-color 0.2s;
}
.gal-thumb:active {
    transform: scale(0.97);
}
.gal-thumb-selected {
    border-color: var(--primary);
    box-shadow: 0 0 0 2px var(--primary-glow);
}

.gal-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.gal-thumb-info {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(transparent, rgba(0,0,0,0.8));
    padding: 1rem 0.3rem 0.2rem;
    display: flex;
    justify-content: space-between;
    font-size: 0.55rem;
    color: #ccc;
}

/* Checkboxes */
.gal-checkbox {
    position: absolute;
    top: 4px;
    left: 4px;
    width: 22px;
    height: 22px;
    border-radius: 5px;
    border: 2px solid rgba(255,255,255,0.6);
    background: rgba(0,0,0,0.4);
    z-index: 2;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    color: #fff;
    transition: all 0.15s;
}
.gal-checkbox.checked {
    background: var(--primary);
    border-color: var(--primary);
}

/* Action bar */
.gallery-actions {
    border-top: 1px solid var(--border);
    flex-shrink: 0;
}

.gal-action-bar {
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
}

.gal-select-all {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
}

.gal-checkbox-small {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid var(--border);
    background: var(--bg-input);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    color: #fff;
    transition: all 0.15s;
}
.gal-checkbox-small.checked {
    background: var(--primary);
    border-color: var(--primary);
}

.gal-action-btns {
    display: flex;
    gap: 0.5rem;
}

.gal-btn-delete {
    flex: 1;
    padding: 0.6rem;
    border-radius: var(--radius);
    border: 1px solid var(--danger);
    background: var(--danger-glow);
    color: var(--danger);
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
}
.gal-btn-delete:hover:not(:disabled) {
    background: var(--danger);
    color: #fff;
}
.gal-btn-delete:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.gal-btn-delete-folder {
    flex: 1;
    padding: 0.6rem;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
}
.gal-btn-delete-folder:hover {
    border-color: var(--danger);
    color: var(--danger);
    background: var(--danger-glow);
}

/* Load more */
.gal-load-more {
    display: block;
    width: 100%;
    margin-top: 0.75rem;
    padding: 0.7rem;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--primary);
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
}
.gal-load-more:hover {
    border-color: var(--primary);
    background: var(--primary-glow);
}

/* Status / spinner / empty / error */
.gal-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 2.5rem 1rem;
    color: var(--text-dim);
    font-size: 0.85rem;
}
.gal-status-error {
    color: var(--danger);
}

.gal-spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--border);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Responsive: 2 columns on very narrow screens */
@media (max-width: 400px) {
    .gal-grid {
        grid-template-columns: repeat(2, 1fr);
    }
    .gal-folder-thumb {
        width: 34px;
        height: 34px;
    }
}
`;
    document.head.appendChild(style);
})();
