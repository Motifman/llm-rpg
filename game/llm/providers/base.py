from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class CompletionRequest:
    prompt: str
    system_prompt: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 512
    json_schema: Optional[Dict[str, Any]] = None  # 構造化出力用（未使用ならNone）


@dataclass
class CompletionResponse:
    text: str
    usage_prompt_tokens: Optional[int] = None
    usage_completion_tokens: Optional[int] = None
    parsed_json: Optional[Dict[str, Any]] = None


class LLMClient(ABC):
    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover - interface
        raise NotImplementedError


