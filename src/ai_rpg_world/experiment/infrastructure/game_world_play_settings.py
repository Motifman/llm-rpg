from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, final

_STUB = "stub"
LITELLM = "litellm"
_CLIENTS = (_STUB, LITELLM)
# 古い世界と同じ作り方で LiteLLM のクライアントを組むので、値の確かめ方と既定値は古い世界の読み手に任せる
_LLM_KEYS = frozenset(
    {
        "LLM_MODEL",
        "OPENAI_API_BASE",
        "OPENROUTER_PROVIDER",
        "OPENROUTER_QUANTIZATION",
        "LLM_REASONING_EFFORT",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "LLM_WALL_TIME_CAP_SECONDS",
        "LLM_RATE_LIMIT_RETRY_ATTEMPTS",
        "LLM_RATE_LIMIT_RETRY_BASE_SLEEP",
    }
)


@final
@dataclass(frozen=True)
class GameWorldPlaySettings:
    llm_client: str = _STUB
    memo_tools_enabled: bool = True
    episode_index_enabled: bool = True
    episode_index_limit: int = 10
    episode_recall_max_handles: int = 3
    wake_waiting_after_rounds: int = 3
    writing_wait_limit_seconds: float = 10.0
    writing_workers: int = 2
    writing_max_pending: int = 100
    random_seed: int = 42
    turn_parallel_workers: int | None = None
    llm_values: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_runtime_config(cls, values: Mapping[str, str]) -> GameWorldPlaySettings:
        # 古い世界の鍵を黙って読み捨てると、効いていない設定で run を回してしまう
        unknown = sorted(set(values) - set(_READERS) - _LLM_KEYS)
        if unknown:
            raise ValueError(f"runtime_config keys not used by the game world: {unknown}")
        read = {name: reader(values[key]) for key, (name, reader) in _READERS.items() if key in values}
        llm_values = {key: values[key] for key in sorted(_LLM_KEYS & set(values))}
        settings = cls(**read, llm_values=llm_values)
        settings._validate()
        return settings

    def to_trace_dict(self) -> dict[str, Any]:
        return asdict(self)

    def _validate(self) -> None:
        if self.llm_client not in _CLIENTS:
            raise ValueError(f"LLM_CLIENT must be one of {list(_CLIENTS)} for the game world, got {self.llm_client!r}")
        for name in ("episode_index_limit", "episode_recall_max_handles", "wake_waiting_after_rounds"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1, got {getattr(self, name)}")
        if self.writing_workers < 1 or self.writing_max_pending < 1:
            raise ValueError("ASYNC_EVENT_WORKERS and ASYNC_EVENT_MAX_PENDING must be >= 1")
        if not math.isfinite(self.writing_wait_limit_seconds) or self.writing_wait_limit_seconds < 0:
            raise ValueError("ASYNC_EVENT_SHUTDOWN_TIMEOUT_SECONDS must be a finite number >= 0")
        if self.turn_parallel_workers is not None and self.turn_parallel_workers < 1:
            raise ValueError(f"LLM_TURN_PARALLEL_WORKERS must be >= 1, got {self.turn_parallel_workers}")
        if self.llm_values and self.llm_client != LITELLM:
            raise ValueError(f"LLM keys {sorted(self.llm_values)} are only read when LLM_CLIENT is litellm")


def _bool(raw: str) -> bool:
    if raw.lower() in ("1", "true"):
        return True
    if raw.lower() in ("0", "false"):
        return False
    raise ValueError(f"expected a boolean, got {raw!r}")


_READERS: dict[str, tuple[str, Any]] = {
    "LLM_CLIENT": ("llm_client", str),
    "MEMO_TOOLS_ENABLED": ("memo_tools_enabled", _bool),
    "BEING_EPISODE_INDEX_ENABLED": ("episode_index_enabled", _bool),
    "BEING_EPISODE_INDEX_LIMIT": ("episode_index_limit", int),
    "BEING_EPISODE_RECALL_MAX_HANDLES": ("episode_recall_max_handles", int),
    "PLAY_WAKE_WAITING_AFTER_ROUNDS": ("wake_waiting_after_rounds", int),
    "ASYNC_EVENT_SHUTDOWN_TIMEOUT_SECONDS": ("writing_wait_limit_seconds", float),
    "ASYNC_EVENT_WORKERS": ("writing_workers", int),
    "ASYNC_EVENT_MAX_PENDING": ("writing_max_pending", int),
    "SCENARIO_RANDOM_SEED": ("random_seed", int),
    "LLM_TURN_PARALLEL_WORKERS": ("turn_parallel_workers", int),
}
