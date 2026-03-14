"""飢餓時のスポット転移（移住）のテスト。"""

import unittest.mock as mock

import pytest
from ai_rpg_world.application.world.services.monster_feed_query_service import (
    MonsterFeedQueryService,
)
from ai_rpg_world.application.world.services.monster_lifecycle_survival_coordinator import (
    MonsterLifecycleSurvivalCoordinator,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootEntry, LootTableAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
    InMemoryLootTableRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


def _template_with_feed_preference(
    forage_threshold: float = 0.5,
    preferred_feed_item_spec_ids: set | None = None,
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


class TestApplyHungerMigrationForSpot:
    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def loot_table_repo(self):
        lt = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        return InMemoryLootTableRepository(initial_data={LootTableId.create(1): lt})

    @pytest.fixture
    def spot1_id(self):
        return SpotId(1)

    @pytest.fixture
    def spot2_id(self):
        return SpotId(2)

    @pytest.fixture
    def map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def monster_repo(self, data_store):
        return InMemoryMonsterAggregateRepository(data_store=data_store)

    @pytest.fixture
    def map1_with_gateway(self, spot1_id, spot2_id, map_repo):
        tiles = [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(5)
            for y in range(5)
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
            for x in range(5)
            for y in range(5)
        ]
        pmap = PhysicalMapAggregate.create(spot2_id, tiles)
        map_repo.save(pmap)
        return pmap

    @pytest.fixture
    def migrant_monster_on_map1(
        self,
        spot1_id,
        monster_repo,
        map_repo,
        map1_with_gateway,
    ):
        template = _template_with_feed_preference(forage_threshold=0.5)
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            owner_id=1000,
            normal_capacity=5,
            awakened_capacity=5,
        )
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1000),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(2, 2, 0), spot1_id, WorldTick(0), initial_hunger=0.95)
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

    def _build_coordinator(
        self,
        *,
        data_store,
        map_repo,
        monster_repo,
        loot_table_repo,
        connected_spots_provider,
        map_transition_service,
    ) -> MonsterLifecycleSurvivalCoordinator:
        uow = InMemoryUnitOfWork(unit_of_work_factory=lambda: None, data_store=data_store)
        feed_query_service = MonsterFeedQueryService(loot_table_repo)
        return MonsterLifecycleSurvivalCoordinator(
            monster_repository=monster_repo,
            physical_map_repository=map_repo,
            connected_spots_provider_getter=lambda: connected_spots_provider,
            map_transition_service_getter=lambda: map_transition_service,
            hunger_migration_policy=mock.Mock(wraps=__import__(
                "ai_rpg_world.application.world.services.hunger_migration_policy",
                fromlist=["HungerMigrationPolicy"],
            ).HungerMigrationPolicy()),
            spot_has_feed_for_monster=feed_query_service.spot_has_feed_for_monster,
            unit_of_work=uow,
            logger=mock.Mock(),
        )

    def test_migrates_highest_hunger_monster_when_spot_has_no_feed(
        self,
        data_store,
        spot1_id,
        spot2_id,
        map_repo,
        monster_repo,
        loot_table_repo,
        map1_with_gateway,
        map2,
        migrant_monster_on_map1,
    ):
        coordinator = self._build_coordinator(
            data_store=data_store,
            map_repo=map_repo,
            monster_repo=monster_repo,
            loot_table_repo=loot_table_repo,
            connected_spots_provider=mock.Mock(
                get_connected_spots=mock.Mock(return_value=[spot2_id])
            ),
            map_transition_service=MapTransitionService(),
        )

        physical_map = map_repo.find_by_spot_id(spot1_id)
        migrated_actor_id = coordinator.apply_hunger_migration_for_spot(
            physical_map,
            WorldTick(1),
        )

        assert migrated_actor_id == WorldObjectId(1000)
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
        loot_table_repo,
        map1_with_gateway,
        migrant_monster_on_map1,
    ):
        coordinator = self._build_coordinator(
            data_store=data_store,
            map_repo=map_repo,
            monster_repo=monster_repo,
            loot_table_repo=loot_table_repo,
            connected_spots_provider=mock.Mock(
                get_connected_spots=mock.Mock(return_value=[])
            ),
            map_transition_service=MapTransitionService(),
        )

        physical_map = map_repo.find_by_spot_id(spot1_id)
        migrated_actor_id = coordinator.apply_hunger_migration_for_spot(
            physical_map,
            WorldTick(1),
        )

        assert migrated_actor_id is None
        after = monster_repo.find_by_world_object_id(WorldObjectId(1000))
        assert after is not None
        assert after.spot_id == spot1_id
        assert after.coordinate == Coordinate(2, 2, 0)

    def test_skips_migration_when_transition_raises_domain_exception(
        self,
        data_store,
        spot1_id,
        map_repo,
        monster_repo,
        loot_table_repo,
        map1_with_gateway,
        map2,
        migrant_monster_on_map1,
    ):
        class FailingMapTransitionService(MapTransitionService):
            def transition_object(self, from_map, to_map, object_id, landing_coordinate):
                raise DomainException("Transition blocked for test")

        coordinator = self._build_coordinator(
            data_store=data_store,
            map_repo=map_repo,
            monster_repo=monster_repo,
            loot_table_repo=loot_table_repo,
            connected_spots_provider=mock.Mock(
                get_connected_spots=mock.Mock(return_value=[SpotId(2)])
            ),
            map_transition_service=FailingMapTransitionService(),
        )

        physical_map = map_repo.find_by_spot_id(spot1_id)
        migrated_actor_id = coordinator.apply_hunger_migration_for_spot(
            physical_map,
            WorldTick(1),
        )

        assert migrated_actor_id is None
        after = monster_repo.find_by_world_object_id(WorldObjectId(1000))
        assert after is not None
        assert after.spot_id == spot1_id
        assert after.coordinate == Coordinate(2, 2, 0)

    def test_uses_hunger_migration_policy_selection_before_applying_transition(
        self,
        data_store,
        spot1_id,
        map_repo,
        monster_repo,
        loot_table_repo,
        map1_with_gateway,
        map2,
        migrant_monster_on_map1,
    ):
        coordinator = self._build_coordinator(
            data_store=data_store,
            map_repo=map_repo,
            monster_repo=monster_repo,
            loot_table_repo=loot_table_repo,
            connected_spots_provider=mock.Mock(
                get_connected_spots=mock.Mock(return_value=[SpotId(2)])
            ),
            map_transition_service=MapTransitionService(),
        )

        physical_map = map_repo.find_by_spot_id(spot1_id)
        coordinator.apply_hunger_migration_for_spot(physical_map, WorldTick(1))

        coordinator._hunger_migration_policy.select_migrant.assert_called_once()
