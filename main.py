from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor
from core.user_inputs import UserConfig
from core.agent_logger import AgentLogger
from helpers.constants import RESPUESTAS_FOLDER
from InputOutputs import FileHandler

# ── Single logger wired at DEBUG across the whole run ──────────────────────
logger = AgentLogger("agente", level="INFO")
fh = FileHandler(logger=logger)

# ── Load configuration ──────────────────────────────────────────────────────
config = RAGConfig(**fh.read_json("config.json"))
user_config = UserConfig(**fh.read_json("user_inputs.json"))

# ── Process PDFs ────────────────────────────────────────────────────────────
logger._logger.info(f"Procesando RAG")
pdf_processor = PDFProcessor(config=config, logger=logger)
docs = pdf_processor.process_all_pdfs()

# ── Read source files ───────────────────────────────────────────────────────
logger._logger.info(f"Conectandose al LLM")
client = FreeClaudeCodeClient()

plantilla     = fh.read_text("Ejemplos/Plantilla.md")
instrucciones = fh.read_text("Documentacion/CleanCoding.md")

# ── Build prompt ────────────────────────────────────────────────────────────
logger._logger.info(f"Completando Prompt")
Pregunta = f"""
Sigue estas instrucciones: {user_config.create_instruction(logger=logger)}" + "De recomendaciones y citas basado en el Clean Code de Rober C Martin que tienes como prompt.
Cualquier pregunta no relacionado a este enfoque, omite analizar y responde aclarando el usuario que no es tu tarea
Utiliza la siguiente plantilla para la respuesta: {plantilla}.
Termina el reporte con una calificacion de 0 a 100 siendo 100 coo codigo totalmetne limpio y recuerda citar las referencias respectivas.
Recomienda patrones de diseño de Design Patterns: Elements of Reusable Object-Oriented Software.
"""

# ── Run LLM ─────────────────────────────────────────────────────────────────
output_file = user_config.get_output_file_name()
logger._logger.info(f"Generando respuesta en {output_file}")
respuesta = client.ask(
    Pregunta,
    system_prompt=docs,
)

# ── Save output ─────────────────────────────────────────────────────────────

logger._logger.debug(respuesta)
fh.write_text(output_file, respuesta)
