"""
Ejemplo de uso del ciclo agentic con tool calling.

Muestra cómo inyectar skills/tools al agente sin ninguna librería adicional.
El modelo decide cuándo y qué tools llamar; tu código las ejecuta.
"""

from core.llm_client import FreeClaudeCodeClient
from core.chroma_db import RAGConfig, PDFProcessor, VectorStore
from core.agent_logger import AgentLogger
import json
import os
import subprocess

# ---------------------------------------------------------------------------
# 1. Preparar el VectorStore (igual que en test1.py)
# ---------------------------------------------------------------------------

with open("config.json", "r", encoding="utf-8") as f:
    config = RAGConfig(**json.load(f))

pdf_processor = PDFProcessor(config=config)
vector_store = VectorStore(config=config)

docs = pdf_processor.process_all_pdfs()
if docs:
    vector_store.add_documents(docs)

# ---------------------------------------------------------------------------
# 2. Definir las tools (le dicen al modelo QUÉ puede hacer)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "buscar_en_documentos",
        "description": (
            "Busca fragmentos relevantes en los PDFs indexados (Clean Code, etc.). "
            "Úsala siempre que necesites citar o fundamentar una respuesta con los documentos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Términos o pregunta para buscar en los documentos.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "leer_archivo_codigo",
        "description": "Lee el contenido de un archivo de código fuente del sistema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Ruta relativa al archivo (ej: Ejemplos/CodeSmell4.cs).",
                }
            },
            "required": ["ruta"],
        },
    },
]

TOOLS.append(
    {
        "name": "git_commit_push",
        "description": (
            "Ejecuta git add -A, git commit con un mensaje descriptivo y git push. "
            "Úsala cuando el usuario pida guardar o subir cambios al repositorio. "
            "Genera un mensaje de commit claro en imperativo que describa QUÉ cambió y POR QUÉ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mensaje": {
                    "type": "string",
                    "description": (
                        "Mensaje de commit en español o inglés. "
                        "Debe ser descriptivo: qué se cambió y por qué. "
                        "Ejemplo: 'feat: agrega ciclo agentic con tool calling al LLM client'"
                    ),
                }
            },
            "required": ["mensaje"],
        },
    }
)

# ---------------------------------------------------------------------------
# 3. Implementar el ejecutor de tools (aquí viven las skills reales)
# ---------------------------------------------------------------------------

def ejecutar_tool(tool_name: str, tool_input: dict) -> str:
    """
    Despacha la llamada al tool_name con los argumentos tool_input.
    Agrega aquí cualquier nueva skill: solo suma un elif.
    """

    if tool_name == "buscar_en_documentos":
        query = tool_input["query"]
        resultados = vector_store.search(query)
        if not resultados:
            return "No se encontraron documentos relevantes para esa búsqueda."

        fragmentos = []
        for r in resultados:
            fragmentos.append(f"[{r['source']}]:\n{r['text']}")
        return "\n\n---\n\n".join(fragmentos)

    elif tool_name == "leer_archivo_codigo":
        ruta = tool_input["ruta"]
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            return f"Archivo no encontrado: {ruta}"

    elif tool_name == "git_commit_push":
        mensaje = tool_input["mensaje"]
        try:
            # git add -A
            subprocess.run(
                ["git", "add", "-A"],
                check=True, capture_output=True, text=True
            )
            # git commit
            commit = subprocess.run(
                ["git", "commit", "-m", mensaje],
                check=True, capture_output=True, text=True
            )
            # git push
            push = subprocess.run(
                ["git"],
                check=True, capture_output=True, text=True
            )
            return (
                f"✓ Commit realizado: {mensaje}\n"
                f"Commit output:\n{commit.stdout.strip()}\n"
                f"Push output:\n{push.stdout.strip()}"
            )
        except subprocess.CalledProcessError as e:
            return (
                f"✗ Error en git:\n"
                f"Comando: {e.cmd}\n"
                f"Stderr: {e.stderr.strip()}\n"
                f"Stdout: {e.stdout.strip()}"
            )

    else:
        return f"Tool desconocida: {tool_name}"

# ---------------------------------------------------------------------------
# 4. Ejecutar el agente con tools inyectadas
# ---------------------------------------------------------------------------

client = FreeClaudeCodeClient()

archivo = open(r"Ejemplos/CodeSmell4.cs").read()

pregunta = (
    "Analiza el siguiente código C# usando leer_archivo_codigo \"Ejemplos/CodeSmell4.cs\" e identifica los code smells presentes. "
    "Usa la tool buscar_en_documentos para fundamentar cada problema con citas "
    "del Clean Code de Robert C. Martin.\n\n"
)

print("Iniciando ciclo agentic...\n")

respuesta = client.run_agent_loop(
    question=pregunta,
    tools=TOOLS,
    tool_executor=ejecutar_tool,
    max_iterations=50,
    logger=AgentLogger("DEBUG")
    # system_prompt=None  ← usa agent_system_prompt() por defecto
)

# ---------------------------------------------------------------------------
# 5. Guardar resultado
# ---------------------------------------------------------------------------

output_path = os.path.join("Respuestas", "output_tools.md")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(respuesta)

print(f"Respuesta guardada en {output_path}")
