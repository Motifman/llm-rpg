"""飢餓時のスポット転移（移住）と「スポットに餌があるか」判定のテスト。"""

import pytest
from ai_rpg_world.application.world.services.world_simulation_service import (
    WorldSimulationApplicationService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.aggregate.world_map_aggregate import WorldMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    HarvestableComponent,
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.connection import Connection
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate, LootEntry
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
    InMemoryLootTableRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_world_map_repository import (
    InMemoryWorldMapRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _template_with_feed_preference(
    forage_threshold: float = 0.5,
    preferred_feed_item_spec_ids: set = None,
) -> MonsterTemplate:
    preferred = preferred_feed_item_spec_ids or {ItemSpecId(1)}
    return MonsterTemplate(
        template_id=MonsterTemplateId(1),
        name="Herbivore",
        base_stats=BaseStats(50, 0, 5, 3, 4, 0, 0),
        reward_info=RewardInfo(5, 2, 1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="Eats plants.",
        hunger_increase_per_tick=0.01,
        hunger_decrease_on_feed=0.3,
        hunger_starvation_threshold=0.9,
        starvation_ticks=50,
        forage_threshold=forage_threshold,
        preferred_feed_item_spec_ids=preferred,
    )


class TestSpotHasFeedForMonster:
    """_spot_has_feed_for_monster の正常・境界・例外ケース"""

    @pytest.fixture
    def loot_table_repo(self):
        lt = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        repo = InMemoryLootTableRepository(
            initial_data={LootTableId.create(1): lt}
        )
        return repo

    @pytest.fixture
    def service_minimal(self, loot_table_repo):
        """_spot_has_feed_for_monster 用の最小サービス（他は None でよい）"""
        return WorldSimulationApplicationService(
            time_provider=None,
            physical_map_repository=InMemoryPhysicalMapRepository(),
            weather_zone_repository=None,
            player_status_repository=None,
            hit_box_repository=None,
            behavior_service=None,
            weather_config_service=None,
            unit_of_work=None,
            monster_repository=None,
            skill_loadout_repository=None,
            monster_skill_execution_domain_service=None,
            hit_box_factory=None,
            monster_action_resolver_factory=None,
            loot_table_repository=loot_table_repo,
        )

    def test_returns_true_when_spot_has_feed(
        self, service_minimal, loot_table_repo
    ):
        """正常: スポットに嗜好に合う餌が1つ以上あれば True"""
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(3) for y in range(3)
        ]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        harvestable = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(1, 1, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=2,
            ),
        )
        pmap.add_object(harvestable)
        template = _template_with_feed_preference(forage_threshold=0.5)
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.8)
        result = service_minimal._spot_has_feed_for_monster(
            pmap, monster, WorldTick(0)
        )
        assert result is True

    def test_returns_false_when_no_harvestable(self, service_minimal):
        """スポットに Harvestable がなければ False"""
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(3) for y in range(3)
        ]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        template = _template_with_feed_preference()
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.8)
        result = service_minimal._spot_has_feed_for_monster(
            pmap, monster, WorldTick(0)
        )
        assert result is False

    def test_returns_false_when_preferred_empty(self, service_minimal, loot_table_repo):
        """嗜好（preferred_feed_item_spec_ids）が空なら False"""
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(3) for y in range(3)
        ]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        harvestable = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(1, 1, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=2,
            ),
        )
        pmap.add_object(harvestable)
        # 嗜好が LootTable の item_spec_id と一致しない（餌とみなされない）
        template = _template_with_feed_preference(
            forage_threshold=0.5,
            preferred_feed_item_spec_ids={ItemSpecId(999)},
        )
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.8)
        result = service_minimal._spot_has_feed_for_monster(
            pmap, monster, WorldTick(0)
        )
        assert result is False

    def test_returns_false_when_quantity_zero(self, service_minimal, loot_table_repo):
        """残量 0 の Harvestable だけなら False"""
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(3) for y in range(3)
        ]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        harvestable = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(1, 1, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=0,
            ),
        )
        pmap.add_object(harvestable)
        template = _template_with_feed_preference()
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.8)
        result = service_minimal._spot_has_feed_for_monster(
            pmap, monster, WorldTick(0)
        )
        assert result is False


class TestProcessHungerMigrationForSpot:
    """_process_hunger_migration_for_spot の正常・スキップケース"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        if hasattr(ds, "clear_all"):
            ds.clear_all()
        return ds

    @pytest.fixture
    def spot1_id(self):
        return SpotId(1)

    @pytest.fixture
    def spot2_id(self):
        return SpotId(2)

    @pytest.fixture
    def world_map(self, spot1_id, spot2_id):
        spots = [
            Spot(spot1_id, "Forest", "No feed", SpotCategoryEnum.OTHER),
            Spot(spot2_id, "Town", "Has feed", SpotCategoryEnum.OTHER),
        ]
        conn = Connection(source_id=spot1_id, destination_id=spot2_id)
        wm = WorldMapAggregate.create(WorldId(1), spots=spots, connections=[conn])
        return wm

    @pytest.fixture
    def map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def monster_repo(self, data_store):
        return InMemoryMonsterAggregateRepository(data_store=data_store)

    @pytest.fixture
    def world_map_repo(self, data_store, world_map):
        repo = InMemoryWorldMapRepository(data_store=data_store)
        repo.save(world_map)
        return repo

    @pytest.fixture
    def map1_with_gateway(self, spot1_id, spot2_id, map_repo):
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(5) for y in range(5)
        ]
        pmap = PhysicalMapAggregate.create(spot1_id, tiles)
        gw = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=PointArea(Coordinate(4, 4, 0)),
            target_spot_id=spot2_id,
            landing_coordinate=Coordinate(0, 0, 0),
        )
        pmap.add_gateway(gw)
        map_repo.save(pmap)
        return pmap

    @pytest.fixture
    def map2(self, spot2_id, map_repo):
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(5) for y in range(5)
        ]
        pmap = PhysicalMapAggregate.create(spot2_id, tiles)
        map_repo.save(pmap)
        return pmap

    @pytest.fixture
    def migrant_monster_on_map1(
        self, spot1_id, monster_repo, map_repo, map1_with_gateway
    ):
        template = _template_with_feed_preference(forage_threshold=0.5)
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1000, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1000),
            skill_loadout=loadout,
        )
        monster.spawn(
            Coordinate(2, 2, 0), spot1_id, WorldTick(0), initial_hunger=0.95
        )
        monster_repo.save(monster)
        actor = WorldObject(
            object_id=WorldObjectId(1000),
            coordinate=Coordinate(2, 2, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=True,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        map1_with_gateway.add_object(actor)
        map_repo.save(map1_with_gateway)
        return monster

    def test_migrates_highest_hunger_monster_when_spot_has_no_feed(
        self,
        data_store,
        spot1_id,
        spot2_id,
        map_repo,
        monster_repo,
        world_map_repo,
        map1_with_gateway,
        map2,
        migrant_monster_on_map1,
    ):
        """正常: スポットに餌がなく接続スポットがあれば飢餓が最も高い1体が移住する"""
        uow = InMemoryUnitOfWork(
            unit_of_work_factory=lambda: None,
            data_store=data_store,
        )
        service = WorldSimulationApplicationService(
            time_provider=None,
            physical_map_repository=map_repo,
            weather_zone_repository=None,
            player_status_repository=None,
            hit_box_repository=None,
            behavior_service=None,
            weather_config_service=None,
            unit_of_work=uow,
            monster_repository=monster_repo,
            skill_loadout_repository=None,
            monster_skill_execution_domain_service=None,
            hit_box_factory=None,
            monster_action_resolver_factory=None,
            loot_table_repository=InMemoryLootTableRepository(),
            world_map_repository=world_map_repo,
            map_transition_service=MapTransitionService(),
        )
        physical_map = map_repo.find_by_spot_id(spot1_id)
        assert physical_map is not None
        with uow:
            service._process_hunger_migration_for_spot(
                physical_map, WorldTick(1), {spot1_id}
            )
        after = monster_repo.find_by_world_object_id(WorldObjectId(1000))
        assert after is not None
        assert after.spot_id == spot2_id
        assert after.coordinate == Coordinate(0, 0, 0)
        map1_after = map_repo.find_by_spot_id(spot1_id)
        map2_after = map_repo.find_by_spot_id(spot2_id)
        with pytest.raises(ObjectNotFoundException):
            map1_after.get_object(WorldObjectId(1000))
        assert map2_after.get_object(WorldObjectId(1000)) is not None

    def test_does_nothing_when_connected_spots_empty(
        self,
        data_store,
        spot1_id,
        map_repo,
        monster_repo,
        map1_with_gateway,
        migrant_monster_on_map1,
    ):
        """接続スポットが0なら移住しない"""
        world_map_single = WorldMapAggregate.create(
            WorldId(1),
            spots=[Spot(spot1_id, "Alone", "No connections", SpotCategoryEnum.OTHER)],
            connections=[],
        )
        world_map_repo = InMemoryWorldMapRepository(data_store=data_store)
        world_map_repo.save(world_map_single)
        uow = InMemoryUnitOfWork(
            unit_of_work_factory=lambda: None,
            data_store=data_store,
        )
        service = WorldSimulationApplicationService(
            time_provider=None,
            physical_map_repository=map_repo,
            weather_zone_repository=None,
            player_status_repository=None,
            hit_box_repository=None,
            behavior_service=None,
            weather_config_service=None,
            unit_of_work=uow,
            monster_repository=monster_repo,
            skill_loadout_repository=None,
            monster_skill_execution_domain_service=None,
            hit_box_factory=None,
            monster_action_resolver_factory=None,
            loot_table_repository=InMemoryLootTableRepository(),
            world_map_repository=world_map_repo,
            map_transition_service=MapTransitionService(),
        )
        physical_map = map_repo.find_by_spot_id(spot1_id)
        with uow:
            service._process_hunger_migration_for_spot(
                physical_map, WorldTick(1), {spot1_id}
            )
        after = monster_repo.find_by_world_object_id(WorldObjectId(1000))
        assert after is not None
        assert after.spot_id == spot1_id
        assert after.coordinate == Coordinate(2, 2, 0)
