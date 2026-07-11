"""El proveedor remoto rechazó la solicitud."""

from core.exceptions.llm_error import LLMError


class LLMProviderError(LLMError):
    """El proveedor remoto rechazó la solicitud."""

# Made with Bob
