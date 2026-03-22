// ApplicationAgent — Sidebar Navigation

let sidebarCollapsed = false;
let activeResumeId = null;
let activeFilter = null;

// ── Sidebar toggle ────────────────────────────────────────────────────────────

function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    document.getElementById('sidebar').classList.toggle('collapsed', sidebarCollapsed);
}

// ── Load sidebar resumes ──────────────────────────────────────────────────────

async function loadSidebarResumes() {
    try {
        const res = await fetch('/api/resumes');
        const data = await res.json();
        renderSidebarResumes(data.resumes);
        return data.resumes;
    } catch (e) {
        document.getElementById('sidebar-resumes').innerHTML =
            '<div class="sidebar-item muted">Error loading</div>';
        return [];
    }
}

function renderSidebarResumes(resumes) {
    const container = document.getElementById('sidebar-resumes');
    if (!resumes.length) {
        container.innerHTML = '<div class="sidebar-item muted">No resumes</div>';
        return;
    }
    container.innerHTML = resumes.map(r => `
        <div class="sidebar-item" data-resume="${r.name}" data-resume-id="${r.id}"
             onclick="sidebarSelectResume('${r.name}', ${r.id})">
            <span class="sidebar-icon">▸</span>
            <span class="sidebar-name">${r.name}</span>
            <span class="sidebar-count">(${r.stats ? r.stats.total_jobs : 0})</span>
            <button class="sidebar-gear" onclick="editResumeFromSidebar(event, ${r.id})" title="Edit resume">⚙</button>
        </div>
    `).join('');
}

// ── Resume selection ──────────────────────────────────────────────────────────

function sidebarSelectResume(name, id) {
    activeResumeId = id;
    activeFilter = null;

    // Highlight active item
    document.querySelectorAll('.sidebar-item[data-resume]').forEach(el => {
        el.classList.toggle('active', el.dataset.resume === name);
    });

    // Sync the main dropdown
    const mainSelect = document.getElementById('resume-select');
    if (mainSelect && mainSelect.value !== name) {
        mainSelect.value = name;
    }

    // Show results view and load results + query filters
    showResultsView();
    resetFilter();
    loadResults(name);
    loadQueryFilters(id);
}

function editResumeFromSidebar(event, id) {
    event.stopPropagation();
    showResumeDetail(id);
}

// Called from app.js onResumeChange — syncs sidebar highlight
function syncSidebarToResume(name) {
    document.querySelectorAll('.sidebar-item[data-resume]').forEach(el => {
        el.classList.toggle('active', el.dataset.resume === name);
    });
}

// ── Results filter ────────────────────────────────────────────────────────────

function applyFilter(decision) {
    activeFilter = decision;

    document.querySelectorAll('.filter-item').forEach(el => {
        const match = decision ? el.dataset.decision === decision : el.dataset.decision === 'all';
        el.classList.toggle('active', match);
    });

    const rows = document.querySelectorAll('#results-table-container tbody tr');
    rows.forEach(row => {
        if (!decision) {
            row.style.display = '';
            return;
        }
        const decisionCell = row.querySelector('td:nth-child(2)');
        row.style.display = (decisionCell && decisionCell.textContent.trim() === decision)
            ? '' : 'none';
    });
}

function resetFilter() {
    applyFilter(null);
}

// ── Query filters ─────────────────────────────────────────────────────────────

let activeQueryFilter = null;

async function loadQueryFilters(resumeId) {
    const container = document.getElementById('sidebar-queries');
    if (!container) return;
    container.innerHTML = '<div class="sidebar-item muted" style="font-size:11px">Loading...</div>';
    try {
        const res = await fetch(`/api/resumes/${resumeId}/queries`);
        const data = await res.json();
        renderQueryFilters(data.queries);
    } catch (e) {
        container.innerHTML = '<div class="sidebar-item muted" style="font-size:11px">—</div>';
    }
}

function renderQueryFilters(queries) {
    const container = document.getElementById('sidebar-queries');
    if (!container) return;
    activeQueryFilter = null;
    if (!queries.length) {
        container.innerHTML = '<div class="sidebar-item muted" style="font-size:11px">No query data yet</div>';
        return;
    }
    const total = queries.reduce((s, q) => s + q.count, 0);
    container.innerHTML = `
        <div class="sidebar-item filter-item active" data-query="" onclick="applyQueryFilter(null, this)">
            <span class="sidebar-icon">●</span>
            <span class="sidebar-name">All queries</span>
            <span class="sidebar-count">(${total})</span>
        </div>
        ${queries.map(q => `
            <div class="sidebar-item filter-item" data-query="${q.query}" onclick="applyQueryFilter('${q.query.replace(/'/g, "\\'")}', this)">
                <span class="sidebar-icon">○</span>
                <span class="sidebar-name">${q.query}</span>
                <span class="sidebar-count">(${q.count})</span>
            </div>
        `).join('')}
    `;
}

function applyQueryFilter(query, el) {
    activeQueryFilter = query;
    document.querySelectorAll('#sidebar-queries .filter-item').forEach(item => {
        const isActive = item === el;
        item.classList.toggle('active', isActive);
        const icon = item.querySelector('.sidebar-icon');
        if (icon) icon.textContent = isActive ? '●' : '○';
    });
    // Filter table rows by search_query data attribute
    const rows = document.querySelectorAll('#results-table-container tbody tr');
    rows.forEach(row => {
        if (!query) { row.style.display = ''; return; }
        row.style.display = (row.dataset.searchQuery === query) ? '' : 'none';
    });
}

// Called by app.js after loadResults() rebuilds the table
function reapplyFilter() {
    if (activeFilter) applyFilter(activeFilter);
}

// ── Resume detail view ────────────────────────────────────────────────────────

async function showResumeDetail(resumeId) {
    activeResumeId = resumeId;
    try {
        const res = await fetch(`/api/resumes/${resumeId}`);
        if (!res.ok) throw new Error('Not found');
        const resume = await res.json();
        document.getElementById('results-view').classList.add('hidden');
        const detail = document.getElementById('resume-detail-view');
        detail.innerHTML = buildResumeDetailHTML(resume);
        detail.classList.remove('hidden');
    } catch (e) {
        alert('Failed to load resume detail: ' + e.message);
    }
}

function showResultsView() {
    document.getElementById('resume-detail-view').classList.add('hidden');
    document.getElementById('results-view').classList.remove('hidden');
}

function buildResumeDetailHTML(resume) {
    const criteria = resume.search_criteria || {};
    const queries = criteria.search_queries || [];
    const excludes = criteria.exclude_keywords || [];
    const locations = criteria.location_preferences || [];
    const stats = resume.stats || {};

    const queryRows = queries.map((q, i) => `
        <div class="detail-query-row" id="qrow-${resume.id}-${i}">
            <input class="detail-query-keywords" value="${q.keywords || ''}" placeholder="Keywords">
            <input class="detail-query-location" value="${q.location || ''}" placeholder="City, State">
            <select class="detail-query-max">
                ${[5,10,15,20,25,30].map(n =>
                    `<option value="${n}" ${n === (q.max_results||15) ? 'selected' : ''}>${n}</option>`
                ).join('')}
            </select>
            <button class="remove-btn" onclick="this.closest('.detail-query-row').remove()">×</button>
        </div>
    `).join('');

    return `
        <div class="resume-detail">
            <div class="resume-detail-header">
                <div>
                    <h2>Resume: ${resume.name}</h2>
                    <div class="muted" style="font-size:11px;margin-top:4px">
                        ${resume.word_count ? resume.word_count + ' words' : ''}
                        ${resume.last_updated ? '· Updated: ' + resume.last_updated : ''}
                    </div>
                </div>
                <div class="detail-header-actions">
                    <button onclick="showResultsView()">← Results</button>
                    <button class="btn-danger" onclick="confirmDeleteResume(${resume.id}, '${resume.name}', ${stats.total_jobs || 0})">Delete</button>
                </div>
            </div>

            <!-- Resume File -->
            <div class="resume-detail-section">
                <div class="detail-section-header">
                    <h3>📄 Resume File</h3>
                </div>
                <div class="muted" style="font-size:11px;margin-bottom:8px">${resume.file_path}</div>
                <label class="detail-file-label">
                    Upload New Version (.txt or .pdf)
                    <input type="file" id="detail-upload-file-${resume.id}" accept=".txt,.pdf">
                </label>
                <button style="margin-top:8px" onclick="uploadNewVersion(${resume.id})">Upload</button>
                <p id="detail-upload-msg-${resume.id}" class="muted" style="font-size:11px;margin-top:4px"></p>
            </div>

            <!-- Search Queries -->
            <div class="resume-detail-section">
                <div class="detail-section-header">
                    <h3>🔍 Search Queries</h3>
                    <button onclick="addDetailQueryRow(${resume.id})">+ Add</button>
                </div>
                <div id="detail-query-rows-${resume.id}">
                    ${queryRows || '<div class="muted" style="font-size:12px">No queries — add one below.</div>'}
                </div>
                <div class="detail-save-row">
                    <button onclick="saveDetailCriteria(${resume.id})">Save Queries</button>
                </div>
                <p id="detail-queries-msg-${resume.id}" class="muted" style="font-size:11px;margin-top:4px"></p>
            </div>

            <!-- Exclusions -->
            <div class="resume-detail-section">
                <div class="detail-section-header">
                    <h3>🚫 Exclude Keywords</h3>
                </div>
                <div class="field-hint" style="margin-bottom:6px">Jobs containing any of these will be excluded. One per line.</div>
                <textarea id="detail-excludes-${resume.id}" class="detail-textarea">${excludes.join('\n')}</textarea>
                <div class="detail-save-row">
                    <button onclick="saveDetailExcludes(${resume.id})">Save Exclusions</button>
                </div>
                <p id="detail-excludes-msg-${resume.id}" class="muted" style="font-size:11px;margin-top:4px"></p>
            </div>

            <!-- Location Preferences -->
            <div class="resume-detail-section">
                <div class="detail-section-header">
                    <h3>📍 Location Preferences</h3>
                </div>
                <div class="field-hint" style="margin-bottom:6px">Jobs not matching any of these are flagged incompatible. One per line.</div>
                <textarea id="detail-locations-${resume.id}" class="detail-textarea">${locations.join('\n')}</textarea>
                <div class="detail-save-row">
                    <button onclick="saveDetailLocations(${resume.id})">Save Locations</button>
                </div>
                <p id="detail-locations-msg-${resume.id}" class="muted" style="font-size:11px;margin-top:4px"></p>
            </div>

            <!-- Stats -->
            <div class="resume-detail-section">
                <div class="detail-section-header">
                    <h3>📊 Stats</h3>
                </div>
                <div class="detail-stats">
                    <div>Total analyzed: <strong>${stats.total_jobs || 0}</strong></div>
                    <div>Strong matches: <strong class="decision-STRONG_MATCH">${stats.strong_matches || 0}</strong></div>
                    <div>Applications: <strong>${stats.applications || 0}</strong></div>
                </div>
            </div>
        </div>
    `;
}

// ── Upload new resume version ─────────────────────────────────────────────────

async function uploadNewVersion(resumeId) {
    const input = document.getElementById(`detail-upload-file-${resumeId}`);
    const msgEl = document.getElementById(`detail-upload-msg-${resumeId}`);
    if (!input || !input.files.length) {
        msgEl.textContent = 'Select a file first.';
        return;
    }

    const file = input.files[0];
    const filename = file.name.toLowerCase();
    if (!filename.endsWith('.txt') && !filename.endsWith('.pdf')) {
        msgEl.textContent = 'File must be .txt or .pdf';
        return;
    }

    // Read as base64
    const fileData = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = e => resolve(e.target.result.split(',')[1]);
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
    });

    try {
        msgEl.textContent = 'Uploading...';
        const res = await fetch(`/api/resumes/${resumeId}/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, file_data: fileData }),
        });
        const data = await res.json();
        if (!res.ok) { msgEl.textContent = data.error || 'Upload failed.'; return; }
        msgEl.textContent = 'Uploaded successfully.';
        showResumeDetail(resumeId);
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
    }
}

// ── Detail panel inline editing ───────────────────────────────────────────────

function addDetailQueryRow(resumeId) {
    const container = document.getElementById(`detail-query-rows-${resumeId}`);
    // Clear any "no queries" placeholder text
    if (container.querySelector('.muted')) container.innerHTML = '';
    const idx = container.querySelectorAll('.detail-query-row').length;
    const row = document.createElement('div');
    row.className = 'detail-query-row';
    row.id = `qrow-${resumeId}-${idx}`;
    row.innerHTML = `
        <input class="detail-query-keywords" value="" placeholder="Keywords">
        <input class="detail-query-location" value="" placeholder="City, State">
        <select class="detail-query-max">
            ${[5,10,15,20,25,30].map(n =>
                `<option value="${n}" ${n === 15 ? 'selected' : ''}>${n}</option>`
            ).join('')}
        </select>
        <button class="remove-btn" onclick="this.closest('.detail-query-row').remove()">×</button>
    `;
    container.appendChild(row);
}

async function _saveCriteriaField(resumeId, patchFn, msgId) {
    const msgEl = document.getElementById(msgId);
    // Load current criteria from server
    try {
        const res = await fetch(`/api/resumes/${resumeId}`);
        const resume = await res.json();
        const criteria = resume.search_criteria || {};
        patchFn(criteria);
        const putRes = await fetch(`/api/resumes/${resumeId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ search_criteria: criteria })
        });
        const data = await putRes.json();
        if (!putRes.ok) throw new Error(data.error || 'Save failed');
        msgEl.textContent = 'Saved.';
        setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 2000);
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
    }
}

function saveDetailCriteria(resumeId) {
    const container = document.getElementById(`detail-query-rows-${resumeId}`);
    const rows = container.querySelectorAll('.detail-query-row');
    const queries = [];
    rows.forEach(row => {
        const kw = row.querySelector('.detail-query-keywords').value.trim();
        const loc = row.querySelector('.detail-query-location').value.trim();
        const max = parseInt(row.querySelector('.detail-query-max').value);
        if (kw && loc) queries.push({ keywords: kw, location: loc, max_results: max });
    });
    _saveCriteriaField(resumeId, c => { c.search_queries = queries; },
        `detail-queries-msg-${resumeId}`);
}

function saveDetailExcludes(resumeId) {
    const raw = document.getElementById(`detail-excludes-${resumeId}`).value;
    const keywords = raw.split('\n').map(s => s.trim()).filter(Boolean);
    _saveCriteriaField(resumeId, c => { c.exclude_keywords = keywords; },
        `detail-excludes-msg-${resumeId}`);
}

function saveDetailLocations(resumeId) {
    const raw = document.getElementById(`detail-locations-${resumeId}`).value;
    const locations = raw.split('\n').map(s => s.trim()).filter(Boolean);
    _saveCriteriaField(resumeId, c => { c.location_preferences = locations; },
        `detail-locations-msg-${resumeId}`);
}

// ── Delete resume ─────────────────────────────────────────────────────────────

function confirmDeleteResume(resumeId, name, jobCount) {
    document.getElementById('delete-resume-name').textContent = name;
    document.getElementById('delete-resume-count').textContent = jobCount;
    document.getElementById('delete-resume-id').value = resumeId;
    document.getElementById('delete-resume-modal').classList.remove('hidden');
}

function closeDeleteResumeModal() {
    document.getElementById('delete-resume-modal').classList.add('hidden');
}

async function confirmDeleteResumeAction() {
    const resumeId = document.getElementById('delete-resume-id').value;
    closeDeleteResumeModal();
    try {
        const res = await fetch(`/api/resumes/${resumeId}?confirm=true`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Delete failed.'); return; }
        showResultsView();
        await loadSidebarResumes();
        await loadResumes();  // refresh main dropdown
        loadResults(document.getElementById('resume-select').value);
    } catch (e) {
        alert('Delete failed: ' + e.message);
    }
}

// ── Edit search criteria ──────────────────────────────────────────────────────

let _criteriaResumeId = null;

function openCriteriaModal(resumeId, criteriaJsonString) {
    _criteriaResumeId = resumeId;
    let parsed;
    try { parsed = JSON.parse(criteriaJsonString); } catch { parsed = {}; }
    document.getElementById('criteria-json').value = JSON.stringify(parsed, null, 2);
    document.getElementById('criteria-error').classList.add('hidden');
    document.getElementById('criteria-modal').classList.remove('hidden');
}

function closeCriteriaModal() {
    document.getElementById('criteria-modal').classList.add('hidden');
    _criteriaResumeId = null;
}

async function saveCriteria() {
    const jsonText = document.getElementById('criteria-json').value;
    const errorEl = document.getElementById('criteria-error');
    let criteria;
    try {
        criteria = JSON.parse(jsonText);
    } catch (e) {
        errorEl.textContent = 'Invalid JSON: ' + e.message;
        errorEl.classList.remove('hidden');
        return;
    }
    errorEl.classList.add('hidden');
    try {
        const res = await fetch(`/api/resumes/${_criteriaResumeId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ search_criteria: criteria })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Save failed');
        closeCriteriaModal();
        showResumeDetail(_criteriaResumeId);
    } catch (e) {
        errorEl.textContent = e.message;
        errorEl.classList.remove('hidden');
    }
}
