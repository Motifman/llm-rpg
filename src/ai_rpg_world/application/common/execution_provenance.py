"""実際の実行境界で確定した出典。保存用LLM呼出しIDとは混同しない。"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionProvenance:
    """一度の実行要求と、実際に進めた当人の手番を識別する。"""

    execution_request_id: str
    actor_player_id: int
    actor_turn: int
    tool_call_id: str | None = None
    llm_call_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.execution_request_id, str) or not self.execution_request_id:
            raise ValueError('execution_request_id は空でない文字列が必要です')
        for name in ('actor_player_id', 'actor_turn'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f'{name} は非負整数が必要です')
        for name in ('tool_call_id', 'llm_call_id'):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f'{name} は空でない文字列か None が必要です')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionProvenance:
        return cls(**data)


_CURRENT: ContextVar[ExecutionProvenance | None] = ContextVar('execution_provenance', default=None)


def current_execution_provenance() -> ExecutionProvenance | None:
    """実行中の要求だけを返す。ツールの入力から出典を受け取らない。"""
    return _CURRENT.get()


@contextmanager
def execution_provenance_scope(provenance: ExecutionProvenance) -> Iterator[None]:
    token = _CURRENT.set(provenance)
    try:
        yield
    finally:
        _CURRENT.reset(token)
