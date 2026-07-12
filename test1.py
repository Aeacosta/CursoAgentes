from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor
from helpers.constants import RESPUESTAS_FOLDER
import os
import json

config = RAGConfig()

with open("config.json", "r", encoding="utf-8") as f:
    data = json.loads(f.read())
    config = RAGConfig(**data)

pdf_processor = PDFProcessor(config=config)

docs = pdf_processor.process_all_pdfs()

client = FreeClaudeCodeClient()

archivo = open(r"Ejemplos/GoodExample.cs").read()

plantilla = open(r"Ejemplos/Plantilla.md", encoding="utf-8").read()

instrucciones = open(r"Documentacion/CleanCoding.md", encoding="utf-8").read()

Pregunta = "Cuales code smells identificas? ->" + archivo + "De recomendaciones y citas basado en el Clean Code de Rober C Martin que tienes como prompt" + "Utiliza la siguiente plantilla para la respuesta: " + plantilla + "Termina el reporte con una calificacion de 0 a 100 siendo 100 coo codigo totalmetne limpio"

respuesta = client.ask(
    Pregunta,
    system_prompt = docs
)


with open(os.path.join(RESPUESTAS_FOLDER,"output.md"), "w", encoding="utf-8") as f:
    print("Generando respuesta..")
    f.write(respuesta)
