"""Being の短期記憶を、毎ターンのプロンプトの【直近の出来事】に出す本文にする (#1824、design_decisions D1824-10、D1824-22)。

行の順は集約の ``recent()`` に従う。自分の行動は「[行動] 要約」の行で、行為について本人が知ったことは、ほかの観測と
同じ 1 行で出す (#2345)。
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.contract import ActionTaken, ObservedTime
from ai_rpg_world.being.domain.old_world_preformatted_line import OldWorldPreformattedLine
from ai_rpg_world.being.domain.short_term_memory import (
    Attempt,
    Experience,
    Lapse,
    Perception,
    ShortTermMemory,
)

NO_RECENT_EVENTS = "（直近の出来事はありません）"


def _line(time: ObservedTime, body: str, inner_thought: str | None = None) -> str:
    thought = (inner_thought or "").strip()
    return f"[{time.display}] {body}" + (f"\n  心の声: {thought}" if thought else "")


def _with_memo_rejections(line: str, attempt: Attempt) -> str:
    return line + "".join(f"\n  メモ: {rejection}" for rejection in attempt.memo_rejections)


class _Line:
    """出来事 1 つを行にする。行にしない出来事は None。"""

    def perceived(self, perception: Perception) -> str | None:
        observation = perception.observation
        return _line(observation.time, observation.body_without_people())

    def attempted(self, attempt: Attempt, taken: ActionTaken) -> str | None:
        summary = taken.summary_text()
        head = "[行動]" if summary is None else f"[行動] {summary}"
        # 呼び出しの行は、通った呼び方を見せる。断られた行動には付けない (#2273)。
        call = f"\n  呼び出し: {attempt.call_text}" if taken.accepted and attempt.call_text is not None else ""
        return _with_memo_rejections(_line(taken.time, head + call, attempt.move.inner_thought), attempt)

    def attempted_without_response(self, attempt: Attempt) -> str | None:
        # 切り替える前のプロンプトに無かった行なので、切り替えでは出さないと決めた (design_decisions D1824-22)。
        return None

    def attempted_in_old_world(self, attempt: Attempt, line: OldWorldPreformattedLine) -> str | None:
        return _with_memo_rejections(_line(line.time, line.body, attempt.move.inner_thought), attempt)

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
