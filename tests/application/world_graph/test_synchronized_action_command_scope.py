"""synchronized action groupの確定境界契約。"""

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.synchronized_action_resolver_stage_service import (
    SynchronizedActionResolverStageService,
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
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_synchronized_action_command_repository_provider import (
    InMemorySynchronizedActionCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_synchronized_action_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)


def _effect(effect_type: InteractionEffectTypeEnum, **parameters) -> InteractionEffect:
    return InteractionEffect(effect_type=effect_type, parameters=parameters)


def _group(
    group_id: str,
    action_names: tuple[str, str],
    *,
    connection_id: int,
) -> SynchronizedActionGroup:
    return SynchronizedActionGroup(
        group_id=group_id,
        required_action_names=action_names,
        window_ticks=2,
        on_complete=(
            _effect(
                InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE,
                connection_id=connection_id,
                new_state="OPEN",
            ),
            _effect(
                InteractionEffectTypeEnum.SET_FLAG,
                flag_name=f"{group_id}_done",
            ),
            _effect(
                InteractionEffectTypeEnum.SHOW_MESSAGE,
                message=f"{group_id} completed",
            ),
        ),
    )


def _build_world(groups: tuple[SynchronizedActionGroup, ...]):
    store = InMemoryDataStore()
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
                from_spot_id=SpotId.create(1),
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
    flags = MutableWorldFlagState()
    registry = SynchronizedActionRegistry(flags)
    delivered_events: list[tuple[str, frozenset[str], tuple[str, str]]] = []
    delivered_messages: list[
        tuple[str, str, tuple[int, ...], str, frozenset[str], tuple[str, str]]
    ] = []
    dispatcher = CommandEventDispatcher()

    def committed_state() -> tuple[frozenset[str], tuple[str, str]]:
        committed_graph = graph.find_graph()
        return (
            flags.as_frozen_set(),
            (
                committed_graph.get_connection(ConnectionId.create(10)).passage.state,
                committed_graph.get_connection(ConnectionId.create(11)).passage.state,
            ),
        )

    def observe(event: BaseDomainEvent) -> None:
        committed_flags, passages = committed_state()
        delivered_events.append((type(event).__name__, committed_flags, passages))

    def message(group_id, outcome, recipients, text) -> None:
        committed_flags, passages = committed_state()
        delivered_messages.append(
            (group_id, outcome, recipients, text, committed_flags, passages)
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
            participants=build_synchronized_action_rollback_participants(
                world_flags=flags,
                spot_graph=graph,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemorySynchronizedActionCommandRepositoryProviderFactory(
                spot_graph=graph,
            )
        ),
    )
    stage = SynchronizedActionResolverStageService(
        groups=groups,
        registry=registry,
        spot_graph_repository=graph,
        spot_interior_repository=InMemorySpotInteriorRepository(data_store=store),
        world_flag_state=flags,
        on_message=message,
        command_scope_factory=factory,
    )
    return stage, registry, graph, flags, delivered_events, delivered_messages


def _prepare(
    registry: SynchronizedActionRegistry,
    action_names: tuple[str, str],
    *,
    first_player_id: int = 1,
) -> None:
    registry.prepare(
        action_id=action_names[0], player_id=first_player_id, current_tick=5
    )
    registry.prepare(
        action_id=action_names[1], player_id=first_player_id + 1, current_tick=5
    )


def _preexisting_event(graph: InMemorySpotGraphRepository):
    return ConnectionStateChangedEvent.create(
        aggregate_id=graph.find_graph().graph_id,
        aggregate_type="SpotGraphAggregate",
        connection_id=ConnectionId.create(99),
        from_spot_id=SpotId.create(1),
        to_spot_id=SpotId.create(2),
        traversable=True,
        cause=PassageChangeCauseEnum.UNKNOWN,
        original_actor_entity_id=None,
    )


def test_group_observations_follow_commit_and_preserve_old_graph_events() -> None:
    """成功eventとmessageはgroupのflag・通路・prepare消去の確定後に届く。"""
    group = _group("alpha", ("left", "right"), connection_id=10)
    stage, registry, graph, flags, events, messages = _build_world((group,))
    old_event = _preexisting_event(graph)
    graph.find_graph().add_event(old_event)
    _prepare(registry, group.required_action_names)

    stage.run(WorldTick(5))

    assert "alpha_done" in flags.as_frozen_set()
    assert registry.entries_for("left") == []
    assert registry.entries_for("right") == []
    assert events == [
        (
            "ConnectionStateChangedEvent",
            frozenset({"alpha_done"}),
            ("OPEN", "LOCKED"),
        )
    ]
    assert messages == [
        (
            "alpha",
            "completed",
            (1, 2),
            "alpha completed",
            frozenset({"alpha_done"}),
            ("OPEN", "LOCKED"),
        )
    ]
    assert graph.find_graph().get_events() == [old_event]


def test_graph_save_failure_rolls_back_effects_prepares_and_observations() -> None:
    """group後段のgraph保存失敗はflag・通路・prepare・成功観測を全て戻す。"""
    group = _group("alpha", ("left", "right"), connection_id=10)
    stage, registry, graph, flags, events, messages = _build_world((group,))
    old_event = _preexisting_event(graph)
    graph.find_graph().add_event(old_event)
    _prepare(registry, group.required_action_names)
    original_flags = flags.as_frozen_set()
    original_save = graph.save
    calls = 0

    def fail_first_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synchronized graph save failed")
        original_save(value)

    graph.save = fail_first_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="synchronized graph save failed"):
        stage.run(WorldTick(5))

    assert flags.as_frozen_set() == original_flags
    assert len(registry.entries_for("left")) == 1
    assert len(registry.entries_for("right")) == 1
    assert graph.find_graph().get_connection(ConnectionId.create(10)).passage.state == "LOCKED"
    assert graph.find_graph().get_events() == [old_event]
    assert events == []
    assert messages == []


def test_later_group_failure_keeps_earlier_group_commit() -> None:
    """後続groupの失敗は先に確定したgroupの状態・観測を巻き戻さない。"""
    first = _group("alpha", ("left", "right"), connection_id=10)
    second = _group("beta", ("up", "down"), connection_id=11)
    stage, registry, graph, flags, events, messages = _build_world((first, second))
    _prepare(registry, first.required_action_names)
    _prepare(registry, second.required_action_names, first_player_id=3)
    original_save = graph.save
    calls = 0

    def fail_second_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second group save failed")
        original_save(value)

    graph.save = fail_second_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="second group save failed"):
        stage.run(WorldTick(5))

    assert "alpha_done" in flags.as_frozen_set()
    assert "beta_done" not in flags.as_frozen_set()
    assert registry.entries_for("left") == []
    assert registry.entries_for("right") == []
    assert len(registry.entries_for("up")) == 1
    assert len(registry.entries_for("down")) == 1
    assert graph.find_graph().get_connection(ConnectionId.create(10)).passage.state == "OPEN"
    assert graph.find_graph().get_connection(ConnectionId.create(11)).passage.state == "LOCKED"
    assert [event[0] for event in events] == ["ConnectionStateChangedEvent"]
    assert [message[0] for message in messages] == ["alpha"]


def test_message_callback_failure_does_not_turn_commit_into_command_failure() -> None:
    """確定後message通知の失敗は確定済みgroupを失敗扱いへ戻さない。"""
    group = _group("alpha", ("left", "right"), connection_id=10)
    stage, registry, graph, flags, _, _ = _build_world((group,))
    _prepare(registry, group.required_action_names)
    stage._on_message = lambda *_args: (_ for _ in ()).throw(  # type: ignore[assignment]
        RuntimeError("message delivery failed")
    )

    stage.run(WorldTick(5))

    assert "alpha_done" in flags.as_frozen_set()
    assert registry.entries_for("left") == []
    assert graph.find_graph().get_connection(ConnectionId.create(10)).passage.state == "OPEN"
