from __future__ import annotations

import logging
import os
from dataclasses import dataclass

_log = logging.getLogger("agente.config")


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 8192
    temperature: float = 0.1
    timeout: int = 150

    @classmethod
    def from_env(cls) -> "LLMConfig":
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:8082/v1/messages?beta=true")
        api_key  = os.getenv("LLM_API_KEY", "freecc")
        model    = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

        _log.debug(
            "LLMConfig.from_env() | LLM_BASE_URL=%r (env=%r) | LLM_MODEL=%r (env=%r) | "
            "LLM_API_KEY set=%s (prefix=%s)",
            base_url,
            os.getenv("LLM_BASE_URL"),
            model,
            os.getenv("LLM_MODEL"),
            bool(os.getenv("LLM_API_KEY")),
            api_key[:8] + "..." if len(api_key) > 8 else api_key,
        )

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "8192")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            timeout=int(os.getenv("LLM_TIMEOUT", "180")),
        )