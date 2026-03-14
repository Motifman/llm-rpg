from ai_rpg_world.application.world.services.monster_feed_query_service import (
    MonsterFeedQueryService,
)
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
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
    HarvestableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
    InMemoryLootTableRepository,
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


def _monster(template: MonsterTemplate) -> MonsterAggregate:
    loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), owner_id=1, normal_capacity=5, awakened_capacity=5)
    monster = MonsterAggregate.create(
        MonsterId(1),
        template,
        WorldObjectId(1),
        skill_loadout=loadout,
    )
    monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.8)
    return monster


def _map_with_tiles() -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(3)
        for y in range(3)
    ]
    return PhysicalMapAggregate.create(SpotId(1), tiles)


class TestMonsterFeedQueryService:
    def test_spot_has_feed_for_monster_returns_true_for_preferred_feed(self):
        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        physical_map.add_object(
            WorldObject(
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
        )

        assert service.spot_has_feed_for_monster(
            physical_map,
            _monster(_template_with_feed_preference()),
            WorldTick(0),
        ) is True

    def test_spot_has_feed_for_monster_returns_false_when_quantity_zero(self):
        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        physical_map.add_object(
            WorldObject(
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
        )

        assert service.spot_has_feed_for_monster(
            physical_map,
            _monster(_template_with_feed_preference()),
            WorldTick(0),
        ) is False

    def test_build_foraging_result_selects_visible_nearest_feed(self):
        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        near_feed = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=2,
            ),
        )
        far_feed = WorldObject(
            object_id=WorldObjectId(101),
            coordinate=Coordinate(2, 2, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=2,
            ),
        )
        physical_map.add_object(near_feed)
        physical_map.add_object(far_feed)
        monster = _monster(_template_with_feed_preference())

        result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert near_feed in result.visible_feed
        assert far_feed in result.visible_feed
        assert result.selected_feed_target == near_feed

    def test_spot_has_feed_for_monster_returns_false_when_loot_table_repository_is_none(self):
        """loot_table_repository が None のとき spot_has_feed_for_monster は False を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()
        physical_map.add_object(
            WorldObject(
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
        )

        assert service.spot_has_feed_for_monster(
            physical_map,
            _monster(_template_with_feed_preference()),
            WorldTick(0),
        ) is False

    def test_build_foraging_result_returns_empty_when_loot_table_repository_is_none(self):
        """loot_table_repository が None のとき build_foraging_result は空の結果を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        physical_map.add_object(
            WorldObject(
                object_id=WorldObjectId(100),
                coordinate=Coordinate(1, 0, 0),
                object_type=ObjectTypeEnum.RESOURCE,
                is_blocking=False,
                component=HarvestableComponent(
                    loot_table_id=LootTableId.create(1),
                    max_quantity=2,
                    initial_quantity=2,
                ),
            )
        )
        monster = _monster(_template_with_feed_preference())

        result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert result.visible_feed == []
        assert result.selected_feed_target is None

    def test_build_foraging_result_skips_object_not_found_in_memory_loop(self):
        """memory ループで ObjectNotFoundException が発生した場合、そのエントリをスキップする"""
        from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        feed_obj = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=2,
            ),
        )
        physical_map.add_object(feed_obj)
        monster = _monster(_template_with_feed_preference())
        monster.remember_feed(WorldObjectId(999), Coordinate(5, 5, 0))

        result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert result.visible_feed == [feed_obj]
        assert result.selected_feed_target == feed_obj

    def test_spot_has_feed_for_monster_returns_false_when_loot_table_repository_is_none(self):
        """loot_table_repository が None のとき spot_has_feed_for_monster は False を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()

        assert service.spot_has_feed_for_monster(
            physical_map,
            _monster(_template_with_feed_preference()),
            WorldTick(0),
        ) is False

    def test_build_foraging_result_returns_empty_when_loot_table_repository_is_none(self):
        """loot_table_repository が None のとき build_foraging_result は空の結果を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        physical_map.add_object(
            WorldObject(
                object_id=WorldObjectId(100),
                coordinate=Coordinate(1, 0, 0),
                object_type=ObjectTypeEnum.RESOURCE,
                is_blocking=False,
                component=HarvestableComponent(
                    loot_table_id=LootTableId.create(1),
                    max_quantity=2,
                    initial_quantity=2,
                ),
            )
        )
        monster = _monster(_template_with_feed_preference())

        result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert result.visible_feed == []
        assert result.selected_feed_target is None

    def test_build_foraging_result_skips_object_not_found_in_memory_loop(self):
        """memory ループで ObjectNotFoundException が発生した場合そのエントリをスキップして続行する"""
        from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        valid_feed = WorldObject(
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
        physical_map.add_object(valid_feed)
        monster = _monster(_template_with_feed_preference())
        monster.remember_feed(
            WorldObjectId(999),
            Coordinate(0, 0, 0),
        )
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)

        result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert len(result.visible_feed) == 1
        assert result.visible_feed[0] == valid_feed

    def test_spot_has_feed_for_monster_returns_false_when_loot_table_repository_is_none(
        self,
    ):
        """loot_table_repository が None のとき spot_has_feed_for_monster は False を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()

        assert (
            service.spot_has_feed_for_monster(
                physical_map,
                _monster(_template_with_feed_preference()),
                WorldTick(0),
            )
            is False
        )

    def test_build_foraging_result_returns_empty_when_loot_table_repository_is_none(
        self,
    ):
        """loot_table_repository が None のとき build_foraging_result は空の結果を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)

        result = service.build_foraging_result(
            actor, physical_map, _monster(_template_with_feed_preference()), WorldTick(0)
        )

        assert result.visible_feed == []
        assert result.selected_feed_target is None

    def test_build_foraging_result_skips_object_not_found_in_memory_loop(self):
        """memory ループで ObjectNotFoundException が発生した場合スキップして次へ進む"""
        from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        monster = _monster(_template_with_feed_preference())
        monster.behavior_last_known_feed = [
            type("FeedMemory", (), {"object_id": WorldObjectId(999), "coordinate": Coordinate(2, 2, 0)})()
        ]
        physical_map.get_object = lambda obj_id: (_ for _ in ()).throw(
            ObjectNotFoundException(obj_id)
        )

        result = service.build_foraging_result(
            actor, physical_map, monster, WorldTick(0)
        )

        assert result.selected_feed_target is None

    def test_spot_has_feed_for_monster_returns_false_when_loot_table_repository_is_none(self):
        """loot_table_repository が None の場合、spot_has_feed_for_monster は False を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()

        assert service.spot_has_feed_for_monster(
            physical_map,
            _monster(_template_with_feed_preference()),
            WorldTick(0),
        ) is False

    def test_build_foraging_result_returns_empty_when_loot_table_repository_is_none(self):
        """loot_table_repository が None の場合、build_foraging_result は空の結果を返す"""
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)

        result = service.build_foraging_result(
            actor, physical_map, _monster(_template_with_feed_preference()), WorldTick(0)
        )

        assert result.visible_feed == []
        assert result.selected_feed_target is None

    def test_build_foraging_result_skips_object_not_found_in_memory_loop(self):
        """memory ループで ObjectNotFoundException が発生した場合、そのエントリはスキップされ次へ進む"""
        from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        monster = _monster(_template_with_feed_preference())
        monster.remember_feed(WorldObjectId(999), Coordinate(5, 5, 0))

        with mock.patch.object(
            physical_map, "get_object", side_effect=ObjectNotFoundException(WorldObjectId(999))
        ):
            result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert result.selected_feed_target is None

    def test_spot_has_feed_for_monster_returns_false_when_loot_table_repository_is_none(self):
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()

        assert service.spot_has_feed_for_monster(
            physical_map,
            _monster(_template_with_feed_preference()),
            WorldTick(0),
        ) is False

    def test_build_foraging_result_returns_empty_when_loot_table_repository_is_none(self):
        service = MonsterFeedQueryService(loot_table_repository=None)
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)

        result = service.build_foraging_result(
            actor, physical_map, _monster(_template_with_feed_preference()), WorldTick(0)
        )

        assert result.visible_feed == []
        assert result.selected_feed_target is None

    def test_build_foraging_result_skips_object_not_found_in_memory_loop(self):
        """memory ループで ObjectNotFoundException が発生した場合、そのエントリをスキップして続行する"""
        from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

        loot_table = LootTableAggregate(
            LootTableId.create(1),
            [LootEntry(ItemSpecId(1), 1)],
            name="Grass",
        )
        service = MonsterFeedQueryService(
            InMemoryLootTableRepository(initial_data={LootTableId.create(1): loot_table})
        )
        physical_map = _map_with_tiles()
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        physical_map.add_object(actor)
        feed_obj = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(
                loot_table_id=LootTableId.create(1),
                max_quantity=2,
                initial_quantity=2,
            ),
        )
        physical_map.add_object(feed_obj)
        monster = _monster(_template_with_feed_preference())
        monster.remember_feed(WorldObjectId(999), Coordinate(5, 5, 0))

        result = service.build_foraging_result(actor, physical_map, monster, WorldTick(0))

        assert result.visible_feed == [feed_obj]
        assert result.selected_feed_target == feed_obj
