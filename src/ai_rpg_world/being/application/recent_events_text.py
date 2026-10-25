"""Being の短期記憶を、毎ターンのプロンプトの【直近の出来事】に出す本文にする (#1824、design_decisions D1824-10)。

行の形は今のプロンプトと同じ。行の順は集約の ``recent()`` に従う。
"""

from __future__ import annotations

from ai_rpg_world.being.contract import Observation, ObservedTime
from ai_rpg_world.being.domain.short_term_memory import (
    Attempt,
    Lapse,
    MemoryOperationOutcome,
    Perception,
    ShortTermMemory,
)

NO_RECENT_EVENTS = "（直近の出来事はありません）"


def _line(time: ObservedTime, body: str, inner_thought: str | None = None) -> str:
    thought = (inner_thought or "").strip()
    return f"[{time.display}] {body}" + (f"\n  心の声: {thought}" if thought else "")


class _Line:
    """出来事 1 つを行にする。行にしない出来事は None。"""

    def perceived(self, perception: Perception) -> str | None:
        return _line(perception.observation.time, perception.observation.body)

    def attempted(self, attempt: Attempt, result: Observation) -> str | None:
        return _line(result.time, result.body, attempt.move.inner_thought)

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationOutcome) -> str | None:
        return _line(result.time, result.body, attempt.move.inner_thought)

    def attempted_without_result(self, attempt: Attempt) -> str | None:
        # 今のプロンプトには結果の無い 1 手の行が無い。出すかは切り替えるときに決める。
        return None

    def lapsed(self, lapse: Lapse) -> str | None:
        return _line(lapse.time, lapse.body)


def recent_events_text(memory: ShortTermMemory) -> str:
    reader = _Line()
    lines = [line for experience in memory.recent() if (line := experience.show_to(reader)) is not None]
    if not lines:
        return NO_RECENT_EVENTS
    return "\n".join(f"- {line}" for line in lines)


__all__ = ["NO_RECENT_EVENTS", "recent_events_text"]
