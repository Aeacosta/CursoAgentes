"""
dashboard/worker.py
-------------------
Runs the same pipeline as main.py and returns the LLM response as a string.
Called from app.py in a background thread so Flask stays responsive.
"""

from __future__ import annotations

import sys
import os
from typing import Callable, Tuple

# ── Make sure the project root is on sys.path so core/helpers/InputOutputs
#    are importable regardless of where the process is launched from. ─────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor, VectorStore
from core.user_inputs import UserConfig
from core.agent_logger import AgentLogger
from core.response_parser import ResponseParser as _ResponseParser, FILE_SIZE_LIMIT_BYTES
from InputOutputs import FileHandler, RunLogger

_parser = _ResponseParser()

# Task and format are fixed — not user-configurable from the UI.
_TAREA  = "find_code_smells"
_FORMATO = "json"


def run_analysis(
    archivo: str,
    salida: str,
    log_level: str = "INFO",
    on_log: Callable[[str], None] | None = None,
    vector_store: VectorStore | None = None,
    run_id: str | None = None,
) -> Tuple[str, str]:
    """
    Execute the full analysis pipeline.

    Parameters
    ----------
    archivo      : relative path to the source file to analyse
    salida       : base name for the output file (written under Respuestas/)
    log_level    : logging level string — DEBUG | INFO | WARNING | ERROR
    on_log       : optional callback(str) called for each progress message
    vector_store : pre-built VectorStore from boot-time RAG init.
                   When provided, PDF parsing and indexing are skipped entirely.
                   When None (e.g. called standalone via main.py), the full
                   parse + index pipeline runs as before.
    run_id       : identifier used as the log sub-folder name under logs/.
                   Auto-generated from timestamp when omitted.

    Returns
    -------
    Tuple of (llm_response, run_id).
    """
    run_logger = RunLogger(run_id=run_id)

    def emit(msg: str) -> None:
        if on_log:
            on_log(msg)

    logger = AgentLogger("agente", level=log_level)
    logger.add_ui_sink(emit)           # forward every log line to the UI
    fh = FileHandler(logger=logger)

    with logger.timer("Carga de configuración"):
        config = RAGConfig(**fh.read_json("config.json"))
        user_config = UserConfig(
            archivo=archivo,
            tarea=_TAREA,
            formato=_FORMATO,
            salida=salida,
        )

    # ── RAG: use pre-built store (boot-time) or build it now (standalone) ────
    if vector_store is None:
        with logger.timer("Indexado RAG (PDFs → Chroma)"):
            pdf_processor = PDFProcessor(config=config, logger=logger)
            chunks = pdf_processor.process_all_pdfs()
            emit(f"  {len(chunks)} chunks extraídos de los PDFs.")
            vector_store = VectorStore(config=config, logger=logger)
            if chunks:
                vector_store.add_documents(chunks)
    else:
        emit("RAG ya inicializado en el arranque — omitiendo parseo de PDFs.")

    # ── Read the source file and retrieve relevant chunks ────────────────────
    with logger.timer("Lectura de código + búsqueda RAG"):
        source_code = fh.read_text(archivo)
        file_size = len(source_code.encode("utf-8"))
        large_file = file_size > FILE_SIZE_LIMIT_BYTES
        if large_file:
            emit(
                f"⚠ Archivo grande ({file_size} bytes > {FILE_SIZE_LIMIT_BYTES} bytes): "
                "solo se reportarán code smells (sin código corregido)."
            )
        emit("Leyendo archivo de código...")
        query = f"clean code violations code smells design patterns: {source_code[:500]}"
        relevant_docs = vector_store.search(query)
        rag_context = "\n\n".join(
            f"[{d['source']}]\n{d['text']}" for d in relevant_docs
        )
        emit(f"  {len(relevant_docs)} chunks relevantes recuperados.")

    # ── Build prompt ─────────────────────────────────────────────────────────
    pregunta = (
        f"Analiza el siguiente código fuente aplicando la tarea '{_TAREA}'.\n\n"
        f"```\n{source_code}\n```\n\n"
        "Sigue estrictamente el esquema JSON definido en el prompt del sistema. "
        "No añadas texto, markdown ni explicaciones fuera del objeto JSON."
    )

    # ── Call LLM ─────────────────────────────────────────────────────────────
    client = FreeClaudeCodeClient()
    if large_file:
        # Override the system prompt used by the client with the lighter variant
        # that skips code generation, reducing output token pressure.
        client.agent_system_prompt = _parser.smells_only_system_prompt  # type: ignore[method-assign]
    emit("Generando respuesta con el LLM...")
    with logger.timer("Llamada al LLM"):
        respuesta = client.ask(pregunta, system_prompt=rag_context)

    # ── Save output ───────────────────────────────────────────────────────────
    with logger.timer("Guardado de resultado"):
        output_file = user_config.get_output_file_name()
        fh.write_text(output_file, respuesta)
        emit(f"Guardando resultado en {output_file}...")

    # ── Log stage 1: raw LLM result ───────────────────────────────────────────
    run_logger.log_llm_raw(respuesta)
    emit(f"Log guardado en logs/{run_logger.run_id}/1_llm_raw.txt")

    emit("¡Análisis completado!")
    return respuesta, run_logger.run_id
