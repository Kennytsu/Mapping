const API = '';

let parsedData = null;
let selectedFile = null;
let frameworksCache = [];
let mappingHistory = [];

const searchState = {
    query: '',
    frameworkId: '',
    offset: 0,
    limit: 50,
    total: 0,
};

let _currentSourceCtrl = null;

const tableState = {
    filter: 'all',
    search: '',
    sortKey: 'source_id',
    sortDir: 'asc',
};

const modalState = {
    mode: 'edit', // 'edit' | 'add'
    mappingId: null,
    sourceCtrl: null,
    targetCtrl: null,
};

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initSearch();
    initCoverage();
    initVersions();
    initUpload();
    initMappingModal();
    loadFrameworks();
});

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.tab-panel').forEach(c => c.classList.remove('active'));
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });
}

function switchToLookup(controlId) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector('.tab[data-tab="lookup"]').classList.add('active');
    document.querySelectorAll('.tab-panel').forEach(c => c.classList.remove('active'));
    document.getElementById('lookup').classList.add('active');
    document.getElementById('search-input').value = controlId;
    clearTimeout(_searchDebounce);
    mappingHistory = [];
    searchState.offset = 0;
    performSearch();
}

// ---------------------------------------------------------------------------
// Framework loading
// ---------------------------------------------------------------------------

async function loadFrameworks() {
    try {
        const res = await fetch(`${API}/api/frameworks`);
        frameworksCache = await res.json();
        populateFrameworkSelects();
        const chip = document.getElementById('fw-count-chip');
        if (chip) {
            const total = frameworksCache.reduce((s, f) => s + f.control_count, 0);
            chip.textContent = `${frameworksCache.length} Frameworks · ${total} Controls`;
        }
    } catch (err) {
        console.error('Failed to load frameworks:', err);
    }
}

function populateFrameworkSelects() {
    const selects = {
        'framework-filter': true,
        'source-fw': false,
        'target-fw': false,
        'version-fw': false,
        'upload-source-fw': false,
        'upload-target-fw': false,
        'mm-target-fw': false,
    };

    for (const [id, addAll] of Object.entries(selects)) {
        const el = document.getElementById(id);
        if (!el) continue;
        const current = el.value;
        el.innerHTML = '';
        if (addAll) el.innerHTML = '<option value="">All Frameworks</option>';
        frameworksCache.forEach(fw => {
            const opt = document.createElement('option');
            opt.value = fw.id;
            opt.textContent = `${fw.short_name} ${fw.version} (${fw.control_count})`;
            el.appendChild(opt);
        });
        if (current) el.value = current;
    }
}

// ---------------------------------------------------------------------------
// Confidence helpers
// ---------------------------------------------------------------------------

function confidenceBand(c) {
    const v = Number(c) || 0;
    if (v >= 0.8) return 'strong';
    if (v >= 0.5) return 'partial';
    if (v > 0) return 'weak';
    return 'none';
}

function confidenceLabel(band) {
    return { strong: 'Strong', partial: 'Partial', weak: 'Weak', none: '—' }[band] || '—';
}

function renderConfidenceChip(confidence) {
    const band = confidenceBand(confidence);
    const pct = Math.round((Number(confidence) || 0) * 100);
    const label = confidenceLabel(band);
    if (band === 'none') return `<span class="confidence-chip none">—</span>`;
    return `<span class="confidence-chip ${band}" title="Confidence ${pct}%">${label} ${pct}%</span>`;
}

// ---------------------------------------------------------------------------
// Control Lookup
// ---------------------------------------------------------------------------

let _searchDebounce = null;

function initSearch() {
    document.getElementById('search-btn').addEventListener('click', () => {
        searchState.offset = 0;
        performSearch();
    });
    document.getElementById('search-input').addEventListener('input', () => {
        clearTimeout(_searchDebounce);
        const val = document.getElementById('search-input').value.trim();
        if (!val) {
            renderEmptySearch();
            return;
        }
        searchState.offset = 0;
        _searchDebounce = setTimeout(performSearch, 350);
    });
    document.getElementById('search-input').addEventListener('keypress', e => {
        if (e.key === 'Enter') {
            clearTimeout(_searchDebounce);
            searchState.offset = 0;
            performSearch();
        }
    });
    document.getElementById('clear-btn').addEventListener('click', () => {
        document.getElementById('search-input').value = '';
        clearTimeout(_searchDebounce);
        renderEmptySearch();
    });

    document.getElementById('framework-filter').addEventListener('change', () => {
        searchState.offset = 0;
        const val = document.getElementById('search-input').value.trim();
        if (val) performSearch();
    });

    document.getElementById('page-prev').addEventListener('click', () => {
        if (searchState.offset >= searchState.limit) {
            searchState.offset -= searchState.limit;
            performSearch();
        }
    });
    document.getElementById('page-next').addEventListener('click', () => {
        if (searchState.offset + searchState.limit < searchState.total) {
            searchState.offset += searchState.limit;
            performSearch();
        }
    });
    document.getElementById('page-size').addEventListener('change', e => {
        searchState.limit = parseInt(e.target.value) || 50;
        searchState.offset = 0;
        const val = document.getElementById('search-input').value.trim();
        if (val) performSearch();
    });
}

function renderEmptySearch() {
    document.getElementById('search-results').innerHTML =
        '<div class="empty-state"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="20" cy="20" r="14"/><path d="M30 30l12 12" stroke-linecap="round"/></svg><p>Search for a control to get started.</p></div>';
    document.getElementById('mapping-results').innerHTML =
        '<div class="empty-state"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 12h36M6 24h24M6 36h30" stroke-linecap="round"/></svg><p>Select a control to view its mappings.</p></div>';
    document.getElementById('search-pagination').classList.add('hidden');
    _currentSourceCtrl = null;
}

async function performSearch() {
    const query = document.getElementById('search-input').value.trim();
    const frameworkId = document.getElementById('framework-filter').value;
    if (!query) return;

    searchState.query = query;
    searchState.frameworkId = frameworkId;

    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '<div class="loading">Searching</div>';
    document.getElementById('mapping-results').innerHTML =
        '<div class="empty-state"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 12h36M6 24h24M6 36h30" stroke-linecap="round"/></svg><p>Select a control to view its mappings.</p></div>';

    try {
        const params = new URLSearchParams({
            q: query,
            limit: String(searchState.limit),
            offset: String(searchState.offset),
        });
        if (frameworkId) params.set('framework_id', frameworkId);

        const res = await fetch(`${API}/api/controls?${params.toString()}`);
        const data = await res.json();
        const items = data.items || [];
        searchState.total = data.total || 0;

        if (searchState.total === 0) {
            resultsDiv.innerHTML = '<div class="empty-state"><p>No controls found.</p></div>';
            document.getElementById('search-pagination').classList.add('hidden');
            return;
        }

        const start = searchState.offset + 1;
        const end = Math.min(searchState.offset + items.length, searchState.total);
        resultsDiv.innerHTML = `<div class="results-heading">Showing ${start}–${end} of ${searchState.total}</div>`;

        items.forEach(ctrl => {
            const item = document.createElement('div');
            item.className = 'result-item';
            item.innerHTML = `
                <span class="ctrl-id">${esc(ctrl.control_id)}</span>
                <span class="fw-badge">${esc(ctrl.framework_short_name)}</span>
                <span class="cat-badge">${esc(ctrl.category)}</span>
                <span class="ctrl-title">${esc(ctrl.title)}</span>
            `;
            item.addEventListener('click', () => {
                document.querySelectorAll('.result-item').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                mappingHistory = [];
                showMappings(ctrl);
            });
            resultsDiv.appendChild(item);
        });

        renderPagination();
    } catch (err) {
        resultsDiv.innerHTML = `<div class="empty-state"><p>Error: ${esc(err.message)}</p></div>`;
    }
}

function renderPagination() {
    const pag = document.getElementById('search-pagination');
    if (searchState.total <= 0) {
        pag.classList.add('hidden');
        return;
    }
    pag.classList.remove('hidden');
    const totalPages = Math.max(1, Math.ceil(searchState.total / searchState.limit));
    const currentPage = Math.floor(searchState.offset / searchState.limit) + 1;
    document.getElementById('page-info').textContent = `Page ${currentPage} of ${totalPages}`;
    document.getElementById('page-prev').disabled = searchState.offset === 0;
    document.getElementById('page-next').disabled =
        searchState.offset + searchState.limit >= searchState.total;
}

async function showMappings(ctrl, pushHistory = true) {
    const div = document.getElementById('mapping-results');
    div.innerHTML = '<div class="loading">Loading mappings</div>';

    if (pushHistory) {
        mappingHistory.push(ctrl);
    }
    _currentSourceCtrl = ctrl;

    try {
        const res = await fetch(
            `${API}/api/mappings/${encodeURIComponent(ctrl.control_id)}?framework_id=${ctrl.framework_id}`
        );
        const data = await res.json();

        if (data.detail) {
            div.innerHTML = `<div class="empty-state"><p>${esc(data.detail)}</p></div>`;
            return;
        }

        // Use the canonical source from the API response so we have its DB id
        // (needed when creating a new mapping from the modal).
        _currentSourceCtrl = data.source || ctrl;

        const fwName = ctrl.framework_short_name || data.source.framework_short_name;
        const backBtn = mappingHistory.length > 1
            ? `<button class="mapping-back-btn" id="mapping-back-btn">&#8592; Back</button>`
            : '';
        let html = `<div class="mappings-header">
            ${backBtn}
            <h2>${esc(ctrl.control_id)}</h2>
            <span class="fw-badge">${esc(fwName)}</span>
            <button class="btn-secondary btn-add-mapping" id="add-mapping-btn">+ Add Mapping</button>
        </div>`;
        html += `<div class="mappings-subtitle">${esc(data.source.title)}</div>`;

        if (!data.mappings || data.mappings.length === 0) {
            html += '<div class="empty-state"><p>No mappings found for this control. Click <strong>+ Add Mapping</strong> to create one.</p></div>';
        } else {
            const grouped = {};
            data.mappings.forEach(m => {
                (grouped[m.framework_short_name] ||= []).push(m);
            });

            for (const [fw, mappings] of Object.entries(grouped)) {
                html += `<div class="mapping-group"><div class="mapping-group-title">${esc(fw)} (${mappings.length})</div>`;
                mappings.forEach(m => {
                    const cls = m.source_type === 'official' ? 'badge-official'
                        : m.source_type === 'manual' ? 'badge-manual'
                        : 'badge-ai';
                    const label = m.source_type === 'official' ? 'Official'
                        : m.source_type === 'manual' ? 'Manual'
                        : 'AI';
                    const fwObj = frameworksCache.find(f => f.short_name === m.framework_short_name);
                    const fwId = fwObj ? fwObj.id : (m.framework_id || '');
                    const notesHtml = m.notes
                        ? `<div class="mapping-notes"><strong>Note:</strong> ${esc(m.notes)}</div>`
                        : '';
                    html += `
                        <div class="mapping-item" data-mapping-id="${m.id}">
                            <div class="mapping-item-row">
                                <span class="m-id mapping-drill" data-control-id="${esc(m.control_id)}" data-framework-id="${fwId}" data-framework-short-name="${esc(m.framework_short_name)}" title="Drill into this control">${esc(m.control_id)}</span>
                                <span class="badge ${cls}">${label}</span>
                                ${renderConfidenceChip(m.confidence)}
                                <span class="m-title">${esc(m.title)}</span>
                                <span class="mapping-actions">
                                    <button class="icon-btn edit-mapping" data-mapping-id="${m.id}" title="Edit">
                                        <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM12.293 4.879L4 13.172V16h2.828l8.293-8.293-2.828-2.828z"/></svg>
                                    </button>
                                    <button class="icon-btn icon-btn-danger delete-mapping" data-mapping-id="${m.id}" title="Delete">
                                        <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"/></svg>
                                    </button>
                                </span>
                            </div>
                            ${notesHtml}
                        </div>`;
                });
                html += '</div>';
            }
        }
        div.innerHTML = html;

        const backEl = document.getElementById('mapping-back-btn');
        if (backEl) {
            backEl.addEventListener('click', () => {
                mappingHistory.pop();
                const prev = mappingHistory[mappingHistory.length - 1];
                showMappings(prev, false);
            });
        }

        const addBtn = document.getElementById('add-mapping-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => openMappingModal('add'));
        }

        div.querySelectorAll('.mapping-drill').forEach(el => {
            el.addEventListener('click', () => {
                showMappings({
                    control_id: el.dataset.controlId,
                    framework_id: parseInt(el.dataset.frameworkId) || 0,
                    framework_short_name: el.dataset.frameworkShortName,
                });
            });
        });

        div.querySelectorAll('.edit-mapping').forEach(el => {
            el.addEventListener('click', () => {
                const id = parseInt(el.dataset.mappingId);
                const m = data.mappings.find(x => x.id === id);
                if (m) openMappingModal('edit', m);
            });
        });

        div.querySelectorAll('.delete-mapping').forEach(el => {
            el.addEventListener('click', async () => {
                const id = parseInt(el.dataset.mappingId);
                const m = data.mappings.find(x => x.id === id);
                const label = m ? `${m.framework_short_name} ${m.control_id}` : `mapping #${id}`;
                if (!confirm(`Delete mapping to ${label}? This cannot be undone.`)) return;
                try {
                    const r = await fetch(`${API}/api/mappings/${id}`, { method: 'DELETE' });
                    if (!r.ok && r.status !== 204) {
                        const t = await r.text();
                        alert(`Delete failed: ${t}`);
                        return;
                    }
                    showMappings(_currentSourceCtrl, false);
                } catch (err) {
                    alert(`Delete failed: ${err.message}`);
                }
            });
        });
    } catch (err) {
        div.innerHTML = `<div class="empty-state"><p>Error: ${esc(err.message)}</p></div>`;
    }
}

// ---------------------------------------------------------------------------
// Mapping Modal (add / edit)
// ---------------------------------------------------------------------------

function initMappingModal() {
    const backdrop = document.getElementById('mapping-modal');
    document.getElementById('mapping-modal-close').addEventListener('click', closeMappingModal);
    document.getElementById('mapping-modal-cancel').addEventListener('click', closeMappingModal);
    backdrop.addEventListener('click', e => {
        if (e.target === backdrop) closeMappingModal();
    });
    document.getElementById('mapping-modal-save').addEventListener('click', saveMappingFromModal);

    const slider = document.getElementById('mm-confidence');
    slider.addEventListener('input', () => {
        const v = parseFloat(slider.value);
        document.getElementById('mm-confidence-value').textContent = v.toFixed(2);
        const band = confidenceBand(v);
        const chip = document.getElementById('mm-confidence-band');
        chip.className = `confidence-chip ${band}`;
        chip.textContent = confidenceLabel(band);
    });

    let _mmSearchDebounce = null;
    const searchInput = document.getElementById('mm-target-search');
    searchInput.addEventListener('input', () => {
        clearTimeout(_mmSearchDebounce);
        _mmSearchDebounce = setTimeout(searchTargetControls, 250);
    });
    document.getElementById('mm-target-fw').addEventListener('change', () => {
        if (searchInput.value.trim()) searchTargetControls();
    });
}

function openMappingModal(mode, ctxOrMapping) {
    modalState.mode = mode;
    modalState.targetCtrl = null;
    modalState.mappingId = null;

    document.getElementById('mapping-modal-error').classList.add('hidden');
    document.getElementById('mapping-modal-title').textContent =
        mode === 'add' ? 'Add Mapping' : 'Edit Mapping';

    const sourceName = _currentSourceCtrl
        ? `${_currentSourceCtrl.framework_short_name || ''} ${_currentSourceCtrl.control_id} — ${_currentSourceCtrl.title || ''}`
        : '-';
    document.getElementById('mapping-modal-source-name').textContent = sourceName.trim();

    const targetPicker = document.getElementById('mapping-modal-target-picker');
    const targetFixed = document.getElementById('mapping-modal-target-fixed');

    if (mode === 'add') {
        targetPicker.classList.remove('hidden');
        targetFixed.classList.add('hidden');
        document.getElementById('mm-target-search').value = '';
        document.getElementById('mm-target-results').innerHTML = '';
        // Default target framework to one different from source
        const tgtSel = document.getElementById('mm-target-fw');
        if (_currentSourceCtrl) {
            const otherFw = frameworksCache.find(f => f.id !== _currentSourceCtrl.framework_id);
            if (otherFw) tgtSel.value = otherFw.id;
        }
        document.getElementById('mm-source-type').value = 'manual';
        document.getElementById('mm-confidence').value = '1';
        document.getElementById('mm-notes').value = '';
    } else {
        const m = ctxOrMapping;
        modalState.mappingId = m.id;
        modalState.targetCtrl = {
            control_id: m.control_id,
            framework_short_name: m.framework_short_name,
            title: m.title,
        };
        targetPicker.classList.add('hidden');
        targetFixed.classList.remove('hidden');
        document.getElementById('mapping-modal-target-name').textContent =
            `${m.framework_short_name} ${m.control_id} — ${m.title || ''}`;
        document.getElementById('mm-source-type').value = m.source_type || 'manual';
        document.getElementById('mm-confidence').value = String(m.confidence ?? 1);
        document.getElementById('mm-notes').value = m.notes || '';
    }

    // Trigger slider event to refresh the chip + value display
    document.getElementById('mm-confidence').dispatchEvent(new Event('input'));

    document.getElementById('mapping-modal').classList.remove('hidden');
}

function closeMappingModal() {
    document.getElementById('mapping-modal').classList.add('hidden');
}

async function searchTargetControls() {
    const fwId = document.getElementById('mm-target-fw').value;
    const q = document.getElementById('mm-target-search').value.trim();
    const resultsEl = document.getElementById('mm-target-results');
    if (!q || !fwId) {
        resultsEl.innerHTML = '';
        return;
    }
    resultsEl.innerHTML = '<div class="loading">Searching</div>';
    try {
        const params = new URLSearchParams({ q, framework_id: fwId, limit: '20', offset: '0' });
        const res = await fetch(`${API}/api/controls?${params.toString()}`);
        const data = await res.json();
        const items = data.items || [];
        if (items.length === 0) {
            resultsEl.innerHTML = '<div class="empty-state-sm">No matches.</div>';
            return;
        }
        resultsEl.innerHTML = items.map(c => `
            <div class="mm-target-item" data-id="${c.id}" data-control-id="${esc(c.control_id)}" data-fw="${esc(c.framework_short_name)}" data-title="${esc(c.title || '')}">
                <span class="ctrl-id">${esc(c.control_id)}</span>
                <span class="ctrl-title">${esc(c.title || '')}</span>
            </div>
        `).join('');
        resultsEl.querySelectorAll('.mm-target-item').forEach(el => {
            el.addEventListener('click', () => {
                resultsEl.querySelectorAll('.mm-target-item').forEach(i => i.classList.remove('selected'));
                el.classList.add('selected');
                modalState.targetCtrl = {
                    id: parseInt(el.dataset.id),
                    control_id: el.dataset.controlId,
                    framework_short_name: el.dataset.fw,
                    title: el.dataset.title,
                };
            });
        });
    } catch (err) {
        resultsEl.innerHTML = `<div class="empty-state-sm">Error: ${esc(err.message)}</div>`;
    }
}

async function saveMappingFromModal() {
    const errEl = document.getElementById('mapping-modal-error');
    errEl.classList.add('hidden');

    const confidence = parseFloat(document.getElementById('mm-confidence').value);
    const sourceType = document.getElementById('mm-source-type').value;
    const notes = document.getElementById('mm-notes').value;

    const saveBtn = document.getElementById('mapping-modal-save');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';

    try {
        if (modalState.mode === 'add') {
            if (!_currentSourceCtrl || !_currentSourceCtrl.id) {
                throw new Error('No source control selected.');
            }
            if (!modalState.targetCtrl || !modalState.targetCtrl.id) {
                throw new Error('Pick a target control by searching above.');
            }
            const body = {
                source_control_id: _currentSourceCtrl.id,
                target_control_id: modalState.targetCtrl.id,
                confidence,
                source_type: sourceType,
                notes,
            };
            const r = await fetch(`${API}/api/mappings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!r.ok) {
                const t = await r.text();
                throw new Error(parseErr(t) || `HTTP ${r.status}`);
            }
        } else {
            const body = { confidence, source_type: sourceType, notes };
            const r = await fetch(`${API}/api/mappings/${modalState.mappingId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!r.ok) {
                const t = await r.text();
                throw new Error(parseErr(t) || `HTTP ${r.status}`);
            }
        }
        closeMappingModal();
        if (_currentSourceCtrl) showMappings(_currentSourceCtrl, false);
    } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.remove('hidden');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
    }
}

function parseErr(text) {
    try {
        const j = JSON.parse(text);
        return j.detail || j.error || '';
    } catch { return text; }
}

// ---------------------------------------------------------------------------
// Coverage Analysis
// ---------------------------------------------------------------------------

let _lastCoverageTable = null;

function initCoverage() {
    document.getElementById('analyze-btn').addEventListener('click', runCoverage);
    document.getElementById('swap-fw-btn').addEventListener('click', () => {
        const src = document.getElementById('source-fw');
        const tgt = document.getElementById('target-fw');
        const tmp = src.value;
        src.value = tgt.value;
        tgt.value = tmp;
    });
    document.getElementById('export-csv-btn').addEventListener('click', exportCoverageCSV);
    document.getElementById('export-xlsx-btn').addEventListener('click', exportCoverageExcel);

    document.getElementById('table-search-input').addEventListener('input', e => {
        tableState.search = e.target.value.trim().toLowerCase();
        renderMappingTable(_lastCoverageTable);
    });

    document.querySelectorAll('#table-filter-chips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('#table-filter-chips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            tableState.filter = chip.dataset.filter;
            renderMappingTable(_lastCoverageTable);
        });
    });
}

async function runCoverage() {
    const srcId = document.getElementById('source-fw').value;
    const tgtId = document.getElementById('target-fw').value;
    if (!srcId || !tgtId || srcId === tgtId) {
        showCoverageStatus('Select two different frameworks.', 'error');
        return;
    }

    const resultsDiv = document.getElementById('coverage-results');
    resultsDiv.classList.remove('hidden');

    const statusEl = document.getElementById('coverage-status');
    if (statusEl) statusEl.classList.add('hidden');

    ['stat-total', 'stat-mapped', 'stat-unmapped', 'stat-percent'].forEach(id => {
        document.getElementById(id).textContent = '...';
    });

    try {
        const [coverageRes, tableRes] = await Promise.all([
            fetch(`${API}/api/coverage?source=${srcId}&target=${tgtId}`),
            fetch(`${API}/api/coverage/table?source=${srcId}&target=${tgtId}`),
        ]);

        const coverage = await coverageRes.json();
        const table = await tableRes.json();
        _lastCoverageTable = table;

        document.getElementById('stat-total').textContent = coverage.total_source_controls;
        document.getElementById('stat-mapped').textContent = coverage.mapped_controls;
        document.getElementById('stat-unmapped').textContent = coverage.unmapped_controls;
        document.getElementById('stat-percent').textContent = coverage.coverage_percentage + '%';
        document.getElementById('coverage-bar').style.width = coverage.coverage_percentage + '%';

        const unmappedList = document.getElementById('unmapped-list');
        document.getElementById('unmapped-count').textContent = `(${coverage.unmapped_control_ids.length})`;
        unmappedList.innerHTML = coverage.unmapped_control_ids.length > 0
            ? coverage.unmapped_control_ids.map(c => `<div class="detail-item coverage-link" data-id="${esc(c.id)}">${esc(c.id)}${c.title ? ` <span class="detail-title">— ${esc(c.title)}</span>` : ''}</div>`).join('')
            : '<div class="empty-state"><p>All controls are mapped.</p></div>';

        const gapList = document.getElementById('gap-list');
        document.getElementById('gap-count').textContent = `(${coverage.gap_controls.length})`;
        gapList.innerHTML = coverage.gap_controls.length > 0
            ? coverage.gap_controls.map(c => `<div class="detail-item coverage-link" data-id="${esc(c.id)}">${esc(c.id)}${c.title ? ` <span class="detail-title">— ${esc(c.title)}</span>` : ''}</div>`).join('')
            : '<div class="empty-state"><p>Full coverage.</p></div>';

        // Reset table filters when running fresh analysis
        tableState.search = '';
        tableState.filter = 'all';
        document.getElementById('table-search-input').value = '';
        document.querySelectorAll('#table-filter-chips .chip').forEach(c =>
            c.classList.toggle('active', c.dataset.filter === 'all'));

        renderMappingTable(table);

        document.querySelectorAll('.coverage-link').forEach(el => {
            el.addEventListener('click', () => switchToLookup(el.dataset.id));
        });
    } catch (err) {
        showCoverageStatus('Coverage analysis failed: ' + err.message, 'error');
    }
}

function showCoverageStatus(message, type) {
    const el = document.getElementById('coverage-status');
    if (!el) return;
    el.textContent = message;
    el.className = `status ${type}`;
    el.classList.remove('hidden');
}

function filterTableRows(rows) {
    return rows.filter(r => {
        const isGap = r.source_type === 'gap';
        if (tableState.filter === 'mapped' && isGap) return false;
        if (tableState.filter === 'gap' && !isGap) return false;
        if (tableState.filter === 'strong' && (isGap || (r.confidence || 0) < 0.8)) return false;
        if (tableState.filter === 'partial' && (isGap || (r.confidence || 0) < 0.5 || (r.confidence || 0) >= 0.8)) return false;
        if (tableState.filter === 'weak' && (isGap || (r.confidence || 0) === 0 || (r.confidence || 0) >= 0.5)) return false;

        if (tableState.search) {
            const haystack = [r.source_id, r.source_title, r.target_id, r.target_title, r.notes]
                .map(s => (s || '').toString().toLowerCase()).join(' ');
            if (!haystack.includes(tableState.search)) return false;
        }
        return true;
    });
}

function sortTableRows(rows) {
    const { sortKey, sortDir } = tableState;
    const dir = sortDir === 'desc' ? -1 : 1;
    const copy = [...rows];
    copy.sort((a, b) => {
        let av = a[sortKey];
        let bv = b[sortKey];
        if (sortKey === 'confidence') {
            av = Number(av) || 0;
            bv = Number(bv) || 0;
        } else {
            av = (av ?? '').toString().toLowerCase();
            bv = (bv ?? '').toString().toLowerCase();
        }
        if (av < bv) return -1 * dir;
        if (av > bv) return 1 * dir;
        return 0;
    });
    return copy;
}

function renderMappingTable(table) {
    const container = document.getElementById('mapping-table-container');
    const countEl = document.getElementById('table-row-count');

    if (!table || !table.rows || table.rows.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No data.</p></div>';
        if (countEl) countEl.textContent = '';
        return;
    }

    const filtered = filterTableRows(table.rows);
    const sorted = sortTableRows(filtered);
    if (countEl) countEl.textContent = `(${sorted.length} of ${table.rows.length})`;

    if (sorted.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No rows match the current filter.</p></div>';
        return;
    }

    const headerCols = [
        { key: 'source_id', label: esc(table.source_framework) },
        { key: 'source_title', label: 'Title' },
        { key: 'target_id', label: esc(table.target_framework) },
        { key: 'target_title', label: 'Title' },
        { key: 'source_type', label: 'Type' },
        { key: 'confidence', label: 'Confidence' },
    ];

    let html = '<table><thead><tr>';
    headerCols.forEach(col => {
        const active = tableState.sortKey === col.key;
        const arrow = active ? (tableState.sortDir === 'asc' ? '▲' : '▼') : '';
        html += `<th class="sortable ${active ? 'active' : ''}" data-key="${col.key}">${col.label} <span class="sort-arrow">${arrow}</span></th>`;
    });
    html += '</tr></thead><tbody>';

    sorted.forEach(r => {
        const isGap = r.source_type === 'gap';
        const typeBadge = isGap
            ? `<span class="badge">gap</span>`
            : `<span class="badge ${r.source_type === 'official' ? 'badge-official' : (r.source_type === 'manual' ? 'badge-manual' : 'badge-ai')}">${esc(r.source_type)}</span>`;
        html += `<tr>
            <td>${esc(r.source_id)}</td>
            <td>${esc(r.source_title)}</td>
            <td class="${isGap ? 'gap' : ''}">${isGap ? 'No mapping' : esc(r.target_id)}</td>
            <td>${esc(r.target_title)}</td>
            <td>${typeBadge}</td>
            <td>${isGap ? '<span class="confidence-chip none">—</span>' : renderConfidenceChip(r.confidence)}</td>
        </tr>`;
    });

    container.innerHTML = html + '</tbody></table>';

    container.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (tableState.sortKey === key) {
                tableState.sortDir = tableState.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                tableState.sortKey = key;
                tableState.sortDir = 'asc';
            }
            renderMappingTable(_lastCoverageTable);
        });
    });
}

function exportCoverageCSV() {
    if (!_lastCoverageTable || !_lastCoverageTable.rows) return;
    const { source_framework, target_framework } = _lastCoverageTable;
    const rows = sortTableRows(filterTableRows(_lastCoverageTable.rows));
    const header = [source_framework, 'Source Title', target_framework, 'Target Title', 'Type', 'Confidence', 'Strength', 'Notes'];
    const lines = [header.map(JSON.stringify).join(',')];
    rows.forEach(r => {
        const band = confidenceBand(r.confidence);
        const strength = r.source_type === 'gap' ? '' : confidenceLabel(band);
        lines.push([
            JSON.stringify(r.source_id || ''),
            JSON.stringify(r.source_title || ''),
            JSON.stringify(r.target_id || 'No mapping'),
            JSON.stringify(r.target_title || ''),
            JSON.stringify(r.source_type || ''),
            JSON.stringify(((r.confidence || 0).toFixed(2))),
            JSON.stringify(strength),
            JSON.stringify(r.notes || ''),
        ].join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `coverage_${source_framework}_to_${target_framework}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

function exportCoverageExcel() {
    const srcId = document.getElementById('source-fw').value;
    const tgtId = document.getElementById('target-fw').value;
    if (!srcId || !tgtId) return;
    window.open(`${API}/api/coverage/export?source=${srcId}&target=${tgtId}`, '_blank');
}


// ---------------------------------------------------------------------------
// Versions
// ---------------------------------------------------------------------------

function initVersions() {
    document.getElementById('version-fw').addEventListener('change', loadTransitions);
    document.getElementById('version-btn').addEventListener('click', loadVersionChanges);
}

async function loadTransitions() {
    const fwId = document.getElementById('version-fw').value;
    const transSelect = document.getElementById('version-transition');
    transSelect.innerHTML = '<option value="">Loading...</option>';

    const fw = frameworksCache.find(f => f.id == fwId);
    if (!fw) return;

    try {
        const res = await fetch(`${API}/api/versions/${fw.short_name}/transitions`);
        const transitions = await res.json();

        if (transitions.length === 0) {
            transSelect.innerHTML = '<option value="">No version changes available</option>';
            document.getElementById('version-empty').style.display = 'block';
            document.getElementById('version-results').classList.add('hidden');
            return;
        }

        document.getElementById('version-empty').style.display = 'none';
        transSelect.innerHTML = '';
        transitions.forEach(t => {
            const opt = document.createElement('option');
            opt.value = `${t.old_version}|${t.new_version}`;
            opt.textContent = `${t.old_version}  \u2192  ${t.new_version}  (${t.change_count} changes)`;
            transSelect.appendChild(opt);
        });
    } catch (err) {
        transSelect.innerHTML = '<option value="">Error loading transitions</option>';
    }
}

async function loadVersionChanges() {
    const fwId = document.getElementById('version-fw').value;
    const transition = document.getElementById('version-transition').value;
    if (!fwId || !transition) return;

    const fw = frameworksCache.find(f => f.id == fwId);
    const [oldV, newV] = transition.split('|');

    try {
        const res = await fetch(
            `${API}/api/versions/${fw.short_name}/changes?from=${encodeURIComponent(oldV)}&to=${encodeURIComponent(newV)}`
        );
        const changes = await res.json();

        const resultsDiv = document.getElementById('version-results');
        resultsDiv.classList.remove('hidden');
        document.getElementById('version-empty').style.display = 'none';

        const grouped = { added: [], modified: [], renamed: [], removed: [] };
        changes.forEach(c => {
            const type = c.change_type.toLowerCase();
            if (grouped[type]) grouped[type].push(c);
            else (grouped.modified ||= []).push(c);
        });

        document.getElementById('stat-added').textContent = grouped.added.length;
        document.getElementById('stat-modified').textContent = grouped.modified.length;
        document.getElementById('stat-renamed').textContent = grouped.renamed.length;
        document.getElementById('stat-removed').textContent = grouped.removed.length;

        let html = '';
        for (const [type, items] of Object.entries(grouped)) {
            if (items.length === 0) continue;
            html += `<div class="change-group ${type}">`;
            html += `<div class="change-group-title">${type.charAt(0).toUpperCase() + type.slice(1)} (${items.length})</div>`;
            items.forEach(c => {
                const ids = type === 'renamed'
                    ? `${esc(c.old_control_id)} \u2192 ${esc(c.new_control_id)}`
                    : esc(c.old_control_id || c.new_control_id);
                html += `<div class="change-item">
                    <span class="ctrl-id">${ids}</span>
                    ${c.description ? `<div class="change-desc">${esc(c.description)}</div>` : ''}
                    ${c.category ? `<span class="cat-badge">${esc(c.category)}</span>` : ''}
                </div>`;
            });
            html += '</div>';
        }

        document.getElementById('version-changes-list').innerHTML =
            html || '<div class="empty-state"><p>No changes found.</p></div>';
    } catch (err) {
        alert('Failed to load version changes: ' + err.message);
    }
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

function initUpload() {
    const fileDrop = document.getElementById('file-drop');
    const fileInput = document.getElementById('file-input');

    fileDrop.addEventListener('dragover', e => { e.preventDefault(); fileDrop.classList.add('dragover'); });
    fileDrop.addEventListener('dragleave', () => fileDrop.classList.remove('dragover'));
    fileDrop.addEventListener('drop', e => {
        e.preventDefault();
        fileDrop.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', e => {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });

    document.getElementById('parse-btn').addEventListener('click', parseDocument);
    document.getElementById('import-btn').addEventListener('click', importData);
}

function handleFile(file) {
    selectedFile = file;
    document.getElementById('file-name').textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    document.getElementById('parse-btn').disabled = false;
    document.getElementById('parse-results').classList.add('hidden');
    document.getElementById('import-status').classList.add('hidden');
}

async function parseDocument() {
    if (!selectedFile) return;
    const btn = document.getElementById('parse-btn');
    btn.disabled = true;
    btn.textContent = 'Parsing...';

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('doc_type', document.getElementById('doc-type').value);

    try {
        const res = await fetch(`${API}/api/upload`, { method: 'POST', body: formData });
        const result = await res.json();
        if (result.success) {
            parsedData = result;
            parsedData.doc_type = document.getElementById('doc-type').value;
            showParsedData(result);
        } else {
            showStatus(`Parsing failed: ${result.error}`, 'error');
        }
    } catch (err) {
        showStatus(`Error: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Parse Document';
    }
}

function showParsedData(data) {
    document.getElementById('parse-results').classList.remove('hidden');

    const srcSel = document.getElementById('upload-source-fw');
    const tgtSel = document.getElementById('upload-target-fw');
    const srcName = srcSel.options[srcSel.selectedIndex]?.text || '?';
    const tgtName = tgtSel.options[tgtSel.selectedIndex]?.text || '?';
    const year = document.getElementById('doc-year').value || '-';
    const fmt = document.getElementById('doc-type').value;

    document.getElementById('upload-summary').innerHTML = `
        <div class="sum-item"><span class="sum-label">Source</span><span class="sum-value">${esc(srcName)}</span></div>
        <div class="sum-item"><span class="sum-label">Target</span><span class="sum-value">${esc(tgtName)}</span></div>
        <div class="sum-item"><span class="sum-label">Year</span><span class="sum-value">${esc(year)}</span></div>
        <div class="sum-item"><span class="sum-label">Format</span><span class="sum-value">${esc(fmt)}</span></div>
        <div class="sum-item"><span class="sum-label">Controls</span><span class="sum-value">${data.controls.length}</span></div>
        <div class="sum-item"><span class="sum-label">Mappings</span><span class="sum-value">${data.mappings.length}</span></div>
    `;

    document.getElementById('control-count').textContent = `(${data.controls.length})`;
    const ct = document.getElementById('controls-table');
    if (data.controls.length > 0) {
        let html = '<table><thead><tr><th>ID</th><th>Title</th><th>Category</th></tr></thead><tbody>';
        data.controls.slice(0, 100).forEach(c => {
            html += `<tr><td>${esc(c.control_id)}</td><td>${esc(c.title || '')}</td><td>${esc(c.category || '')}</td></tr>`;
        });
        ct.innerHTML = html + '</tbody></table>';
    } else {
        ct.innerHTML = '<div class="empty-state"><p>No controls found</p></div>';
    }

    document.getElementById('mapping-count').textContent = `(${data.mappings.length})`;
    const mt = document.getElementById('mappings-table');
    if (data.mappings.length > 0) {
        let html = '<table><thead><tr><th>Source (ISO)</th><th>Target</th></tr></thead><tbody>';
        data.mappings.slice(0, 100).forEach(m => {
            html += `<tr><td>${esc(m.source)}</td><td>${esc(m.target)}</td></tr>`;
        });
        mt.innerHTML = html + '</tbody></table>';
    } else {
        mt.innerHTML = '<div class="empty-state"><p>No mappings found</p></div>';
    }
}

async function importData() {
    if (!parsedData) return;
    const btn = document.getElementById('import-btn');
    btn.disabled = true;
    btn.textContent = 'Importing...';

    const payload = {
        ...parsedData,
        source_framework_id: parseInt(document.getElementById('upload-source-fw').value) || 0,
        target_framework_id: parseInt(document.getElementById('upload-target-fw').value) || 0,
        document_year: document.getElementById('doc-year').value || '',
        source_document: selectedFile ? selectedFile.name : '',
    };

    try {
        const res = await fetch(`${API}/api/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const result = await res.json();
        if (result.success) {
            showStatus(`Imported ${result.controls_added} controls and ${result.mappings_added} mappings`, 'success');
            loadFrameworks();
        } else {
            showStatus(`Import failed: ${result.error}`, 'error');
        }
    } catch (err) {
        showStatus(`Error: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Import to Database';
    }
}

function showStatus(message, type) {
    const el = document.getElementById('import-status');
    el.textContent = message;
    el.className = `status ${type}`;
    el.classList.remove('hidden');
}

// ---------------------------------------------------------------------------
// Utils
// ---------------------------------------------------------------------------

function esc(str) {
    if (str === undefined || str === null) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
}


// ---------------------------------------------------------------------------
// Compliance Tab
// ---------------------------------------------------------------------------

(function() {
    const uploadBtn = document.getElementById('reg-upload-btn');
    const checkBtn = document.getElementById('check-run-btn');

    if (!uploadBtn) return;

    let regulations = [];

    uploadBtn.addEventListener('click', uploadRegulation);
    checkBtn.addEventListener('click', runComplianceCheck);

    loadRegulations();

    async function loadRegulations() {
        try {
            const resp = await fetch('/api/regulations');
            regulations = await resp.json();
            renderRegList();
            updateRegSelect();
        } catch(e) {}
    }

    async function uploadRegulation() {
        const name = document.getElementById('reg-name').value.trim();
        const shortName = document.getElementById('reg-short').value.trim();
        const jurisdiction = document.getElementById('reg-jurisdiction').value.trim();
        const fullText = document.getElementById('reg-text').value.trim();

        if (!name || !shortName || !fullText) {
            showComplianceStatus('reg-upload-status', 'Please fill in name, short name, and text.', 'error');
            return;
        }

        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Analyzing...';

        try {
            const resp = await fetch('/api/regulations/upload', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, short_name: shortName, jurisdiction, full_text: fullText}),
            });
            const reg = await resp.json();

            // Extract tuples
            const tupleResp = await fetch(`/api/regulations/${reg.id}/extract-tuples`, {method: 'POST'});
            const tupleData = await tupleResp.json();

            // Build eventic graph
            const graphResp = await fetch('/api/eventic-graph/build', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({regulation_id: reg.id}),
            });
            const graphData = await graphResp.json();

            showComplianceStatus('reg-upload-status',
                `Uploaded "${shortName}" - extracted ${tupleData.count} tuples, built graph with ${graphData.nodes.length} nodes.`, 'success');

            renderTuples(tupleData.tuples);
            renderGraph(graphData);

            await loadRegulations();

            document.getElementById('reg-name').value = '';
            document.getElementById('reg-short').value = '';
            document.getElementById('reg-jurisdiction').value = '';
            document.getElementById('reg-text').value = '';
        } catch(e) {
            showComplianceStatus('reg-upload-status', 'Upload failed: ' + e.message, 'error');
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload & Analyze';
        }
    }

    async function runComplianceCheck() {
        const regId = document.getElementById('check-regulation').value;
        const businessText = document.getElementById('check-business-text').value.trim();

        if (!regId || !businessText) {
            showComplianceStatus('check-status', 'Select a regulation and enter business text.', 'error');
            return;
        }

        checkBtn.disabled = true;
        checkBtn.textContent = 'Checking...';

        try {
            const resp = await fetch('/api/compliance/check', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({regulation_id: parseInt(regId), business_text: businessText}),
            });
            const data = await resp.json();

            renderCheckResults(data.results);
            showComplianceStatus('check-status', `Analysis complete - ${data.results.length} chunks evaluated.`, 'success');
        } catch(e) {
            showComplianceStatus('check-status', 'Check failed: ' + e.message, 'error');
        } finally {
            checkBtn.disabled = false;
            checkBtn.textContent = 'Run Compliance Check';
        }
    }

    function renderRegList() {
        const el = document.getElementById('reg-list');
        if (!regulations.length) {
            el.innerHTML = '<p class="muted">No regulations uploaded yet.</p>';
            return;
        }
        el.innerHTML = regulations.map(r => `
            <div class="reg-item" data-id="${r.id}">
                <span class="reg-short">${esc(r.short_name)}</span>
                <span class="reg-meta">${esc(r.name)} ${r.jurisdiction ? '(' + esc(r.jurisdiction) + ')' : ''}</span>
            </div>
        `).join('');

        el.querySelectorAll('.reg-item').forEach(item => {
            item.addEventListener('click', () => viewRegTuples(item.dataset.id));
        });
    }

    function updateRegSelect() {
        const sel = document.getElementById('check-regulation');
        sel.innerHTML = '<option value="">-- Select regulation --</option>' +
            regulations.map(r => `<option value="${r.id}">${esc(r.short_name)} - ${esc(r.name)}</option>`).join('');
    }

    async function viewRegTuples(regId) {
        try {
            const resp = await fetch(`/api/regulations/${regId}/tuples`);
            const data = await resp.json();
            renderTuples(data.tuples);

            const graphResp = await fetch('/api/eventic-graph/build', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({regulation_id: parseInt(regId)}),
            });
            const graphData = await graphResp.json();
            renderGraph(graphData);
        } catch(e) {}
    }

    function renderTuples(tuples) {
        const card = document.getElementById('tuples-card');
        const el = document.getElementById('tuples-list');
        card.style.display = 'block';

        if (!tuples || !tuples.length) {
            el.innerHTML = '<p class="muted">No tuples extracted.</p>';
            return;
        }

        el.innerHTML = tuples.map(t => `
            <div class="tuple-item">
                <span class="tuple-type ${t.tuple_type}">${t.tuple_type}</span>
                ${t.deontic_modal ? `<span class="tuple-type">${t.deontic_modal}</span>` : ''}
                <div style="margin-top:4px;">${esc(t.source_statement || '')}</div>
                ${t.verb ? `<div style="color:#6b7280;font-size:0.7rem;margin-top:2px;">verb: <b>${esc(t.verb)}</b></div>` : ''}
            </div>
        `).join('');
    }

    function renderGraph(data) {
        const card = document.getElementById('graph-card');
        const el = document.getElementById('graph-viz');
        card.style.display = 'block';

        if (!data.nodes || !data.nodes.length) {
            el.innerHTML = '<p class="muted">No graph data.</p>';
            return;
        }

        let html = '<div style="margin-bottom:8px;font-weight:600;">Nodes</div>';
        html += data.nodes.map(n =>
            `<span class="graph-node ${n.node_type}">${esc(n.text)}</span>`
        ).join('');

        html += '<div style="margin-top:12px;margin-bottom:8px;font-weight:600;">Edges</div>';
        const nodeMap = {};
        data.nodes.forEach(n => nodeMap[n.id] = n.text);

        html += data.edges.map(e =>
            `<div class="graph-edge"><b>${esc(nodeMap[e.source] || '?')}</b> &mdash;<i>${esc(e.relation)}</i>&mdash;&gt; <b>${esc(nodeMap[e.target] || '?')}</b></div>`
        ).join('');

        el.innerHTML = html;
    }

    function renderCheckResults(results) {
        const card = document.getElementById('check-results-card');
        const el = document.getElementById('check-results');
        card.style.display = 'block';

        if (!results.length) {
            el.innerHTML = '<p class="muted">No results.</p>';
            return;
        }

        el.innerHTML = results.map(r => `
            <div class="check-result-item ${r.result}">
                <span class="result-badge">${r.result.replace('_', ' ')}</span>
                <div class="result-chunk">"${esc(r.chunk.substring(0, 150))}${r.chunk.length > 150 ? '...' : ''}"</div>
                <div class="result-explanation">${esc(r.explanation)}</div>
            </div>
        `).join('');
    }

    function showComplianceStatus(id, message, type) {
        const el = document.getElementById(id);
        el.textContent = message;
        el.className = `status ${type}`;
        el.classList.remove('hidden');
        setTimeout(() => el.classList.add('hidden'), 8000);
    }
})();
