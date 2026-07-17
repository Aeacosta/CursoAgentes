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


import logging
_module_log = logging.getLogger("agente.llm_client")


class _CaseSensitiveRequest(urllib.request.Request):
    """
    urllib.request.Request title-cases all header names (e.g. x-api-key → X-Api-Key).
    Some proxies are case-sensitive and require lowercase header names.
    This subclass preserves the exact casing provided by the caller.
    """

    def add_unredirected_header(self, key: str, val: str) -> None:
        # Store under the original key, bypassing the title-case normalisation.
        self.unredirected_hdrs[key] = val

    def get_header(self, header_name: str) -> str | None:  # type: ignore[override]
        # urllib internally looks up headers with title-cased keys; check both.
        return (
            self.headers.get(header_name)
            or self.headers.get(header_name.capitalize())
            or self.unredirected_hdrs.get(header_name)
            or self.unredirected_hdrs.get(header_name.capitalize())
        )


def _make_request(url: str, data: bytes, headers: dict[str, str]) -> "_CaseSensitiveRequest":
    """Builds a POST Request preserving exact header casing."""
    req = _CaseSensitiveRequest(url=url, data=data, method="POST")
    for key, value in headers.items():
        # Use the internal dict directly to skip title-casing.
        req.headers[key] = value
    return req


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
Eres un ingeniero de software experto y auditor de calidad de código, especializado en Clean Code (Robert C. Martin)
y en los patrones de diseño de la Banda de los Cuatro (Design Patterns: Elements of Reusable Object-Oriented Software).

TU ÚNICA TAREA es analizar el código fuente proporcionado y devolver un único objeto JSON válido.

REGLAS DE SALIDA — ABSOLUTAMENTE CRÍTICAS:
1. El PRIMER carácter de tu respuesta DEBE ser "{". No escribas ninguna palabra, saludo, explicación ni pensamiento antes del JSON.
2. El ÚLTIMO carácter de tu respuesta DEBE ser "}". No escribas nada después del JSON.
3. NO uses bloques de código markdown (sin ```, sin ```json).
4. NO incluyas comentarios dentro del JSON.
5. Todos los saltos de línea dentro de cadenas deben escaparse como \\n.
6. El JSON debe poder parsearse con json.loads() de Python sin ningún preprocesamiento.

ESQUEMA JSON REQUERIDO (todas las claves son obligatorias):

{
  "reporte": [
    {
      "id": "<número secuencial como cadena, p. ej. '1'>",
      "code_smell": "<nombre del problema de código>",
      "violacion": "<qué regla de Clean Code o principio SOLID se incumple y por qué>",
      "referencia": "<libro, capítulo o principio exacto, p. ej. 'Clean Code - Capítulo 2: Nombres con Significado'>",
      "metrica": <entero de 0 a 100 donde 100 = código perfectamente limpio y 0 = extremadamente sucio>
    }
  ],
  "codigo_original": "<el código fuente original como cadena con saltos de línea escapados>",
  "codigo_corregido": "<el código fuente completamente refactorizado como cadena con saltos de línea escapados>",
  "resumen_ejecutivo": "<párrafo explicando cada corrección aplicada y qué patrón(es) de diseño GoF se utilizaron, citando nombre e intención del patrón>",
  "puntuacion_general": <entero de 0 a 100 que representa la calidad ponderada del código original>
}

GUÍA DE PUNTUACIÓN:
- puntuacion_general = promedio de todos los valores de metrica individuales, redondeado al entero más cercano.
- metrica por problema: comenzar en 100 y restar proporcionalmente según la gravedad (crítico = -30 a -40, mayor = -15 a -25, menor = -5 a -10).

RECUERDA: tu respuesta empieza con { y termina con }. Absolutamente nada más.
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

        # Combine the fixed agent instructions with any caller-supplied context
        # (e.g. RAG docs). The agent rules come first so the model sees them as
        # the primary directive; RAG context is appended after.
        agent_instructions = self.agent_system_prompt()
        if system_prompt:
            combined = agent_instructions + "\n\n---\n\n" + system_prompt
        else:
            combined = agent_instructions
        body["system"] = combined

        request = _make_request(
            url=self.config.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-api-key": self.config.api_key,
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )

        _module_log.debug(
            "stream() → POST %s | model=%s | api_key_prefix=%s",
            self.config.base_url,
            self.config.model,
            self.config.api_key[:8] + "..." if len(self.config.api_key) > 8 else self.config.api_key,
        )

        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                _module_log.debug("stream() ← HTTP %s OK", response.status)
                yield from self._read_sse_stream(response)

        except urllib.error.HTTPError as error:
            response_body = error.read().decode(
                "utf-8",
                errors="replace",
            )
            _module_log.debug(
                "stream() ← HTTP %d ERROR | url=%s | body=%s",
                error.code,
                self.config.base_url,
                response_body[:500],
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

        request = _make_request(
            url=self.config.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-api-key": self.config.api_key,
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )

        _module_log.debug(
            "_call_with_tools() → POST %s | model=%s | api_key_prefix=%s | tools=%s",
            self.config.base_url,
            self.config.model,
            self.config.api_key[:8] + "..." if len(self.config.api_key) > 8 else self.config.api_key,
            [t["name"] for t in tools],
        )
        _module_log.debug(
            "_call_with_tools() request body (truncated):\n%s",
            json.dumps({**body, "messages": f"[{len(messages)} messages]"}, ensure_ascii=False, indent=2)[:800],
        )

        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                _module_log.debug("_call_with_tools() ← HTTP OK | response_len=%d", len(raw))
        except urllib.error.HTTPError as error:
            body_text = error.read().decode("utf-8", errors="replace")
            _module_log.debug(
                "_call_with_tools() ← HTTP %d ERROR | url=%s | body=%s",
                error.code,
                self.config.base_url,
                body_text[:500],
            )
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