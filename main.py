from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor, VectorStore
from core.user_inputs import UserConfig
from core.agent_logger import AgentLogger
from InputOutputs import FileHandler

logger = AgentLogger("agente", level="INFO")
fh = FileHandler(logger=logger)

with logger.timer("Carga de configuración"):
    config = RAGConfig(**fh.read_json("config.json"))
    user_config = UserConfig(**fh.read_json("user_inputs.json"))

with logger.timer("Indexado RAG (PDFs → Chroma)"):
    pdf_processor = PDFProcessor(config=config, logger=logger)
    chunks = pdf_processor.process_all_pdfs()
    logger._logger.info("  %d chunks extraídos.", len(chunks))
    vector_store = VectorStore(config=config, logger=logger)
    if chunks:
        vector_store.add_documents(chunks)

with logger.timer("Lectura de código + búsqueda RAG"):
    source_code = fh.read_text(user_config.archivo)
    query = f"clean code violations code smells design patterns: {source_code[:500]}"
    relevant_docs = vector_store.search(query)
    rag_context = "\n\n".join(
        f"[{d['source']}]\n{d['text']}" for d in relevant_docs
    )
    logger._logger.info("  %d chunks relevantes recuperados.", len(relevant_docs))

pregunta = (
    f"Analiza el siguiente código fuente aplicando la tarea '{user_config.tarea}'.\n\n"
    f"```\n{source_code}\n```\n\n"
    "Sigue estrictamente el esquema JSON definido en el prompt del sistema. "
    "No añadas texto, markdown ni explicaciones fuera del objeto JSON."
)

client = FreeClaudeCodeClient()
output_file = user_config.get_output_file_name()

with logger.timer("Llamada al LLM"):
    respuesta = client.ask(pregunta, system_prompt=rag_context)

with logger.timer("Guardado de resultado"):
    fh.write_text(output_file, respuesta)
    logger._logger.info("Guardado en %s", output_file)
