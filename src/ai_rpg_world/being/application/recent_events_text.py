"""Being の短期記憶を、毎ターンのプロンプトの【直近の出来事】に出す本文にする (#1824、design_decisions D1824-10、D1824-22)。

行の形は、今の短期記憶から作っていたころのプロンプトと同じ。行の順は集約の ``recent()`` に従う。
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.contract import (
    ContractViolation,
    Observation,
    ObservedTime,
    OwnActionCompleted,
    OwnActionResult,
    TextWithPeople,
)
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


def _attempt_line(
    attempt: Attempt, time: ObservedTime, result_body: str, *, summary: str | None, succeeded: bool
) -> str:
    # 要約の無い試み (古い run と、要約を足す前の snapshot) は、結果の文だけの行のまま出す。古い run の結果の文は、
    # すでに古い run の行の形になっている。
    body = (
        result_body
        if summary is None
        else _own_move_body(summary, result_body, succeeded=succeeded, call_text=attempt.call_text)
    )
    return _line(time, body, attempt.move.inner_thought) + "".join(
        f"\n  メモ: {line}" for line in attempt.memo_rejections
    )


def _own_move_body(summary: str, result_body: str, *, succeeded: bool, call_text: str | None) -> str:
    """失敗には呼び出しの行を付けない。"""
    if not succeeded:
        return f"[行動] {summary} → [失敗] | {result_body}"
    call = "" if call_text is None else f"\n  呼び出し: {call_text}"
    return f"[行動] {summary} → [結果] {result_body}{call}"


def _summary_of(route: object) -> str | None:
    if not isinstance(route, OwnActionResult) or route.action_summary is None:
        return None
    return _summary_text(route.action_summary)


def _summary_text(summary: str | TextWithPeople) -> str:
    if isinstance(summary, TextWithPeople):
        raise ContractViolation("an action summary with people placeholders cannot be read before they are filled in")
    return summary


class _Line:
    """出来事 1 つを行にする。行にしない出来事は None。"""

    def perceived(self, perception: Perception) -> str | None:
        observation = perception.observation
        route = observation.route
        if isinstance(route, OwnActionCompleted):
            # あとから届く結果は呼び出しと 1 対 1 ではないので、古い run と同じく引数の無い呼び出しの行を付ける。
            body = _own_move_body(
                _summary_text(route.action_summary),
                observation.body_without_people(),
                succeeded=route.succeeded,
                call_text=f"{route.tool}()",
            )
            return _line(observation.time, body)
        return _line(observation.time, observation.body_without_people())

    def attempted(self, attempt: Attempt, result: Observation) -> str | None:
        route = result.route
        succeeded = isinstance(route, OwnActionResult) and route.succeeded
        return _attempt_line(
            attempt, result.time, result.body_without_people(), summary=_summary_of(route), succeeded=succeeded
        )

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationOutcome) -> str | None:
        return _attempt_line(
            attempt, result.time, result.body, summary=result.action_summary, succeeded=result.succeeded
        )

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
