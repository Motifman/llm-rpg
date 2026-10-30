"""Being の短期記憶から、毎ターンのプロンプトの【直近の出来事】の本文を作る規則を保証する (#1824、design_decisions D1824-10)。"""

from __future__ import annotations

from ai_rpg_world.being.application.recent_events_text import NO_RECENT_EVENTS, recent_events_text
from ai_rpg_world.being.contract import (
    UNKNOWN,
    AgentMove,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnActionResult,
    SeenOrHeard,
)
from ai_rpg_world.being.domain.short_term_memory import MemoryOperationOutcome, ObservedOutcome, ShortTermMemory
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_p1")


def _observation(
    body: str, *, display: str = "1日目 朝", route: object = SeenOrHeard(), order: OccurrenceOrder | None = None
) -> Observation:
    return Observation(
        body=body,
        route=route,
        time=ObservedTime(display=display),
        subject_is_self=isinstance(route, OwnActionResult),
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
        order=order,
    )


def _move(call_id: str, *, inner_thought: str | None = None) -> AgentMove:
    return AgentMove(call_id=call_id, tool_name="interact", arguments={}, inner_thought=inner_thought)


def _answered(
    memory: ShortTermMemory,
    call_id: str,
    body: str,
    *,
    turn: int,
    inner_thought: str | None = None,
    order: OccurrenceOrder | None = None,
) -> None:
    memory.act(_move(call_id, inner_thought=inner_thought), current_turn=turn)
    memory.receive_result(
        ObservedOutcome(_observation(body, route=OwnActionResult(call_id=call_id, succeeded=True), order=order)),
        current_turn=turn,
    )


class TestRecentEventsText:
    """recent_events_text が、出来事の種類ごとに今のプロンプトと同じ行を作ることを保証する。"""

    def test_empty_memory_shows_the_placeholder(self) -> None:
        """出来事が 1 つも無ければ、今のプロンプトと同じ「（直近の出来事はありません）」になる。"""
        assert recent_events_text(ShortTermMemory.empty(ADA)) == NO_RECENT_EVENTS == "（直近の出来事はありません）"

    def test_perception_is_a_line_with_its_time(self) -> None:
        """見聞きしたことは「- [時刻] 本文」の 1 行になる。"""
        memory = ShortTermMemory.empty(ADA)
        memory.perceive(_observation("ミオが坑道から戻ってきた"), current_turn=0)

        assert recent_events_text(memory) == "- [1日目 朝] ミオが坑道から戻ってきた"

    def test_attempt_shows_its_result_and_the_inner_thought_of_the_move(self) -> None:
        """結果のある試みは、結果の時刻と本文の行に、1 手の心の声の続き行が付く。心の声が無ければ続き行は無い。"""
        memory = ShortTermMemory.empty(ADA)
        _answered(memory, "call-1", "[行動] 扉を調べた → [結果] 鍵がかかっていた", turn=1, inner_thought="鍵を探そう")
        _answered(memory, "call-2", "[行動] 待った → [結果] 様子を見た", turn=2)

        assert recent_events_text(memory) == (
            "- [1日目 朝] [行動] 扉を調べた → [結果] 鍵がかかっていた\n  心の声: 鍵を探そう\n"
            "- [1日目 朝] [行動] 待った → [結果] 様子を見た"
        )

    def test_memory_operation_shows_its_result_and_the_inner_thought(self) -> None:
        """記憶の道具の試みも、記憶の結果の時刻と本文の行に、1 手の心の声の続き行が付く。"""
        memory = ShortTermMemory.empty(ADA)
        memory.act(_move("call-1", inner_thought="思い出そう"), current_turn=1)
        memory.receive_result(
            MemoryOperationOutcome(
                call_id="call-1", body="[行動] 思い出した → [結果] 鍵は事務所", time=ObservedTime(display="1日目 昼")
            ),
            current_turn=1,
        )

        assert recent_events_text(memory) == "- [1日目 昼] [行動] 思い出した → [結果] 鍵は事務所\n  心の声: 思い出そう"

    def test_lapse_is_a_line_without_inner_thought(self) -> None:
        """1 手を出せなかったことは「- [時刻] 本文」の 1 行になる。"""
        memory = ShortTermMemory.empty(ADA)
        memory.lapse(
            body="[行動] 迷い → [失敗] | 決められなかった", time=ObservedTime(display="1日目 夜"), current_turn=1
        )

        assert recent_events_text(memory) == "- [1日目 夜] [行動] 迷い → [失敗] | 決められなかった"

    def test_attempt_without_result_is_not_shown(self) -> None:
        """結果の分からない試みは行にしない。今のプロンプトには、結果の無い 1 手の行が無いため。"""
        memory = ShortTermMemory.empty(ADA)
        memory.act(_move("call-1"), current_turn=1)
        memory.perceive(_observation("鐘が鳴った"), current_turn=1)
        memory.act(_move("call-2"), current_turn=2)

        assert recent_events_text(memory) == "- [1日目 朝] 鐘が鳴った"

    def test_only_unknown_attempts_show_the_placeholder(self) -> None:
        """出来事が結果の分からない試みだけなら、行が無いので「（直近の出来事はありません）」になる。"""
        memory = ShortTermMemory.empty(ADA)
        memory.act(_move("call-1"), current_turn=1)
        memory.act(_move("call-2"), current_turn=2)

        assert recent_events_text(memory) == NO_RECENT_EVENTS

    def test_lines_follow_the_occurrence_order(self) -> None:
        """行は集約の recent() の順。同じ環境で先に起きた他人の行動は、自分の 1 手の結果より前の行になる。"""
        memory = ShortTermMemory.empty(ADA)
        _answered(
            memory,
            "call-1",
            "[行動] 奪おうとした → [失敗]",
            turn=5,
            order=OccurrenceOrder(environment="廃坑の山村", value=20.0),
        )
        memory.perceive(
            _observation("ゲンが周囲を探索している", order=OccurrenceOrder(environment="廃坑の山村", value=10.0)),
            current_turn=5,
        )

        assert recent_events_text(memory) == (
            "- [1日目 朝] ゲンが周囲を探索している\n- [1日目 朝] [行動] 奪おうとした → [失敗]"
        )
