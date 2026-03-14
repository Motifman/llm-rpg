import unittest.mock as mock

from ai_rpg_world.application.world.services.monster_behavior_context_builder import (
    MonsterBehaviorContextBuilder,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage
from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.behavior_context import GrowthContext
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestMonsterBehaviorContextBuilder:
    def test_build_skill_context_returns_none_for_non_autonomous_actor(self):
        builder = MonsterBehaviorContextBuilder(monster_repository=mock.Mock())
        actor = WorldObject(
            WorldObjectId(100),
            Coordinate(0, 0),
            ObjectTypeEnum.PLAYER,
            component=ActorComponent(),
        )

        assert builder.build_skill_context(actor, WorldTick(0)) is None

    def test_build_skill_context_returns_usable_slots_only(self):
        loadout = mock.Mock()
        loadout.can_use_skill.side_effect = lambda slot_index, _tick: slot_index in {1, 3}
        monster = mock.Mock(skill_loadout=loadout)
        monster_repository = mock.Mock(find_by_world_object_id=mock.Mock(return_value=monster))
        builder = MonsterBehaviorContextBuilder(monster_repository=monster_repository)
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(
                available_skills=[
                    MonsterSkillInfo(slot_index=1, range=1, mp_cost=1),
                    MonsterSkillInfo(slot_index=2, range=1, mp_cost=1),
                    MonsterSkillInfo(slot_index=3, range=1, mp_cost=1),
                ]
            ),
        )

        context = builder.build_skill_context(actor, WorldTick(5))

        assert context is not None
        assert context.usable_slot_indices == {1, 3}

    def test_build_growth_context_returns_none_when_monster_missing(self):
        builder = MonsterBehaviorContextBuilder(
            monster_repository=mock.Mock(find_by_world_object_id=mock.Mock(return_value=None))
        )
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(),
        )

        assert builder.build_growth_context(actor, WorldTick(0)) is None

    def test_build_growth_context_returns_context_when_growth_stages_exist(self):
        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="grower",
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="grow",
            growth_stages=[GrowthStage(after_ticks=0, stats_multiplier=1.0)],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 1, 10, 10)
        monster = MonsterAggregate.create(
            MonsterId(1),
            template,
            WorldObjectId(1),
            skill_loadout=loadout,
        )
        monster.get_effective_flee_threshold = mock.Mock(return_value=0.3)
        monster.get_allow_chase = mock.Mock(return_value=False)
        builder = MonsterBehaviorContextBuilder(
            monster_repository=mock.Mock(find_by_world_object_id=mock.Mock(return_value=monster))
        )
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(),
        )

        context = builder.build_growth_context(actor, WorldTick(50))

        assert isinstance(context, GrowthContext)
        assert context.effective_flee_threshold == 0.3
        assert context.allow_chase is False
