from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LLMSettings:
    provider: str = os.getenv("LLM_PROVIDER", "openai")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "512"))
    memory_maxlen: int = int(os.getenv("LLM_MEMORY_MAXLEN", "20"))


def get_settings() -> LLMSettings:
    return LLMSettings()


