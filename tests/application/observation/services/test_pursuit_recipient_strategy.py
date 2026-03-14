"""PursuitRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.pursuit_recipient_strategy import (
    PursuitRecipientStrategy,
)
from ai_rpg_world.application.observation.services.world_object_to_player_resolver import (
    WorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import PursuitLastKnownState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import PursuitTargetSnapshot
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)


def _build_pursuit_snapshot(
    target_id: int = 22,
    spot_id: int = 7,
) -> PursuitTargetSnapshot:
    return PursuitTargetSnapshot(
        target_id=WorldObjectId(target_id),
        spot_id=SpotId(spot_id),
        coordinate=Coordinate(12, 4, 0),
    )


def _build_pursuit_last_known(
    target_id: int = 22,
    spot_id: int = 7,
    observed_at_tick: int = 30,
) -> PursuitLastKnownState:
    return PursuitLastKnownState(
        target_id=WorldObjectId(target_id),
        spot_id=SpotId(spot_id),
        coordinate=Coordinate(12, 4, 0),
        observed_at_tick=WorldTick(observed_at_tick),
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


class TestPursuitRecipientStrategyNormal:
    """PursuitRecipientStrategy 正常系テスト"""

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
        return PursuitRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=world_object_resolver,
        )

    def test_pursuit_started_returns_actor_and_target_when_both_on_map(
        self, strategy, physical_map_repo
    ):
        """PursuitStartedEvent: actor と target がマップ上にいるとき両方が配信先"""
        physical_map_repo.save(
            _make_minimal_map(1, [
                _create_player_object(3, 0, 0),
                _create_player_object(7, 1, 0),
            ])
        )
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Actor",
            actor_id=WorldObjectId.create(3),
            target_id=WorldObjectId.create(7),
            target_snapshot=_build_pursuit_snapshot(7),
            last_known=_build_pursuit_last_known(7),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {3, 7}

    def test_pursuit_updated_returns_actor_when_on_map(self, strategy, physical_map_repo):
        """PursuitUpdatedEvent: actor がマップ上にいるときそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(2, [_create_player_object(5, 0, 0)])
        )
        event = PursuitUpdatedEvent.create(
            aggregate_id=WorldObjectId(2),
            aggregate_type="Actor",
            actor_id=WorldObjectId.create(5),
            target_id=WorldObjectId(99),
            last_known=_build_pursuit_last_known(99),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5

    def test_pursuit_failed_returns_actor_when_on_map(self, strategy, physical_map_repo):
        """PursuitFailedEvent: actor がマップ上にいるときそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(3, [_create_player_object(2, 0, 0)])
        )
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(3),
            aggregate_type="Actor",
            actor_id=WorldObjectId.create(2),
            target_id=WorldObjectId(99),
            failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
            last_known=_build_pursuit_last_known(99),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 2

    def test_pursuit_cancelled_returns_actor_and_target_when_both_on_map(
        self, strategy, physical_map_repo
    ):
        """PursuitCancelledEvent: actor と target がマップ上にいるとき両方が配信先"""
        physical_map_repo.save(
            _make_minimal_map(4, [
                _create_player_object(1, 0, 0),
                _create_player_object(9, 1, 0),
            ])
        )
        event = PursuitCancelledEvent.create(
            aggregate_id=WorldObjectId(4),
            aggregate_type="Actor",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(9),
            last_known=_build_pursuit_last_known(9),
            target_snapshot=_build_pursuit_snapshot(9),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 9}


class TestPursuitRecipientStrategyExceptions:
    """PursuitRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def world_object_resolver(self, physical_map_repo):
        return WorldObjectToPlayerResolver(physical_map_repo)

    def test_pursuit_started_returns_empty_when_neither_on_map(self, world_object_resolver):
        """PursuitStartedEvent: actor も target もマップにいないとき空リスト"""
        strategy = PursuitRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=world_object_resolver,
        )
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Actor",
            actor_id=WorldObjectId(88888),
            target_id=WorldObjectId(99999),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_resolve_propagates_resolver_exception(self):
        """resolve: リゾルバが例外を投げた場合、その例外が伝播する"""
        resolver = MagicMock()
        resolver.resolve_player_id.side_effect = RuntimeError("Resolver failed")
        strategy = PursuitRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=resolver,
        )
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Actor",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        with pytest.raises(RuntimeError, match="Resolver failed"):
            strategy.resolve(event)


class TestPursuitRecipientStrategySupports:
    """PursuitRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return PursuitRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            world_object_to_player_resolver=MagicMock(),
        )

    def test_supports_pursuit_started_event(self, strategy):
        """PursuitStartedEvent を supports"""
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Actor",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
