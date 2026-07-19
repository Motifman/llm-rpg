"""特性化テスト: PipelineEventPublisher._dispatch の配信契約を固定する。

ドメインイベント配信の一元化リファクタ (docs/refactor_plans/domain_event_dispatch_refactor_plan.md)
の Stage 0b。棚卸し (stage0a_inventory.md) で「相 ① = 即時性が load-bearing な同期
side handler」が 6 サイトに集中すると分かった。その即時性を支えているのが本 publisher の
``_dispatch`` の以下の契約であり、リファクタで最も壊してはいけない部分:

1. side handler は publish/publish_all の呼び出し内で **同期実行** される
   (呼び出しから戻った時点で副作用が反映済み)。
2. side handler は **observation pipeline より先** に走る
   (「downed → DEAD outcome が立った状態で観測が emit される」順序)。
3. side handler は **登録順** に走る。
4. 1 つの side handler が例外を投げても、後続 handler と observation pipeline は
   止まらない (カスケード障害の回避 = 静かな失敗ではなく log に残して継続)。
5. 実 handler 配線での即時性: PlayerDownedEvent → grace 登録済み /
   PlayerRevivedEvent → grace 解除済み が publish から戻った時点で成立している。

本テストは挙動を変えない。commit 後一括 dispatch などへ移行して即時性が崩れると赤くなる。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Tuple

from ai_rpg_world.application.player.handlers.player_downed_outcome_handler import (
    PlayerDownedOutcomeHandler,
)
from ai_rpg_world.application.player.handlers.player_revived_outcome_handler import (
    PlayerRevivedOutcomeHandler,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.application.world_runtime.pipeline_event_publisher import (
    PipelineEventPublisher,
)
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _RecordingObsPipeline:
    """observation pipeline spy。run(event) 呼び出しを recorder に記録し、空 items を返す。

    空 items を返すことで _dispatch は appender 経路に入らず早期 return する
    (appender/scheduler は None のままでよい)。
    """

    def __init__(self, recorder: List[str]) -> None:
        self._recorder = recorder

    def run(self, event: Any) -> list:
        self._recorder.append("obs")
        return []


class _FakeRuntime:
    """PipelineEventPublisher が参照する runtime の最小 spy。

    _dispatch は _obs_pipeline.run のみ使う (items が空なので appender 以降は不使用)。
    """

    def __init__(self, recorder: List[str]) -> None:
        self._obs_pipeline = _RecordingObsPipeline(recorder)
        self._observation_appender = None
        self._observation_turn_scheduler = None

    def _time_label(self) -> str:
        return "day"


class _RecordingTraceRecorder:
    """trace recorder spy。record(kind, *, tick, player_id, **payload) を記録する。"""

    def __init__(self) -> None:
        self.records: List[dict] = []

    def record(self, kind: str, *, tick=None, player_id=None, **payload):
        self.records.append({"kind": kind, "tick": tick, "player_id": player_id, **payload})


class _FakeRuntimeWithTrace(_FakeRuntime):
    """_trace_recorder と current_tick を持つ runtime spy。"""

    def __init__(self, recorder: List[str], trace_recorder) -> None:
        super().__init__(recorder)
        self._trace_recorder = trace_recorder

    def current_tick(self):
        return 7


@dataclass
class _RecordingHandler:
    """handle(event) 呼び出しを recorder に記録する side handler spy。fail=True で例外を投げる。"""

    name: str
    recorder: List[str]
    fail: bool = False

    def handle(self, event: Any) -> None:
        self.recorder.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} boom")


class _EventA:
    pass


class _EventB:
    pass


def _make_downed_event(player_id: int) -> PlayerDownedEvent:
    return PlayerDownedEvent.create(
        aggregate_id=PlayerId(player_id),
        aggregate_type="PlayerStatusAggregate",
        killer_player_id=None,
    )


def _make_revived_event(player_id: int, hp: int = 40) -> PlayerRevivedEvent:
    return PlayerRevivedEvent.create(
        aggregate_id=PlayerId(player_id),
        aggregate_type="PlayerStatusAggregate",
        hp_recovered=hp,
        total_hp=hp,
    )


class TestDispatchOrdering:
    """side handler と observation pipeline の実行順序を固定する。"""

    def test_side_handler_runs_before_observation_pipeline(self) -> None:
        """side handler は同 event の observation pipeline より先に同期実行される。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("h1", recorder))

        publisher.publish(_EventA())

        assert recorder == ["h1", "obs"]

    def test_side_handlers_run_in_registration_order(self) -> None:
        """複数の side handler は登録順に実行される。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("first", recorder))
        publisher.register_handler(_EventA, _RecordingHandler("second", recorder))

        publisher.publish(_EventA())

        assert recorder == ["first", "second", "obs"]

    def test_side_handler_filtered_by_event_type(self) -> None:
        """登録した event 型と一致しない event では side handler は走らない。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("only_a", recorder))

        publisher.publish(_EventB())

        assert recorder == ["obs"]

    def test_publish_all_dispatches_each_event(self) -> None:
        """publish_all は渡した events を 1 件ずつ _dispatch に流す。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("h", recorder))

        publisher.publish_all([_EventA(), _EventA()])

        assert recorder == ["h", "obs", "h", "obs"]


class TestDispatchExceptionIsolation:
    """1 つの side handler の例外が後続 handler / observation を止めないことを固定する。"""

    def test_failing_side_handler_does_not_stop_pipeline(self) -> None:
        """先に登録した handler が例外を投げても、後続 handler と observation は実行される。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("boom", recorder, fail=True))
        publisher.register_handler(_EventA, _RecordingHandler("after", recorder))

        publisher.publish(_EventA())

        assert recorder == ["boom", "after", "obs"]

    def test_failing_side_handler_is_logged_not_swallowed_silently(self, caplog) -> None:
        """例外は握りつぶさず log に残す (静かな失敗にしない)。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("boom", recorder, fail=True))

        with caplog.at_level(logging.ERROR):
            publisher.publish(_EventA())

        assert any("side handler" in rec.message for rec in caplog.records)


class TestRealHandlerImmediacy:
    """実 handler 配線で、publish から戻った時点で grace state が反映済みであることを固定する。"""

    def test_player_downed_registers_grace_synchronously_on_publish(self) -> None:
        """PlayerDownedEvent を publish すると、戻った時点で grace timer に登録済み。"""
        recorder: List[str] = []
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        handler = PlayerDownedOutcomeHandler(
            outcome_registry=reg,
            grace_timer=timer,
            current_tick_provider=lambda: 42,
        )
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(PlayerDownedEvent, handler)
        assert timer.is_pending(PlayerId(1)) is False

        publisher.publish(_make_downed_event(1))

        assert timer.is_pending(PlayerId(1)) is True

    def test_player_revived_cancels_grace_synchronously_on_publish(self) -> None:
        """PlayerRevivedEvent を publish すると、戻った時点で grace timer から解除済み。"""
        recorder: List[str] = []
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(1), downed_at_tick=10)
        handler = PlayerRevivedOutcomeHandler(grace_timer=timer)
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(PlayerRevivedEvent, handler)
        assert timer.is_pending(PlayerId(1)) is True

        publisher.publish(_make_revived_event(1))

        assert timer.is_pending(PlayerId(1)) is False

    def test_downed_then_revived_sequence_ends_not_pending(self) -> None:
        """同一 grace timer に downed → revived を順に publish すると、最終的に pending でない。"""
        recorder: List[str] = []
        reg = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        timer = PlayerDeathGraceTimer()
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(
            PlayerDownedEvent,
            PlayerDownedOutcomeHandler(
                outcome_registry=reg,
                grace_timer=timer,
                current_tick_provider=lambda: 10,
            ),
        )
        publisher.register_handler(
            PlayerRevivedEvent,
            PlayerRevivedOutcomeHandler(grace_timer=timer),
        )

        publisher.publish(_make_downed_event(1))
        assert timer.is_pending(PlayerId(1)) is True
        publisher.publish(_make_revived_event(1))

        assert timer.is_pending(PlayerId(1)) is False


class TestSideHandlerFailureTrace:
    """side handler の失敗を SIDE_HANDLER_FAILED trace に落とす (観測。挙動は変えない)。"""

    def test_failing_handler_records_side_handler_failed_trace(self) -> None:
        """side handler が例外を投げると SIDE_HANDLER_FAILED trace が payload 付きで 1 件残る。"""
        recorder: List[str] = []
        tracer = _RecordingTraceRecorder()
        publisher = PipelineEventPublisher(_FakeRuntimeWithTrace(recorder, tracer))
        publisher.register_handler(_EventA, _RecordingHandler("boom", recorder, fail=True))

        publisher.publish(_EventA())

        # 観測は握った後も継続する (挙動不変)
        assert recorder == ["boom", "obs"]
        # 失敗が trace に 1 件残る
        assert len(tracer.records) == 1
        rec = tracer.records[0]
        assert rec["kind"] == "side_handler_failed"
        assert rec["handler"] == "_RecordingHandler"
        assert rec["event_type"] == "_EventA"
        assert rec["error_type"] == "RuntimeError"
        assert rec["tick"] == 7

    def test_no_trace_recorder_is_safe(self) -> None:
        """_trace_recorder が無い構成でも、失敗時に crash せず pipeline は継続する。"""
        recorder: List[str] = []
        publisher = PipelineEventPublisher(_FakeRuntime(recorder))
        publisher.register_handler(_EventA, _RecordingHandler("boom", recorder, fail=True))

        publisher.publish(_EventA())

        assert recorder == ["boom", "obs"]

    def test_successful_handler_records_no_trace(self) -> None:
        """成功した side handler では SIDE_HANDLER_FAILED trace は残らない。"""
        recorder: List[str] = []
        tracer = _RecordingTraceRecorder()
        publisher = PipelineEventPublisher(_FakeRuntimeWithTrace(recorder, tracer))
        publisher.register_handler(_EventA, _RecordingHandler("ok", recorder))

        publisher.publish(_EventA())

        assert tracer.records == []
