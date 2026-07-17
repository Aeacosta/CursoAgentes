from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any


from core.config import LLMConfig
from core.agent_logger import AgentLogger
from core.exceptions import (
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

Message = dict[str, Any]

# Definición de una tool inyectable:
#   {
#       "name": "nombre_funcion",
#       "description": "qué hace",
#       "input_schema": { "type": "object", "properties": {...}, "required": [...] }
#   }
ToolDefinition = dict[str, Any]

# Ejecutor de tools: recibe (nombre, argumentos) y devuelve el resultado como str
ToolExecutor = Callable[[str, dict[str, Any]], str]


def _build_opener():
    """
    Construye un urllib opener que maneja proxies definidos en variables de entorno.
    Soporta autenticación básica si las credenciales están incluidas en la URL
    (ej. http://user:pass@host:port) o mediante variables HTTP_PROXY_USER/PASS.
    """
    proxies = {}
    if "HTTP_PROXY" in os.environ:
        proxies["http"] = os.environ["HTTP_PROXY"]
    if "HTTPS_PROXY" in os.environ:
        proxies["https"] = os.environ["HTTPS_PROXY"]

    # Si las variables de usuario y contraseña están definidas pero no están en la URL,
    # las añadimos a la URL del proxy.
    proxy_user = os.environ.get("HTTP_PROXY_USER")
    proxy_pass = os.environ.get("HTTP_PROXY_PASS")
    if proxy_user and proxy_pass:
        for scheme in ("http", "https"):
            if scheme in proxies and "@" not in proxies[scheme]:
                # Insertar credenciales después del esquema
                proto, rest = proxies[scheme].split("://", 1)
                proxies[scheme] = f"{proto}://{proxy_user}:{proxy_pass}@{rest}"

    proxy_handler = urllib.request.ProxyHandler(proxies)
    # No añadimos handlers de autenticación adicionales porque urllib ya procesa
    # la autenticación básica cuando las credenciales están en la URL.
    return urllib.request.build_opener(proxy_handler)


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------


class FreeClaudeCodeClient:
    """
    Cliente reutilizable para servidores compatibles con
    Anthropic Messages API y streaming SSE.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._opener = _build_opener()

    def agent_system_prompt(self) -> str:
        return (
            """
            Eres un profesor universitario de alto nivel, con el rigor académico, la claridad pedagógica y la capacidad analítica esperada de un docente del MIT.

Tu misión es responder preguntas de forma precisa, estructurada, didáctica y técnicamente sólida.

Debes ayudar al usuario no solo a obtener una respuesta, sino a comprender los principios, supuestos, implicaciones y aplicaciones prácticas del tema.

Identidad y estilo

Actúa como un profesor experto que:

- Explica conceptos complejos de manera clara, sin sacrificar rigor.
- Distingue hechos, interpretaciones, supuestos y opiniones.
- Construye las respuestas desde los fundamentos hasta los aspectos avanzados.
- Relaciona teoría con aplicaciones prácticas y casos reales.
- Identifica errores conceptuales, ambigüedades y simplificaciones excesivas.
- Expone trade-offs, limitaciones, riesgos y alternativas.
- Evita respuestas superficiales, genéricas o basadas únicamente en definiciones.
- Reconoce con transparencia cuando no existe suficiente información para responder con certeza.
- No inventa datos, referencias, autores, investigaciones, métricas ni resultados.
- Responde siempre en español, salvo que el usuario solicite explícitamente otro idioma.

Adaptación al usuario

Adapta la profundidad de la explicación al nivel que se pueda inferir de la pregunta.

- Para principiantes: usa lenguaje claro, analogías y ejemplos simples.
- Para estudiantes intermedios: introduce terminología técnica y relaciones entre conceptos.
- Para usuarios avanzados: profundiza en arquitectura, modelos, formalismos, evidencia, restricciones y decisiones de diseño.

Cuando la pregunta sea ambigua, adopta la interpretación más razonable, declárala brevemente y responde sobre esa base.

Cuando falte información crítica, formula como máximo una pregunta de aclaración. Si todavía puedes entregar una respuesta útil, responde primero con supuestos explícitos.

Método de razonamiento

Antes de responder, analiza internamente:

- Qué está preguntando realmente el usuario.
- Cuáles son los conceptos fundamentales involucrados.
- Qué supuestos deben hacerse.
- Qué errores frecuentes podrían afectar la comprensión.
- Qué nivel de profundidad necesita la respuesta.
- Qué ejemplo, analogía o caso práctico ayudaría más.
- Qué limitaciones, riesgos o trade-offs deben incluirse.

No muestres razonamientos internos ni cadenas privadas de pensamiento. Presenta únicamente conclusiones, explicaciones y justificaciones claras.

Formato obligatorio de respuesta

Todas las respuestas deben seguir exactamente esta estructura:

1. Respuesta directa

Responde primero la pregunta en uno o dos párrafos claros. El usuario debe poder entender la idea principal sin leer el resto de la explicación.

2. Fundamento conceptual

Explica los principios, conceptos o teorías que sustentan la respuesta.

Incluye cuando corresponda:

- Definiciones precisas.
- Relaciones entre conceptos.
- Causas y consecuencias.
- Supuestos relevantes.
- Modelos mentales útiles.

3. Desarrollo paso a paso

Descompón el tema en una secuencia lógica.

Usa pasos numerados únicamente cuando exista un proceso, procedimiento, evolución o relación causal que lo justifique.

No presentes una lista arbitraria de puntos sin conexión lógica.

4. Ejemplo aplicado

Incluye al menos un ejemplo concreto.

El ejemplo debe:

- Ser coherente con la pregunta.
- Mostrar cómo se aplica el concepto.
- Evitar detalles innecesarios.
- Explicar qué conclusión debe extraerse.

Cuando el tema sea técnico, incluye pseudocódigo, código, ecuaciones, diagramas textuales o escenarios cuando aporten valor.

5. Análisis crítico

Expone los principales:

- Beneficios.
- Limitaciones.
- Riesgos.
- Trade-offs.
- Alternativas.

No presentes una solución como universalmente correcta si depende del contexto.

6. Errores comunes

Identifica entre dos y cuatro errores frecuentes relacionados con el tema.

Explica brevemente por qué son incorrectos o problemáticos.

7. Conclusión

Resume la idea central y establece una recomendación, criterio de decisión o aprendizaje clave.

La conclusión no debe repetir literalmente la respuesta inicial.

8. Pregunta de comprobación

Finaliza con una sola pregunta breve que permita verificar si el usuario comprendió el concepto o que lo invite a aplicarlo.

Reglas de calidad

- Prioriza precisión sobre extensión.
- Evita frases grandilocuentes o innecesariamente académicas.
- No uses jerga sin explicarla.
- No abuses de analogías.
- No repitas la misma idea en varias secciones.
- No uses citas inventadas.
- No atribuyas opiniones al MIT ni afirmes representar oficialmente a esa institución.
- No digas que eres realmente profesor del MIT. Adopta únicamente un nivel de rigor y estilo pedagógico comparable.
- Cuando existan varias interpretaciones válidas, preséntalas de forma equilibrada.
- Cuando el tema sea controversial, separa claramente evidencia, consenso, hipótesis y opinión.
- Cuando el usuario solicite una respuesta breve, conserva las mismas secciones, pero reduce cada una al mínimo necesario.
- Cuando el usuario solicite código, entrega código funcional, claro, comentado de forma útil y acompañado por una explicación de las decisiones relevantes.
- Cuando el usuario solicite una comparación, define primero los criterios y luego compara las opciones bajo esos mismos criterios.
- Cuando el usuario solicite una recomendación, explica las condiciones bajo las cuales esa recomendación es válida.

Tratamiento de información incierta

Cuando no exista certeza suficiente:

- Indica claramente qué parte es segura.
- Señala qué parte depende de supuestos.
- Explica qué información permitiría mejorar la respuesta.
- Evita presentar estimaciones como hechos.

Longitud

La longitud predeterminada debe ser suficiente para explicar correctamente el tema, sin extenderse innecesariamente.

Como referencia:

- Pregunta simple: 400 a 700 palabras.
- Pregunta intermedia: 700 a 1.200 palabras.
- Pregunta compleja: 1.200 a 2.000 palabras.

Reduce la longitud cuando el usuario lo solicite explícitamente.
            """
        )

    def stream(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> Iterator[str]:
        """
        Envía mensajes al LLM y devuelve fragmentos de texto
        conforme llegan mediante SSE.
        """

        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": (
                temperature if temperature is not None else self.config.temperature
            ),
            "messages": messages,
            "stream": True,
        }

        system_prompt = self.agent_system_prompt()

        if system_prompt:
            body["system"] = system_prompt

        request = urllib.request.Request(
            url=self.config.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-api-key": self.config.api_key,
            },
            method="POST",
        )

        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                yield from self._read_sse_stream(response)

        except urllib.error.HTTPError as error:
            response_body = error.read().decode(
                "utf-8",
                errors="replace",
            )
            raise LLMProviderError(
                f"Error HTTP {error.code}: {response_body}"
            ) from error

        except urllib.error.URLError as error:
            raise LLMConnectionError(
                f"No fue posible conectarse con "
                f"{self.config.base_url}: {error.reason}"
            ) from error

        except TimeoutError as error:
            raise LLMConnectionError(
                "La conexión con el LLM excedió el tiempo límite."
            ) from error

    def complete(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Consume completamente el stream y devuelve la
        respuesta final como texto.
        """

        fragments = list(
            self.stream(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
            )
        )

        answer = "".join(fragments).strip()

        if not answer:
            raise LLMEmptyResponseError(
                "El LLM finalizó sin devolver texto."
            )

        return answer

    def ask(
        self,
        question: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Método simplificado para hacer una sola pregunta.
        """

        return self.complete(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            system_prompt=system_prompt,
        )

    def stream_question(
        self,
        question: str,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """
        Método simplificado para hacer una pregunta
        recibiendo los fragmentos del stream.
        """

        return self.stream(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            system_prompt=system_prompt,
        )

    # ------------------------------------------------------------------
    # Ciclo agentic con tool calling
    # ------------------------------------------------------------------

    def run_agent_loop(
        self,
        question: str,
        tools: list[ToolDefinition],
        tool_executor: ToolExecutor,
        system_prompt: str | None = None,
        max_iterations: int = 10,
        logger: AgentLogger | None = None,
    ) -> str:
        """
        Ejecuta un ciclo agentic completo con soporte de tool calling nativo
        de la API de Anthropic.

        Parámetros
        ----------
        question:
            Pregunta inicial del usuario.
        tools:
            Lista de definiciones de tools (nombre, descripción, input_schema).
        tool_executor:
            Función Python que recibe (tool_name, tool_input) y devuelve
            el resultado como str. Es aquí donde inyectas tus skills.
        system_prompt:
            Prompt de sistema opcional (si no se pasa, usa agent_system_prompt).
        max_iterations:
            Número máximo de ciclos tool_use → tool_result para evitar loops.
        logger:
            Instancia de AgentLogger. Si no se pasa, se crea uno por defecto
            con nivel INFO. Pasa AgentLogger(level="DEBUG") para ver previews
            de resultados de tools, o AgentLogger(log_file="agent.log") para
            guardar a archivo.

        Retorna
        -------
        La respuesta final en texto del modelo.
        """
        log = logger or AgentLogger()
        messages: list[Message] = [{"role": "user", "content": question}]
        active_system = system_prompt or self.agent_system_prompt()

        log.inicio(question, [t["name"] for t in tools])

        for iteration in range(max_iterations):
            log.iteracion(iteration + 1)
            response = self._call_with_tools(
                messages=messages,
                tools=tools,
                system_prompt=active_system,
            )

            stop_reason = response.get("stop_reason")
            content_blocks = response.get("content", [])
            log.stop_reason(stop_reason)

            # Agregar la respuesta del asistente al historial
            messages.append({"role": "assistant", "content": content_blocks})

            if stop_reason == "end_turn":
                # Extraer texto de los bloques de contenido
                text_parts = [
                    block["text"]
                    for block in content_blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                answer = "".join(text_parts).strip()
                if not answer:
                    raise LLMEmptyResponseError(
                        "El LLM finalizó sin devolver texto."
                    )
                log.respuesta_final(answer)
                return answer

            if stop_reason == "tool_use":
                # Ejecutar todas las tools solicitadas en este turno
                tool_results: list[dict[str, Any]] = []
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue

                    tool_name = block["name"]
                    tool_input = block.get("input", {})
                    tool_use_id = block["id"]

                    log.tool_llamada(tool_name, tool_input)
                    try:
                        result_content = tool_executor(tool_name, tool_input)
                        log.tool_resultado(tool_name, result_content)
                    except Exception as exc:
                        log.tool_error(tool_name, exc)
                        result_content = f"Error ejecutando {tool_name}: {exc}"

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result_content,
                        }
                    )

                # Agregar los resultados al historial como mensaje del usuario
                messages.append({"role": "user", "content": tool_results})
                continue

            # stop_reason inesperado — salir del ciclo
            log.stop_inesperado(stop_reason)
            break

        raise LLMProviderError(
            f"El agente alcanzó el límite de {max_iterations} iteraciones "
            "sin producir una respuesta final."
        )

    def _call_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system_prompt: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        Llama a la API y reensambla la respuesta SSE en un objeto equivalente
        al JSON no‑streaming de Anthropic:
          { "stop_reason": "...", "content": [ {type, text|id|name|input}, ... ] }

        El servidor siempre responde con SSE, incluso sin pedir stream=True,
        por lo que parseamos los eventos aquí en vez de esperar JSON puro.
        """
        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": (
                temperature if temperature is not None else self.config.temperature
            ),
            "messages": messages,
            "tools": tools,
            "system": system_prompt,
            "stream": True,
        }

        request = urllib.request.Request(
            url=self.config.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-api-key": self.config.api_key,
            },
            method="POST",
        )

        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            body_text = error.read().decode("utf-8", errors="replace")
            raise LLMProviderError(
                f"Error HTTP {error.code}: {body_text}"
            ) from error
        except urllib.error.URLError as error:
            raise LLMConnectionError(
                f"No fue posible conectarse con {self.config.base_url}: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise LLMConnectionError(
                "La conexión con el LLM excedió el tiempo límite."
            ) from error

        return self._parse_sse_into_message(raw)

    def _parse_sse_into_message(self, raw: str) -> dict[str, Any]:
        """
        Convierte un stream SSE completo en un objeto de mensaje con la forma:
          {
            "stop_reason": "end_turn" | "tool_use",
            "content": [
              {"type": "text", "text": "..."},
              {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
              ...
            ]
          }

        Maneja los eventos de Anthropic SSE:
          - content_block_start   → abre un bloque (text o tool_use)
          - content_block_delta   → appenda texto o input_json al bloque activo
          - content_block_stop    → cierra el bloque activo
          - message_delta         → captura stop_reason
          - error                 → lanza LLMProviderError
        """
        # bloques reconstruidos indexados por su posición
        blocks: dict[int, dict[str, Any]] = {}
        stop_reason: str = "end_turn"
        current_index: int | None = None

        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue

            data_text = line[5:].strip()
            if not data_text or data_text == "[DONE]":
                continue

            try:
                ev = json.loads(data_text)
            except json.JSONDecodeError:
                continue

            ev_type = ev.get("type", "")

            if ev_type == "content_block_start":
                current_index = ev.get("index", 0)
                block = ev.get("content_block", {})
                btype = block.get("type", "text")
                if btype == "tool_use":
                    blocks[current_index] = {
                        "type": "tool_use",
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "_input_json": "",   # buffer acumulador
                    }
                else:
                    blocks[current_index] = {"type": "text", "text": ""}

            elif ev_type == "content_block_delta":
                idx = ev.get("index", current_index)
                delta = ev.get("delta", {})
                dtype = delta.get("type", "")
                block = blocks.get(idx)
                if block is None:
                    continue

                if dtype == "text_delta":
                    block["text"] = block.get("text", "") + delta.get("text", "")

                elif dtype == "input_json_delta":
                    block["_input_json"] = block.get("_input_json", "") + delta.get("partial_json", "")

            elif ev_type == "content_block_stop":
                idx = ev.get("index", current_index)
                block = blocks.get(idx)
                if block and block.get("type") == "tool_use":
                    # Parsear el JSON acumulado del input
                    raw_input = block.pop("_input_json", "") or "{}"
                    try:
                        block["input"] = json.loads(raw_input)
                    except json.JSONDecodeError:
                        block["input"] = {}

            elif ev_type == "message_delta":
                delta = ev.get("delta", {})
                if "stop_reason" in delta:
                    stop_reason = delta["stop_reason"]

            elif ev_type == "error":
                self._raise_stream_error(ev)

        # Ordenar bloques por índice y eliminar buffers internos
        content = [blocks[i] for i in sorted(blocks)]
        return {"stop_reason": stop_reason, "content": content}

    # ------------------------------------------------------------------
    # SSE stream (sin cambios)
    # ------------------------------------------------------------------

    def _read_sse_stream(
        self,
        response: Any,
    ) -> Iterator[str]:
        """
        Procesa una respuesta Server-Sent Events.
        """

        current_event: str | None = None

        for raw_line in response:
            line = raw_line.decode(
                "utf-8",
                errors="replace",
            ).strip()

            if not line:
                continue

            if line.startswith("event:"):
                current_event = line[6:].strip()
                continue

            if not line.startswith("data:"):
                continue

            data_text = line[5:].strip()

            if not data_text:
                continue

            if data_text == "[DONE]":
                break

            try:
                event_data = json.loads(data_text)
            except json.JSONDecodeError:
                continue

            event_type = event_data.get(
                "type",
                current_event,
            )

            if event_type == "content_block_delta":
                delta = event_data.get("delta", {})

                if isinstance(delta, dict):
                    text = delta.get("text")

                    if text:
                        yield str(text)

            elif event_type == "error":
                self._raise_stream_error(event_data)

            elif event_type == "message_stop":
                break

    @staticmethod
    def _raise_stream_error(
        event_data: dict[str, Any],
    ) -> None:
        error_data = event_data.get("error", {})

        if isinstance(error_data, dict):
            message = error_data.get(
                "message",
                "El proveedor devolvió un error desconocido.",
            )
        else:
            message = str(error_data)

        raise LLMProviderError(str(message))