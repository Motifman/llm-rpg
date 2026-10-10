"""WorldTickFailureIsolator が 1 体の処理の例外を、方針に従って trace に残して取りやめるか止めるかを保証する。"""

from __future__ import annotations

from dataclasses import replace
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

    def test_post_commit_failure_is_recorded_as_committed_then_reraised(self) -> None:
        """isolate でも commit 後の後始末に失敗した例外は取りやめず、committed=True で残したうえで投げ直す。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with pytest.raises(CommandPostCommitException):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(CommandPostCommitException(cleanup_error=RuntimeError("release failed")))

        assert recorder.events[0].payload["committed"] is True
        assert isolator.failure_counts() == {"travel": 1}

    def test_non_json_target_id_is_recorded_as_text(self) -> None:
        """int と str 以外の対象 ID は文字列にして残し、JSON に書けない値で記録が失敗しない。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(stage="trade_offer_expiry", tick=WorldTick(1), target_kind="trade_offer", target_id=("offer", 9)):
            _raise(RuntimeError("boom"))

        assert recorder.events[0].payload["target_id"] == "('offer', 9)"

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

    def test_recorder_that_drops_the_event_reraises(self) -> None:
        """閉じた recorder のように例外を出さず捨てた (seq が負) ときも、記録できなかったとして元の例外を投げ、件数に数えない。"""

        class _DroppingRecorder(NullTraceRecorder):
            def record(self, kind: str, **kwargs: Any) -> Any:
                return replace(super().record(kind, **kwargs), seq=-1)

        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, _DroppingRecorder())

        with pytest.raises(ValueError, match="passage closed"):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
                _raise(ValueError("passage closed"))

        assert isolator.failure_counts() == {}

    def test_unit_that_is_not_a_command_scope_records_committed_as_unknown(self) -> None:
        """CommandScope 1 回でない単位として包むと、取りやめる前に何が確定したか分からないので committed を None で残す。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(stage="llm_turn", tick=WorldTick(1), target_kind="player", command_scoped=False):
            _raise(RuntimeError("prompt build failed"))

        assert recorder.events[0].payload["committed"] is None

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

    def test_nested_units_record_the_failure_once(self) -> None:
        """fail_fast で 1 体の単位を段の単位が包んでいても、例外は内側の 1 件だけ記録され、件数も 1 になる。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.FAIL_FAST, recorder)

        with pytest.raises(ValueError):
            with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="stage"):
                with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player", target_id=3):
                    _raise(ValueError("passage closed"))

        assert [e.payload["target_kind"] for e in recorder.events] == ["player"]
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


class TestRecordContinuedFailure:
    """確定済みの処理に続く後処理の失敗を、取りやめずに trace と件数へ残すこと。"""

    def test_isolate_records_and_continues(self) -> None:
        """isolate では committed=True / continued=True の world_tick_unit_failed を 1 件残し、例外を投げずに件数へ数える。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        isolator.record_continued_failure(
            RuntimeError("observer failed"),
            stage="travel.arrival_observer",
            tick=WorldTick(3),
            target_kind="player",
            target_id=2,
            player_id=2,
        )

        event = recorder.events[0]
        assert event.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED
        assert event.tick == 3
        assert event.payload["committed"] is True
        assert event.payload["continued"] is True
        assert isolator.failure_counts() == {"travel.arrival_observer": 1}

    def test_without_recorder_continues_without_counting(self) -> None:
        """isolate で記録先が無ければ、確定済みの状態は戻らないので例外を投げずに続け、件数には数えない。"""
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, None)

        isolator.record_continued_failure(
            RuntimeError("observer failed"),
            stage="travel.arrival_observer",
            tick=None,
            target_kind="player",
        )

        assert isolator.failure_counts() == {}

    def test_fail_fast_records_then_raises(self) -> None:
        """fail_fast では trace に残したうえで、渡された例外を投げる。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.FAIL_FAST, recorder)

        with pytest.raises(RuntimeError, match="observer failed"):
            isolator.record_continued_failure(
                RuntimeError("observer failed"),
                stage="travel.arrival_observer",
                tick=WorldTick(1),
                target_kind="player",
            )

        assert len(recorder.events) == 1

    def test_unit_failure_is_marked_not_continued(self) -> None:
        """1 体の処理を取りやめた行は continued=False で、後処理の失敗と見分けられる。"""
        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)

        with isolator.unit(stage="travel", tick=WorldTick(1), target_kind="player"):
            _raise(RuntimeError("boom"))

        assert recorder.events[0].payload["continued"] is False


class TestAfterCommitFailureObserver:
    """CommandEventDispatcher の best-effort な commit 後ハンドラの失敗が、trace と件数に出ること。"""

    def test_best_effort_handler_failure_is_recorded_as_continued(self) -> None:
        """best-effort な commit 後ハンドラが例外を出すと、after_commit.<配送先> の段・出来事の型名を対象として、続けた失敗が 1 件残る。"""
        from datetime import datetime, timezone

        from ai_rpg_world.application.common.event_delivery import (
            DeliveryChannel,
            DeliveryGuarantee,
        )
        from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
        from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
            CommandEventDispatcher,
        )

        recorder = _CollectingRecorder()
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, recorder)
        dispatcher = CommandEventDispatcher(
            failure_observer=isolator.after_commit_failure_observer(tick_provider=lambda: 6)
        )
        dispatcher.register_after_commit(
            BaseDomainEvent,
            lambda event: _raise(RuntimeError("observation pipeline failed")),
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )
        event = BaseDomainEvent(
            event_id=1,
            occurred_at=datetime.now(timezone.utc),
            aggregate_id="aggregate",
            aggregate_type="Aggregate",
        )

        dispatcher.handoff([event])

        assert [(e.tick, e.payload["stage"], e.payload["target_id"], e.payload["continued"]) for e in recorder.events] == [
            (6, "after_commit.observation", "BaseDomainEvent", True)
        ]
        assert isolator.failure_counts() == {"after_commit.observation": 1}


class TestRecordContinuedFailureEdges:
    """後処理の失敗の入口が、記録先が無いときと記録できないときに黙らないこと。"""

    def test_fail_fast_without_recorder_raises(self) -> None:
        """fail_fast で記録先が無ければ、ログに残したうえで渡された例外を投げる。部品を渡されていない段の後処理が黙らない。"""
        isolator = WorldTickFailureIsolator.fail_fast()

        with pytest.raises(RuntimeError, match="observer failed"):
            isolator.record_continued_failure(
                RuntimeError("observer failed"),
                stage="travel.arrival_observer",
                tick=WorldTick(1),
                target_kind="player",
            )

    def test_broken_recorder_raises_instead_of_continuing(self) -> None:
        """isolate でも記録先が記録に失敗したら、黙って続けずに記録の失敗を投げ、件数に数えない。"""
        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, _BrokenRecorder())

        with pytest.raises(OSError, match="disk full"):
            isolator.record_continued_failure(
                RuntimeError("observer failed"),
                stage="travel.arrival_observer",
                tick=WorldTick(1),
                target_kind="player",
            )

        assert isolator.failure_counts() == {}

    def test_dropping_recorder_raises_instead_of_continuing(self) -> None:
        """isolate で閉じた記録先が黙って捨てた (seq が負) ときも、続けずに例外を投げ、件数に数えない。"""

        class _DroppingRecorder(NullTraceRecorder):
            def record(self, kind: str, **kwargs: Any) -> Any:
                return replace(super().record(kind, **kwargs), seq=-1)

        isolator = _isolator(WorldTickFailurePolicy.ISOLATE, _DroppingRecorder())

        with pytest.raises(RuntimeError, match="dropped"):
            isolator.record_continued_failure(
                RuntimeError("observer failed"),
                stage="travel.arrival_observer",
                tick=WorldTick(1),
                target_kind="player",
            )

        assert isolator.failure_counts() == {}
