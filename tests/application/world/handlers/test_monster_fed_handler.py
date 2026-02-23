"""MonsterFedEvent を購読し record_feed を実行する MonsterFedHandler のテスト。"""

import pytest
from ai_rpg_world.application.world.handlers.monster_fed_handler import MonsterFedHandler
from ai_rpg_world.domain.monster.event.monster_events import MonsterFedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)


def _template_with_feed(
    hunger_decrease_on_feed: float = 0.3,
    starvation_ticks: int = 50,
) -> MonsterTemplate:
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
        hunger_decrease_on_feed=hunger_decrease_on_feed,
        hunger_starvation_threshold=0.9,
        starvation_ticks=starvation_ticks,
    )


class TestMonsterFedHandler:
    """MonsterFedHandler の正常・スキップ・境界ケース"""

    @pytest.fixture
    def monster_repo(self):
        return InMemoryMonsterAggregateRepository()

    @pytest.fixture
    def handler(self, monster_repo):
        return MonsterFedHandler(monster_repository=monster_repo)

    def test_record_feed_reduces_hunger(self, handler, monster_repo):
        """正常: 採食イベントで飢餓が減少すること"""
        template = _template_with_feed(hunger_decrease_on_feed=0.4)
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=100, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            monster_id=MonsterId(1),
            template=template,
            world_object_id=WorldObjectId(100),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.8)
        monster_repo.save(monster)

        event = MonsterFedEvent.create(
            aggregate_id=WorldObjectId(200),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            target_coordinate=Coordinate(1, 0, 0),
        )
        handler.handle(event)

        after = monster_repo.find_by_world_object_id(WorldObjectId(100))
        assert after is not None
        assert after.hunger == pytest.approx(0.4)  # 0.8 - 0.4

    def test_skip_when_monster_not_found(self, handler):
        """actor_id に該当するモンスターがいないときはスキップ（例外にならない）"""
        event = MonsterFedEvent.create(
            aggregate_id=WorldObjectId(999),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(999),
            target_id=WorldObjectId(998),
            target_coordinate=Coordinate(0, 0, 0),
        )
        repo = InMemoryMonsterAggregateRepository()
        h = MonsterFedHandler(monster_repository=repo)
        h.handle(event)  # 例外なし

    def test_skip_when_starvation_disabled(self, handler, monster_repo):
        """starvation_ticks が 0 のときは record_feed が何もしない（飢餓変化なし）"""
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.common.value_object import WorldTick
        t_disabled = _template_with_feed(hunger_decrease_on_feed=0.4, starvation_ticks=0)
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=101, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            monster_id=MonsterId(2),
            template=t_disabled,
            world_object_id=WorldObjectId(101),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.5)
        monster_repo.save(monster)

        event = MonsterFedEvent.create(
            aggregate_id=WorldObjectId(201),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(101),
            target_id=WorldObjectId(201),
            target_coordinate=Coordinate(2, 0, 0),
        )
        handler.handle(event)

        after = monster_repo.find_by_world_object_id(WorldObjectId(101))
        assert after is not None
        assert after.hunger == pytest.approx(0.5)  # 変化なし

    def test_remember_feed_updates_feed_memory(self, handler, monster_repo):
        """正常: 採食時に餌場記憶が更新されること"""
        template = _template_with_feed(hunger_decrease_on_feed=0.2)
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=200, normal_capacity=5, awakened_capacity=5
        )
        monster = MonsterAggregate.create(
            monster_id=MonsterId(3),
            template=template,
            world_object_id=WorldObjectId(200),
            skill_loadout=loadout,
        )
        monster.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0), initial_hunger=0.6)
        monster_repo.save(monster)

        feed_coord = Coordinate(3, 4, 0)
        event = MonsterFedEvent.create(
            aggregate_id=WorldObjectId(300),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(200),
            target_id=WorldObjectId(300),
            target_coordinate=feed_coord,
        )
        handler.handle(event)

        after = monster_repo.find_by_world_object_id(WorldObjectId(200))
        assert after is not None
        assert len(after.behavior_last_known_feed) == 1
        assert after.behavior_last_known_feed[0].object_id == WorldObjectId(300)
        assert after.behavior_last_known_feed[0].coordinate == feed_coord
