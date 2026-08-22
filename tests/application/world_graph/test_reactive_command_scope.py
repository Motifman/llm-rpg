"""reactive object / passageの確定境界契約。"""

import random

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.reactive_object_state_binding_stage_service import (
    ReactiveObjectStateBindingStageService,
)
from ai_rpg_world.application.world_graph.reactive_passage_binding_stage_service import (
    ReactivePassageBindingStageService,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_reactive_command_repository_provider import (
    InMemoryReactiveCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_reactive_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)


SPOT_ID = SpotId.create(1)
OBJECT_ID = SpotObjectId.create(7)


class _NoopStatusRepository:
    def find_all(self):
        return []


class _NoopInventoryRepository:
    def find_by_id(self, *_args, **_kwargs):
        return None


class _NoopItemRepository:
    pass


def _probability_binding(
    *, key: str, connection_id: int | None = None
) -> ReactiveObjectStateBinding | ReactivePassageBinding:
    predicate = ScenarioEventCondition(
        condition_type="PROBABILITY",
        probability=1.0,
    )
    if connection_id is not None:
        return ReactivePassageBinding(
            target_connection_id=ConnectionId.create(connection_id),
            predicate=predicate,
            on_true_state="OPEN",
            on_false_state="LOCKED",
        )
    return ReactiveObjectStateBinding(
        target_object_id=OBJECT_ID,
        predicate=predicate,
        on_true_state_updates=((key, True),),
        on_false_state_updates=((key, False),),
    )


def _build_world(*, object_state: dict | None = None):
    store = InMemoryDataStore()
    interiors = InMemorySpotInteriorRepository(data_store=store)
    graph_value = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id in (1, 2, 3):
        graph_value.add_spot(
            SpotNode(
                spot_id=SpotId.create(spot_id),
                name=f"spot-{spot_id}",
                description="",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    for connection_id, destination in ((10, 2), (11, 3)):
        graph_value.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(connection_id),
                from_spot_id=SPOT_ID,
                to_spot_id=SpotId.create(destination),
                name=f"door-{connection_id}",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.door(DoorStateEnum.LOCKED),
            )
        )
    graph_value.clear_events()
    graph = InMemorySpotGraphRepository(graph_value)
    target = SpotObject(
        object_id=OBJECT_ID,
        name="relay",
        description="",
        object_type=SpotObjectTypeEnum.OTHER,
        state=dict(object_state or {"power": False, "alarm": False}),
        interactions=(),
    )
    interiors.save(SPOT_ID, SpotInterior((), (target,), (), ()))
    evaluator = ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=interiors,
        player_status_repository=_NoopStatusRepository(),
        player_inventory_repository=_NoopInventoryRepository(),
        item_repository=_NoopItemRepository(),
        random_source=random.Random(17),
    )
    observed: list[tuple[str, dict, tuple[str, str]]] = []
    dispatcher = CommandEventDispatcher()

    def observe(event: BaseDomainEvent) -> None:
        interior = interiors.find_by_spot_id(SPOT_ID)
        assert interior is not None
        observed.append(
            (
                type(event).__name__,
                dict(interior.objects[0].state),
                (
                    graph.find_graph()
                    .get_connection(ConnectionId.create(10))
                    .passage.state,
                    graph.find_graph()
                    .get_connection(ConnectionId.create(11))
                    .passage.state,
                ),
            )
        )

    dispatcher.register_after_commit(
        BaseDomainEvent,
        observe,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(store),
            participants=build_reactive_rollback_participants(
                spot_graph=graph,
                condition_evaluator=evaluator,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=InMemoryReactiveCommandRepositoryProviderFactory(
            spot_graph=graph
        ),
    )
    return store, interiors, graph, evaluator, observed, factory


def _preexisting_event(graph: InMemorySpotGraphRepository):
    return ConnectionStateChangedEvent.create(
        aggregate_id=graph.find_graph().graph_id,
        aggregate_type="SpotGraphAggregate",
        connection_id=ConnectionId.create(99),
        from_spot_id=SPOT_ID,
        to_spot_id=SpotId.create(2),
        traversable=True,
        cause=PassageChangeCauseEnum.UNKNOWN,
        original_actor_entity_id=None,
    )


def test_object_binding_observation_follows_commit_and_preserves_old_events() -> None:
    """object観測はinterior確定後に届き、以前のgraph eventを横取りしない。"""
    _, interiors, graph, evaluator, observed, factory = _build_world()
    old_event = _preexisting_event(graph)
    graph.find_graph().add_event(old_event)
    stage = ReactiveObjectStateBindingStageService(
        bindings=(_probability_binding(key="power"),),
        spot_graph_repository=graph,
        spot_interior_repository=interiors,
        condition_evaluator=evaluator,
        command_scope_factory=factory,
    )

    stage.run(WorldTick(1))

    assert observed == [
        (
            "SpotObjectStateChangedEvent",
            {"power": True, "alarm": False},
            ("LOCKED", "LOCKED"),
        )
    ]
    assert graph.find_graph().get_events() == [old_event]


def test_object_binding_save_failure_rolls_back_state_event_and_random() -> None:
    """object更新後のgraph保存失敗はinterior・event・確率乱数を戻す。"""
    _, interiors, graph, evaluator, observed, factory = _build_world()
    random_before = evaluator.rollback_snapshot()
    original_save = graph.save
    calls = 0

    def fail_first_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("object graph save failed")
        original_save(value)

    graph.save = fail_first_save  # type: ignore[method-assign]
    stage = ReactiveObjectStateBindingStageService(
        bindings=(_probability_binding(key="power"),),
        spot_graph_repository=graph,
        spot_interior_repository=interiors,
        condition_evaluator=evaluator,
        command_scope_factory=factory,
    )

    with pytest.raises(RuntimeError, match="object graph save failed"):
        stage.run(WorldTick(1))

    interior = interiors.find_by_spot_id(SPOT_ID)
    assert interior is not None
    assert interior.objects[0].state == {"power": False, "alarm": False}
    assert graph.find_graph().get_events() == []
    assert evaluator.rollback_snapshot() == random_before
    assert observed == []


def test_later_object_binding_failure_keeps_earlier_binding_commit() -> None:
    """後続binding失敗は先に確定したobject更新と観測を戻さない。"""
    _, interiors, graph, evaluator, observed, factory = _build_world()
    original_save = graph.save
    calls = 0

    def fail_second_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second binding failed")
        original_save(value)

    graph.save = fail_second_save  # type: ignore[method-assign]
    stage = ReactiveObjectStateBindingStageService(
        bindings=(
            _probability_binding(key="power"),
            _probability_binding(key="alarm"),
        ),
        spot_graph_repository=graph,
        spot_interior_repository=interiors,
        condition_evaluator=evaluator,
        command_scope_factory=factory,
    )

    with pytest.raises(RuntimeError, match="second binding failed"):
        stage.run(WorldTick(1))

    interior = interiors.find_by_spot_id(SPOT_ID)
    assert interior is not None
    assert interior.objects[0].state == {"power": True, "alarm": False}
    assert [entry[0] for entry in observed] == ["SpotObjectStateChangedEvent"]
    expected_random = random.Random(17)
    expected_random.random()
    assert evaluator.rollback_snapshot() == expected_random.getstate()


def test_passage_stage_save_failure_rolls_back_all_bindings_and_random() -> None:
    """passage stage後段失敗は全接続・event・確率乱数を一括で戻す。"""
    _, _, graph, evaluator, observed, factory = _build_world()
    random_before = evaluator.rollback_snapshot()
    original_save = graph.save
    calls = 0

    def fail_first_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("passage graph save failed")
        original_save(value)

    graph.save = fail_first_save  # type: ignore[method-assign]
    stage = ReactivePassageBindingStageService(
        bindings=(
            _probability_binding(key="", connection_id=10),
            _probability_binding(key="", connection_id=11),
        ),
        spot_graph_repository=graph,
        condition_evaluator=evaluator,
        command_scope_factory=factory,
    )

    with pytest.raises(RuntimeError, match="passage graph save failed"):
        stage.run(WorldTick(1))

    loaded = graph.find_graph()
    assert loaded.get_connection(ConnectionId.create(10)).passage.state == "LOCKED"
    assert loaded.get_connection(ConnectionId.create(11)).passage.state == "LOCKED"
    assert loaded.get_events() == []
    assert evaluator.rollback_snapshot() == random_before
    assert observed == []


def test_passage_observations_see_all_stage_changes_after_commit() -> None:
    """passage観測は全接続確定後に届き、以前のeventを横取りしない。"""
    _, _, graph, evaluator, observed, factory = _build_world()
    old_event = _preexisting_event(graph)
    graph.find_graph().add_event(old_event)
    stage = ReactivePassageBindingStageService(
        bindings=(
            _probability_binding(key="", connection_id=10),
            _probability_binding(key="", connection_id=11),
        ),
        spot_graph_repository=graph,
        condition_evaluator=evaluator,
        command_scope_factory=factory,
    )

    stage.run(WorldTick(1))

    assert [entry[0] for entry in observed] == [
        "ConnectionStateChangedEvent",
        "ConnectionStateChangedEvent",
    ]
    assert all(entry[2] == ("OPEN", "OPEN") for entry in observed)
    assert graph.find_graph().get_events() == [old_event]
