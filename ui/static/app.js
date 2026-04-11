// ApplicationAgent UI

document.addEventListener('DOMContentLoaded', () => {
    checkApiKeySetup();
    loadResumes();
    loadSidebarResumes();

    document.addEventListener('paste', function(e) {
        if (!analyzeModalOpen) return;
        const items = e.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.type.startsWith('image/')) {
                const file = item.getAsFile();
                if (file) handleScreenshot(file);
                break;
            }
        }
    });

    document.getElementById('screenshot-input').addEventListener('change', function(e) {
        if (e.target.files[0]) handleScreenshot(e.target.files[0]);
    });

    document.getElementById('screenshot-clear').addEventListener('click', function() {
        document.getElementById('screenshot-preview').style.display = 'none';
        document.getElementById('screenshot-zone').querySelector('.screenshot-hint').style.display = 'flex';
        document.getElementById('screenshot-input').value = '';
    });
});

// ── API Key Setup ─────────────────────────────────────────────────────────────

async function checkApiKeySetup() {
    const res = await fetch('/api/settings/status');
    const data = await res.json();
    if (!data.api_key_configured) {
        document.getElementById('settings-modal-close').classList.add('hidden');
        if (data.requires_reentry) {
            const hint = document.getElementById('settings-reentry-hint');
            if (hint) hint.classList.remove('hidden');
        }
        openSettingsModal();
    }
}

function openSettingsModal() {
    document.getElementById('settings-modal').classList.remove('hidden');
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.add('hidden');
    document.getElementById('settings-error').classList.add('hidden');
}

async function saveApiKey() {
    const key = document.getElementById('settings-api-key').value.trim();
    const err = document.getElementById('settings-error');
    if (!key.startsWith('sk-ant-')) {
        err.textContent = 'Invalid key — must start with sk-ant-';
        err.classList.remove('hidden');
        return;
    }
    const res = await fetch('/api/settings/apikey', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({api_key: key})
    });
    const data = await res.json();
    if (data.status === 'ok') {
        window.location.reload();
    } else {
        err.textContent = data.error || 'Failed to save key';
        err.classList.remove('hidden');
    }
}

// ── Resumes ───────────────────────────────────────────────────────────────────

async function loadResumes() {
    const ids = ['resume-select', 'run-resume-select', 'analyze-resume-select'];
    try {
        const res = await fetch('/api/resumes');
        const data = await res.json();
        // API now returns objects with {id, name, ...}; use r.name for option value/label
        const options = data.resumes.length
            ? data.resumes.map(r => `<option value="${r.name}">${r.name}</option>`).join('')
            : '<option value="">No resumes found</option>';
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = options;
        });
        const mainSelect = document.getElementById('resume-select');
        if (mainSelect && mainSelect.value) loadResults(mainSelect.value);
        // Refresh sidebar resume list too
        renderSidebarResumes(data.resumes);
    } catch (e) {
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<option value="">Error loading resumes</option>';
        });
    }
}

function onResumeChange() {
    const resumeType = document.getElementById('resume-select').value;
    syncSidebarToResume(resumeType);
    resetFilter();
    loadResults(resumeType);
}

// ── Results ───────────────────────────────────────────────────────────────────

async function loadResults(resumeType) {
    const container = document.getElementById('results-table-container');
    const countEl = document.getElementById('results-count');
    try {
        const url = resumeType
            ? `/api/results?resume_type=${encodeURIComponent(resumeType)}`
            : '/api/results';
        const res = await fetch(url);
        const data = await res.json();

        if (!data.results || data.results.length === 0) {
            countEl.textContent = '';
            container.innerHTML = '<p class="muted">No results yet. Run the pipeline or check data/ directory.</p>';
            return;
        }

        countEl.textContent = `(${data.count})`;
        container.innerHTML = buildResultsTable(data.results);
        reapplyFilter();
    } catch (e) {
        container.innerHTML = `<p class="muted">Error loading results: ${e.message}</p>`;
    }
}

// ── Delete Job ────────────────────────────────────────────────────────────────

let currentResults = [];
let pendingDelete = null;
let analyzeModalOpen = false;

function openDeleteModal(idx, rowEl) {
    const r = currentResults[idx];
    const job = r.job_metadata || {};
    pendingDelete = { result: r, rowEl };
    document.getElementById('delete-confirm-text').textContent =
        `Remove "${job.title}" at ${job.company}?`;
    document.getElementById('delete-modal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.add('hidden');
    pendingDelete = null;
}

async function confirmDelete() {
    if (!pendingDelete) return;
    const { result, rowEl } = pendingDelete;
    const job = result.job_metadata || {};
    closeDeleteModal();

    try {
        const res = await fetch('/api/delete-job', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: result.id,
                title: job.title || '',
                company: job.company || '',
            })
        });
        if (res.ok) {
            rowEl.remove();
            const remaining = document.querySelectorAll('#results-table-container tbody tr').length;
            document.getElementById('results-count').textContent = remaining ? `(${remaining})` : '';
        }
    } catch (e) {
        console.error('Delete failed:', e);
    }
}

// ── Consider override ────────────────────────────────────────────────────────

function markConsider(jobId, score, btn) {
    fetch(`/api/consider/${jobId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fit_score: score})
    }).then(r => r.json()).then(() => {
        const row = btn.closest('tr');
        const cell = row.querySelector('[data-decision-cell]');
        cell.className = 'decision-CONSIDER';
        cell.textContent = 'CONSIDER';
        btn.remove();
    });
}

// ── Forward to Pipeorgan ─────────────────────────────────────────────────────

async function forwardToForge(jobId) {
    const btn = document.querySelector(`.forge-btn[data-job-id="${jobId}"]`);
    btn.textContent = '→ sending...';
    btn.disabled = true;

    try {
        const resp = await fetch(`/api/forward/${jobId}`, { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            btn.textContent = '✓ queued';
            btn.style.color = '#00aa44';
        } else {
            btn.textContent = '✗ failed';
            btn.style.color = '#ff4444';
            btn.disabled = false;
        }
    } catch (e) {
        btn.textContent = '✗ error';
        btn.style.color = '#ff4444';
        btn.disabled = false;
    }
}

// ── Low-score URL intercept ──────────────────────────────────────────────────

let _pendingUrl = null;

function handleJobUrl(event, url, score) {
    event.preventDefault();
    if (score < 0.65) {
        _pendingUrl = url;
        const row = event.target.closest('tr');
        let reasoning = '';
        if (row) {
            const jobId = parseInt(row.dataset.jobId);
            const result = currentResults.find(r => r.id === jobId);
            if (result) reasoning = (result.ai_analysis || {}).overall_reasoning || '';
        }
        document.getElementById('low-score-value').textContent = score.toFixed(2);
        document.getElementById('low-score-reasoning').textContent = reasoning;
        document.getElementById('low-score-modal').classList.remove('hidden');
    } else {
        window.open(url, '_blank');
    }
}

function closeLowScoreModal() {
    _pendingUrl = null;
    document.getElementById('low-score-modal').classList.add('hidden');
}

function confirmLowScoreApply() {
    if (_pendingUrl) window.open(_pendingUrl, '_blank');
    closeLowScoreModal();
}

// ── Applied state (DB) ───────────────────────────────────────────────────────

function toggleApplied(jobId, checkbox) {
    const row = checkbox.closest('tr');
    const method = checkbox.checked ? 'POST' : 'DELETE';
    fetch(`/api/applied/${jobId}`, { method })
        .catch(e => console.error('Applied toggle failed:', e));
    row.classList.toggle('applied', checkbox.checked);
}

// ── PDF filename ──────────────────────────────────────────────────────────────

function pdfFilename(company, title) {
    const clean = s => s.split('').map(c => /[a-zA-Z0-9 \-]/.test(c) ? c : '_').join('');
    return (clean(company) + '_' + clean(title) + '.pdf').replace(/ /g, '_').slice(0, 100);
}

function buildResultsTable(results) {
    currentResults = results;
    const rows = results.map((r, idx) => {
        const job = r.job_metadata || {};
        const ai = r.ai_analysis || {};
        const score = r.fit_score || 0;
        const scoreClass = score >= 0.90 ? 'score-high' : score >= 0.50 ? 'score-med' : 'score-low';
        const decisionClass = `decision-${r.decision}`;
        const companyDisplay = job.url
            ? `<a href="#" onclick="handleJobUrl(event, '${job.url}', ${score})">${job.company || 'Link'}</a>`
            : (job.company || '');

        let reasoning = '';
        if (job.company && job.title) {
            const pdf = pdfFilename(job.company, job.title);
            reasoning = `<a href="/output/pdf/${pdf}" target="_blank">PDF</a>`;
        }
        if (r.decision === 'ATS_ONLY') {
            const gap = ai.role_fit_reasoning || 'role fit gap';
            reasoning += `${reasoning ? ' ' : ''}<span class="ats-only-warning" title="Will pass ATS (${ai.ats_pass_likelihood || 'HIGH'}). Human will likely reject: ${gap}">⚠</span>`;
        }

        const rowClass = r.applied ? 'applied' : '';
        const searchQuery = r.job_metadata ? (r.job_metadata.search_query || '') : '';
        const showConsider = !['STRONG_MATCH', 'APPLY', 'CONSIDER'].includes(r.decision);
        const considerBtn = showConsider
            ? `<button class="consider-btn" onclick="markConsider(${r.id}, ${score}, this)">Consider</button>`
            : '';
        const forgeBtn = r.decision === 'STRONG_MATCH'
            ? `<button class="forge-btn" data-job-id="${r.id}" onclick="forwardToForge(${r.id})">→ FORGE</button>`
            : '';
        return `<tr class="${rowClass}" data-search-query="${searchQuery}" data-job-id="${r.id}">
            <td class="applied-cb-cell"><input type="checkbox" class="applied-cb" ${r.applied ? 'checked' : ''} onchange="toggleApplied(${r.id}, this)"></td>
            <td class="${decisionClass}" data-decision-cell>${r.decision}</td>
            <td class="${scoreClass}">${score.toFixed(2)}</td>
            <td>${job.title || ''}</td>
            <td>${companyDisplay}</td>
            <td>${job.location || ''}</td>
            <td>${job.salary || ''}</td>
            <td>${ai.ats_pass_likelihood || ''}</td>
            <td>${reasoning}</td>
            <td class="consider-cell">${considerBtn}${forgeBtn}</td>
            <td class="delete-cell"><button class="delete-btn" onclick="openDeleteModal(${idx}, this.closest('tr'))">×</button></td>
        </tr>`;
    }).join('');

    return `<table>
        <thead>
            <tr>
                <th>Applied</th>
                <th>Decision</th>
                <th>Score</th>
                <th>Title</th>
                <th>Company</th>
                <th>Location</th>
                <th>Salary</th>
                <th>ATS</th>
                <th>Reasoning</th>
                <th></th>
                <th></th>
            </tr>
        </thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// ── Run Modal ─────────────────────────────────────────────────────────────────

async function loadScrapers() {
    const select = document.getElementById('run-scraper-select');
    try {
        const res = await fetch('/api/scrapers');
        const data = await res.json();
        select.innerHTML = data.scrapers.map(s =>
            `<option value="${s.name}">${s.display_name}</option>`
        ).join('');
    } catch (e) {
        select.innerHTML = '<option value="hybrid_scraper">Hybrid Scraper</option>';
    }
}

function openRunModal() {
    const mainVal = document.getElementById('resume-select').value;
    const runSelect = document.getElementById('run-resume-select');
    if (mainVal) runSelect.value = mainVal;
    document.querySelector('input[name="run-mode"][value="full"]').checked = true;
    document.getElementById('run-reset-cache').checked = false;
    document.getElementById('data-file-row').classList.add('hidden');
    document.getElementById('scraper-row').classList.remove('hidden');
    document.getElementById('run-modal').classList.remove('hidden');
    loadScrapers();
}

function closeRunModal() {
    document.getElementById('run-modal').classList.add('hidden');
}

function onModeChange() {
    const mode = document.querySelector('input[name="run-mode"]:checked').value;
    const dataFileRow = document.getElementById('data-file-row');
    const scraperRow = document.getElementById('scraper-row');
    if (mode === 'analyze') {
        dataFileRow.classList.remove('hidden');
        loadDataFiles();
    } else {
        dataFileRow.classList.add('hidden');
    }
    // Scraper only applies to modes that invoke the scraper
    if (mode === 'full' || mode === 'scrape') {
        scraperRow.classList.remove('hidden');
    } else {
        scraperRow.classList.add('hidden');
    }
}

async function loadDataFiles() {
    const resumeType = document.getElementById('run-resume-select').value;
    const select = document.getElementById('run-data-file');
    select.innerHTML = '<option value="">Loading...</option>';
    try {
        const res = await fetch(`/api/data-files?resume_type=${encodeURIComponent(resumeType)}`);
        const data = await res.json();
        select.innerHTML = data.files.length
            ? data.files.map(f => `<option value="${f}">${f}</option>`).join('')
            : '<option value="">No data files found</option>';
    } catch (e) {
        select.innerHTML = '<option value="">Error loading files</option>';
    }
}

function submitRun() {
    const resumeType = document.getElementById('run-resume-select').value;
    const mode = document.querySelector('input[name="run-mode"]:checked').value;
    const dataFile = document.getElementById('run-data-file').value;
    const resetCache = document.getElementById('run-reset-cache').checked;

    if (!resumeType) return;

    closeRunModal();

    const statusMsg = document.getElementById('status-msg');
    const btn = document.getElementById('run-btn');
    const progress = document.getElementById('progress');
    const logOutput = document.getElementById('log-output');

    btn.disabled = true;
    statusMsg.textContent = 'Running...';
    logOutput.textContent = '';
    progress.classList.remove('hidden');

    const scraper = document.getElementById('run-scraper-select').value || 'hybrid_scraper';
    let url = `/api/run?resume_type=${encodeURIComponent(resumeType)}&mode=${mode}&reset_cache=${resetCache}&scraper=${encodeURIComponent(scraper)}`;
    if (mode === 'analyze' && dataFile) url += `&data_file=${encodeURIComponent(dataFile)}`;

    const es = new EventSource(url);
    es.onmessage = (e) => {
        if (e.data === '__done__') {
            es.close();
            btn.disabled = false;
            statusMsg.textContent = 'Done.';
            loadResults(document.getElementById('resume-select').value);
            loadSidebarResumes();
            return;
        }
        logOutput.textContent += e.data + '\n';
        logOutput.scrollTop = logOutput.scrollHeight;
    };
    es.onerror = () => {
        es.close();
        btn.disabled = false;
        statusMsg.textContent = 'Error — check terminal for details.';
    };
}

// ── Analyze Single Job Modal ──────────────────────────────────────────────────

function openAnalyzeModal() {
    const mainVal = document.getElementById('resume-select').value;
    const analyzeSelect = document.getElementById('analyze-resume-select');
    if (mainVal) analyzeSelect.value = mainVal;
    document.getElementById('analyze-job-name').value = '';
    document.getElementById('analyze-company').value = '';
    document.getElementById('analyze-salary').value = '';
    document.getElementById('analyze-url').value = '';
    document.getElementById('analyze-job-desc').value = '';
    document.getElementById('analyze-result').classList.add('hidden');
    document.getElementById('analyze-error').classList.add('hidden');
    // Reset screenshot zone
    document.getElementById('screenshot-preview').style.display = 'none';
    document.getElementById('screenshot-zone').querySelector('.screenshot-hint').style.display = 'flex';
    document.getElementById('screenshot-input').value = '';
    document.getElementById('analyze-modal').classList.remove('hidden');
    analyzeModalOpen = true;
}

function closeAnalyzeModal() {
    document.getElementById('analyze-modal').classList.add('hidden');
    analyzeModalOpen = false;
}

async function submitAnalyze() {
    const jobName = document.getElementById('analyze-job-name').value.trim();
    const company = document.getElementById('analyze-company').value.trim();
    const salary = document.getElementById('analyze-salary').value.trim();
    const resumeType = document.getElementById('analyze-resume-select').value;
    const jobDesc = document.getElementById('analyze-job-desc').value.trim();
    const errorEl = document.getElementById('analyze-error');
    const resultEl = document.getElementById('analyze-result');
    const btn = document.getElementById('analyze-submit-btn');

    const showError = msg => {
        errorEl.textContent = msg;
        errorEl.classList.remove('hidden');
    };

    if (!jobName) return showError('Job title is required.');
    if (!company) return showError('Company is required.');
    if (!resumeType) return showError('Select a resume.');
    if (!jobDesc) return showError('Paste a job description.');

    errorEl.classList.add('hidden');
    resultEl.classList.add('hidden');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';

    try {
        const res = await fetch('/api/analyze-single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_name: jobName, company, salary, url: document.getElementById('analyze-url').value.trim(), resume_type: resumeType, job_description: jobDesc })
        });
        const data = await res.json();
        if (!res.ok) return showError(data.error || 'Analysis failed.');
        resultEl.innerHTML = buildSingleResult(data);
        resultEl.classList.remove('hidden');
        loadResults(document.getElementById('resume-select').value);
    } catch (e) {
        showError(`Error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Analyze';
    }
}

function buildSingleResult(r) {
    const ai = r.ai_analysis || {};
    const score = r.fit_score || 0;
    const scoreClass = score >= 0.7 ? 'score-high' : score >= 0.5 ? 'score-med' : 'score-low';
    const decisionClass = `decision-${r.decision}`;
    const strengths = (ai.competitive_strengths || []).map(s => `<li>${s}</li>`).join('');
    const missing = (ai.missing_keywords || []).join(', ');
    const strategy = ai.application_strategy || '';

    return `<div class="single-result">
        <div class="result-header">
            <span class="${decisionClass}">${r.decision}</span>
            <span class="${scoreClass}"> &nbsp;${score.toFixed(2)}</span>
            <span class="muted"> &nbsp;| ATS: ${ai.ats_pass_likelihood || '?'}</span>
        </div>
        ${strengths ? `<div class="result-section"><div class="result-label">Strengths</div><ul>${strengths}</ul></div>` : ''}
        ${missing ? `<div class="result-section"><div class="result-label">Gaps</div><p>${missing}</p></div>` : ''}
        ${strategy ? `<div class="result-section"><div class="result-label">Strategy</div><p>${strategy}</p></div>` : ''}
    </div>`;
}

// ── Screenshot autofill ───────────────────────────────────────────────────────

async function handleScreenshot(file) {
    const thumb = document.getElementById('screenshot-thumb');
    const status = document.getElementById('screenshot-status');
    const preview = document.getElementById('screenshot-preview');
    const zone = document.getElementById('screenshot-zone');

    thumb.src = URL.createObjectURL(file);
    preview.style.display = 'flex';
    zone.querySelector('.screenshot-hint').style.display = 'none';
    status.textContent = 'Extracting fields...';
    status.style.color = '';

    const fd = new FormData();
    fd.append('image', file);

    try {
        const res = await fetch('/api/extract-job-screenshot', { method: 'POST', body: fd });
        const data = await res.json();

        if (!res.ok) {
            status.textContent = 'Extraction failed — fill fields manually';
            return;
        }

        if (data.company && !document.getElementById('analyze-company').value)
            document.getElementById('analyze-company').value = data.company;
        if (data.title && !document.getElementById('analyze-job-name').value)
            document.getElementById('analyze-job-name').value = data.title;
        if (data.salary && !document.getElementById('analyze-salary').value)
            document.getElementById('analyze-salary').value = data.salary;
        if (data.url && !document.getElementById('analyze-url').value)
            document.getElementById('analyze-url').value = data.url;

        const filled = [data.company, data.title, data.salary, data.url].filter(Boolean).length;
        if (data.confidence < 0.7) {
            status.textContent = `${filled} field(s) extracted — low confidence, please review`;
            status.style.color = 'var(--amber)';
        } else {
            status.textContent = `${filled} field(s) extracted`;
            status.style.color = 'var(--green-dim)';
        }
    } catch (err) {
        status.textContent = 'Error — fill fields manually';
    }
}

// ── Upload Resume Modal ───────────────────────────────────────────────────────

function openUploadModal() {
    document.getElementById('upload-name').value = '';
    document.getElementById('upload-file').value = '';
    document.getElementById('query-rows').innerHTML = '';
    document.getElementById('keyword-rows').innerHTML = '';
    document.getElementById('upload-error').classList.add('hidden');
    addQueryRow();
    document.getElementById('upload-modal').classList.remove('hidden');
}

function closeUploadModal() {
    document.getElementById('upload-modal').classList.add('hidden');
}

function addQueryRow() {
    const container = document.getElementById('query-rows');
    const row = document.createElement('div');
    row.className = 'query-row';
    row.innerHTML = `
        <input type="text" placeholder="Keywords" class="q-keywords" />
        <input type="text" placeholder="City, State" class="q-location" />
        <select class="q-max">
            <option value="5">5</option>
            <option value="10">10</option>
            <option value="15" selected>15</option>
            <option value="20">20</option>
            <option value="25">25</option>
            <option value="30">30</option>
        </select>
        <button class="remove-btn" onclick="this.closest('.query-row').remove()">×</button>
    `;
    container.appendChild(row);
}

function addKeywordRow(text = '') {
    const container = document.getElementById('keyword-rows');
    const row = document.createElement('div');
    row.className = 'query-row';
    row.innerHTML = `
        <input type="text" placeholder="e.g. Security Clearance" class="kw-text" value="${text}" />
        <button class="remove-btn" onclick="this.closest('.query-row').remove()">×</button>
    `;
    container.appendChild(row);
}

async function submitUpload() {
    const name = document.getElementById('upload-name').value.trim();
    const fileInput = document.getElementById('upload-file');
    const errorEl = document.getElementById('upload-error');

    const showError = msg => {
        errorEl.textContent = msg;
        errorEl.classList.remove('hidden');
    };

    if (!name) return showError('Resume name is required.');
    if (!/^[a-zA-Z0-9_]+$/.test(name)) return showError('Name must be letters, numbers, and underscores only.');
    if (!fileInput.files.length) return showError('Select a resume file (.txt or .pdf).');

    const file = fileInput.files[0];
    const filename = file.name.toLowerCase();
    if (!filename.endsWith('.txt') && !filename.endsWith('.pdf')) {
        return showError('File must be .txt or .pdf');
    }

    const rows = document.querySelectorAll('#query-rows .query-row');
    const queries = [];
    for (const row of rows) {
        const keywords = row.querySelector('.q-keywords').value.trim();
        const location = row.querySelector('.q-location').value.trim();
        const max_results = parseInt(row.querySelector('.q-max').value);
        if (!keywords || !location) return showError('Each query needs keywords and location.');
        queries.push({ keywords, location, max_results });
    }
    if (!queries.length) return showError('Add at least one search query.');

    const keywords = [];
    for (const row of document.querySelectorAll('#keyword-rows .query-row')) {
        const text = row.querySelector('.kw-text').value.trim();
        if (text) keywords.push({ text, type: 'exclude' });
    }

    // Read file as base64
    const fileData = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = e => resolve(e.target.result.split(',')[1]); // strip data:...;base64,
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
    });

    try {
        const res = await fetch('/api/upload-resume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                filename: file.name,
                file_data: fileData,
                search_queries: queries,
                keywords,
            }),
        });
        const data = await res.json();
        if (!res.ok) return showError(data.error || 'Upload failed.');
        closeUploadModal();
        await loadResumes();
        document.getElementById('resume-select').value = name;
        loadResults(name);
    } catch (e) {
        showError(`Error: ${e.message}`);
    }
}
