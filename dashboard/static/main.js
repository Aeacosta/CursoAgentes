// ─────────────────────────────────────────────────────────────────────────────
// JSON Report Renderer
// ─────────────────────────────────────────────────────────────────────────────

// scoreColor: high value = good (green). Used for puntuacion_general.
function scoreColor(v) {
  if (v >= 75) return { bar: '#22863a', bg: '#d4edda', text: '#155724' };
  if (v >= 45) return { bar: '#856404', bg: '#fff3cd', text: '#856404' };
  return { bar: '#cb2431', bg: '#f8d7da', text: '#721c24' };
}

// severityColor: high value = bad (red). Used for metrica (smell severity).
// Thresholds align with ScoreCalculator impact values: critico=85, mayor=55, menor=20.
function severityColor(v) {
  if (v >= 70) return { bar: '#cb2431', bg: '#f8d7da', text: '#721c24' };   // critico
  if (v >= 35) return { bar: '#856404', bg: '#fff3cd', text: '#856404' };   // mayor
  return        { bar: '#b45309', bg: '#fef3c7', text: '#92400e' };          // menor (amber — still a problem)
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Replace literal \n escape sequences with real newlines.
 *  Needed because json.dumps() inside the SSE payload double-encodes
 *  newlines inside string values, leaving them as the two-char sequence \n
 *  after the outer JSON.parse() on the client. */
function unescapeNewlines(str) {
  return String(str).replace(/\\n/g, '\n');
}

function renderJsonReport(data) {
  const parts = [];

  // ── 1. Overall score banner ──────────────────────────────────────────────
  const score = Number(data.puntuacion_general ?? data.overall_score ?? 0);
  const sc    = scoreColor(score);
  parts.push(`
    <div class="score-banner" style="background:${sc.bg};border-color:${sc.bar};color:${sc.text}">
      <span class="score-label">Puntuación general</span>
      <span class="score-number">${score}<span class="score-denom"> / 100</span></span>
      <div class="score-bar-wrap">
        <div class="score-bar-fill" style="width:${score}%;background:${sc.bar}"></div>
      </div>
    </div>`);

  // ── 2. Report table ──────────────────────────────────────────────────────
  const smells = data.reporte ?? data.report ?? [];
  if (smells.length) {
    parts.push('<h2 class="section-heading">Reporte de Code Smells</h2>');
    parts.push('<div class="report-table-wrap"><table class="report-table">');
    parts.push(`<thead><tr>
      <th>#</th>
      <th>Code Smell</th>
      <th>Violación</th>
      <th>Referencia</th>
      <th>Métrica</th>
    </tr></thead><tbody>`);

    smells.forEach((row, i) => {
      const m   = Number(row.metrica ?? row.metric ?? 0);
      const mc  = severityColor(m);
      const id  = escapeHtml(row.id ?? i + 1);
      const cs  = escapeHtml(unescapeNewlines(row.code_smell ?? ''));
      const vio = escapeHtml(unescapeNewlines(row.violacion ?? row.violation ?? ''));
      const ref = escapeHtml(unescapeNewlines(row.referencia ?? row.reference ?? ''));
      parts.push(`<tr>
        <td class="col-id">${id}</td>
        <td><strong>${cs}</strong></td>
        <td>${vio}</td>
        <td class="col-ref">${ref}</td>
        <td class="col-metric">
          <div class="metric-pill" style="background:${mc.bg};color:${mc.text}">
            <span class="metric-val">${m}</span>
          </div>
          <div class="metric-bar-wrap">
            <div class="metric-bar-fill" style="width:${m}%;background:${mc.bar}"></div>
          </div>
        </td>
      </tr>`);
    });

    parts.push('</tbody></table></div>');
  }

  // ── 3. Metrics summary (bar chart) ───────────────────────────────────────
  if (smells.length) {
    parts.push('<h2 class="section-heading">Métricas por problema</h2>');
    parts.push('<div class="metrics-chart">');
    smells.forEach((row, i) => {
      const m  = Number(row.metrica ?? row.metric ?? 0);
      const mc = severityColor(m);
      const cs = escapeHtml(row.code_smell ?? `Smell ${i + 1}`);
      parts.push(`
        <div class="metric-row">
          <div class="metric-name" title="${cs}">${cs}</div>
          <div class="metric-track">
            <div class="metric-fill" style="width:${m}%;background:${mc.bar}"></div>
          </div>
          <div class="metric-score" style="color:${mc.text}">${m}</div>
        </div>`);
    });
    parts.push('</div>');
  }

  // ── 4. Fixed code ────────────────────────────────────────────────────────
  const fixedCode = data.codigo_corregido ?? data.fixed_code ?? '';
  if (fixedCode) {
    parts.push('<h2 class="section-heading">Código corregido</h2>');
    parts.push(`<pre class="code-block code-block--fixed"><code>${escapeHtml(unescapeNewlines(fixedCode))}</code></pre>`);
  }

  // ── 6. Executive summary ─────────────────────────────────────────────────
  const summary = data.resumen_ejecutivo ?? data.executive_summary ?? '';
  if (summary) {
    parts.push('<h2 class="section-heading">Resumen ejecutivo</h2>');
    parts.push(`<div class="exec-summary">${escapeHtml(unescapeNewlines(summary)).replace(/\n/g, '<br>')}</div>`);
  }

  return parts.join('\n');
}

// ── Legacy markdown score badge (fallback path) ───────────────────────────────
function scoreBadge(md) {
  const m = md.match(/calificaci[oó]n[:\s]+(\d{1,3})/i) ||
            md.match(/score[:\s]+(\d{1,3})/i) ||
            md.match(/\b(\d{1,3})\s*\/\s*100\b/);
  if (!m) return '';
  const score = parseInt(m[1]);
  const cls   = score >= 75 ? 'score-high' : score >= 50 ? 'score-medium' : 'score-low';
  return `<div style="margin-top:20px">
    <span class="score-badge ${cls}">Puntuación: ${score} / 100</span>
  </div>`;
}

// ── DOM refs ──────────────────────────────────────────────────────────────────
const dropzone        = document.getElementById('dropzone');
const fileInput       = document.getElementById('json-file-input');
const browseBtn       = document.getElementById('browse-btn');
const runBtn          = document.getElementById('run-btn');
const resetBtn        = document.getElementById('reset-btn');
const statusText      = document.getElementById('status-text');
const errorBox        = document.getElementById('error-box');
const progressSection = document.getElementById('progress-section');
const progressBar     = document.getElementById('progress-bar');
const logBox          = document.getElementById('log-box');
const reportSection   = document.getElementById('report-section');
const reportBody      = document.getElementById('report-body');
const downloadBtn     = document.getElementById('download-btn');

let _rawResult    = '';
let _currentJobId = null;
let _evtSource    = null;

// ── Log steps for progress bar ────────────────────────────────────────────────
// Must match the timer() labels used in worker.py (case-insensitive substring match).
const LOG_STEPS = [
  'Carga de configuración',
  'Indexado RAG',
  'Lectura de código',
  'Llamada al LLM',
  'Guardado de resultado',
  'completado',
];

function updateProgress(logs) {
  let step = 0;
  for (let i = 0; i < LOG_STEPS.length; i++) {
    if (logs.some(l => l.toLowerCase().includes(LOG_STEPS[i].toLowerCase()))) step = i + 1;
  }
  progressBar.style.width = Math.round((step / LOG_STEPS.length) * 100) + '%';
}

// ── File drop / browse ────────────────────────────────────────────────────────
browseBtn.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('click', e => { if (e.target !== browseBtn) fileInput.click(); });
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) loadJsonFile(file);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) loadJsonFile(fileInput.files[0]);
});

function loadJsonFile(file) {
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const obj = JSON.parse(e.target.result);
      if (obj.archivo) document.getElementById('f-archivo').value = obj.archivo;
      if (obj.salida)  document.getElementById('f-salida').value  = obj.salida;
      dropzone.style.background = '#f0fff4';
      dropzone.querySelector('strong').textContent = '✓ ' + file.name + ' cargado';
    } catch {
      showError('El archivo no es un JSON válido.');
    }
  };
  reader.readAsText(file);
}

// ── Run ───────────────────────────────────────────────────────────────────────
runBtn.addEventListener('click', startAnalysis);

function startAnalysis() {
  const payload = {
    archivo:   document.getElementById('f-archivo').value.trim(),
    salida:    document.getElementById('f-salida').value.trim(),
    log_level: document.getElementById('f-log-level').value,
  };

  if (!payload.archivo) { showError('Debes especificar un archivo de código.'); return; }
  if (!payload.salida)  { showError('Debes especificar un nombre de salida.');  return; }

  clearError();
  runBtn.disabled = true;
  resetBtn.style.display = 'none';
  progressSection.style.display = 'block';
  reportSection.style.display   = 'none';
  logBox.textContent = '';
  progressBar.style.width = '0%';
  statusText.textContent = 'Iniciando...';

  fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { showError(data.error); runBtn.disabled = false; return; }
    _currentJobId = data.job_id;
    listenToJob(_currentJobId);
  })
  .catch(err => { showError('Error de red: ' + err); runBtn.disabled = false; });
}

function listenToJob(jid) {
  if (_evtSource) _evtSource.close();
  _evtSource = new EventSource('/api/stream/' + jid);

  _evtSource.onmessage = e => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'log') {
      logBox.textContent += msg.text + '\n';
      logBox.scrollTop = logBox.scrollHeight;
      updateProgress(Array.from(logBox.textContent.split('\n')));
      statusText.textContent = msg.text;
    }

    if (msg.type === 'done') {
      _evtSource.close();
      progressBar.style.width = '100%';
      statusText.textContent  = '✓ Análisis completado.';
      resetBtn.style.display  = 'inline-block';
      _rawResult = msg.result;

      if (msg.json) {
        // Structured JSON path
        reportBody.innerHTML = renderJsonReport(msg.json);
      } else {
        // Fallback: render markdown
        reportBody.innerHTML = msg.html + scoreBadge(msg.result);
      }

      reportSection.style.display = 'block';
      reportSection.scrollIntoView({ behavior: 'smooth' });
    }

    if (msg.type === 'error') {
      _evtSource.close();
      showError(msg.text);
      runBtn.disabled = false;
      resetBtn.style.display = 'inline-block';
    }
  };

  _evtSource.onerror = () => {
    // Connection closed normally after done/error — ignore.
    _evtSource.close();
  };
}

// ── Download ──────────────────────────────────────────────────────────────────
downloadBtn.addEventListener('click', () => {
  if (!_rawResult) return;
  const salida = document.getElementById('f-salida').value || 'Reporte';
  const blob = new Blob([_rawResult], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = salida + '.json';
  a.click();
  URL.revokeObjectURL(url);
});

// ── Reset ─────────────────────────────────────────────────────────────────────
resetBtn.addEventListener('click', () => {
  progressSection.style.display = 'none';
  reportSection.style.display   = 'none';
  runBtn.disabled                = false;
  resetBtn.style.display         = 'none';
  statusText.textContent         = '';
  logBox.textContent             = '';
  progressBar.style.width        = '0%';
  _rawResult                     = '';
  clearError();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function showError(msg) {
  errorBox.textContent   = '⚠ ' + msg;
  errorBox.style.display = 'block';
}
function clearError() {
  errorBox.textContent   = '';
  errorBox.style.display = 'none';
}
