"""Centralised file read/write utilities for the agent pipeline.

Wraps every I/O operation so that:
  - All paths are resolved relative to the workspace root by default.
  - UTF-8 encoding is enforced consistently.
  - Errors surface as descriptive exceptions instead of bare OSError.
  - Every operation is logged through AgentLogger when one is supplied.

Typical usage
-------------
from InputOutputs.file_handler import FileHandler

fh = FileHandler(logger=AgentLogger())

text    = fh.read_text("Ejemplos/GoodExample.cs")
fh.write_text("Respuestas/output.md", text)

data    = fh.read_json("config.json")
fh.write_json("Respuestas/result.json", data)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

_module_log = logging.getLogger("agente.file_handler")


class FileHandlerError(OSError):
    """Raised when a read or write operation fails."""


class FileHandler:
    """
    Wraps text and JSON file I/O with consistent encoding, path handling,
    and optional logging.

    Parameters
    ----------
    base_dir:
        Root directory used to resolve relative paths.
        Defaults to the current working directory at instantiation time.
    encoding:
        Character encoding for all file operations. Defaults to ``"utf-8"``.
    logger:
        Optional :class:`core.agent_logger.AgentLogger` instance.
        When supplied, every read/write emits a DEBUG log entry.
    """

    def __init__(
        self,
        base_dir: str | os.PathLike[str] | None = None,
        encoding: str = "utf-8",
        logger: Any | None = None,
    ) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self._encoding = encoding
        # Support both AgentLogger (._logger) and a plain logging.Logger
        self._log: logging.Logger = (
            logger._logger if hasattr(logger, "_logger") else _module_log
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, path: str | os.PathLike[str]) -> Path:
        """Return an absolute path; relative paths are anchored to base_dir."""
        p = Path(path)
        return p if p.is_absolute() else self._base_dir / p

    # ------------------------------------------------------------------
    # Text operations
    # ------------------------------------------------------------------

    def read_text(self, path: str | os.PathLike[str]) -> str:
        """Read and return the full contents of a text file.

        Raises
        ------
        FileHandlerError
            If the file is not found or cannot be read.
        """
        resolved = self._resolve(path)
        self._log.debug("FileHandler.read_text | path=%s", resolved)
        try:
            return resolved.read_text(encoding=self._encoding, errors="replace")
        except FileNotFoundError:
            raise FileHandlerError(f"File not found: {resolved}")
        except OSError as exc:
            raise FileHandlerError(f"Cannot read '{resolved}': {exc}") from exc

    def write_text(
        self,
        path: str | os.PathLike[str],
        content: str,
        *,
        create_parents: bool = True,
    ) -> None:
        """Write *content* to a text file, overwriting if it already exists.

        Parameters
        ----------
        create_parents:
            When ``True`` (default), any missing parent directories are
            created automatically.

        Raises
        ------
        FileHandlerError
            If the file cannot be written.
        """
        resolved = self._resolve(path)
        self._log.debug(
            "FileHandler.write_text | path=%s | bytes=%d",
            resolved,
            len(content.encode(self._encoding, errors="replace")),
        )
        try:
            if create_parents:
                resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding=self._encoding)
        except OSError as exc:
            raise FileHandlerError(f"Cannot write '{resolved}': {exc}") from exc

    # ------------------------------------------------------------------
    # JSON operations
    # ------------------------------------------------------------------

    def read_json(self, path: str | os.PathLike[str]) -> Any:
        """Parse a JSON file and return the decoded Python object.

        Raises
        ------
        FileHandlerError
            If the file is not found, cannot be read, or is not valid JSON.
        """
        resolved = self._resolve(path)
        self._log.debug("FileHandler.read_json | path=%s", resolved)
        try:
            text = resolved.read_text(encoding=self._encoding)
        except FileNotFoundError:
            raise FileHandlerError(f"File not found: {resolved}")
        except OSError as exc:
            raise FileHandlerError(f"Cannot read '{resolved}': {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise FileHandlerError(
                f"Invalid JSON in '{resolved}' at line {exc.lineno}: {exc.msg}"
            ) from exc

    def write_json(
        self,
        path: str | os.PathLike[str],
        data: Any,
        *,
        indent: int = 2,
        ensure_ascii: bool = False,
        create_parents: bool = True,
    ) -> None:
        """Serialise *data* as JSON and write it to *path*.

        Parameters
        ----------
        indent:
            JSON indentation level. Defaults to ``2``.
        ensure_ascii:
            When ``False`` (default), non-ASCII characters are kept as-is
            instead of being escaped.
        create_parents:
            When ``True`` (default), any missing parent directories are
            created automatically.

        Raises
        ------
        FileHandlerError
            If the file cannot be written or *data* is not JSON-serialisable.
        """
        resolved = self._resolve(path)
        self._log.debug("FileHandler.write_json | path=%s", resolved)
        try:
            text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        except (TypeError, ValueError) as exc:
            raise FileHandlerError(f"Data is not JSON-serialisable: {exc}") from exc
        try:
            if create_parents:
                resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(text, encoding=self._encoding)
        except OSError as exc:
            raise FileHandlerError(f"Cannot write '{resolved}': {exc}") from exc
