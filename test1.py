from core.llm_client import FreeClaudeCodeClient

client = FreeClaudeCodeClient()

respuesta = client.ask(
    "¿Cual es la mejor forma de aprender a programar agentes?"
)

print(respuesta)