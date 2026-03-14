"""CombatRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.combat_recipient_strategy import (
    CombatRecipientStrategy,
)
from ai_rpg_world.application.observation.services.world_object_to_player_resolver import (
    WorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)


def _create_player_object(player_id: int, x: int = 0, y: int = 0) -> WorldObject:
    """プレイヤー用 WorldObject"""
    return WorldObject(
        object_id=WorldObjectId.create(player_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.PLAYER,
        component=ActorComponent(
            direction=DirectionEnum.SOUTH,
            player_id=PlayerId(player_id),
        ),
    )


def _make_minimal_map(spot_id: int, objects: list) -> PhysicalMapAggregate:
    """複数タイルの最小マップ（オブジェクトごとに異なる座標が必要）"""
    tiles = {}
    for i in range(max(len(objects) + 1, 2)):
        coord = Coordinate(i, 0, 0)
        tiles[coord] = Tile(coord, TerrainType.grass())
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
    )


class TestCombatRecipientStrategyNormal:
    """CombatRecipientStrategy 正常系テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def world_object_resolver(self, physical_map_repo):
        return WorldObjectToPlayerResolver(physical_map_repo)

    @pytest.fixture
    def strategy(self, world_object_resolver):
        return CombatRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=world_object_resolver,
        )

    def test_hit_box_hit_recorded_returns_owner_and_target_when_both_on_map(
        self, strategy, physical_map_repo
    ):
        """HitBoxHitRecordedEvent: owner と target がマップ上にいるとき両方が配信先"""
        physical_map_repo.save(
            _make_minimal_map(1, [
                _create_player_object(3, 0, 0),
                _create_player_object(7, 1, 0),
            ])
        )
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId.create(3),
            target_id=WorldObjectId.create(7),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {3, 7}

    def test_hit_box_hit_recorded_returns_owner_only_when_target_not_on_map(
        self, strategy, physical_map_repo
    ):
        """HitBoxHitRecordedEvent: target がマップにいないとき owner のみ"""
        physical_map_repo.save(_make_minimal_map(5, [_create_player_object(2)]))
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId.create(2),
            target_id=WorldObjectId(99999),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 2

    def test_hit_box_created_returns_empty_per_spec(self, strategy):
        """HitBoxCreatedEvent: 仕様により観測対象外、空リストを返す"""
        event = HitBoxCreatedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(1),
            initial_coordinate=Coordinate(0, 0, 0),
            duration=10,
            power_multiplier=1.0,
            shape_cell_count=1,
            effect_count=0,
            activation_tick=0,
        )
        result = strategy.resolve(event)
        assert result == []

    def test_hit_box_moved_returns_empty_per_spec(self, strategy):
        """HitBoxMovedEvent: 仕様により観測対象外、空リストを返す"""
        event = HitBoxMovedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            from_coordinate=Coordinate(0, 0, 0),
            to_coordinate=Coordinate(1, 0, 0),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_hit_box_deactivated_returns_empty_per_spec(self, strategy):
        """HitBoxDeactivatedEvent: 仕様により観測対象外、空リストを返す"""
        event = HitBoxDeactivatedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            reason="timeout",
        )
        result = strategy.resolve(event)
        assert result == []

    def test_hit_box_obstacle_collided_returns_empty_per_spec(self, strategy):
        """HitBoxObstacleCollidedEvent: 仕様により観測対象外、空リストを返す"""
        event = HitBoxObstacleCollidedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            collision_coordinate=Coordinate(0, 0, 0),
            obstacle_collision_policy="destroy",
        )
        result = strategy.resolve(event)
        assert result == []


class TestCombatRecipientStrategyExceptions:
    """CombatRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def world_object_resolver(self, physical_map_repo):
        return WorldObjectToPlayerResolver(physical_map_repo)

    def test_hit_box_hit_recorded_returns_empty_when_neither_on_map(self, world_object_resolver):
        """HitBoxHitRecordedEvent: owner も target もマップにいないとき空リスト"""
        strategy = CombatRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=world_object_resolver,
        )
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(88888),
            target_id=WorldObjectId(99999),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_resolve_propagates_resolver_exception(self):
        """resolve: リゾルバが例外を投げた場合、その例外が伝播する"""
        resolver = MagicMock()
        resolver.resolve_player_id.side_effect = RuntimeError("Resolver failed")
        strategy = CombatRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=resolver,
        )
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        with pytest.raises(RuntimeError, match="Resolver failed"):
            strategy.resolve(event)


class TestCombatRecipientStrategySupports:
    """CombatRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return CombatRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=MagicMock(),
        )

    def test_supports_hit_box_hit_recorded_event(self, strategy):
        """HitBoxHitRecordedEvent を supports"""
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        assert strategy.supports(event) is True

    def test_supports_hit_box_created_event(self, strategy):
        """HitBoxCreatedEvent を supports（resolve は空リストを返す）"""
        event = HitBoxCreatedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(1),
            initial_coordinate=Coordinate(0, 0, 0),
            duration=10,
            power_multiplier=1.0,
            shape_cell_count=1,
            effect_count=0,
            activation_tick=0,
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
