"""Logger dedicado al ciclo agentic.

Usa el módulo estándar `logging` con un handler de consola formateado.
Se puede silenciar, redirigir a archivo o cambiar de nivel sin tocar
el código del agente.

Uso típico
----------
from core.agent_logger import AgentLogger

log = AgentLogger()          # nivel INFO, solo consola
log = AgentLogger(level="DEBUG", log_file="agent.log")  # también a archivo
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class AgentLogger:
    """
    Logger con formato legible para el ciclo agentic.

    Niveles usados
    --------------
    INFO   — inicio, iteraciones, stop_reason, respuesta final
    DEBUG  — preview de inputs/outputs de cada tool
    ERROR  — errores capturados durante la ejecución de tools
    """

    _LINE = "─" * 62

    def __init__(
        self,
        name: str = "agente",
        level: str = "INFO",
        log_file: str | None = None,
    ) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level.upper())

        # Evitar duplicar handlers si se instancia más de una vez
        if not self._logger.handlers:
            formatter = logging.Formatter(
                fmt="%(asctime)s  %(levelname)-5s  %(message)s",
                datefmt="%H:%M:%S",
            )

            # Handler de consola (stdout)
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            self._logger.addHandler(console)

            # Handler de archivo (opcional)
            if log_file:
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)

        # Evitar que el logger raíz duplique mensajes
        self._logger.propagate = False

    # ------------------------------------------------------------------
    # Métodos de ciclo agentic
    # ------------------------------------------------------------------

    def inicio(self, question: str, tool_names: list[str]) -> None:
        self._logger.info(self._LINE)
        self._logger.info("AGENTE  |  tools: %s", tool_names)
        preview = question[:120] + ("..." if len(question) > 120 else "")
        self._logger.info("Pregunta: %s", preview)
        self._logger.info(self._LINE)

    def iteracion(self, numero: int) -> None:
        self._logger.info("[iter %d] Llamando al modelo...", numero)

    def stop_reason(self, reason: str) -> None:
        self._logger.info("stop_reason=%r", reason)

    def tool_llamada(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        input_str = json.dumps(tool_input, ensure_ascii=False)
        if len(input_str) > 120:
            input_str = input_str[:120] + "..."
        self._logger.info("→ tool_use: %s(%s)", tool_name, input_str)

    def tool_resultado(self, tool_name: str, result: str) -> None:
        preview = result[:80].replace("\n", " ")
        suffix = f" ... [{len(result)} chars]" if len(result) > 80 else ""
        self._logger.debug("← %s resultado: %s%s", tool_name, preview, suffix)

    def tool_error(self, tool_name: str, exc: Exception) -> None:
        self._logger.error("✗ Error en tool %r: %s", tool_name, exc)

    def respuesta_final(self, answer: str) -> None:
        self._logger.info(self._LINE)
        self._logger.info("Respuesta final  (%d caracteres)", len(answer))
        self._logger.info(self._LINE)

    def stop_inesperado(self, reason: str) -> None:
        self._logger.warning("stop_reason inesperado: %r — saliendo del ciclo.", reason)
