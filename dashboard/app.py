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

_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br", "sane_lists"]


def render_markdown(text: str) -> str:
    """Convert a Markdown string to safe HTML using the `markdown` library."""
    return _md.markdown(text, extensions=_MD_EXTENSIONS)


def _try_parse_json(text: str) -> dict | None:
    """
    Robustly extract a JSON object from the LLM response.

    Strategy (in order):
    1. Try the whole string as-is.
    2. Strip a single ```json ... ``` fence and retry.
    3. Find the first '{' and the last '}' in the string and try that slice —
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

    cleaned = text.strip()

    # 1. Direct parse
    result = _attempt(cleaned)
    if result is not None:
        return result

    # 2. Strip markdown fence
    no_fence = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    no_fence = re.sub(r"\s*```\s*$", "", no_fence)
    result = _attempt(no_fence)
    if result is not None:
        return result

    # 3. Extract the outermost { ... } block — handles leading/trailing prose
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


def _run_worker(jid: str, archivo: str, tarea: str, formato: str, salida: str) -> None:
    """Runs in a background thread."""
    try:
        from dashboard.worker import run_analysis
    except ImportError:
        from worker import run_analysis

    def on_log(msg: str) -> None:
        _append_log(jid, msg)

    try:
        result = run_analysis(
            archivo=archivo,
            tarea=tarea,
            formato=formato,
            salida=salida,
            on_log=on_log,
        )
        _finish_job(jid, result)
    except Exception as exc:
        _fail_job(jid, str(exc))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(force=True) or {}
    archivo = body.get("archivo", "").strip()
    tarea   = body.get("tarea",   "find_code_smells").strip()
    formato = body.get("formato", "markdown").strip()
    salida  = body.get("salida",  "Reporte").strip()

    if not archivo:
        return jsonify({"error": "El campo 'archivo' es obligatorio."}), 400
    if not salida:
        return jsonify({"error": "El campo 'salida' es obligatorio."}), 400

    jid = _new_job()
    t = threading.Thread(
        target=_run_worker,
        args=(jid, archivo, tarea, formato, salida),
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
                parsed = _try_parse_json(raw)
                if parsed is not None:
                    payload = {"type": "done", "result": raw, "json": parsed}
                else:
                    html = render_markdown(raw)
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
