"""El servidor no devolvió contenido de texto."""

from core.exceptions.llm_error import LLMError


class LLMEmptyResponseError(LLMError):
    """El servidor no devolvió contenido de texto."""

# Made with Bob
