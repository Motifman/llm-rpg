"""HarvestRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.harvest_recipient_strategy import (
    HarvestRecipientStrategy,
)
from ai_rpg_world.application.observation.services.world_object_to_player_resolver import (
    WorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
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
    """複数タイルの最小マップ"""
    tiles = {}
    for i in range(max(len(objects) + 1, 2)):
        coord = Coordinate(i, 0, 0)
        tiles[coord] = Tile(coord, TerrainType.grass())
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
    )


class TestHarvestRecipientStrategyNormal:
    """HarvestRecipientStrategy 正常系テスト"""

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
        return HarvestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=world_object_resolver,
        )

    def test_harvest_started_returns_actor_player_when_on_map(self, strategy, physical_map_repo):
        """HarvestStartedEvent: actor がマップ上のプレイヤーならそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(1, [_create_player_object(4, 0, 0)])
        )
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(99),
            aggregate_type="Harvest",
            actor_id=WorldObjectId.create(4),
            target_id=WorldObjectId(100),
            finish_tick=WorldTick(10),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 4

    def test_harvest_completed_returns_actor_player_when_on_map(self, strategy, physical_map_repo):
        """HarvestCompletedEvent: actor がマップ上のプレイヤーならそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(2, [_create_player_object(6, 0, 0)])
        )
        event = HarvestCompletedEvent.create(
            aggregate_id=WorldObjectId(99),
            aggregate_type="Harvest",
            actor_id=WorldObjectId.create(6),
            target_id=WorldObjectId(100),
            loot_table_id=LootTableId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 6

    def test_harvest_cancelled_returns_actor_player_when_on_map(self, strategy, physical_map_repo):
        """HarvestCancelledEvent: actor がマップ上のプレイヤーならそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(3, [_create_player_object(3, 0, 0)])
        )
        event = HarvestCancelledEvent.create(
            aggregate_id=WorldObjectId(99),
            aggregate_type="Harvest",
            actor_id=WorldObjectId.create(3),
            target_id=WorldObjectId(100),
            reason="interrupted",
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 3


class TestHarvestRecipientStrategyExceptions:
    """HarvestRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def world_object_resolver(self, physical_map_repo):
        return WorldObjectToPlayerResolver(physical_map_repo)

    def test_harvest_started_returns_empty_when_actor_not_on_map(self, world_object_resolver):
        """HarvestStartedEvent: actor がマップにいないとき空リスト"""
        strategy = HarvestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=world_object_resolver,
        )
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(99),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(99999),
            target_id=WorldObjectId(100),
            finish_tick=WorldTick(10),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_resolve_propagates_resolver_exception(self):
        """resolve: リゾルバが例外を投げた場合、その例外が伝播する"""
        resolver = MagicMock()
        resolver.resolve_player_id.side_effect = RuntimeError("Resolver failed")
        strategy = HarvestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=resolver,
        )
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(99),
            aggregate_type="Harvest",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId(100),
            finish_tick=WorldTick(10),
        )
        with pytest.raises(RuntimeError, match="Resolver failed"):
            strategy.resolve(event)


class TestHarvestRecipientStrategySupports:
    """HarvestRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return HarvestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=MagicMock(),
        )

    def test_supports_harvest_started_event(self, strategy):
        """HarvestStartedEvent を supports"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
