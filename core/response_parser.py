"""
core/response_parser.py
-----------------------
Owns everything that sits between the raw LLM response string and a parsed
Python dict:

  • The canonical system prompt that instructs the model to emit JSON wrapped
    in ###JSON_START### / ###JSON_END### delimiters.
  • The multi-strategy JSON extractor that handles delimiter-less responses,
    leaked reasoning blocks, markdown fences, and stray braces in prose.

Both the dashboard (app.py) and the LLM client (llm_client.py) should import
from here so the rules live in exactly one place.
"""

from __future__ import annotations

import json
import re


# ---------------------------------------------------------------------------
# Delimiter constants
# ---------------------------------------------------------------------------

JSON_START = "###JSON_START###"
JSON_END   = "###JSON_END###"

# Top-level keys that must appear immediately after '{' in the expected schema.
# Used by the schema-aware extractor to skip stray braces in reasoning prose.
_SCHEMA_KEYS: tuple[str, ...] = (
    '"reporte"',
    '"codigo_corregido"',
    '"resumen_ejecutivo"',
)

# Files larger than this threshold get the smells-only prompt (no refactored code).
FILE_SIZE_LIMIT_BYTES: int = 2048


# ---------------------------------------------------------------------------
# ResponseParser
# ---------------------------------------------------------------------------

class ResponseParser:
    """
    Stateless helper that converts a raw LLM response string into a parsed
    dict (or None when all strategies fail).

    Extraction strategies (in order)
    ---------------------------------
    0. Strip ``<think>…</think>`` blocks emitted by reasoning models.
    1. Extract the slice between ``###JSON_START###`` / ``###JSON_END###``.
    2. Direct ``json.loads`` on the cleaned string.
    3. Strip a single `` ```json … ``` `` fence and retry.
    4. Schema-aware brace walk: find the first ``{`` whose immediate content
       starts with a known schema key, then walk character-by-character to
       its matching ``}``.  This correctly skips stray braces that appear
       inside leaked reasoning prose.

    Usage
    -----
    >>> parser = ResponseParser()
    >>> result = parser.extract(raw_llm_text)   # dict | None
    >>> prompt = parser.system_prompt()          # str
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def system_prompt(self) -> str:
        """Return the canonical system prompt for the code-review task."""
        return (
            "Eres un ingeniero de software experto y auditor de calidad de código, "
            "especializado en Clean Code (Robert C. Martin) y en los patrones de diseño "
            "de la Banda de los Cuatro (Design Patterns: Elements of Reusable Object-Oriented Software).\n\n"
            "TU ÚNICA TAREA es analizar el código fuente proporcionado y devolver un único objeto JSON válido.\n\n"
            "EXHAUSTIVIDAD — OBLIGATORIA:\n"
            "- El array \"reporte\" DEBE contener UNA entrada por CADA code smell, violación o problema de "
            "calidad que encuentres en el código.\n"
            "- No te detengas en el primer problema. Analiza el código completo e incluye TODOS los problemas encontrados.\n"
            "- Si no encuentras más problemas, di por qué en el resumen ejecutivo.\n\n"
            "REGLAS DE SALIDA — ABSOLUTAMENTE CRÍTICAS:\n"
            f"1. Tu respuesta DEBE comenzar EXACTAMENTE con la marca {JSON_START} en su propia línea.\n"
            f"2. Tu respuesta DEBE terminar EXACTAMENTE con la marca {JSON_END} en su propia línea.\n"
            "3. Entre esas dos marcas va ÚNICAMENTE el objeto JSON, sin texto adicional.\n"
            "4. NO uses bloques de código markdown (sin ```, sin ```json).\n"
            "5. NO incluyas comentarios dentro del JSON.\n"
            "6. Todos los saltos de línea dentro de cadenas deben escaparse como \\n.\n"
            "7. El JSON entre las marcas debe poder parsearse con json.loads() de Python sin ningún preprocesamiento.\n"
            "8. NO escribas ningún razonamiento ni texto previo antes de la marca de inicio.\n\n"
            "ESQUEMA JSON REQUERIDO (todas las claves son obligatorias):\n\n"
            "{\n"
            "  \"reporte\": [\n"
            "    {\n"
            "      \"id\": \"<número secuencial como cadena, p. ej. '1'>\",\n"
            "      \"code_smell\": \"<nombre del problema de código>\",\n"
            "      \"violacion\": \"<qué regla de Clean Code o principio SOLID se incumple y por qué>\",\n"
            "      \"referencia\": \"<libro, capítulo o principio exacto, p. ej. 'Clean Code - Capítulo 2: Nombres con Significado'>\",\n"
            "      \"severidad\": \"<uno de exactamente estos tres valores: 'critico', 'mayor', 'menor'>\"\n"
            "    }\n"
            "  ],\n"
            "  \"codigo_corregido\": \"<el código fuente completamente refactorizado como cadena con saltos de línea escapados>\",\n"
            "  \"resumen_ejecutivo\": \"<párrafo explicando cada corrección aplicada y qué patrón(es) de diseño GoF se utilizaron, citando nombre e intención del patrón>\"\n"
            "}\n\n"
            "GUÍA DE SEVERIDAD:\n"
            "- \"critico\": viola SRP, God Class, lista de 10+ parámetros, acoplamiento fuerte, código duplicado masivo.\n"
            "- \"mayor\":   nombres poco claros, métodos largos, falta de encapsulación, lógica condicional compleja.\n"
            "- \"menor\":   comentarios innecesarios, formato inconsistente, código muerto pequeño.\n\n"
            f"RECUERDA: envuelve tu respuesta SIEMPRE con {JSON_START} al inicio y {JSON_END} al final. "
            "Nada fuera de esas marcas."
        )

    def smells_only_system_prompt(self) -> str:
        """
        Lighter prompt for files that exceed FILE_SIZE_LIMIT_BYTES.
        Asks only for the code-smells list — no refactored code, no executive
        summary — so the LLM output stays within token limits.
        """
        return (
            "Eres un ingeniero de software experto especializado en Clean Code "
            "(Robert C. Martin) y principios SOLID.\n\n"
            "TU ÚNICA TAREA es listar TODOS los code smells y violaciones de calidad "
            "presentes en el código proporcionado. "
            "El archivo es demasiado grande para refactorizarlo, por lo que NO debes "
            "incluir código corregido ni resumen ejecutivo.\n\n"
            "REGLAS DE SALIDA — ABSOLUTAMENTE CRÍTICAS:\n"
            f"1. Tu respuesta DEBE comenzar EXACTAMENTE con la marca {JSON_START} en su propia línea.\n"
            f"2. Tu respuesta DEBE terminar EXACTAMENTE con la marca {JSON_END} en su propia línea.\n"
            "3. Entre esas dos marcas va ÚNICAMENTE el objeto JSON, sin texto adicional.\n"
            "4. NO uses bloques de código markdown (sin ```, sin ```json).\n"
            "5. NO incluyas comentarios dentro del JSON.\n"
            "6. El JSON debe poder parsearse con json.loads() de Python sin ningún preprocesamiento.\n"
            "7. NO escribas ningún razonamiento ni texto previo antes de la marca de inicio.\n\n"
            "ESQUEMA JSON REQUERIDO:\n\n"
            "{\n"
            "  \"reporte\": [\n"
            "    {\n"
            "      \"id\": \"<número secuencial como cadena, p. ej. '1'>\",\n"
            "      \"code_smell\": \"<nombre del problema>\",\n"
            "      \"violacion\": \"<qué regla o principio se incumple y por qué>\",\n"
            "      \"referencia\": \"<libro, capítulo o principio exacto>\",\n"
            "      \"severidad\": \"<'critico', 'mayor' o 'menor'>\"\n"
            "    }\n"
            "  ],\n"
            "  \"codigo_corregido\": \"\",\n"
            "  \"resumen_ejecutivo\": \"Archivo demasiado grande — solo se reportan code smells.\"\n"
            "}\n\n"
            "GUÍA DE SEVERIDAD:\n"
            "- \"critico\": viola SRP, God Class, lista de 10+ parámetros, acoplamiento fuerte, código duplicado masivo.\n"
            "- \"mayor\":   nombres poco claros, métodos largos, falta de encapsulación, lógica condicional compleja.\n"
            "- \"menor\":   comentarios innecesarios, formato inconsistente, código muerto pequeño.\n\n"
            f"RECUERDA: envuelve tu respuesta SIEMPRE con {JSON_START} al inicio y {JSON_END} al final. "
            "Nada fuera de esas marcas."
        )

    def extract(self, text: str) -> dict | None:
        """
        Try all strategies in order and return the first successfully parsed
        dict, or None if every strategy fails.
        """
        # 0. Strip <think>…</think> reasoning blocks
        cleaned = re.sub(
            r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE
        ).strip()

        # 1. Delimiter markers
        result = self._from_delimiters(cleaned)
        if result is not None:
            return result

        # 2. Direct parse
        result = self._attempt(cleaned)
        if result is not None:
            return result

        # 3. Strip markdown fence
        no_fence = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        no_fence = re.sub(r"\s*```\s*$", "", no_fence)
        result = self._attempt(no_fence)
        if result is not None:
            return result

        # 4. Schema-aware brace walk
        schema_slice = self._find_schema_json(cleaned)
        if schema_slice is not None:
            result = self._attempt(schema_slice)
            if result is not None:
                return result

        return None

    def extract_partial(self, text: str) -> dict | None:
        """
        Last-resort recovery for truncated / broken LLM responses.

        Tries to salvage the ``reporte`` array even when the surrounding JSON
        object is incomplete (e.g. the model was cut off mid-generation).
        Returns a minimal valid dict with ``reporte``, ``codigo_corregido``
        (empty) and ``resumen_ejecutivo`` so the normal render path works, or
        ``None`` when no array can be extracted at all.
        """
        cleaned = re.sub(
            r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE
        ).strip()

        # Try to locate the opening of the reporte array.
        # Handles both  "reporte": [  and  "report": [
        match = re.search(r'"(?:reporte|report)"\s*:\s*\[', cleaned)
        if match is None:
            return None

        start = match.end() - 1  # position of '['
        # Walk from '[' tracking depth to find the matching ']'
        depth = 0
        in_string = False
        escape_next = False
        end = None
        for i in range(start, len(cleaned)):
            c = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\" and in_string:
                escape_next = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end is None:
            return None

        array_text = cleaned[start:end]
        try:
            items = json.loads(array_text)
        except json.JSONDecodeError:
            return None

        if not isinstance(items, list):
            return None

        return {
            "reporte": items,
            "codigo_corregido": "",
            "resumen_ejecutivo": (
                "⚠ La respuesta del LLM fue truncada o incompleta — "
                "se recuperó solo la lista de code smells."
            ),
        }

    def clean_reasoning(self, text: str) -> str:
        """Return *text* with ``<think>…</think>`` blocks removed."""
        return re.sub(
            r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE
        ).strip()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _attempt(s: str) -> dict | None:
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    @staticmethod
    def _from_delimiters(text: str) -> dict | None:
        s_idx = text.find(JSON_START)
        e_idx = text.find(JSON_END)
        if s_idx == -1 or e_idx <= s_idx:
            return None
        between = text[s_idx + len(JSON_START) : e_idx].strip()
        return ResponseParser._attempt(between)

    @staticmethod
    def _find_schema_json(text: str) -> str | None:
        """
        Scan *text* for the first ``{`` immediately followed (within 60 chars,
        after stripping whitespace) by one of the known schema keys.  Once
        found, walk character-by-character tracking brace depth to locate the
        matching ``}``.

        This is safer than ``text.rfind("}")`` because reasoning prose often
        contains its own ``{…}`` blocks (e.g. code examples) that would cause
        the naïve approach to grab the wrong slice.
        """
        length = len(text)
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            peek = text[i + 1 : i + 61].lstrip()
            if not any(peek.startswith(k) for k in _SCHEMA_KEYS):
                continue
            # Balance braces from this position
            depth = 0
            in_string = False
            escape_next = False
            for j in range(i, length):
                c = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if c == "\\" and in_string:
                    escape_next = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[i : j + 1]
        return None
