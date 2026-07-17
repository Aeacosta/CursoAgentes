from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor
from core.user_inputs import UserConfig
from  core.agent_logger import AgentLogger
from helpers.constants import RESPUESTAS_FOLDER
import os
import json

config = RAGConfig()

with open("config.json", "r", encoding="utf-8") as f:
    data = json.loads(f.read())
    config = RAGConfig(**data)

with open("user_inputs.json", "r", encoding="utf-8") as f:
    data = json.loads(f.read())
    user_config = UserConfig(**data)


pdf_processor = PDFProcessor(config=config)

docs = pdf_processor.process_all_pdfs()

client = FreeClaudeCodeClient()

archivo = open(r"Ejemplos/GoodExample.cs").read()

plantilla = open(r"Ejemplos/Plantilla.md", encoding="utf-8").read()

instrucciones = open(r"Documentacion/CleanCoding.md", encoding="utf-8").read()

Pregunta = f"""
Sigue estas instrucciones: {user_config.create_instruction(logger = AgentLogger())}" + "De recomendaciones y citas basado en el Clean Code de Rober C Martin que tienes como prompt.
Cualquier pregunta no relacionado a este enfoque, omite analizar y responde aclarando el usuario que no es tu tarea
Utiliza la siguiente plantilla para la respuesta: {plantilla}.
Termina el reporte con una calificacion de 0 a 100 siendo 100 coo codigo totalmetne limpio y recuerda citar las referencias respectivas.
"""

respuesta = client.ask(
    Pregunta,
    system_prompt = docs
)


with open(os.path.join(RESPUESTAS_FOLDER,"output.md"), "w", encoding="utf-8") as f:
    print("Generando respuesta..")
    f.write(respuesta)
