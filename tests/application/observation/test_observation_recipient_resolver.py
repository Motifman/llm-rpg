"""ObservationRecipientResolver のテスト（正常・観測対象外・境界・例外）"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
    ObservationRecipientResolver,
)
from ai_rpg_world.application.observation.services.world_object_to_player_resolver import (
    WorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.recipient_strategies import (
    DefaultRecipientStrategy,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum, InteractionTypeEnum
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLocationChangedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
)
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.conversation.event.conversation_event import ConversationStartedEvent
from ai_rpg_world.domain.monster.event.monster_events import MonsterDamagedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.combat.event.combat_events import HitBoxMovedEvent
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.skill.event.skill_events import SkillUsedEvent
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)


def _create_player_object(player_id: int, x: int = 0, y: int = 0) -> WorldObject:
    """プレイヤー用 WorldObject（ActorComponent に player_id を持つ）"""
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
    """1タイルのみの最小マップ（object 配置用）"""
    coord = Coordinate(0, 0, 0)
    tiles = {coord: Tile(coord, TerrainType.grass())}
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
    )


def _make_status(player_id: int, spot_id: int = 1) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(spot_id),
        current_coordinate=Coordinate(0, 0, 0),
    )


class TestObservationRecipientResolver:
    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def resolver(self, status_repo, physical_map_repo):
        return create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
        )

    def test_resolve_gateway_triggered_includes_actor_and_players_at_target_spot(
        self, resolver, status_repo
    ):
        """GatewayTriggeredEvent: 本人と target_spot にいるプレイヤーが配信先"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        status_repo.save(_make_status(3, spot_id=2))
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        ids = resolver.resolve(event)
        assert len(ids) >= 1
        values = [p.value for p in ids]
        assert 1 in values
        assert 2 in values
        assert 3 in values

    def test_resolve_deduplicates_recipients_when_same_player_in_multiple_sources(
        self, resolver, status_repo
    ):
        """同一プレイヤーが複数ソース（本人＋同一スポット）で含まれる場合、重複せず1回のみ配信先に含まれる"""
        # プレイヤー1が target_spot (2) にいる。かつ player_id_value=1（本人）なので二重に add されうる
        status_repo.save(_make_status(1, spot_id=2))
        status_repo.save(_make_status(2, spot_id=2))
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        ids = resolver.resolve(event)
        values = [p.value for p in ids]
        assert 1 in values
        assert 2 in values
        assert values.count(1) == 1
        assert values.count(2) == 1
        assert len(ids) == 2

    def test_resolve_gateway_triggered_no_player_id_value_only_target_spot_players(
        self, resolver, status_repo
    ):
        """player_id_value が None のときは target_spot のプレイヤーのみ"""
        status_repo.save(_make_status(2, spot_id=2))
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(99),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=None,
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 2

    def test_resolve_player_level_up_returns_aggregate_player(self, resolver, status_repo):
        """PlayerLevelUpEvent: aggregate_id のプレイヤーが配信先"""
        status_repo.save(_make_status(1))
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 1

    def test_resolve_player_gold_earned_returns_aggregate_player(self, resolver, status_repo):
        """PlayerGoldEarnedEvent: aggregate_id のプレイヤーが配信先"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(5),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 5

    def test_resolve_item_taken_from_chest_returns_player_id_value(self, resolver):
        """ItemTakenFromChestEvent: player_id_value が配信先"""
        event = ItemTakenFromChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="PhysicalMap",
            spot_id=SpotId(1),
            chest_id=WorldObjectId(10),
            actor_id=WorldObjectId(1),
            item_instance_id=ItemInstanceId(100),
            player_id_value=7,
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 7

    def test_resolve_spot_weather_changed_returns_players_at_spot(self, resolver, status_repo):
        """SpotWeatherChangedEvent: その spot にいるプレイヤーが配信先"""
        status_repo.save(_make_status(1, spot_id=3))
        status_repo.save(_make_status(2, spot_id=3))
        event = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(3),
            aggregate_type="Weather",
            spot_id=SpotId(3),
            old_weather_state=WeatherState.clear(),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
        )
        ids = resolver.resolve(event)
        assert len(ids) == 2
        assert {p.value for p in ids} == {1, 2}

    def test_resolve_item_added_to_inventory_returns_aggregate_player(self, resolver):
        """ItemAddedToInventoryEvent: aggregate_id が配信先"""
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(3),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId(1),
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 3

    def test_resolve_unknown_event_returns_empty_list(self, resolver):
        """観測対象外・未知のイベントは空リスト"""
        class UnknownEvent:
            pass
        ids = resolver.resolve(UnknownEvent())
        assert ids == []

    def test_resolve_with_empty_strategies_returns_empty_list(self):
        """戦略が空の Resolver はどのイベントでも空リストを返す"""
        resolver = ObservationRecipientResolver(strategies=[])
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        ids = resolver.resolve(event)
        assert ids == []

    def test_resolve_player_location_changed_includes_self_and_players_at_new_spot(
        self, resolver, status_repo
    ):
        """PlayerLocationChangedEvent: 本人と new_spot_id にいるプレイヤー"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )
        ids = resolver.resolve(event)
        values = [p.value for p in ids]
        assert 1 in values
        assert 2 in values

    # --- WorldObjectId → PlayerId 解決（ResourceHarvested / LocationExited / WorldObjectInteracted）---

    def test_resolve_resource_harvested_returns_player_when_actor_is_on_map(
        self, resolver, physical_map_repo
    ):
        """ResourceHarvestedEvent: actor_id がマップ上のプレイヤーならそのプレイヤーが配信先"""
        player_oid = WorldObjectId.create(1)
        spot_id = 10
        physical_map_repo.save(
            _make_minimal_map(spot_id, [_create_player_object(1)])
        )
        event = ResourceHarvestedEvent.create(
            aggregate_id=WorldObjectId(999),
            aggregate_type="WorldObject",
            object_id=WorldObjectId(999),
            actor_id=player_oid,
            loot_table_id=LootTableId(1),
            obtained_items=[],
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 1

    def test_resolve_resource_harvested_returns_empty_when_actor_not_on_map(
        self, resolver
    ):
        """ResourceHarvestedEvent: actor_id がどのマップにもいなければ配信先なし"""
        event = ResourceHarvestedEvent.create(
            aggregate_id=WorldObjectId(999),
            aggregate_type="WorldObject",
            object_id=WorldObjectId(999),
            actor_id=WorldObjectId(99999),
            loot_table_id=LootTableId(1),
            obtained_items=[],
        )
        ids = resolver.resolve(event)
        assert ids == []

    def test_resolve_location_exited_returns_player_when_object_is_player_on_map(
        self, resolver, physical_map_repo
    ):
        """LocationExitedEvent: object_id がマップ上のプレイヤーならそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(5, [_create_player_object(3)])
        )
        event = LocationExitedEvent.create(
            aggregate_id=LocationAreaId(1),
            aggregate_type="LocationArea",
            location_id=LocationAreaId(1),
            spot_id=SpotId(5),
            object_id=WorldObjectId.create(3),
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 3

    def test_resolve_location_exited_returns_empty_when_object_not_on_map(
        self, resolver
    ):
        """LocationExitedEvent: object_id がマップにいなければ配信先なし"""
        event = LocationExitedEvent.create(
            aggregate_id=LocationAreaId(1),
            aggregate_type="LocationArea",
            location_id=LocationAreaId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(88888),
        )
        ids = resolver.resolve(event)
        assert ids == []

    def test_resolve_world_object_interacted_returns_player_when_actor_is_on_map(
        self, resolver, physical_map_repo
    ):
        """WorldObjectInteractedEvent: actor_id がマップ上のプレイヤーならそのプレイヤーが配信先"""
        physical_map_repo.save(
            _make_minimal_map(7, [_create_player_object(2)])
        )
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(100),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId.create(2),
            target_id=WorldObjectId(100),
            interaction_type=InteractionTypeEnum.OPEN_CHEST,
            data={},
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 2

    def test_resolve_world_object_interacted_returns_empty_when_actor_not_on_map(
        self, resolver
    ):
        """WorldObjectInteractedEvent: actor_id がマップにいなければ配信先なし"""
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(100),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(77777),
            target_id=WorldObjectId(100),
            interaction_type=InteractionTypeEnum.OPEN_CHEST,
            data={},
        )
        ids = resolver.resolve(event)
        assert ids == []

    # --- 例外ケース（リポジトリが例外を投げた場合は伝播）---

    def test_resolve_when_player_status_find_all_raises_propagates(
        self, physical_map_repo, data_store
    ):
        """PlayerStatusRepository.find_all が例外を投げた場合、その例外が伝播する"""
        status_repo = MagicMock()
        status_repo.find_all.side_effect = RuntimeError("find_all failed")
        world_object_resolver = WorldObjectToPlayerResolver(physical_map_repo)
        default_strategy = DefaultRecipientStrategy(
            player_status_repository=status_repo,
            world_object_to_player_resolver=world_object_resolver,
        )
        resolver = ObservationRecipientResolver(strategies=[default_strategy])
        event = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Weather",
            spot_id=SpotId(1),
            old_weather_state=WeatherState.clear(),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
        )
        with pytest.raises(RuntimeError, match="find_all failed"):
            resolver.resolve(event)


class TestDefaultRecipientStrategy:
    """DefaultRecipientStrategy の単体テスト（supports / resolve）"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def world_object_resolver(self, physical_map_repo):
        return WorldObjectToPlayerResolver(physical_map_repo)

    @pytest.fixture
    def strategy(self, status_repo, world_object_resolver):
        return DefaultRecipientStrategy(
            player_status_repository=status_repo,
            world_object_to_player_resolver=world_object_resolver,
        )

    def test_supports_gateway_triggered_event(self, strategy):
        """GatewayTriggeredEvent を supports する"""
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        assert strategy.supports(event) is True

    def test_supports_player_level_up_event(self, strategy):
        """PlayerLevelUpEvent を supports する"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは supports が False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False

    def test_resolve_player_level_up_returns_aggregate_id(self, strategy):
        """PlayerLevelUpEvent の resolve が aggregate_id を返す"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(7),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        ids = strategy.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 7


class TestWorldObjectToPlayerResolver:
    """WorldObjectToPlayerResolver の単体テスト（正常・対象不在・例外）"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def resolver(self, physical_map_repo):
        return WorldObjectToPlayerResolver(physical_map_repo)

    def test_resolve_player_id_returns_player_when_object_on_map(
        self, resolver, physical_map_repo
    ):
        """マップ上にプレイヤーオブジェクトがある場合その PlayerId を返す（正常系）"""
        physical_map_repo.save(
            _make_minimal_map(10, [_create_player_object(3)])
        )
        pid = resolver.resolve_player_id(WorldObjectId.create(3))
        assert pid is not None
        assert pid.value == 3

    def test_resolve_player_id_returns_none_when_object_not_on_any_map(
        self, resolver
    ):
        """どのマップにも存在しない object_id の場合は None（境界）"""
        pid = resolver.resolve_player_id(WorldObjectId(99999))
        assert pid is None
