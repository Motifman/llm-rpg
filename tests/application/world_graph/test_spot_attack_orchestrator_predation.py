"""SpotAttackOrchestrator.execute_predation_attack の単体テスト。

検証範囲:
- 通常攻撃 (target 生存) で event 発火 + cooldown 記録 + record_attacked_by_in_spot
- 致命攻撃で hunger 回復 (record_prey_kill 経由)
- target_dead / cooldown / 視認不可 / zero_damage で executed=False
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
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


def _make_template(
    *,
    name: str,
    race: Race,
    attack: int = 5,
    max_hp: int = 30,
    hunger_decrease_on_prey_kill: float = 0.5,
    starvation_ticks: int = 5,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name=name,
        base_stats=BaseStats(
            max_hp=max_hp, max_mp=0, attack=attack,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=race,
        faction=MonsterFactionEnum.NEUTRAL,
        description=f"{name}.",
        starvation_ticks=starvation_ticks,
        hunger_increase_per_tick=0.1,
        hunger_starvation_threshold=1.0,
        hunger_decrease_on_prey_kill=hunger_decrease_on_prey_kill,
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


def _make_orchestrator(graph, attacker, prey):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()

    def _find(monster_id):
        if monster_id == attacker.monster_id:
            return attacker
        if monster_id == prey.monster_id:
            return prey
        return None

    monster_repo.find_by_id.side_effect = _find
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


class TestPredationSuccess:
    """通常攻撃 (target 生存) 成立。"""

    def test_event_発火_と_3_セーブ_と_record_attacked_by_in_spot(self) -> None:
        """attack 成立で event + monster save 2 件 + graph save、prey に
        record_attacked_by_in_spot が記録される。"""
        wolf_t = _make_template(name="Wolf", race=Race.BEAST, attack=5, max_hp=30)
        rabbit_t = _make_template(name="Rabbit", race=Race.BEAST, attack=1, max_hp=20)
        wolf = _make_monster(wolf_t, 1)
        rabbit = _make_monster(rabbit_t, 2)
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)
        graph.clear_events()

        orch, spot_repo, monster_repo = _make_orchestrator(graph, wolf, rabbit)
        outcome = orch.execute_predation_attack(
            attacker_monster=wolf,
            prey_monster=rabbit,
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
        assert events[0].damage == 5

        # Phase 4 用の attack 記録
        assert rabbit.last_attacked_tick == WorldTick(10)

        # save 呼出
        assert monster_repo.save.call_count == 2
        spot_repo.save.assert_called_once_with(graph)


class TestPredationKill:
    """致命攻撃で hunger 回復。"""

    def test_致命攻撃で_record_prey_kill_経由で_hunger_減少(self) -> None:
        """attacker.attack >= prey.hp で致命、hunger が回復する。"""
        wolf_t = _make_template(
            name="Wolf",
            race=Race.BEAST,
            attack=999,  # 致命
            hunger_decrease_on_prey_kill=0.4,
            starvation_ticks=10,
        )
        rabbit_t = _make_template(name="Rabbit", race=Race.BEAST, attack=0, max_hp=10)
        wolf = _make_monster(wolf_t, 1)
        rabbit = _make_monster(rabbit_t, 2)

        # 攻撃前にお腹を空かせる
        wolf._lifecycle_state = wolf._lifecycle_state.tick_hunger(
            hunger_increase_per_tick=0.6,
            hunger_starvation_threshold=1.0,
            starvation_ticks=10,
        )[0]
        initial_hunger = wolf.hunger
        assert initial_hunger > 0

        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, wolf, rabbit)
        outcome = orch.execute_predation_attack(
            attacker_monster=wolf,
            prey_monster=rabbit,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(20),
        )

        assert outcome.executed is True
        assert outcome.target_incapacitated is True
        # hunger が 0.4 だけ減少（または 0 でクランプ）
        assert wolf.hunger < initial_hunger
        assert rabbit.status != MonsterStatusEnum.ALIVE


class TestPredationFailure:
    """各失敗系。"""

    def test_target_dead_で_executed_false(self) -> None:
        """既に死んでいる prey は捕食できない。"""
        from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
            MonsterLifecycleState,
        )

        wolf = _make_monster(_make_template(name="Wolf", race=Race.BEAST), 1)
        rabbit = _make_monster(_make_template(name="Rabbit", race=Race.BEAST), 2)
        # rabbit を死亡状態に強制
        rabbit._lifecycle_state = MonsterLifecycleState(
            hp=rabbit._lifecycle_state.hp,
            mp=rabbit._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(5),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, wolf, rabbit)
        outcome = orch.execute_predation_attack(
            attacker_monster=wolf,
            prey_monster=rabbit,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "target_dead"

    def test_暗闇_かつ_dark_vision無しで_not_visible(self) -> None:
        """DARK + dark_vision なしの捕食者は狩らない。"""
        wolf = _make_monster(_make_template(name="Wolf", race=Race.BEAST), 1)
        rabbit = _make_monster(_make_template(name="Rabbit", race=Race.BEAST), 2)
        graph = _make_graph(lighting=LightingEnum.DARK)
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, wolf, rabbit)
        outcome = orch.execute_predation_attack(
            attacker_monster=wolf,
            prey_monster=rabbit,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "not_visible"

    def test_attack_ゼロで_zero_damage(self) -> None:
        """attack=0 のテンプレでは捕食成立しない。"""
        wolf = _make_monster(_make_template(name="Wolf", race=Race.BEAST, attack=0), 1)
        rabbit = _make_monster(_make_template(name="Rabbit", race=Race.BEAST), 2)
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)

        orch, *_ = _make_orchestrator(graph, wolf, rabbit)
        outcome = orch.execute_predation_attack(
            attacker_monster=wolf,
            prey_monster=rabbit,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "zero_damage"
