from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.recent_events_shadow import RecentEventsShadow
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.application.recent_events_text import NO_RECENT_EVENTS
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = PlayerId(1)
ADA_BEING = BeingId("being_p1")
NPC = PlayerId(9)
_MISMATCH = TraceEventKind.RECENT_EVENTS_SHADOW_MISMATCH


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, tick, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)

    def mismatches(self) -> list[dict[str, Any]]:
        return [p for k, _, _, p in self.events if k == _MISMATCH]


def _seen(body: str) -> Observation:
    return Observation(body=body, route=SeenOrHeard(), time=ObservedTime(display="深夜 0:01"), subject_is_self=False, subject_name=UNKNOWN, source=UNKNOWN, place=UNKNOWN, addressed_to_self=UNKNOWN)


class _World:
    """影に渡す世界の事実を集めた試験用の部品。"""

    def __init__(self, *, projection: bool = False) -> None:
        self.store = InMemoryShortTermMemoryRepository()
        self.recorder = _Recorder()
        self.shadow = RecentEventsShadow(
            store=self.store,
            being_id_of=lambda pid: ADA_BEING if pid == ADA else None,
            projection_active=lambda: projection,
            current_tick_provider=lambda: 7,
            trace_recorder_provider=lambda: self.recorder,
        )

    def perceive(self, *bodies: str) -> None:
        memory = self.store.get(ADA_BEING)
        for body in bodies:
            memory.perceive(_seen(body), current_turn=0)
        self.store.save(memory)


class TestRecentEventsShadow:
    """RecentEventsShadow が、今の【直近の出来事】と Being の側の文を比べ、違うときだけ種類を付けて trace に残すことを保証する (design_decisions D1824-10)。"""

    def test_same_text_leaves_no_trace(self) -> None:
        """2 つの文が同じなら、何も残さない。"""
        world = _World()
        world.perceive("鐘が鳴った", "扉が開いた")

        world.shadow.compare(ADA, "- [深夜 0:01] 鐘が鳴った\n- [深夜 0:01] 扉が開いた")

        assert world.recorder.events == []

    def test_different_line_is_traced_with_its_position_and_both_lines(self) -> None:
        """今の短期記憶がまだ畳んでいなければ全体を比べ、違えば different と、最初に違った行の位置、両方の行、行の数を 1 件残す。"""
        world = _World()
        world.perceive("鐘が鳴った", "扉が開いた")

        world.shadow.compare(ADA, "- [深夜 0:01] 鐘が鳴った\n- [深夜 0:01] 窓が開いた")

        assert world.recorder.mismatches() == [{
            "being_id": "being_p1",
            "mismatch_kind": "different",
            "compared_as": "whole",
            "line_index": 1,
            "current_line": "- [深夜 0:01] 窓が開いた",
            "being_line": "- [深夜 0:01] 扉が開いた",
            "current_line_count": 2,
            "being_line_count": 2,
        }]
        assert [(t, p) for k, t, p, _ in world.recorder.events] == [(7, 1)]

    def test_missing_lines_are_a_difference_before_compaction(self) -> None:
        """畳む前は、今の文が Being の側の文の一部だけでも違いとして残す。Being の側の行が多い位置を、今の文の行を None にして示す。"""
        world = _World()
        world.perceive("鐘が鳴った", "扉が開いた")

        world.shadow.compare(ADA, "- [深夜 0:01] 鐘が鳴った")

        (payload,) = world.recorder.mismatches()
        assert (payload["line_index"], payload["current_line"], payload["being_line"]) == (1, None, "- [深夜 0:01] 扉が開いた")

    def test_after_compaction_lines_kept_in_order_leave_no_trace(self) -> None:
        """今の短期記憶が畳んだあとは、今の文の行が同じ順で Being の側の文に含まれていれば、間の行が抜けていても何も残さない。"""
        world = _World()
        world.perceive("鐘が鳴った", "扉が開いた", "窓が閉まった")
        world.shadow.note_compacted(ADA)

        world.shadow.compare(ADA, "- [深夜 0:01] 鐘が鳴った\n- [深夜 0:01] 窓が閉まった")

        assert world.recorder.events == []

    def test_after_compaction_a_line_out_of_order_is_traced(self) -> None:
        """畳んだあとでも、今の文の行が Being の側の文に同じ順で無ければ、compared_as を subsequence にして、見つからなかった最初の行を残す。"""
        world = _World()
        world.perceive("鐘が鳴った", "扉が開いた")
        world.shadow.note_compacted(ADA)

        world.shadow.compare(ADA, "- [深夜 0:01] 扉が開いた\n- [深夜 0:01] 鐘が鳴った")

        (payload,) = world.recorder.mismatches()
        assert (payload["compared_as"], payload["line_index"], payload["current_line"], payload["being_line"]) == (
            "subsequence",
            1,
            "- [深夜 0:01] 鐘が鳴った",
            None,
        )

    def test_continuation_line_is_compared_with_its_event(self) -> None:
        """続き行 (心の声など) は、その前の「- 」で始まる行とひとまとまりで比べる。別の出来事の同じ続き行と取り違えない。"""
        world = _World()
        world.perceive("鐘が鳴った", "扉が開いた")
        world.shadow.note_compacted(ADA)

        world.shadow.compare(ADA, "- [深夜 0:01] 窓が開いた\n  心の声: 寒い\n- [深夜 0:01] 扉が開いた")

        (payload,) = world.recorder.mismatches()
        assert (payload["line_index"], payload["current_line"]) == (0, "- [深夜 0:01] 窓が開いた\n  心の声: 寒い")

    def test_restored_memory_is_compared_as_lines_in_order(self) -> None:
        """Being の記憶を snapshot から戻したあとは、前の run の出来事が今の文に無くても、今の文の行が同じ順で含まれていれば何も残さない。"""
        world = _World()
        world.perceive("前の run で鐘が鳴った", "扉が開いた")
        world.shadow.note_restored(ADA_BEING)

        world.shadow.compare(ADA, "- [深夜 0:01] 扉が開いた")

        assert world.recorder.events == []

    def test_empty_current_text_after_compaction_leaves_no_trace(self) -> None:
        """畳んだあとで今の文に出来事が無い (「（直近の出来事はありません）」) ときは、比べる行が無いので何も残さない。"""
        world = _World()
        world.perceive("鐘が鳴った")
        world.shadow.note_compacted(ADA)

        world.shadow.compare(ADA, NO_RECENT_EVENTS)

        assert world.recorder.events == []

    def test_public_sns_projection_skips_the_comparison_once(self) -> None:
        """公開 SNS の投影がある世界では比べず、そのことを Being ごとに 1 回だけ public_sns_projection として残す。"""
        world = _World(projection=True)
        world.perceive("鐘が鳴った")

        world.shadow.compare(ADA, "まったく違う文")
        world.shadow.compare(ADA, "まったく違う文")

        assert world.recorder.mismatches() == [{"being_id": "being_p1", "mismatch_kind": "public_sns_projection"}]

    def test_player_without_being_is_not_compared(self) -> None:
        """Being の無いプレイヤーは比べず、何も残さない。"""
        world = _World()

        world.shadow.compare(NPC, "- [深夜 0:01] 鐘が鳴った")

        assert world.recorder.events == []

    def test_failure_inside_the_comparison_does_not_stop_the_prompt(self) -> None:
        """比べる途中で例外が起きても外へ投げない。プロンプトは今の文で組めるため。"""
        world = _World()

        def broken(pid: PlayerId) -> BeingId | None:
            raise RuntimeError("引けない")

        world.shadow._being_id_of = broken

        world.shadow.compare(ADA, "- [深夜 0:01] 鐘が鳴った")

        assert world.recorder.events == []

