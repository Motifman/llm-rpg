"""Being の短期記憶を、毎ターンのプロンプトの【直近の出来事】に出す本文にする (#1824、design_decisions D1824-10、D1824-22)。

行の形は、今の短期記憶から作っていたころのプロンプトと同じ。行の順は集約の ``recent()`` に従う。
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.contract import Observation, ObservedTime
from ai_rpg_world.being.domain.short_term_memory import (
    Attempt,
    Experience,
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
        # 切り替える前のプロンプトに無かった行なので、切り替えでは出さないと決めた (design_decisions D1824-22)。
        return None

    def lapsed(self, lapse: Lapse) -> str | None:
        return _line(lapse.time, lapse.body)


def recent_events_text(memory: ShortTermMemory) -> str:
    return experiences_text(memory.recent())


def experiences_text(experiences: Sequence[Experience]) -> str:
    """並べた順のまま、出来事を【直近の出来事】と同じ行にする。いきさつやエピソードの材料にも使う。"""
    text = experience_lines(experiences)
    return NO_RECENT_EVENTS if text is None else text


def experience_lines(experiences: Sequence[Experience]) -> str | None:
    """``experiences_text`` と同じ行。行になる出来事が 1 つも無ければ None。"""
    reader = _Line()
    lines = [line for experience in experiences if (line := experience.show_to(reader)) is not None]
    if not lines:
        return None
    return "\n".join(f"- {line}" for line in lines)


__all__ = ["NO_RECENT_EVENTS", "experience_lines", "experiences_text", "recent_events_text"]
