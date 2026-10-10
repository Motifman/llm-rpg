"""WorldTickFailureIsolator が 1 体の処理の例外を、方針に従って trace に残して取りやめるか止めるかを保証する。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
)
from ai_rpg_world.domain.common.value_object import WorldTick


class _CollectingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    def record(self, kind: str, **kwargs: Any) -> Any:
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


class _BrokenRecorder(NullTraceRecorder):
    def record(self, kind: str, **kwargs: Any) -> Any:
        raise OSError("disk full")


def _isolator(
    policy: WorldTickFailurePolicy, recorder: Any | None
) -> WorldTickFailureIsolator:
    return WorldTickFailureIsolator(policy=policy, trace_recorder_provider=lambda: recorder)


def _raise(exc: BaseException) -> None:
    raise exc


class TestIsolatePolicy:
    """isolate のとき、例外を出した 1 体だけを取りやめ、trace と件数に必ず出すこと。"""

    def test_failure_is_suppressed_and_recorded_with_stage_target_and_error(self) -> None:
        """isolate で 1 体の処理が例外を出すと、例外は外へ出ず、段・対象・例外の型と文・発生箇所を持つ world_tick_unit_failed が 1 件残る。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(
            stage="travel", tick=WorldTick(7), target_kind="player", target_id=3, player_id=3
        ):
            _raise(ValueError("passage closed"))

        assert len(recorder.events) == 1
        event = recorder.events[0]
        assert event.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED
        assert event.tick == 7
        assert event.player_id == 3
        assert event.payload["stage"] == "travel"
        assert event.payload["target_kind"] == "player"
        assert event.payload["target_id"] == 3
        assert event.payload["error_type"] == "ValueError"
        assert event.payload["error_message"] == "passage closed"
        assert event.payload["committed"] is False
        assert event.payload["policy"] == "isolate"
        assert "_raise" in event.payload["error_origin"]

    def test_counts_failures_per_stage(self) -> None:
        """isolate で取りやめた件数は段ごとに数えられ、例外の無かった処理は数えない。"""
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, _CollectingRecorder())

        for stage, fails in (("travel", True), ("travel", True), ("monster_behavior", True), ("travel", False)):
            with isolator.unit(stage=stage, tick=WorldTick(1), target_kind="player"):
                if fails:
                    _raise(RuntimeError("boom"))

        assert isolator.failure_counts() == {"travel": 2, "monster_behavior": 1}

    def test_no_failure_records_nothing(self) -> None:
        """例外が出なければ trace に何も残さず、件数は空のまま。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
            pass

        assert recorder.events == []
        assert isolator.failure_counts() == {}

    def test_post_commit_failure_is_marked_committed(self) -> None:
        """commit 済みで後処理だけが失敗した例外は committed=True で残り、状態が確定済みだと trace から分かる。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
            _raise(CommandPostCommitException(handoff_error=RuntimeError("handoff")))

        assert recorder.events[0].payload["committed"] is True

    def test_long_message_is_truncated(self) -> None:
        """500 字を超える例外の文は 500 字で切り詰めて残す。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
            _raise(RuntimeError("x" * 600))

        assert recorder.events[0].payload["error_message"] == "x" * 500 + "…"

    def test_without_recorder_reraises_because_it_cannot_be_traced(self) -> None:
        """isolate でも trace の記録先が無ければ、黙って続けず元の例外を投げる。"""
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, None)

        with pytest.raises(ValueError, match="passage closed"):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(ValueError("passage closed"))

        assert isolator.failure_counts() == {}

    def test_broken_recorder_reraises_original_exception(self) -> None:
        """trace の記録そのものが失敗したら、元の例外を投げて止める。"""
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, _BrokenRecorder())

        with pytest.raises(ValueError, match="passage closed"):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(ValueError("passage closed"))

    def test_base_exception_is_not_caught(self) -> None:
        """KeyboardInterrupt のような Exception 以外は取りやめの対象にせず、trace にも残さない。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with pytest.raises(KeyboardInterrupt):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(KeyboardInterrupt())

        assert recorder.events == []


class TestFailFastPolicy:
    """fail_fast のとき、例外で止めつつ、どこで止まったかを trace に残すこと。"""

    def test_failure_is_recorded_then_reraised(self) -> None:
        """fail_fast で 1 体の処理が例外を出すと、world_tick_unit_failed を残したうえで元の例外を投げる。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.FAIL_FAST, recorder)

        with pytest.raises(ValueError, match="passage closed"):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(ValueError("passage closed"))

        assert [e.kind for e in recorder.events] == [TraceEventKind.WORLD_TICK_UNIT_FAILED]
        assert recorder.events[0].payload["policy"] == "fail_fast"
        assert isolator.failure_counts() == {"travel": 1}

    def test_without_recorder_reraises(self) -> None:
        """fail_fast で trace の記録先が無くても、元の例外をそのまま投げる。"""
        isolator = WorldTickFailureIsolator.fail_fast()

        with pytest.raises(ValueError, match="passage closed"):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(ValueError("passage closed"))


class TestWorldTickFailurePolicyParse:
    """設定の文字列から方針を解決するときに、知らない値を黙って既定へ倒さないこと。"""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("isolate", WorldTickFailurePolicy.ISOLATE),
            ("fail_fast", WorldTickFailurePolicy.FAIL_FAST),
            (" FAIL_FAST ", WorldTickFailurePolicy.FAIL_FAST),
        ],
    )
    def test_known_values_are_resolved(self, raw: str, expected: WorldTickFailurePolicy) -> None:
        """isolate / fail_fast は前後の空白と大文字小文字を無視して解決する。"""
        assert WorldTickFailurePolicy.parse(raw) is expected

    def test_unknown_value_raises(self) -> None:
        """知らない値は ValueError で止め、受け付ける値を文に含める。"""
        with pytest.raises(ValueError, match="fail_fast"):
            WorldTickFailurePolicy.parse("skip")
