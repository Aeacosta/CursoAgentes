from __future__ import annotations


import json
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


from core.config import LLMConfig
from core.exceptions import (
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
)




Message = dict[str, str]




class FreeClaudeCodeClient:
    """
    Cliente reutilizable para servidores compatibles con
    Anthropic Messages API y streaming SSE.
    """


    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()

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
            """) 

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
                temperature
                if temperature is not None
                else self.config.temperature
            ),
            "messages": messages,
            "stream": True,
        }

        system_prompt = self.agent_system_prompt()

        if system_prompt:
            body["system"] = system_prompt


        request = Request(
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
            with urlopen(
                request,
                timeout=self.config.timeout,
            ) as response:
                yield from self._read_sse_stream(response)


        except HTTPError as error:
            response_body = error.read().decode(
                "utf-8",
                errors="replace",
            )


            raise LLMProviderError(
                f"Error HTTP {error.code}: {response_body}"
            ) from error


        except URLError as error:
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
