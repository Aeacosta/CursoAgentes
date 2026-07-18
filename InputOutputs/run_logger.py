"""InputOutputs/run_logger.py
-----------------------------
Persists the three pipeline stages of an LLM analysis run to disk.

Each run gets its own sub-directory under *log_dir* (default: ``logs/``
relative to the current working directory).  Three text files are written:

  logs/<run_id>/1_llm_raw.txt     — verbatim response from the LLM
  logs/<run_id>/2_cleaned.txt     — response after <think> stripping / fence removal
  logs/<run_id>/3_final.txt       — final payload sent to the client (JSON or Markdown)

Typical usage
-------------
from InputOutputs.run_logger import RunLogger

rl = RunLogger(run_id="20240101_120000")   # or omit for auto timestamp
rl.log_llm_raw(llm_response)
rl.log_cleaned(cleaned_text)
rl.log_final(final_text)                   # pass json.dumps(parsed) or rendered html
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path


class RunLogger:
    """
    Writes the three processing stages of a pipeline run to individual
    files inside ``<log_dir>/<run_id>/``.

    Parameters
    ----------
    run_id:
        Identifier used as the log sub-folder name.
        Auto-generated from the current timestamp (``YYYYMMDD_HHMMSS``)
        when not supplied.
    log_dir:
        Root log directory.  Defaults to ``logs/`` relative to the
        current working directory at instantiation time.
    encoding:
        File encoding.  Defaults to ``"utf-8"``.
    """

    _STAGE_NAMES = {
        "llm_raw": "1_llm_raw.txt",
        "cleaned":  "2_cleaned.txt",
        "final":    "3_final.txt",
    }

    def __init__(
        self,
        run_id: str | None = None,
        log_dir: str | os.PathLike[str] | None = None,
        encoding: str = "utf-8",
    ) -> None:
        self.run_id = run_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _root = Path(log_dir) if log_dir is not None else Path.cwd() / "logs"
        self.run_dir = _root / self.run_id
        self._encoding = encoding

    # ------------------------------------------------------------------
    # Public stage writers
    # ------------------------------------------------------------------

    def log_llm_raw(self, content: str) -> Path:
        """Save the verbatim LLM response."""
        return self._write("llm_raw", content)

    def log_cleaned(self, content: str) -> Path:
        """Save the response after <think> stripping and fence removal."""
        return self._write("cleaned", content)

    def log_final(self, content: str) -> Path:
        """Save the final payload (serialised JSON or rendered Markdown/HTML)."""
        return self._write("final", content)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _write(self, stage: str, content: str) -> Path:
        """Write *content* to the appropriate file; create dirs if needed."""
        filename = self._STAGE_NAMES[stage]
        self.run_dir.mkdir(parents=True, exist_ok=True)
        dest = self.run_dir / filename
        dest.write_text(content, encoding=self._encoding)
        return dest
