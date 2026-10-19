"""死亡イベントが、場所情報に依存せず討伐者の飢餓だけを更新することを保証する。"""

import pytest

from ai_rpg_world.application.world.handlers.monster_death_hunger_handler import MonsterDeathHungerHandler
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)


class _FakeUow:
    pass


def _create_killer_and_prey(monster_repo, prey_race):
    killer_template = MonsterTemplate(
        template_id=MonsterTemplateId(1),
        name="Wolf",
        base_stats=BaseStats(100, 20, 15, 10, 12, 0.05, 0.05),
        reward_info=RewardInfo(20, 10, 1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A wolf.",
        prey_races=frozenset({prey_race}),
        hunger_increase_per_tick=0.01,
        hunger_decrease_on_prey_kill=0.4,
        hunger_starvation_threshold=0.9,
        starvation_ticks=50,
    )
    dead_template = MonsterTemplate(
        template_id=MonsterTemplateId(2),
        name="Goblin",
        base_stats=BaseStats(30, 0, 5, 2, 4, 0, 0),
        reward_info=RewardInfo(5, 2, None),
        respawn_info=RespawnInfo(50, True),
        race=Race.GOBLIN,
        faction=MonsterFactionEnum.ENEMY,
        description="A goblin.",
    )
    killer = MonsterAggregate.create(
        monster_id=MonsterId(2),
        template=killer_template,
        world_object_id=WorldObjectId(100),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1001, normal_capacity=5, awakened_capacity=5
        ),
    )
    dead = MonsterAggregate.create(
        monster_id=MonsterId(1),
        template=dead_template,
        world_object_id=WorldObjectId(101),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(2), owner_id=1002, normal_capacity=5, awakened_capacity=5
        ),
    )
    killer.spawn(Coordinate(2, 2, 0), SpotId(1), WorldTick(0), initial_hunger=0.9)
    monster_repo.save(killer)
    monster_repo.save(dead)


class TestMonsterDeathHungerHandler:
    """実在する討伐者と獲物を用い、飢餓の保存と対象外イベントの無視を確認する。"""

    @pytest.fixture
    def monster_repo(self):
        return InMemoryMonsterAggregateRepository()

    @pytest.fixture
    def handler(self, monster_repo):
        return MonsterDeathHungerHandler(monster_repo, _FakeUow())

    @pytest.mark.parametrize(
        ("prey_race", "spot_id", "expected_hunger"),
        [
            pytest.param(Race.GOBLIN, SpotId(1), 0.5, id="prey-with-spot"),
            pytest.param(Race.GOBLIN, None, 0.5, id="prey-without-spot"),
            pytest.param(Race.ORC, SpotId(1), 0.9, id="not-prey"),
        ],
    )
    def test_prey_kill_updates_hunger_without_requiring_spot(
        self, handler, monster_repo, prey_race, spot_id, expected_hunger
    ):
        """獲物なら場所情報なしでも飢餓が0.4減り、獲物でなければ0.9のまま保存される。"""
        _create_killer_and_prey(monster_repo, prey_race)
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=150,
            exp=5,
            gold=2,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=WorldObjectId(100),
            cause=None,
            spot_id=spot_id,
        )

        handler.handle(event)

        killer_after = monster_repo.find_by_world_object_id(WorldObjectId(100))
        assert killer_after.hunger == pytest.approx(expected_hunger)

    @pytest.mark.parametrize(
        "killer_id",
        [pytest.param(None, id="no-killer"), pytest.param(WorldObjectId(999), id="unknown-killer")],
    )
    def test_missing_killer_leaves_existing_monster_hunger_unchanged(self, handler, monster_repo, killer_id):
        """討伐者が不明または未登録なら無例外で終了し、既存モンスターの飢餓を変えない。"""
        _create_killer_and_prey(monster_repo, Race.GOBLIN)
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=10,
            gold=5,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=killer_id,
            cause=None,
            spot_id=None,
        )

        handler.handle(event)

        assert monster_repo.find_by_world_object_id(WorldObjectId(100)).hunger == pytest.approx(0.9)
