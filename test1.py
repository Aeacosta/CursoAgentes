from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor
from helpers.constants import RESPUESTAS_FOLDER
import os
config = RAGConfig()

pdf_processor = PDFProcessor(config=config)

docs = pdf_processor.process_all_pdfs()

client = FreeClaudeCodeClient()

respuesta = client.ask(
    "¿Cual es la cantidad de argumentos recomendada para una funcion?",
    system_prompt = docs
)


with open(os.path.join(RESPUESTAS_FOLDER,"output.md"), "w", encoding="utf-8") as f:
    f.write(respuesta)
