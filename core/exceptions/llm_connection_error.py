"""No fue posible conectarse con el servidor LLM."""

from core.exceptions.llm_error import LLMError


class LLMConnectionError(LLMError):
    """No fue posible conectarse con el servidor LLM."""

# Made with Bob
