"""SpotAttackOrchestrator.execute_monster_to_monster_attack の単体テスト。

検証範囲:
- 通常攻撃成立で event 発火 + cooldown + record_attacked_by_in_spot に
  attacker_ref(MONSTER) が付与される（反撃連鎖の前提）
- predation と異なり hunger 回復は行われない
- 致命攻撃で target が DEAD になる
- attacker_dead / target_dead / cannot_attack / not_visible / zero_damage で
  executed=False
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import (
    AttackerKind,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
    MonsterLifecycleState,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterPredatedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _template(*, attack: int = 5, max_hp: int = 30) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=max_hp, max_mp=0, attack=attack,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
    )


def _make_monster(template: MonsterTemplate, monster_id: int) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(monster_id),
        template=template,
        world_object_id=WorldObjectId.create(9000 + monster_id),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(monster_id), owner_id=monster_id,
            normal_capacity=4, awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )


def _make_graph(*, lighting: LightingEnum = LightingEnum.BRIGHT) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(
        SpotNode(
            spot_id=SPOT_A,
            name="Forest",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
            atmosphere=SpotAtmosphere(
                lighting=lighting,
                sound_ambient=None,
                temperature=TemperatureEnum.NORMAL,
                smell=None,
            ),
        )
    )
    return g


def _make_orchestrator(graph, attacker, target):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.side_effect = lambda mid: (
        attacker if mid == attacker.monster_id
        else target if mid == target.monster_id
        else None
    )
    player_repo = MagicMock()
    return (
        SpotAttackOrchestrator(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
        ),
        spot_repo,
        monster_repo,
    )


class TestRetaliationSuccess:
    """通常攻撃 (target 生存) 成立。"""

    def test_event_発火_target_に_attacker_ref_MONSTER_が_記録される(self) -> None:
        """attack 成立で event 発火 + target.last_attacker_ref が attacker MONSTER を指す。"""
        attacker = _make_monster(_template(attack=5), 1)
        target = _make_monster(_template(attack=3, max_hp=20), 2)
        graph = _make_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(target.monster_id, SPOT_A)
        graph.clear_events()

        orch, spot_repo, monster_repo = _make_orchestrator(graph, attacker, target)
        outcome = orch.execute_monster_to_monster_attack(
            attacker_monster=attacker,
            target_monster=target,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )

        assert outcome.executed is True
        assert outcome.damage == 5
        assert outcome.target_incapacitated is False
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterPredatedMonsterInSpotEvent)
        ]
        assert len(events) == 1

        # 反撃連鎖の前提: target 側が attacker を覚えている
        assert target.last_attacker_ref is not None
        assert target.last_attacker_ref.kind == AttackerKind.MONSTER
        assert target.last_attacker_ref.monster_id == attacker.monster_id
        assert target.last_attacked_tick == WorldTick(10)

        # save 呼出
        assert monster_repo.save.call_count == 2
        spot_repo.save.assert_called_once_with(graph)


class TestRetaliationKill:
    """致命攻撃。predation と異なり hunger は回復しない。"""

    def test_致命攻撃で_target_は_DEAD_だが_hunger_は_回復しない(self) -> None:
        """attacker.attack >= target.hp で致命、attacker の hunger は変化しない。"""
        attacker_t = _template(attack=999)
        target_t = _template(attack=0, max_hp=10)
        attacker = _make_monster(attacker_t, 1)
        target = _make_monster(target_t, 2)
        # attacker をお腹を空かせておく
        attacker._lifecycle_state = attacker._lifecycle_state.tick_hunger(
            hunger_increase_per_tick=0.6,
            hunger_starvation_threshold=1.0,
            starvation_ticks=10,
        )[0]
        initial_hunger = attacker.hunger
        assert initial_hunger > 0

        graph = _make_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(target.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, attacker, target)
        outcome = orch.execute_monster_to_monster_attack(
            attacker_monster=attacker,
            target_monster=target,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(20),
        )

        assert outcome.executed is True
        assert outcome.target_incapacitated is True
        assert target.status != MonsterStatusEnum.ALIVE
        # hunger は変化しない（捕食ではなく報復行動）
        assert attacker.hunger == initial_hunger


class TestRetaliationFailure:
    """失敗系: target_dead / not_visible / zero_damage / cannot_attack。"""

    def test_target_dead_で_executed_false(self) -> None:
        """既に死んでいる target は反撃対象にならない。"""
        attacker = _make_monster(_template(), 1)
        target = _make_monster(_template(), 2)
        target._lifecycle_state = MonsterLifecycleState(
            hp=target._lifecycle_state.hp,
            mp=target._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(5),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        graph = _make_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(target.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, attacker, target)
        outcome = orch.execute_monster_to_monster_attack(
            attacker_monster=attacker,
            target_monster=target,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "target_dead"

    def test_attack_ゼロで_zero_damage(self) -> None:
        """attack=0 のテンプレでは反撃が成立しない。"""
        attacker = _make_monster(_template(attack=0), 1)
        target = _make_monster(_template(), 2)
        graph = _make_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(target.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, attacker, target)
        outcome = orch.execute_monster_to_monster_attack(
            attacker_monster=attacker,
            target_monster=target,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "zero_damage"

    def test_暗闇_dark_vision無しで_not_visible(self) -> None:
        """DARK + dark_vision なしの attacker は反撃できない。"""
        attacker = _make_monster(_template(), 1)
        target = _make_monster(_template(), 2)
        graph = _make_graph(lighting=LightingEnum.DARK)
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(target.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, attacker, target)
        outcome = orch.execute_monster_to_monster_attack(
            attacker_monster=attacker,
            target_monster=target,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "not_visible"
