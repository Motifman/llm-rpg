"""通常の物体interactionが一つのCommandScopeで確定することを保証する。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    InteractionCooldownStore,
    object_action_key,
)
from ai_rpg_world.application.world_graph.overflow_sinks import GroundOverflowSink
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerOverflowedItemEvent,
    SpotObjectInteractionFailedEvent,
    SpotObjectInteractedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_interaction_command_repository_provider import (
    InMemoryInteractionCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
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
    build_interaction_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)

PLAYER_ID = PlayerId(1)
ORIGIN = SpotId.create(1)
DESTINATION = SpotId.create(2)
OBJECT_ID = SpotObjectId.create(10)


@dataclass(frozen=True)
class _ObservedState:
    flag_is_set: bool
    object_is_active: bool
    player_spot_id: SpotId
    cooldown_tick: int | None


def _graph_repository() -> InMemorySpotGraphRepository:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id, name in ((ORIGIN, "開始地点"), (DESTINATION, "移動先")):
        graph.add_spot(
            SpotNode(
                spot_id=spot_id,
                name=name,
                description="CommandScope試験用",
                category=SpotCategoryEnum.DUNGEON,
                parent_id=None,
            )
        )
    graph.place_entity(EntityId.create(int(PLAYER_ID)), ORIGIN)
    graph.clear_events()
    return InMemorySpotGraphRepository(graph)


def _interaction_object(
    *, reject: bool = False, grant_overflow_item: bool = False
) -> SpotObject:
    return SpotObject(
        object_id=OBJECT_ID,
        name="転送装置",
        description="状態と位置を同時に変える",
        object_type=SpotObjectTypeEnum.OTHER,
        state={"active": False},
        interactions=(
            InteractionDef(
                action_name="activate",
                display_label="起動する",
                preconditions=(
                    (
                        InteractionCondition(
                            condition_type=InteractionConditionTypeEnum.FLAG_SET,
                            flag_name="permission",
                            failure_message="権限がありません",
                        ),
                    )
                    if reject
                    else ()
                ),
                effects=(
                    *(
                        (
                            InteractionEffect(
                                effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
                                parameters={"item_spec_id": 6},
                            ),
                        )
                        if grant_overflow_item
                        else ()
                    ),
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SET_FLAG,
                        parameters={"flag_name": "activated"},
                    ),
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                        parameters={"state_updates": {"active": True}},
                    ),
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.TELEPORT_ENTITY,
                        parameters={"spot_id": int(DESTINATION)},
                    ),
                ),
                cooldown_ticks=3,
                cooldown_scope=InteractionCooldownScope.ACTOR,
            ),
        ),
    )


class _EventPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish_all(self, events: object) -> None:
        self.events.extend(events)  # type: ignore[arg-type]


def _build_service(
    *,
    fail_before_commit: bool = False,
    reject: bool = False,
    grant_overflow_item: bool = False,
):
    data_store = InMemoryDataStore()
    graph_repository = _graph_repository()
    interior_repository = InMemorySpotInteriorRepository(data_store=data_store)
    interior_repository.save(
        ORIGIN,
        SpotInterior(
            (),
            (
                _interaction_object(
                    reject=reject,
                    grant_overflow_item=grant_overflow_item,
                ),
            ),
            (),
            (),
        ),
    )
    inventory_repository = InMemoryPlayerInventoryRepository(data_store)
    inventory_repository.save(
        PlayerInventoryAggregate(
            player_id=PLAYER_ID,
            max_slots=0 if grant_overflow_item else 20,
        )
    )
    item_repository = InMemoryItemRepository(data_store)
    item_spec_repository = InMemoryItemSpecRepository()
    status_repository = InMemoryPlayerStatusRepository(data_store)
    world_flags = MutableWorldFlagState()
    cooldowns = InteractionCooldownStore()
    departed = DepartedPositionStore()
    flag_notifications: list[str] = []
    world_flags.set_change_callback(
        lambda change: flag_notifications.append(change.flag_name)
    )

    dispatcher = CommandEventDispatcher()
    if fail_before_commit:
        dispatcher.register_required_before_commit(
            SpotObjectInteractedEvent,
            lambda event, context: (_ for _ in ()).throw(
                RuntimeError("sync interaction handler failed")
            ),
        )
    observations: list[_ObservedState] = []
    failure_publisher = _EventPublisher()
    dispatcher.register_after_commit(
        PlayerOverflowedItemEvent,
        lambda event: failure_publisher.events.append(event),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    def observe(_: object) -> None:
        interior = interior_repository.find_by_spot_id(ORIGIN)
        obj = interior.get_object(OBJECT_ID) if interior is not None else None
        observations.append(
            _ObservedState(
                flag_is_set="activated" in world_flags.as_frozen_set(),
                object_is_active=bool(obj and obj.state.get("active")),
                player_spot_id=graph_repository.find_graph().get_entity_spot(
                    EntityId.create(int(PLAYER_ID))
                ),
                cooldown_tick=cooldowns.last_success_tick(
                    PLAYER_ID,
                    object_action_key(int(OBJECT_ID), "activate"),
                ),
            )
        )

    dispatcher.register_after_commit(
        SpotObjectInteractedEvent,
        observe,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    participants = build_interaction_rollback_participants(
        world_flags=world_flags,
        cooldowns=cooldowns,
        departed_positions=departed,
        spot_graph=graph_repository,
    )
    scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=participants,
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryInteractionCommandRepositoryProviderFactory(
                spot_graph=graph_repository,
                item_specs=item_spec_repository,
            )
        ),
    )
    service = SpotInteractionApplicationService(
        spot_graph_repository=graph_repository,
        spot_interior_repository=interior_repository,
        player_inventory_repository=inventory_repository,
        item_repository=item_repository,
        item_spec_repository=item_spec_repository,
        world_flag_state=world_flags,
        player_status_repository=status_repository,
        event_publisher=failure_publisher,
        interaction_command_scope_factory=scope_factory,
        overflow_sink=GroundOverflowSink(
            spot_graph_repository=graph_repository,
            spot_interior_repository=interior_repository,
            item_repository=item_repository,
            item_spec_repository=item_spec_repository,
            event_publisher=failure_publisher,
        ),
    )
    service.set_cooldown_store(cooldowns)
    return (
        service,
        graph_repository,
        interior_repository,
        world_flags,
        cooldowns,
        flag_notifications,
        observations,
        failure_publisher,
    )


def test_success_commits_every_resource_before_observation() -> None:
    """成功観測はrepositoryと外部4資源がすべて確定した後にだけ届く。"""
    service, _, _, _, _, notifications, observations, failure_publisher = (
        _build_service()
    )

    service.execute_interaction(
        PLAYER_ID,
        OBJECT_ID,
        "activate",
        current_tick=WorldTick(7),
    )

    assert observations == [_ObservedState(True, True, DESTINATION, 7)]
    assert notifications == ["activated"]
    assert failure_publisher.events == []


def test_sync_failure_rolls_back_repository_external_state_and_observation() -> None:
    """同期必須処理の失敗ではinterior・flag・位置・待ち時間・成功観測を残さない。"""
    (
        service,
        graph_repository,
        interior_repository,
        world_flags,
        cooldowns,
        notifications,
        observations,
        failure_publisher,
    ) = _build_service(fail_before_commit=True)

    with pytest.raises(RuntimeError, match="sync interaction handler failed"):
        service.execute_interaction(
            PLAYER_ID,
            OBJECT_ID,
            "activate",
            current_tick=WorldTick(7),
        )

    interior = interior_repository.find_by_spot_id(ORIGIN)
    obj = interior.get_object(OBJECT_ID) if interior is not None else None
    assert obj is not None and obj.state == {"active": False}
    assert world_flags.as_frozen_set() == frozenset()
    assert graph_repository.find_graph().get_entity_spot(
        EntityId.create(int(PLAYER_ID))
    ) == ORIGIN
    assert cooldowns.last_success_tick(
        PLAYER_ID,
        object_action_key(int(OBJECT_ID), "activate"),
    ) is None
    assert notifications == []
    assert observations == []
    assert failure_publisher.events == []


def test_overflow_is_rolled_back_before_its_observation_is_delivered() -> None:
    """付与品の溢れ後に同期処理が失敗すると、地面・品・溢れ観測を残さない。"""
    (
        service,
        _,
        interior_repository,
        _,
        _,
        _,
        _,
        failure_publisher,
    ) = _build_service(fail_before_commit=True, grant_overflow_item=True)

    with pytest.raises(RuntimeError, match="sync interaction handler failed"):
        service.execute_interaction(
            PLAYER_ID,
            OBJECT_ID,
            "activate",
            current_tick=WorldTick(7),
        )

    interior = interior_repository.find_by_spot_id(ORIGIN)
    assert interior is not None
    assert interior.ground_items == ()
    assert failure_publisher.events == []


def test_precondition_failure_is_observed_after_rollback_without_success_event() -> None:
    """前提条件拒否は成功eventへ混ぜず、rollback後の確定状態から一度だけ観測する。"""
    (
        service,
        graph_repository,
        _,
        world_flags,
        _,
        notifications,
        observations,
        failure_publisher,
    ) = _build_service(reject=True)

    with pytest.raises(InteractionNotAllowedException, match="権限がありません"):
        service.execute_interaction(PLAYER_ID, OBJECT_ID, "activate")

    assert world_flags.as_frozen_set() == frozenset()
    assert graph_repository.find_graph().get_entity_spot(
        EntityId.create(int(PLAYER_ID))
    ) == ORIGIN
    assert notifications == []
    assert observations == []
    failed = [
        event
        for event in failure_publisher.events
        if isinstance(event, SpotObjectInteractionFailedEvent)
    ]
    assert len(failed) == 1


def test_cooldown_refusal_does_not_become_a_precondition_failure_observation() -> None:
    """待ち時間中の拒否は、従来どおり前提条件失敗の観測へ変換しない。"""
    service, graph_repository, _, _, _, _, _, failure_publisher = _build_service()
    service.execute_interaction(
        PLAYER_ID,
        OBJECT_ID,
        "activate",
        current_tick=WorldTick(7),
    )
    graph = graph_repository.find_graph()
    entity_id = EntityId.create(int(PLAYER_ID))
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, ORIGIN)
    graph.clear_events()
    graph_repository.save(graph)

    with pytest.raises(InteractionNotAllowedException):
        service.execute_interaction(
            PLAYER_ID,
            OBJECT_ID,
            "activate",
            current_tick=WorldTick(8),
        )

    assert not any(
        isinstance(event, SpotObjectInteractionFailedEvent)
        for event in failure_publisher.events
    )
