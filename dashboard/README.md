# Code Review Agent — Dashboard

A web dashboard that wraps the same pipeline as `main.py` and displays the
generated report as rendered HTML in the browser.

## Project structure

```
dashboard/
├── app.py          ← Flask server + full HTML/CSS/JS UI (single file)
├── worker.py       ← Pipeline logic (mirrors main.py, importable)
├── requirements.txt
└── README.md
```

## Quick start

### 1. Install dependencies (from the project root)

```powershell
pip install -r dashboard/requirements.txt
```

Or, if you have a virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r dashboard/requirements.txt
```

### 2. Run the dashboard

```powershell
# Always launch from the project root so relative paths work correctly.
python dashboard/app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## How to use

1. **Upload** a `user_inputs.json` file by dragging it onto the drop zone — the
   form fields are filled in automatically.  
   *Or* fill in the fields manually.

2. Click **▶ Ejecutar análisis**.

3. Watch the live progress log while the pipeline runs (PDF indexing → LLM call).

4. The generated report is rendered as HTML below the progress panel.

5. Use **⬇ Descargar Markdown** to save the raw `.md` file locally.

## `user_inputs.json` format

```json
{
  "archivo": "Ejemplos/CodeSmell4.cs",
  "tarea":   "find_code_smells",
  "formato": "markdown",
  "salida":  "Reporte"
}
```

| Field    | Description                                         |
|----------|-----------------------------------------------------|
| archivo  | Relative path to the source file to analyse         |
| tarea    | Task: `find_code_smells`, `code_review`, …          |
| formato  | `markdown` (default) or `text`                      |
| salida   | Base name of the output file saved in `Respuestas/` |

## Notes

- The LLM connection is configured via the same environment variables as the
  rest of the project (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`).
- The output report is **also** saved to `Respuestas/<salida>.md` as usual.
- The server is single-process; only one analysis runs at a time per worker
  thread.  For concurrent use, deploy behind Gunicorn with multiple workers.
