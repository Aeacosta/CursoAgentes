from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 2048
    temperature: float = 0.2
    timeout: int = 120

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.getenv(
                "LLM_BASE_URL",
                "http://localhost:8082/v1/messages",
            ),
            api_key=os.getenv(
                "LLM_API_KEY",
                "freecc",
            ),
            model=os.getenv(
                "LLM_MODEL",
                "claude-3-5-sonnet-20241022",
            ),
            max_tokens=int(
                os.getenv("LLM_MAX_TOKENS", "2048")
            ),
            temperature=float(
                os.getenv("LLM_TEMPERATURE", "0.2")
            ),
            timeout=int(
                os.getenv("LLM_TIMEOUT", "120")
            ),
        )