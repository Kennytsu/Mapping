// API Base URL
const API = '';

// State
let parsedData = null;
let selectedFile = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initSearch();
    initUpload();
    loadFrameworks();
});

// Tab navigation
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });
}

// Load frameworks for filter
async function loadFrameworks() {
    try {
        const res = await fetch(`${API}/api/frameworks`);
        const frameworks = await res.json();
        
        const select = document.getElementById('framework-filter');
        frameworks.forEach(fw => {
            const option = document.createElement('option');
            option.value = fw.id;
            option.textContent = `${fw.short_name} (${fw.control_count} controls)`;
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load frameworks:', err);
    }
}

// Search functionality
function initSearch() {
    const searchBtn = document.getElementById('search-btn');
    const searchInput = document.getElementById('search-input');
    
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });
}

async function performSearch() {
    const query = document.getElementById('search-input').value.trim();
    const frameworkId = document.getElementById('framework-filter').value;
    
    if (!query) return;
    
    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
    
    try {
        let url = `${API}/api/controls?q=${encodeURIComponent(query)}`;
        if (frameworkId) url += `&framework_id=${frameworkId}`;
        
        const res = await fetch(url);
        const controls = await res.json();
        
        if (controls.length === 0) {
            resultsDiv.innerHTML = '<div class="empty-state">No controls found matching your search.</div>';
            return;
        }
        
        resultsDiv.innerHTML = `<h3>Found ${controls.length} controls</h3>`;
        
        controls.slice(0, 20).forEach(ctrl => {
            const item = document.createElement('div');
            item.className = 'result-item';
            item.innerHTML = `
                <h3>${ctrl.control_id}</h3>
                <span class="framework">${ctrl.framework_short_name}</span>
                <span class="category">${ctrl.category || ''}</span>
                <p>${ctrl.title || ''}</p>
            `;
            item.addEventListener('click', () => showMappings(ctrl));
            resultsDiv.appendChild(item);
        });
    } catch (err) {
        resultsDiv.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
}

async function showMappings(ctrl) {
    const mappingsDiv = document.getElementById('mapping-results');
    mappingsDiv.innerHTML = '<div class="loading">Loading mappings...</div>';
    
    // Highlight selected
    document.querySelectorAll('.result-item').forEach(i => i.classList.remove('selected'));
    event.currentTarget.classList.add('selected');
    
    try {
        const res = await fetch(`${API}/api/mappings/${encodeURIComponent(ctrl.control_id)}?framework_id=${ctrl.framework_id}`);
        const data = await res.json();
        
        if (data.error) {
            mappingsDiv.innerHTML = `<div class="empty-state">${data.error}</div>`;
            return;
        }
        
        let html = `<h2>Mappings for ${ctrl.control_id}</h2>`;
        html += `<p><strong>${data.source.title}</strong></p>`;
        
        if (!data.mappings || data.mappings.length === 0) {
            html += '<div class="empty-state">No mappings found for this control.</div>';
        } else {
            // Group by framework
            const grouped = {};
            data.mappings.forEach(m => {
                if (!grouped[m.framework_short_name]) {
                    grouped[m.framework_short_name] = [];
                }
                grouped[m.framework_short_name].push(m);
            });
            
            for (const [fw, mappings] of Object.entries(grouped)) {
                html += `<div class="mapping-group">`;
                html += `<h3>${fw}</h3>`;
                mappings.forEach(m => {
                    const badge = m.source_type === 'official' ? 'Official' : 'Manual';
                    html += `
                        <div class="mapping-item">
                            <strong>${m.control_id}</strong>
                            <span class="badge">${badge}</span>
                            <span class="title">${m.title || ''}</span>
                        </div>
                    `;
                });
                html += `</div>`;
            }
        }
        
        mappingsDiv.innerHTML = html;
    } catch (err) {
        mappingsDiv.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
}

// Upload functionality
function initUpload() {
    const fileDrop = document.getElementById('file-drop');
    const fileInput = document.getElementById('file-input');
    const parseBtn = document.getElementById('parse-btn');
    const importBtn = document.getElementById('import-btn');
    
    // Drag and drop
    fileDrop.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileDrop.classList.add('dragover');
    });
    
    fileDrop.addEventListener('dragleave', () => {
        fileDrop.classList.remove('dragover');
    });
    
    fileDrop.addEventListener('drop', (e) => {
        e.preventDefault();
        fileDrop.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });
    
    parseBtn.addEventListener('click', parseDocument);
    importBtn.addEventListener('click', importData);
}

function handleFile(file) {
    selectedFile = file;
    document.getElementById('file-name').textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    document.getElementById('parse-btn').disabled = false;
    
    // Reset results
    document.getElementById('parse-results').classList.add('hidden');
    document.getElementById('import-status').classList.add('hidden');
}

async function parseDocument() {
    if (!selectedFile) return;
    
    const parseBtn = document.getElementById('parse-btn');
    parseBtn.disabled = true;
    parseBtn.textContent = 'Parsing...';
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('doc_type', document.getElementById('doc-type').value);
    
    try {
        const res = await fetch(`${API}/api/upload`, {
            method: 'POST',
            body: formData
        });
        
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
        parseBtn.disabled = false;
        parseBtn.textContent = 'Parse Document';
    }
}

function showParsedData(data) {
    const resultsDiv = document.getElementById('parse-results');
    resultsDiv.classList.remove('hidden');
    
    // Controls table
    document.getElementById('control-count').textContent = `(${data.controls.length})`;
    const controlsTable = document.getElementById('controls-table');
    
    if (data.controls.length > 0) {
        let html = '<table><thead><tr><th>ID</th><th>Category</th></tr></thead><tbody>';
        data.controls.slice(0, 100).forEach(c => {
            html += `<tr><td>${c.control_id}</td><td>${c.category || ''}</td></tr>`;
        });
        html += '</tbody></table>';
        controlsTable.innerHTML = html;
    } else {
        controlsTable.innerHTML = '<div class="empty-state">No controls found</div>';
    }
    
    // Mappings table
    document.getElementById('mapping-count').textContent = `(${data.mappings.length})`;
    const mappingsTable = document.getElementById('mappings-table');
    
    if (data.mappings.length > 0) {
        let html = '<table><thead><tr><th>Source</th><th>Target</th></tr></thead><tbody>';
        data.mappings.slice(0, 100).forEach(m => {
            html += `<tr><td>${m.source}</td><td>${m.target}</td></tr>`;
        });
        html += '</tbody></table>';
        mappingsTable.innerHTML = html;
    } else {
        mappingsTable.innerHTML = '<div class="empty-state">No mappings found</div>';
    }
}

async function importData() {
    if (!parsedData) return;
    
    const importBtn = document.getElementById('import-btn');
    importBtn.disabled = true;
    importBtn.textContent = 'Importing...';
    
    try {
        const res = await fetch(`${API}/api/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(parsedData)
        });
        
        const result = await res.json();
        
        if (result.success) {
            showStatus(`Imported ${result.controls_added} controls and ${result.mappings_added} mappings`, 'success');
        } else {
            showStatus(`Import failed: ${result.error}`, 'error');
        }
    } catch (err) {
        showStatus(`Error: ${err.message}`, 'error');
    } finally {
        importBtn.disabled = false;
        importBtn.textContent = 'Import to Database';
    }
}

function showStatus(message, type) {
    const statusDiv = document.getElementById('import-status');
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.classList.remove('hidden');
}
