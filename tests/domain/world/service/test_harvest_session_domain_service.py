"""HarvestSessionDomainService の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    HarvestableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.world.exception.harvest_exception import (
    HarvestInProgressException,
    HarvestNotStartedException,
    NotHarvestableException,
    ResourceExhaustedException,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
)
from ai_rpg_world.domain.world.service.harvest_session_domain_service import HarvestSessionDomainService
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@pytest.fixture
def current_tick():
    return WorldTick(10)


def _make_actor(coord, direction=DirectionEnum.EAST, busy_until=None, object_id=100):
    kwargs = {"component": ActorComponent(direction=direction)}
    if busy_until is not None:
        kwargs["busy_until"] = busy_until
    return WorldObject(
        WorldObjectId(object_id),
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
        @pytest.mark.parametrize(
            "actor_coord,direction,target_coord,harvest_kwargs,busy_until,finish_tick",
            [
                pytest.param(
                    (0, 0, 0),
                    DirectionEnum.EAST,
                    (1, 0, 0),
                    {"max_quantity": 1, "harvest_duration": 10},
                    None,
                    20,
                    id="east-duration10",
                ),
                pytest.param((0, 0, 0), DirectionEnum.EAST, (1, 0, 0), {}, None, 15, id="east-default"),
                pytest.param((0, 0, 0), DirectionEnum.SOUTH, (0, 1, 0), {}, None, 15, id="south-default"),
                pytest.param((1, 1, 0), DirectionEnum.EAST, (1, 1, 0), {}, None, 15, id="same-cell-east"),
                pytest.param((1, 1, 0), DirectionEnum.NORTH, (1, 1, 0), {}, None, 15, id="same-cell-north"),
                pytest.param((0, 0, 0), DirectionEnum.SOUTHEAST, (1, 1, 0), {}, None, 15, id="diagonal-southeast"),
                pytest.param(
                    (0, 0, 0),
                    DirectionEnum.SOUTH,
                    (0, 1, 0),
                    {"max_quantity": 5, "respawn_interval": 100, "harvest_duration": 15, "stamina_cost": 20},
                    None,
                    25,
                    id="south-explicit",
                ),
                pytest.param((0, 0, 0), DirectionEnum.EAST, (1, 0, 0), {}, WorldTick(5), 15, id="busy-expired"),
                pytest.param((0, 0, 0), DirectionEnum.EAST, (1, 0, 0), {}, WorldTick(10), 15, id="busy-at-deadline"),
            ],
        )
        def test_returns_event_and_sets_actor_busy(
            self,
            current_tick,
            actor_coord,
            direction,
            target_coord,
            harvest_kwargs,
            busy_until,
            finish_tick,
        ):
            """同一マス・8方向隣接・期限終了後の開始は、指定時間の通知と占有状態を返す。"""
            actor = _make_actor(Coordinate(*actor_coord), direction, busy_until)
            target = _make_harvestable(Coordinate(*target_coord), **harvest_kwargs)

            event = HarvestSessionDomainService.start_harvest(actor, target, current_tick)

            assert isinstance(event, HarvestStartedEvent)
            assert event.actor_id == actor.object_id
            assert event.target_id == target.object_id
            assert event.finish_tick == WorldTick(finish_tick)
            assert actor.is_busy(current_tick)
            assert actor.busy_until == WorldTick(finish_tick)
            assert target.component.current_actor_id == actor.object_id

    class TestExceptionCases:
        def test_raises_when_actor_busy(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.EAST, busy_until=WorldTick(20))
            target = _make_harvestable(Coordinate(1, 0, 0))

            with pytest.raises(ActorBusyException) as exc_info:
                HarvestSessionDomainService.start_harvest(actor, target, current_tick)
            assert "busy" in str(exc_info.value).lower()

        @pytest.mark.parametrize("target_coord", [(2, 2, 0), (2, 0, 0)], ids=["diagonal-two", "straight-two"])
        def test_raises_when_too_far(self, current_tick, target_coord):
            """斜め・直線とも距離2では、距離不足を示す例外で開始を拒否する。"""
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(*target_coord))

            with pytest.raises(InteractionOutOfRangeException, match="(?i)far|too"):
                HarvestSessionDomainService.start_harvest(actor, target, current_tick)

        def test_raises_when_not_facing(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.WEST)
            target = _make_harvestable(Coordinate(1, 0, 0))

            with pytest.raises(NotFacingTargetException, match="(?i)facing"):
                HarvestSessionDomainService.start_harvest(actor, target, current_tick)

        def test_raises_when_target_not_harvestable(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.WEST),
            )

            with pytest.raises(NotHarvestableException, match="(?i)harvestable|not"):
                HarvestSessionDomainService.start_harvest(actor, target, current_tick)

        def test_raises_when_component_none(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            with pytest.raises(NotHarvestableException, match="(?i)harvestable|not"):
                HarvestSessionDomainService.start_harvest(actor, target, current_tick)

        @pytest.mark.parametrize("second_actor_id", [100, 101], ids=["same-id-retry", "different-actor"])
        def test_raises_when_already_harvesting(self, current_tick, second_actor_id):
            """既に占有された資源は、同じIDの再試行でも別の行為者でも開始を拒否する。"""
            actor = _make_actor(Coordinate(0, 0, 0), DirectionEnum.EAST)
            target = _make_harvestable(Coordinate(1, 0, 0))
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)

            actor2 = _make_actor(Coordinate(2, 0, 0), DirectionEnum.WEST, object_id=second_actor_id)
            with pytest.raises(HarvestInProgressException):
                HarvestSessionDomainService.start_harvest(actor2, target, current_tick)

        def test_raises_when_resource_exhausted(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(
                Coordinate(1, 0, 0),
                max_quantity=1,
                initial_quantity=0,
                last_harvest_tick=current_tick,
            )

            with pytest.raises(ResourceExhaustedException):
                HarvestSessionDomainService.start_harvest(actor, target, current_tick)


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
            event = HarvestSessionDomainService.finish_harvest(actor, target, finish_tick)

            # Then
            assert event is not None
            assert isinstance(event, HarvestCompletedEvent)
            assert event.actor_id == actor.object_id
            assert event.target_id == target.object_id
            assert event.loot_table_id == LootTableId(1)
            assert not actor.is_busy(finish_tick)
            # 現在状態DTOと保存先に古い終了時刻を残さない。
            assert actor.busy_until is None
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

            event = HarvestSessionDomainService.finish_harvest(actor, target, finish_tick)

            assert event is not None
            assert target.component.get_available_quantity(finish_tick) == 2

    class TestReturnsNoneWhenNotComplete:
        def test_returns_none_when_time_not_elapsed(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0), harvest_duration=10)
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)
            # 9ティックしか経過していない
            early_tick = WorldTick(19)

            event = HarvestSessionDomainService.finish_harvest(actor, target, early_tick)

            assert event is None
            assert actor.is_busy(early_tick)
            assert target.component.current_actor_id == actor.object_id

    class TestExceptionCases:
        @pytest.mark.parametrize(
            "harvest_kwargs",
            [{}, {"max_quantity": 5, "harvest_duration": 10}],
            ids=["default-quantity-and-duration", "quantity5-duration10"],
        )
        def test_unstarted_resource_reaches_session_guard(self, current_tick, harvest_kwargs):
            """未開始の資源も採集可能な型として通し、未開始を示す例外で完了を拒否する。"""
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0), **harvest_kwargs)

            with pytest.raises(HarvestNotStartedException):
                HarvestSessionDomainService.finish_harvest(actor, target, current_tick)

        @pytest.mark.parametrize("target_direction", [None, DirectionEnum.EAST], ids=["default-south", "east"])
        def test_raises_when_target_not_harvestable(self, current_tick, target_direction):
            """非採集コンポーネントは、向きに関係なく採集対象の例外で拒否する。"""
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=(
                    ActorComponent() if target_direction is None else ActorComponent(direction=target_direction)
                ),
            )

            with pytest.raises(NotHarvestableException, match="(?i)harvestable|not"):
                HarvestSessionDomainService.finish_harvest(actor, target, current_tick)

        def test_raises_when_component_none(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            with pytest.raises(NotHarvestableException, match="(?i)harvestable|not"):
                HarvestSessionDomainService.finish_harvest(actor, target, current_tick)


class TestCancelHarvest:
    """cancel_harvest のテスト"""

    class TestSuccessCases:
        def test_returns_event_and_clears_actor_busy(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = _make_harvestable(Coordinate(1, 0, 0))
            HarvestSessionDomainService.start_harvest(actor, target, current_tick)

            event = HarvestSessionDomainService.cancel_harvest(actor, target, reason="interrupted")

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
        @pytest.mark.parametrize("target_direction", [None, DirectionEnum.EAST], ids=["default-south", "east"])
        def test_raises_when_target_not_harvestable(self, current_tick, target_direction):
            """非採集コンポーネントは、向きに関係なく採集対象の例外で拒否する。"""
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=(
                    ActorComponent() if target_direction is None else ActorComponent(direction=target_direction)
                ),
            )

            with pytest.raises(NotHarvestableException, match="(?i)harvestable|not"):
                HarvestSessionDomainService.cancel_harvest(actor, target, reason="test")

        def test_raises_when_component_none(self, current_tick):
            actor = _make_actor(Coordinate(0, 0, 0))
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            with pytest.raises(NotHarvestableException, match="(?i)harvestable|not"):
                HarvestSessionDomainService.cancel_harvest(actor, target, reason="test")
