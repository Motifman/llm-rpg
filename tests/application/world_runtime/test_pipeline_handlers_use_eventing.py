"""本番の四つの受け手の対象と、確定後・直接発行の観測の順序を守る。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.common.command_scope import CommandScope
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.world_runtime.pipeline_event_publisher import PipelineEventPublisher
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent, PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
    PlayerInteractedWithPlayerEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee, EventDispatcher

_EXPECTED = [
    ("PlayerDownedEvent", "_MarkKillerAsHavingSeenTheBody"),
    ("PlayerRevivedEvent", "PlayerRevivedPostHocObservationHandler"),
    ("PlayerInteractedWithPlayerEvent", "TargetedWhileDownRecorder"),
    ("EntityEnteredSpotEvent", "SpotArrivalEncounterHandler"),
]


@pytest.fixture
def wired(monkeypatch):
    timeline, registrations = [], []
    original = PipelineEventPublisher.register_handler

    def register(publisher, event_type, handler):
        name = type(handler).__name__
        registrations.append((event_type.__name__, name))
        monkeypatch.setattr(handler, "handle", lambda event: timeline.append(name))
        original(publisher, event_type, handler)

    monkeypatch.setattr(PipelineEventPublisher, "register_handler", register)
    runtime = create_world_runtime(
        Path("data/scenarios/station_drill.json"),
        config=ResolvedLlmRuntimeConfig.for_tests(),
    )
    monkeypatch.setattr(PipelineEventPublisher, "register_handler", original)
    timeline.clear()
    tracer = CollectingTraceRecorder()
    runtime.set_trace_recorder(tracer)

    def observe(event):
        timeline.append("observation")
        return [(PlayerId(1), object())]

    def append(*args):
        timeline.append("append")
        return True

    runtime._obs_pipeline = SimpleNamespace(run=observe)
    runtime._observation_appender = SimpleNamespace(append=append)
    runtime._observation_turn_scheduler = SimpleNamespace(maybe_schedule=lambda *args: timeline.append("schedule"))
    return runtime._speech_event_publisher, registrations, timeline, tracer


def test_production_registers_the_same_four_handlers_in_order(wired) -> None:
    """世界を組み立てると、従来の四つのイベント型と受け手を同じ順で登録する。"""
    _, registrations, _, _ = wired
    assert registrations == _EXPECTED


def _event(index):
    common = dict(aggregate_id=PlayerId(1), aggregate_type="PlayerStatusAggregate")
    if index == 0:
        return PlayerDownedEvent.create(**common)
    if index == 1:
        return PlayerRevivedEvent.create(**common, hp_recovered=10, total_hp=10)
    common = dict(aggregate_id="world", aggregate_type="SpotGraph")
    if index == 2:
        return PlayerInteractedWithPlayerEvent.create(
            **common,
            entity_id=EntityId.create(1),
            target_entity_id=EntityId.create(2),
            spot_id=SpotId(1),
            action_name="tend",
            result_message="介抱した",
        )
    return EntityEnteredSpotEvent.create(
        **common,
        entity_id=EntityId.create(1),
        spot_id=SpotId(1),
        from_spot_id=None,
    )


class _Transaction:
    is_active = False

    def begin(self):
        self.is_active = True

    def commit(self):
        self.is_active = False

    def rollback(self):
        self.is_active = False


def _publish(publisher, event, route):
    if route == "command":
        dispatcher = EventDispatcher(failure_observer=lambda *args: pytest.fail("配送の失敗"))
        dispatcher.register_after_commit(
            DomainEvent,
            publisher.publish,
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )
        transaction = _Transaction()
        with CommandScope(transaction, sync_dispatcher=dispatcher, after_commit_handoff=dispatcher) as context:
            context.collect(event)
        assert not transaction.is_active
    elif route == "publish":
        publisher.publish(event)
    else:
        getattr(publisher, route)([event])


@pytest.mark.parametrize("route", ["publish", "publish_all", "publish_async_events", "command"])
@pytest.mark.parametrize("index", range(4))
def test_each_production_handler_precedes_observation_on_both_routes(wired, index, route) -> None:
    """確定後と直接発行のどちらでも、該当する受け手だけを同期実行してから観測を配る。"""
    publisher, _, timeline, _ = wired
    _publish(publisher, _event(index), route)
    assert timeline == [_EXPECTED[index][1], "observation", "append", "schedule"]


@pytest.mark.parametrize("route", ["publish", "command"])
def test_failure_keeps_all_trace_fields_and_continues_delivery(wired, route) -> None:
    """受け手が失敗すると従来の全項目を一件だけ記録し、後続と観測の配送を続ける。"""
    publisher, _, timeline, tracer = wired

    class FailingHandler:
        def handle(self, event):
            timeline.append("failed")
            raise ValueError("受け手の失敗")

    class FollowingHandler:
        def handle(self, event):
            timeline.append("following")

    publisher.register_handler(PlayerDownedEvent, FailingHandler())
    publisher.register_handler(PlayerDownedEvent, FollowingHandler())
    event = _event(0)
    _publish(publisher, event, route)
    assert timeline == [_EXPECTED[0][1], "failed", "following", "observation", "append", "schedule"]
    failures = tracer.of_kind("side_handler_failed")
    assert len(failures) == 1
    assert failures[0].player_id == 1
    assert failures[0].tick == 0
    assert failures[0].payload == {
        "handler": "FailingHandler",
        "event_type": "PlayerDownedEvent",
        "event_id": event.event_id,
        "aggregate_type": "PlayerStatusAggregate",
        "aggregate_id": 1,
        "error_type": "ValueError",
        "error_message": "受け手の失敗",
    }


def test_subclass_event_reaches_the_registered_base_type(wired) -> None:
    """登録したイベントを継承するイベントでも、同じ受け手を観測より先に呼ぶ。"""

    class SpecialDownedEvent(PlayerDownedEvent):
        pass

    publisher, _, timeline, _ = wired
    publisher.publish(SpecialDownedEvent.create(aggregate_id=PlayerId(1), aggregate_type="PlayerStatusAggregate"))
    assert timeline == [_EXPECTED[0][1], "observation", "append", "schedule"]


def test_production_registration_uses_the_common_after_commit_dispatcher(monkeypatch) -> None:
    """本番の四つの受け手は、共通の配送器へ確定後・同期・最善努力の観測として登録する。"""
    registrations = []
    original = EventDispatcher.register_after_commit

    def register(dispatcher, event_type, handler, **options):
        registrations.append(
            (event_type.__name__, getattr(handler, "receiver", getattr(handler, "__self__", None)), options)
        )
        original(dispatcher, event_type, handler, **options)

    monkeypatch.setattr(EventDispatcher, "register_after_commit", register)
    create_world_runtime(Path("data/scenarios/station_drill.json"), config=ResolvedLlmRuntimeConfig.for_tests())
    names = {name for _, name in _EXPECTED}
    selected = [
        (event, type(handler).__name__, options)
        for event, handler, options in registrations
        if type(handler).__name__ in names
    ]
    assert [(event, handler) for event, handler, _ in selected] == _EXPECTED
    assert all(
        options == {"channel": DeliveryChannel.OBSERVATION, "guarantee": DeliveryGuarantee.BEST_EFFORT}
        for _, _, options in selected
    )


@pytest.mark.parametrize("as_attribute", [False, True])
def test_failure_trace_keeps_receiver_name_without_a_bound_method(wired, as_attribute) -> None:
    """handle が静的メソッドや属性の関数でも、失敗の記録には元の受け手の型名を残す。"""

    def fail(event):
        raise RuntimeError("失敗")

    class DetachedHandler:
        handle = staticmethod(fail)

    handler = DetachedHandler()
    if as_attribute:
        handler.handle = fail
    publisher, _, _, tracer = wired
    publisher.register_handler(PlayerDownedEvent, handler)
    publisher.publish(_event(0))
    assert tracer.of_kind("side_handler_failed")[0].payload["handler"] == "DetachedHandler"
