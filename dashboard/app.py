"""
dashboard/app.py
----------------
Self-contained Flask dashboard for the Code Review Agent.

Features
--------
• Upload a user_inputs.json file (or fill the form manually).
• Run the same analysis pipeline as main.py.
• Display the Markdown report rendered as HTML.
• Live progress log via Server-Sent Events (SSE).
• Download the raw Markdown output.

Run
---
    cd <project_root>
    python dashboard/app.py
Then open  http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid

# ── Project root on sys.path ─────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import markdown as _md

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

try:
    from dashboard.score_calculator import ScoreCalculator
except ImportError:
    from score_calculator import ScoreCalculator

from core.chroma_db import RAGConfig, PDFProcessor, VectorStore
from core.agent_logger import AgentLogger
from InputOutputs import FileHandler, RunLogger

_scorer = ScoreCalculator()

# ── Boot-time RAG initialisation (runs once when the app process starts) ──────
# PDF parsing and Chroma indexing are expensive; they must not repeat per request.
_rag_logger = AgentLogger("rag_boot", level="INFO")
_fh = FileHandler(logger=_rag_logger)
_rag_config = RAGConfig(**_fh.read_json("config.json"))
_pdf_processor = PDFProcessor(config=_rag_config, logger=_rag_logger)
_vector_store = VectorStore(config=_rag_config, logger=_rag_logger)
_boot_chunks = _pdf_processor.process_all_pdfs()
if _boot_chunks:
    _vector_store.add_documents(_boot_chunks)
_rag_logger._logger.info(
    "RAG boot complete — %d chunks indexed into '%s'.",
    len(_boot_chunks),
    _rag_config.collection_name,
)

_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br", "sane_lists"]


def render_markdown(text: str) -> str:
    """Convert a Markdown string to safe HTML using the `markdown` library."""
    return _md.markdown(text, extensions=_MD_EXTENSIONS)


_JSON_START = "###JSON_START###"
_JSON_END   = "###JSON_END###"


def _try_parse_json(text: str) -> dict | None:
    """
    Robustly extract a JSON object from the LLM response.

    Strategy (in order):
    0. Strip <think>...</think> reasoning blocks that some models emit.
    1. Extract content between ###JSON_START### / ###JSON_END### markers.
    2. Try the whole string as-is.
    3. Strip a single ```json ... ``` fence and retry.
    4. Find the first '{' and the last '}' in the string and try that slice —
       handles models that leak reasoning prose before or after the JSON.
    """
    def _attempt(s: str) -> dict | None:
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    # 0. Remove <think>...</think> blocks (reasoning models leak these)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 1. Extract between ###JSON_START### / ###JSON_END### markers
    s_idx = cleaned.find(_JSON_START)
    e_idx = cleaned.find(_JSON_END)
    if s_idx != -1 and e_idx > s_idx:
        between = cleaned[s_idx + len(_JSON_START) : e_idx].strip()
        result = _attempt(between)
        if result is not None:
            return result

    # 2. Direct parse
    result = _attempt(cleaned)
    if result is not None:
        return result

    # 3. Strip markdown fence
    no_fence = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    no_fence = re.sub(r"\s*```\s*$", "", no_fence)
    result = _attempt(no_fence)
    if result is not None:
        return result

    # 4. Extract the outermost { ... } block — handles leading/trailing prose.
    # Search only after any remaining prose so we don't pick up a brace inside
    # reasoning text that was not wrapped in <think> tags.
    start = cleaned.find("{")
    end   = cleaned.rfind("}")
    if start != -1 and end > start:
        result = _attempt(cleaned[start : end + 1])
        if result is not None:
            return result

    return None

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.urandom(24)

# Global state: { job_id: {"status": ..., "log": [...], "result": str|None, "error": str|None} }
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_job() -> str:
    jid = str(uuid.uuid4())
    with _JOBS_LOCK:
        _JOBS[jid] = {"status": "running", "log": [], "result": None, "error": None}
    return jid


def _append_log(jid: str, msg: str) -> None:
    with _JOBS_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["log"].append(msg)


def _finish_job(jid: str, result: str) -> None:
    with _JOBS_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["status"] = "done"
            _JOBS[jid]["result"] = result


def _fail_job(jid: str, error: str) -> None:
    with _JOBS_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["status"] = "error"
            _JOBS[jid]["error"] = error


def _run_worker(jid: str, archivo: str, salida: str, log_level: str) -> None:
    """Runs in a background thread."""
    try:
        from dashboard.worker import run_analysis
    except ImportError:
        from worker import run_analysis

    def on_log(msg: str) -> None:
        _append_log(jid, msg)

    try:
        result, _run_id = run_analysis(
            archivo=archivo,
            salida=salida,
            log_level=log_level,
            on_log=on_log,
            vector_store=_vector_store,
            run_id=jid,
        )
        _finish_job(jid, result)
    except Exception as exc:
        _fail_job(jid, str(exc))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/api/reports")
def api_reports():
    """Return a list of report files found in the Respuestas/ folder."""
    folder = os.path.join(_ROOT, "Respuestas")
    if not os.path.isdir(folder):
        return jsonify([])

    files = []
    for fname in sorted(os.listdir(folder)):
        if fname.lower().endswith((".json", ".md")):
            fpath = os.path.join(folder, fname)
            files.append({
                "name": fname,
                "type": "json" if fname.lower().endswith(".json") else "md",
                "mtime": os.path.getmtime(fpath),
            })

    # Sort newest first
    files.sort(key=lambda f: f["mtime"], reverse=True)
    for f in files:
        del f["mtime"]
    return jsonify(files)


@app.route("/api/reports/<path:filename>")
def api_report_file(filename: str):
    """Return the parsed content of a single report file."""
    # Prevent path traversal: only allow simple filenames (no slashes)
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename."}), 400

    folder = os.path.join(_ROOT, "Respuestas")
    fpath  = os.path.join(folder, filename)
    if not os.path.isfile(fpath):
        return jsonify({"error": "File not found."}), 404

    raw = open(fpath, encoding="utf-8").read()

    if filename.lower().endswith(".json"):
        parsed = _try_parse_json(raw)
        if parsed is not None:
            _scorer.enrich(parsed)
            return jsonify({"type": "json", "raw": raw, "json": parsed})
        return jsonify({"type": "json", "raw": raw, "json": None})

    # Markdown
    html = render_markdown(raw)
    return jsonify({"type": "md", "raw": raw, "html": html})


@app.route("/api/run", methods=["POST"])
def api_run():
    body      = request.get_json(force=True) or {}
    archivo   = body.get("archivo",   "").strip()
    salida    = body.get("salida",    "Reporte").strip()
    log_level = body.get("log_level", "INFO").strip().upper()

    if not archivo:
        return jsonify({"error": "El campo 'archivo' es obligatorio."}), 400
    if not salida:
        return jsonify({"error": "El campo 'salida' es obligatorio."}), 400

    jid = _new_job()
    t = threading.Thread(
        target=_run_worker,
        args=(jid, archivo, salida, log_level),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": jid})


@app.route("/api/stream/<jid>")
def api_stream(jid: str):
    """Server-Sent Events endpoint that streams log lines then the result."""

    def generate():
        sent_index = 0
        while True:
            with _JOBS_LOCK:
                job = _JOBS.get(jid)

            if job is None:
                yield f"data: {json.dumps({'type': 'error', 'text': 'Job not found'})}\n\n"
                return

            # Stream any new log lines
            logs = job["log"]
            while sent_index < len(logs):
                line = logs[sent_index]
                yield f"data: {json.dumps({'type': 'log', 'text': line})}\n\n"
                sent_index += 1

            status = job["status"]

            if status == "done":
                raw    = job["result"]
                rl     = RunLogger(run_id=jid)
                parsed = _try_parse_json(raw)
                if parsed is not None:
                    # Reproduce the cleaned text (_try_parse_json strips <think> internally)
                    cleaned = re.sub(
                        r"<think>.*?</think>", "", raw,
                        flags=re.DOTALL | re.IGNORECASE,
                    ).strip()
                    rl.log_cleaned(cleaned)
                    _scorer.enrich(parsed)
                    final_text = json.dumps(parsed, ensure_ascii=False, indent=2)
                    rl.log_final(final_text)
                    payload = {"type": "done", "result": raw, "json": parsed}
                else:
                    rl.log_cleaned(raw)          # nothing stripped
                    html = render_markdown(raw)
                    rl.log_final(html)
                    payload = {"type": "done", "result": raw, "html": html}
                yield f"data: {json.dumps(payload)}\n\n"
                return

            if status == "error":
                yield f"data: {json.dumps({'type': 'error', 'text': job['error']})}\n\n"
                return

            time.sleep(0.4)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Always run from the project root so relative paths (config.json, Ejemplos/, …) work.
    os.chdir(_ROOT)
    print(f"Starting dashboard at http://127.0.0.1:5000  (project root: {_ROOT})")
    app.run(debug=False, threaded=True, port=5000)
