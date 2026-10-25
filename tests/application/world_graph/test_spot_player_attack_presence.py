"""実際の攻撃処理に渡したグラフで、致命攻撃直後の配置保持を検証する。"""

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import SpotAttackOrchestrator
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum, MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def test_killing_blow_preserves_monster_presence() -> None:
    """HP5の対象へ999の攻撃を行っても、呼出先へ渡したグラフの配置は直後に残る。

    ドメイン側にあった入力と配置の断言を、グラフも受け取る実際の入口へ移す。
    保存や、その後のイベント配送で起こる配置変更はこの試験の対象に含めない。
    """
    template = MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="灰色のオオカミ",
        base_stats=BaseStats(
            max_hp=5,
            max_mp=0,
            attack=5,
            defense=0,
            speed=1,
            critical_rate=0.0,
            evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A grey wolf.",
    )
    monster = MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=template,
        world_object_id=WorldObjectId.create(9001),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            owner_id=101,
            normal_capacity=4,
            awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )
    attacker = MagicMock()
    attacker.player_id = PlayerId(1)
    attacker.base_stats = MagicMock(attack=999)
    attacker.is_down = False
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    spot = SpotId.create(1)
    graph.add_spot(
        SpotNode(
            spot_id=spot,
            name="森",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    graph.place_monster(MonsterId.create(101), spot)
    orchestrator = SpotAttackOrchestrator(
        spot_graph_repository=MagicMock(),
        monster_repository=MagicMock(),
        player_status_repository=MagicMock(),
    )

    outcome = orchestrator.execute_player_attack(
        attacker_player=attacker,
        target_monster=monster,
        graph=graph,
        current_tick=WorldTick(20),
    )

    assert outcome.executed is True
    assert monster.hp.value == 0
    assert outcome.target_incapacitated is True
    assert graph.is_monster_present(MonsterId.create(101)) is True
    assert graph.get_monster_spot(MonsterId.create(101)) == spot
