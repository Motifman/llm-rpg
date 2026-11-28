"""古い世界 (タイルマップの世界) だけが使う、自分の 1 手への返事。古い世界を消すときに一緒に消す (#2236)。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from ai_rpg_world.being.contract import ObservedTime, OccurrenceOrder
from ai_rpg_world.being.domain.short_term_memory import Attempt, AttemptResponse, ExperienceReader
from ai_rpg_world.domain.being.exception.being_exceptions import ShortTermMemoryValidationException

_T_co = TypeVar("_T_co", covariant=True)


@dataclass(frozen=True, kw_only=True)
class OldWorldPreformattedLine(AttemptResponse):
    """古い世界が「[行動] 要約 → [結果] 文」に組み終えて渡す、【直近の出来事】の 1 行の本文 (design_decisions D1824-7)。"""

    call_id: str
    body: str
    time: ObservedTime
    order: OccurrenceOrder | None = None

    def __post_init__(self) -> None:
        for name in ("call_id", "body"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ShortTermMemoryValidationException(f"{name} must be non-blank str")
        if not isinstance(self.time, ObservedTime):
            raise ShortTermMemoryValidationException("time must be ObservedTime")
        if self.order is not None and not isinstance(self.order, OccurrenceOrder):
            raise ShortTermMemoryValidationException("order must be OccurrenceOrder or None")

    def answers(self, call_id: str) -> bool:
        return self.call_id == call_id

    def show_to(self, attempt: Attempt, reader: ExperienceReader[_T_co]) -> _T_co:
        return reader.attempted_in_old_world(attempt, self)


__all__ = ["OldWorldPreformattedLine"]
