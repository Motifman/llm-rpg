"""scenario eventがevent定義1件ごとに状態・進捗・観測を確定する契約。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_stage_service import (
    SpotGraphScenarioEventStageService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
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
    build_scenario_event_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)

PLAYER_ID = PlayerId(1)
ORIGIN = SpotId.create(1)
DESTINATION = SpotId.create(2)
OBJECT_ID = SpotObjectId.create(7)
CONNECTION_ID = ConnectionId.create(5)
REWARD_SPEC_ID = ItemSpecId(10)


def _status() -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PLAYER_ID,
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(100, 100),
        mp=Mp(50, 50),
        stamina=Stamina(100, 100),
    )


def _event(event_id: str, *, full_effects: bool) -> ScenarioEventDef:
    effects: list[InteractionEffect] = [
        InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SET_FLAG,
            parameters={"flag_name": f"{event_id}_flag"},
        )
    ]
    if full_effects:
        effects.extend(
            (
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                    parameters={
                        "object_id": OBJECT_ID.value,
                        "state_updates": {"active": True},
                    },
                ),
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE,
                    parameters={
                        "connection_id": CONNECTION_ID.value,
                        "new_state": "OPEN",
                    },
                ),
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
                    parameters={"item_spec_id": REWARD_SPEC_ID.value},
                ),
            )
        )
    effects.append(
        InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
            parameters={"message": f"{event_id} committed"},
        )
    )
    return ScenarioEventDef(
        event_id=event_id,
        trigger="ON_TICK",
        once=True,
        conditions=(),
        effects=tuple(effects),
    )


@dataclass
class _Harness:
    stage: SpotGraphScenarioEventStageService
    store: InMemoryDataStore
    graph_repository: InMemorySpotGraphRepository
    interior_repository: InMemorySpotInteriorRepository
    inventory_repository: InMemoryPlayerInventoryRepository
    item_repository: InMemoryItemRepository
    flags: MutableWorldFlagState
    progress: InMemorySpotGraphScenarioEventProgressStore
    messages: list[str]
    observed_event_types: list[str]


def _build(events: tuple[ScenarioEventDef, ...]) -> _Harness:
    store = InMemoryDataStore()
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id, name in ((ORIGIN, "origin"), (DESTINATION, "destination")):
        graph.add_spot(
            SpotNode(
                spot_id=spot_id,
                name=name,
                description="",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    graph.add_connection_dynamic(
        SpotConnection(
            connection_id=CONNECTION_ID,
            from_spot_id=ORIGIN,
            to_spot_id=DESTINATION,
            name="door",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        )
    )
    graph.place_entity(EntityId.create(PLAYER_ID.value), ORIGIN)
    graph.clear_events()
    graph_repository = InMemorySpotGraphRepository(graph)
    interior_repository = InMemorySpotInteriorRepository(data_store=store)
    interior_repository.save(
        ORIGIN,
        SpotInterior(
            (),
            (
                SpotObject(
                    object_id=OBJECT_ID,
                    name="switch",
                    description="",
                    object_type=SpotObjectTypeEnum.OTHER,
                    state={"active": False},
                    interactions=(),
                ),
            ),
            (),
            (),
        ),
    )
    status_repository = InMemoryPlayerStatusRepository(store)
    inventory_repository = InMemoryPlayerInventoryRepository(store)
    item_repository = InMemoryItemRepository(store)
    item_spec_repository = InMemoryItemSpecRepository()
    status_repository.save(_status())
    inventory_repository.save(PlayerInventoryAggregate(player_id=PLAYER_ID))
    item_spec_repository.save(
        ItemSpecReadModel(
            item_spec_id=REWARD_SPEC_ID,
            name="reward",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="command scope reward",
            max_stack_size=MaxStackSize(99),
        )
    )
    flags = MutableWorldFlagState()
    progress = InMemorySpotGraphScenarioEventProgressStore()
    messages: list[str] = []
    observed_event_types: list[str] = []
    dispatcher = CommandEventDispatcher()
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: observed_event_types.append(type(event).__name__),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(store),
            participants=build_scenario_event_rollback_participants(
                world_flags=flags,
                spot_graph=graph_repository,
                progress=progress,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=InMemoryInteractionCommandRepositoryProviderFactory(
            spot_graph=graph_repository,
            item_specs=item_spec_repository,
        ),
    )

    def record_message(_event: ScenarioEventDef, message: str) -> None:
        interior = interior_repository.find_by_spot_id(ORIGIN)
        inventory = inventory_repository.find_by_id(PLAYER_ID)
        assert interior is not None and inventory is not None
        assert progress.is_fired(events[0].event_id)
        assert f"{events[0].event_id}_flag" in flags.as_frozen_set()
        messages.append(message)

    stage = SpotGraphScenarioEventStageService(
        scenario_events=events,
        spot_graph_repository=graph_repository,
        spot_interior_repository=interior_repository,
        player_status_repository=status_repository,
        player_inventory_repository=inventory_repository,
        item_repository=item_repository,
        item_spec_repository=item_spec_repository,
        world_flag_state=flags,
        progress_store=progress,
        on_message=record_message,
        command_scope_factory=scope_factory,
    )
    return _Harness(
        stage=stage,
        store=store,
        graph_repository=graph_repository,
        interior_repository=interior_repository,
        inventory_repository=inventory_repository,
        item_repository=item_repository,
        flags=flags,
        progress=progress,
        messages=messages,
        observed_event_types=observed_event_types,
    )


def _object_active(harness: _Harness) -> bool:
    interior = harness.interior_repository.find_by_spot_id(ORIGIN)
    assert interior is not None
    return bool(interior.get_object(OBJECT_ID).state["active"])


def _passage_state(harness: _Harness) -> str:
    connection = harness.graph_repository.find_graph().get_connection(CONNECTION_ID)
    return connection.passage.state


class TestScenarioEventCommandScope:
    """event定義1件の全更新と確定後観測を検証する。"""

    def test_success_commits_every_resource_before_observation(self) -> None:
        """flag・interior・graph・item・progress確定後にeventとmessageを届ける。"""
        harness = _build((_event("alarm", full_effects=True),))

        harness.stage.run(WorldTick(1))

        assert harness.flags.as_frozen_set() == frozenset({"alarm_flag"})
        assert harness.progress.is_fired("alarm")
        assert _object_active(harness) is True
        assert _passage_state(harness) == "OPEN"
        assert len(harness.item_repository.find_by_spec_id(REWARD_SPEC_ID)) == 1
        assert harness.messages == ["alarm committed"]
        assert "ConnectionStateChangedEvent" in harness.observed_event_types

    def test_progress_failure_rolls_back_all_resources_and_observations(self) -> None:
        """進捗保存相当の後段失敗で全効果・event・messageを開始前へ戻す。"""
        event = replace(
            _event("alarm", full_effects=True),
            next_event_id="next",
            delay_ticks=3,
        )
        harness = _build((event,))
        original_record_progress = harness.stage._record_event_progress

        def fail_after_progress(event_def: ScenarioEventDef, tick: WorldTick) -> None:
            original_record_progress(event_def, tick)
            raise RuntimeError("progress failed")

        harness.stage._record_event_progress = fail_after_progress  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="progress failed"):
            harness.stage.run(WorldTick(1))

        assert harness.flags.as_frozen_set() == frozenset()
        assert harness.progress.is_fired("alarm") is False
        assert harness.progress.is_scheduled("next") is False
        assert _object_active(harness) is False
        assert _passage_state(harness) == "LOCKED"
        assert harness.item_repository.find_by_spec_id(REWARD_SPEC_ID) == []
        assert harness.messages == []
        assert harness.observed_event_types == []

    def test_each_event_definition_commits_independently(self) -> None:
        """後続event失敗でも同じtickで確定済みの先行eventは保持する。"""
        first = _event("first", full_effects=False)
        second = _event("second", full_effects=False)
        harness = _build((first, second))
        original_mark_fired = harness.progress.mark_fired

        def fail_second(event_id: str) -> None:
            original_mark_fired(event_id)
            if event_id == "second":
                raise RuntimeError("second failed")

        harness.progress.mark_fired = fail_second  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="second failed"):
            harness.stage.run(WorldTick(1))

        assert harness.flags.as_frozen_set() == frozenset({"first_flag"})
        assert harness.progress.is_fired("first") is True
        assert harness.progress.is_fired("second") is False
        assert harness.messages == ["first committed"]

    def test_message_follows_a_commit_with_cleanup_failure(self) -> None:
        """commit後cleanup失敗でもmessageを届けて元の例外を維持する。"""
        harness = _build((_event("alarm", full_effects=False),))
        original_release = harness.store.release_uow_transaction

        def release_then_fail() -> None:
            original_release()
            raise RuntimeError("release failed")

        harness.store.release_uow_transaction = release_then_fail  # type: ignore[method-assign]

        with pytest.raises(CommandPostCommitException):
            harness.stage.run(WorldTick(1))

        assert harness.flags.as_frozen_set() == frozenset({"alarm_flag"})
        assert harness.progress.is_fired("alarm") is True
        assert harness.messages == ["alarm committed"]

    def test_message_callback_failure_does_not_change_committed_result(self) -> None:
        """確定後message観測の失敗は警告に留め、event成功を維持する。"""
        harness = _build((_event("alarm", full_effects=False),))

        def fail_message(_event: ScenarioEventDef, _message: str) -> None:
            raise RuntimeError("message failed")

        harness.stage.set_message_callback(fail_message)

        harness.stage.run(WorldTick(1))

        assert harness.flags.as_frozen_set() == frozenset({"alarm_flag"})
        assert harness.progress.is_fired("alarm") is True
