"""
dashboard/worker.py
-------------------
Runs the same pipeline as main.py and returns the LLM response as a string.
Called from app.py in a background thread so Flask stays responsive.
"""

from __future__ import annotations

import sys
import os

# ── Make sure the project root is on sys.path so core/helpers/InputOutputs
#    are importable regardless of where the process is launched from. ─────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor
from core.user_inputs import UserConfig
from core.agent_logger import AgentLogger
from InputOutputs import FileHandler


def run_analysis(
    archivo: str,
    tarea: str,
    formato: str,
    salida: str,
    on_log: "Callable[[str], None] | None" = None,
) -> str:
    """
    Execute the full analysis pipeline.

    Parameters
    ----------
    archivo   : relative path to the source file to analyse
    tarea     : task label (e.g. 'find_code_smells')
    formato   : output format ('markdown' | 'text')
    salida    : base name for the output file (written under Respuestas/)
    on_log    : optional callback(str) called for each progress message

    Returns
    -------
    The LLM response as a string.
    """

    def emit(msg: str) -> None:
        if on_log:
            on_log(msg)

    emit("Inicializando logger...")
    logger = AgentLogger("agente", level="INFO")
    fh = FileHandler(logger=logger)

    emit("Cargando configuración...")
    config = RAGConfig(**fh.read_json("config.json"))
    user_config = UserConfig(
        archivo=archivo,
        tarea=tarea,
        formato=formato,
        salida=salida,
    )

    emit("Procesando documentos RAG (PDFs)...")
    pdf_processor = PDFProcessor(config=config, logger=logger)
    docs = pdf_processor.process_all_pdfs()
    emit(f"  {len(docs)} chunks indexados.")

    emit("Conectando con el LLM...")
    client = FreeClaudeCodeClient()

    plantilla = fh.read_text("Ejemplos/Plantilla.md")

    emit("Construyendo prompt...")
    instruccion = user_config.create_instruction(logger=logger)
    pregunta = (
        f"Sigue estas instrucciones: {instruccion}\""
        " + \"De recomendaciones y citas basado en el Clean Code de Rober C Martin "
        "que tienes como prompt.\n"
        "Cualquier pregunta no relacionado a este enfoque, omite analizar y responde "
        "aclarando al usuario que no es tu tarea.\n"
        f"Utiliza la siguiente plantilla para la respuesta: {plantilla}.\n"
        "Termina el reporte con una calificacion de 0 a 100 siendo 100 codigo "
        "totalmente limpio y recuerda citar las referencias respectivas.\n"
        "Recomienda patrones de diseño de Design Patterns: Elements of Reusable "
        "Object-Oriented Software."
    )

    emit("Generando respuesta con el LLM (puede tardar)...")
    respuesta = client.ask(pregunta, system_prompt=str(docs))

    output_file = user_config.get_output_file_name()
    emit(f"Guardando resultado en {output_file}...")
    fh.write_text(output_file, respuesta)
    emit("¡Análisis completado!")

    return respuesta
