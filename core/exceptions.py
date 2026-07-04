class LLMError(Exception):
    """Error general al comunicarse con el LLM."""


class LLMConnectionError(LLMError):
    """No fue posible conectarse con el servidor LLM."""


class LLMProviderError(LLMError):
    """El proveedor remoto rechazó la solicitud."""


class LLMEmptyResponseError(LLMError):
    """El servidor no devolvió contenido de texto."""