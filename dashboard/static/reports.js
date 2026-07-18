// ─────────────────────────────────────────────────────────────────────────────
// reports.js  — Reports browser page logic
// ─────────────────────────────────────────────────────────────────────────────

const fileListLoading = document.getElementById('file-list-loading');
const fileListError   = document.getElementById('file-list-error');
const fileListEl      = document.getElementById('file-list');
const viewerCard      = document.getElementById('viewer-card');
const viewerTitle     = document.getElementById('viewer-title');
const viewerBody      = document.getElementById('viewer-body');
const downloadBtnR    = document.getElementById('download-btn');
const closeBtn        = document.getElementById('close-btn');

let _currentRaw  = '';
let _currentName = '';

// ── Load file list ────────────────────────────────────────────────────────────
fetch('/api/reports')
  .then(r => r.json())
  .then(files => {
    fileListLoading.style.display = 'none';

    if (!files.length) {
      fileListEl.innerHTML =
        '<li style="color:#57606a;font-size:13px;padding:10px 0">No se encontraron reportes en <code>Respuestas/</code>.</li>';
      return;
    }

    files.forEach(f => {
      const li   = document.createElement('li');
      li.className = 'report-file-item';

      const icon = f.type === 'json' ? '{ }' : '#';
      const pill = `<span class="file-type-pill file-type-pill--${f.type}">${icon}</span>`;

      li.innerHTML = `
        ${pill}
        <span class="file-name">${escapeHtml(f.name)}</span>
        <button class="btn-secondary btn-sm" data-name="${escapeHtml(f.name)}">Ver reporte</button>
      `;

      li.querySelector('button').addEventListener('click', () => loadReport(f.name));
      fileListEl.appendChild(li);
    });
  })
  .catch(err => {
    fileListLoading.style.display = 'none';
    fileListError.textContent   = '⚠ Error al cargar la lista: ' + err;
    fileListError.style.display = 'block';
  });

// ── Load a single report ──────────────────────────────────────────────────────
function loadReport(name) {
  // Highlight selected item
  document.querySelectorAll('.report-file-item').forEach(li => li.classList.remove('selected'));
  const selectedLi = [...document.querySelectorAll('.report-file-item')]
    .find(li => li.querySelector('button').dataset.name === name);
  if (selectedLi) selectedLi.classList.add('selected');

  viewerTitle.textContent = name;
  viewerBody.innerHTML    = '<div style="color:#57606a;font-size:13px">Cargando…</div>';
  viewerCard.style.display = 'block';
  viewerCard.scrollIntoView({ behavior: 'smooth' });

  fetch('/api/reports/' + encodeURIComponent(name))
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        viewerBody.innerHTML = `<div class="alert-error" style="display:block">⚠ ${escapeHtml(data.error)}</div>`;
        return;
      }

      _currentRaw  = data.raw;
      _currentName = name;

      if (data.type === 'json' && data.json) {
        viewerBody.innerHTML = renderJsonReport(data.json);
      } else if (data.type === 'md') {
        viewerBody.innerHTML = data.html + scoreBadge(data.raw);
      } else {
        // JSON file that couldn't be parsed as a structured report — show raw
        viewerBody.innerHTML = `<pre class="code-block"><code>${escapeHtml(data.raw)}</code></pre>`;
      }
    })
    .catch(err => {
      viewerBody.innerHTML =
        `<div class="alert-error" style="display:block">⚠ Error al cargar el reporte: ${escapeHtml(String(err))}</div>`;
    });
}

// ── Download ──────────────────────────────────────────────────────────────────
downloadBtnR.addEventListener('click', () => {
  if (!_currentRaw) return;
  const mime = _currentName.endsWith('.json') ? 'application/json' : 'text/markdown';
  const blob = new Blob([_currentRaw], { type: mime });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = _currentName;
  a.click();
  URL.revokeObjectURL(url);
});

// ── Close viewer ──────────────────────────────────────────────────────────────
closeBtn.addEventListener('click', () => {
  viewerCard.style.display = 'none';
  _currentRaw  = '';
  _currentName = '';
  document.querySelectorAll('.report-file-item').forEach(li => li.classList.remove('selected'));
  window.scrollTo({ top: 0, behavior: 'smooth' });
});
