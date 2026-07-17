// ── Score badge (appended to server-rendered HTML) ────────────────────────
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

// ── DOM refs ──────────────────────────────────────────────────────────────
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

let _rawMarkdown  = '';
let _currentJobId = null;
let _evtSource    = null;

// ── Log steps for progress bar (ordered) ──────────────────────────────────
const LOG_STEPS = [
  'Inicializando', 'configuración', 'documentos RAG',
  'Conectando', 'prompt', 'Generando respuesta',
  'Guardando', 'completado'
];

function updateProgress(logs) {
  let step = 0;
  for (let i = 0; i < LOG_STEPS.length; i++) {
    if (logs.some(l => l.toLowerCase().includes(LOG_STEPS[i].toLowerCase()))) step = i + 1;
  }
  progressBar.style.width = Math.round((step / LOG_STEPS.length) * 100) + '%';
}

// ── File drop / browse ────────────────────────────────────────────────────
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
      if (obj.tarea) {
        const sel = document.getElementById('f-tarea');
        if ([...sel.options].find(o => o.value === obj.tarea)) sel.value = obj.tarea;
      }
      if (obj.formato) {
        const sel = document.getElementById('f-formato');
        if ([...sel.options].find(o => o.value === obj.formato)) sel.value = obj.formato;
      }
      if (obj.salida) document.getElementById('f-salida').value = obj.salida;
      dropzone.style.background = '#f0fff4';
      dropzone.querySelector('strong').textContent = '✓ ' + file.name + ' cargado';
    } catch {
      showError('El archivo no es un JSON válido.');
    }
  };
  reader.readAsText(file);
}

// ── Run ───────────────────────────────────────────────────────────────────
runBtn.addEventListener('click', startAnalysis);

function startAnalysis() {
  const payload = {
    archivo: document.getElementById('f-archivo').value.trim(),
    tarea:   document.getElementById('f-tarea').value,
    formato: document.getElementById('f-formato').value,
    salida:  document.getElementById('f-salida').value.trim(),
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
      _rawMarkdown = msg.result;
      reportBody.innerHTML = msg.html + scoreBadge(msg.result);
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

// ── Download ──────────────────────────────────────────────────────────────
downloadBtn.addEventListener('click', () => {
  if (!_rawMarkdown) return;
  const blob = new Blob([_rawMarkdown], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = (document.getElementById('f-salida').value || 'Reporte') + '.md';
  a.click();
  URL.revokeObjectURL(url);
});

// ── Reset ─────────────────────────────────────────────────────────────────
resetBtn.addEventListener('click', () => {
  progressSection.style.display = 'none';
  reportSection.style.display   = 'none';
  runBtn.disabled                = false;
  resetBtn.style.display         = 'none';
  statusText.textContent         = '';
  logBox.textContent             = '';
  progressBar.style.width        = '0%';
  _rawMarkdown                   = '';
  clearError();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ── Helpers ───────────────────────────────────────────────────────────────
function showError(msg) {
  errorBox.textContent   = '⚠ ' + msg;
  errorBox.style.display = 'block';
}
function clearError() {
  errorBox.textContent   = '';
  errorBox.style.display = 'none';
}
