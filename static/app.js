const API = '';

let parsedData = null;
let selectedFile = null;
let frameworksCache = [];

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initSearch();
    initCoverage();
    initVersions();
    initUpload();
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
// Control Lookup
// ---------------------------------------------------------------------------

function initSearch() {
    document.getElementById('search-btn').addEventListener('click', performSearch);
    document.getElementById('search-input').addEventListener('keypress', e => {
        if (e.key === 'Enter') performSearch();
    });
    document.getElementById('clear-btn').addEventListener('click', () => {
        document.getElementById('search-input').value = '';
        document.getElementById('search-results').innerHTML =
            '<div class="empty-state"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="20" cy="20" r="14"/><path d="M30 30l12 12" stroke-linecap="round"/></svg><p>Search for a control to get started.</p></div>';
        document.getElementById('mapping-results').innerHTML =
            '<div class="empty-state"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 12h36M6 24h24M6 36h30" stroke-linecap="round"/></svg><p>Select a control to view its mappings.</p></div>';
    });
}

async function performSearch() {
    const query = document.getElementById('search-input').value.trim();
    const frameworkId = document.getElementById('framework-filter').value;
    if (!query) return;

    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '<div class="loading">Searching</div>';
    document.getElementById('mapping-results').innerHTML =
        '<div class="empty-state"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 12h36M6 24h24M6 36h30" stroke-linecap="round"/></svg><p>Select a control to view its mappings.</p></div>';

    try {
        let url = `${API}/api/controls?q=${encodeURIComponent(query)}`;
        if (frameworkId) url += `&framework_id=${frameworkId}`;

        const res = await fetch(url);
        const controls = await res.json();

        if (controls.length === 0) {
            resultsDiv.innerHTML = '<div class="empty-state"><p>No controls found.</p></div>';
            return;
        }

        resultsDiv.innerHTML = `<div class="results-heading">Found ${controls.length} control${controls.length > 1 ? 's' : ''}</div>`;

        controls.slice(0, 50).forEach(ctrl => {
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
                showMappings(ctrl);
            });
            resultsDiv.appendChild(item);
        });
    } catch (err) {
        resultsDiv.innerHTML = `<div class="empty-state"><p>Error: ${esc(err.message)}</p></div>`;
    }
}

async function showMappings(ctrl) {
    const div = document.getElementById('mapping-results');
    div.innerHTML = '<div class="loading">Loading mappings</div>';

    try {
        const res = await fetch(
            `${API}/api/mappings/${encodeURIComponent(ctrl.control_id)}?framework_id=${ctrl.framework_id}`
        );
        const data = await res.json();

        if (data.detail) {
            div.innerHTML = `<div class="empty-state"><p>${esc(data.detail)}</p></div>`;
            return;
        }

        const fwName = ctrl.framework_short_name || data.source.framework_short_name;
        let html = `<div class="mappings-header"><h2>${esc(ctrl.control_id)}</h2><span class="fw-badge">${esc(fwName)}</span></div>`;
        html += `<div class="mappings-subtitle">${esc(data.source.title)}</div>`;

        if (!data.mappings || data.mappings.length === 0) {
            html += '<div class="empty-state"><p>No mappings found for this control.</p></div>';
        } else {
            const grouped = {};
            data.mappings.forEach(m => {
                (grouped[m.framework_short_name] ||= []).push(m);
            });

            for (const [fw, mappings] of Object.entries(grouped)) {
                html += `<div class="mapping-group"><div class="mapping-group-title">${esc(fw)} (${mappings.length})</div>`;
                mappings.forEach(m => {
                    const cls = m.source_type === 'official' ? 'badge-official' : 'badge-ai';
                    const label = m.source_type === 'official' ? 'Official' : 'AI';
                    const fwObj = frameworksCache.find(f => f.short_name === m.framework_short_name);
                    const fwId = fwObj ? fwObj.id : '';
                    html += `
                        <div class="mapping-item clickable" data-control-id="${esc(m.control_id)}" data-framework-id="${fwId}" data-framework-short-name="${esc(m.framework_short_name)}">
                            <span class="m-id">${esc(m.control_id)}</span>
                            <span class="badge ${cls}">${label}</span>
                            <span class="m-title">${esc(m.title)}</span>
                            <span class="drill-arrow">&#8594;</span>
                        </div>`;
                });
                html += '</div>';
            }
        }
        div.innerHTML = html;

        div.querySelectorAll('.mapping-item.clickable').forEach(el => {
            el.addEventListener('click', () => {
                showMappings({
                    control_id: el.dataset.controlId,
                    framework_id: parseInt(el.dataset.frameworkId) || 0,
                    framework_short_name: el.dataset.frameworkShortName,
                });
            });
        });
    } catch (err) {
        div.innerHTML = `<div class="empty-state"><p>Error: ${esc(err.message)}</p></div>`;
    }
}

// ---------------------------------------------------------------------------
// Coverage Analysis
// ---------------------------------------------------------------------------

function initCoverage() {
    document.getElementById('analyze-btn').addEventListener('click', runCoverage);
}

async function runCoverage() {
    const srcId = document.getElementById('source-fw').value;
    const tgtId = document.getElementById('target-fw').value;
    if (!srcId || !tgtId || srcId === tgtId) {
        alert('Select two different frameworks.');
        return;
    }

    const resultsDiv = document.getElementById('coverage-results');
    resultsDiv.classList.remove('hidden');

    ['stat-total','stat-mapped','stat-unmapped','stat-percent'].forEach(id => {
        document.getElementById(id).textContent = '...';
    });

    try {
        const [coverageRes, tableRes] = await Promise.all([
            fetch(`${API}/api/coverage?source=${srcId}&target=${tgtId}`),
            fetch(`${API}/api/coverage/table?source=${srcId}&target=${tgtId}`),
        ]);

        const coverage = await coverageRes.json();
        const table = await tableRes.json();

        document.getElementById('stat-total').textContent = coverage.total_source_controls;
        document.getElementById('stat-mapped').textContent = coverage.mapped_controls;
        document.getElementById('stat-unmapped').textContent = coverage.unmapped_controls;
        document.getElementById('stat-percent').textContent = coverage.coverage_percentage + '%';
        document.getElementById('coverage-bar').style.width = coverage.coverage_percentage + '%';

        const unmappedList = document.getElementById('unmapped-list');
        document.getElementById('unmapped-count').textContent = `(${coverage.unmapped_control_ids.length})`;
        unmappedList.innerHTML = coverage.unmapped_control_ids.length > 0
            ? coverage.unmapped_control_ids.map(id => `<div class="detail-item">${esc(id)}</div>`).join('')
            : '<div class="empty-state"><p>All controls are mapped.</p></div>';

        const gapList = document.getElementById('gap-list');
        document.getElementById('gap-count').textContent = `(${coverage.gap_controls.length})`;
        gapList.innerHTML = coverage.gap_controls.length > 0
            ? coverage.gap_controls.map(id => `<div class="detail-item">${esc(id)}</div>`).join('')
            : '<div class="empty-state"><p>Full coverage.</p></div>';

        renderMappingTable(table);
    } catch (err) {
        alert('Coverage analysis failed: ' + err.message);
    }
}

function renderMappingTable(table) {
    const container = document.getElementById('mapping-table-container');
    if (!table.rows || table.rows.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No data.</p></div>';
        return;
    }

    let html = `<table>
        <thead><tr>
            <th>${esc(table.source_framework)}</th>
            <th>Title</th>
            <th>${esc(table.target_framework)}</th>
            <th>Title</th>
            <th>Type</th>
        </tr></thead><tbody>`;

    table.rows.forEach(r => {
        const isGap = r.source_type === 'gap';
        html += `<tr>
            <td>${esc(r.source_id)}</td>
            <td>${esc(r.source_title)}</td>
            <td class="${isGap ? 'gap' : ''}">${isGap ? 'No mapping' : esc(r.target_id)}</td>
            <td>${esc(r.target_title)}</td>
            <td><span class="badge ${isGap ? '' : 'badge-official'}">${esc(r.source_type)}</span></td>
        </tr>`;
    });

    container.innerHTML = html + '</tbody></table>';
}

// ---------------------------------------------------------------------------
// Version Tracking
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
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}
