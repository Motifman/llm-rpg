"""HarvestSessionDomainService の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.harvest_session_domain_service import HarvestSessionDomainService
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    HarvestableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestStartedEvent,
    HarvestCompletedEvent,
    HarvestCancelledEvent,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
)
from ai_rpg_world.domain.world.exception.harvest_exception import (
    NotHarvestableException,
    HarvestInProgressException,
    ResourceExhaustedException,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


@pytest.fixture
def current_tick():
    return WorldTick(10)


def _make_actor(coord, direction=DirectionEnum.EAST, busy_until=None):
    kwargs = {"component": ActorComponent(direction=direction)}
    if busy_until is not None:
        kwargs["busy_until"] = busy_until
    return WorldObject(
        WorldObjectId(100),
        coord,
        ObjectTypeEnum.PLAYER,
        **kwargs,
    )


def _make_harvestable(coord, loot_table_id=1, **kwargs):
    return WorldObject(
        WorldObjectId(200),
        coord,
        ObjectTypeEnum.RESOURCE,
        component=HarvestableComponent(loot_table_id=loot_table_id, **kwargs),
    )


class TestStartHarvest:
    """start_harvest のテスト"""

    class TestSuccessCases:
        def test_returns_event_and_sets_actor_busy(self, current_tick):
            # Given
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.EAST)
            target = _make_harvestable(Coordinate(1, 0, 0), harvest_duration=10)

            # When
            event = HarvestSessionDomainService.start_harvest(
                actor, target, current_tick
            )

            # Then
            assert isinstance(event, HarvestStartedEvent)
            assert event.actor_id == actor.object_id
            assert event.target_id == target.object_id
            assert event.finish_tick == WorldTick(20)
            assert actor.is_busy(current_tick)
            assert actor.busy_until == WorldTick(20)
            assert target.component.current_actor_id == actor.object_id

        def test_adjacent_facing_south_succeeds(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.SOUTH)
            target = _make_harvestable(Coordinate(0, 1, 0))

            event = HarvestSessionDomainService.start_harvest(
                actor, target, current_tick
            )

            assert event is not None
            assert actor.is_busy(current_tick)

        def test_same_cell_succeeds(self, current_tick):
            actor = _make_actor(Coordinate(1, 1, 0))
            target = _make_harvestable(Coordinate(1, 1, 0))

            event = HarvestSessionDomainService.start_harvest(
                actor, target, current_tick
            )

            assert event is not None

    class TestExceptionCases:
        def test_raises_when_actor_busy(self, current_tick):
            actor = _make_actor(
                Coordinate(0, 0, 0), DirectionEnum.EAST, busy_until=WorldTick(20)
            )
            target = _make_harvestable(Coordinate(1, 0, 0))

            with pytest.raises(ActorBusyException) as exc_info:
                HarvestSessionDomainService.start_harvest(
                    actor, target, current_tick
                )
            assert "busy" in str(exc_info.value).lower()

        def test_raises_when_too_far(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(2, 2, 0))

            with pytest.raises(InteractionOutOfRangeException):
                HarvestSessionDomainService.start_harvest(
                    actor, target, current_tick
                )

        def test_raises_when_not_facing(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.WEST)
            target = _make_harvestable(Coordinate(1, 0, 0))

            with pytest.raises(NotFacingTargetException):
                HarvestSessionDomainService.start_harvest(
                    actor, target, current_tick
                )

        def test_raises_when_target_not_harvestable(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.WEST),
            )

            with pytest.raises(NotHarvestableException):
                HarvestSessionDomainService.start_harvest(
                    actor, target, current_tick
                )

        def test_raises_when_component_none(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            with pytest.raises(NotHarvestableException):
                HarvestSessionDomainService.start_harvest(
                    actor, target, current_tick
                )

        def test_raises_when_already_harvesting(self, current_tick):
            # Given: actor1 が採取開始済み。actor2 は同じ resource に隣接・正しい向き。
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.EAST)
            target = _make_harvestable(Coordinate(1, 0, 0))
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)

            actor2 = _make_actor(Coordinate(2, 0, 0), DirectionEnum.WEST)
            with pytest.raises(HarvestInProgressException):
                HarvestSessionDomainService.start_harvest(
                    actor2, target, current_tick
                )

        def test_raises_when_resource_exhausted(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(
                Coordinate(1, 0, 0),
                max_quantity=1,
                initial_quantity=0,
                last_harvest_tick=current_tick,
            )

            with pytest.raises(ResourceExhaustedException):
                HarvestSessionDomainService.start_harvest(
                    actor, target, current_tick
                )


class TestFinishHarvest:
    """finish_harvest のテスト"""

    class TestSuccessCases:
        def test_returns_event_and_clears_actor_busy_when_complete(self, current_tick):
            # Given: 採取開始済み、完了時間経過
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0), harvest_duration=10)
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)
            finish_tick = WorldTick(20)

            # When
            event = HarvestSessionDomainService.finish_harvest(
                actor, target, finish_tick
            )

            # Then
            assert event is not None
            assert isinstance(event, HarvestCompletedEvent)
            assert event.actor_id == actor.object_id
            assert event.target_id == target.object_id
            assert event.loot_table_id == LootTableId(1)
            assert not actor.is_busy(finish_tick)
            assert target.component.current_actor_id is None

        def test_resource_quantity_decreases(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(
                Coordinate(1, 0, 0),
                max_quantity=3,
                harvest_duration=5,
            )
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)
            finish_tick = WorldTick(15)

            event = HarvestSessionDomainService.finish_harvest(
                actor, target, finish_tick
            )

            assert event is not None
            assert target.component.get_available_quantity(finish_tick) == 2

    class TestReturnsNoneWhenNotComplete:
        def test_returns_none_when_time_not_elapsed(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0), harvest_duration=10)
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)
            # 9ティックしか経過していない
            early_tick = WorldTick(19)

            event = HarvestSessionDomainService.finish_harvest(
                actor, target, early_tick
            )

            assert event is None
            assert actor.is_busy(early_tick)
            assert target.component.current_actor_id == actor.object_id

    class TestExceptionCases:
        def test_raises_when_target_not_harvestable(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )

            with pytest.raises(NotHarvestableException):
                HarvestSessionDomainService.finish_harvest(
                    actor, target, current_tick
                )

        def test_raises_when_component_none(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            with pytest.raises(NotHarvestableException):
                HarvestSessionDomainService.finish_harvest(
                    actor, target, current_tick
                )


class TestCancelHarvest:
    """cancel_harvest のテスト"""

    class TestSuccessCases:
        def test_returns_event_and_clears_actor_busy(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0))
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)

            event = HarvestSessionDomainService.cancel_harvest(
                actor, target, reason="interrupted"
            )

            assert isinstance(event, HarvestCancelledEvent)
            assert event.actor_id == actor.object_id
            assert event.target_id == target.object_id
            assert event.reason == "interrupted"
            assert not actor.is_busy(current_tick)
            assert target.component.current_actor_id is None

        def test_default_reason_is_cancelled(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0))
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)

            event = HarvestSessionDomainService.cancel_harvest(actor, target)

            assert event.reason == "cancelled"

    class TestExceptionCases:
        def test_raises_when_target_not_harvestable(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )

            with pytest.raises(NotHarvestableException):
                HarvestSessionDomainService.cancel_harvest(
                    actor, target, reason="test"
                )

        def test_raises_when_component_none(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            with pytest.raises(NotHarvestableException):
                HarvestSessionDomainService.cancel_harvest(
                    actor, target, reason="test"
                )
