"""SpotMonsterBehaviorTickService の捕食 (Phase 3b) 統合テスト。

検証範囲:
- hungry な捕食者 + 同 spot に prey 種族 → 捕食成立
- player attack が prey より優先される (priority chain)
- 飢餓未閾値では捕食しない (forage_threshold 未満)
- prey 種族なしで捕食しない
- 捕食成立後は wander スキップ (continue)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
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
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterPredatedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _wolf_template(
    *,
    prey: frozenset = frozenset({Race.BEAST}),
    attack: int = 5,
    hunger_decrease: float = 0.5,
    forage_threshold: float = 0.5,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=attack,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        # NEUTRAL: 種族関係 (prey) で狩るが faction では player 攻撃しない設定
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
        prey_races=prey,
        starvation_ticks=10,
        hunger_increase_per_tick=0.6,  # 1 tick で forage_threshold=0.5 超え
        hunger_starvation_threshold=1.0,
        hunger_decrease_on_prey_kill=hunger_decrease,
        forage_threshold=forage_threshold,
        idle_wander_chance=0.0,
    )


def _rabbit_template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(2),
        name="Rabbit",
        base_stats=BaseStats(
            max_hp=10, max_mp=0, attack=1,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A rabbit.",
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


def _make_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(
        SpotNode(
            spot_id=SPOT_A,
            name="Forest",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    return g


def _make_svc(graph, monsters: dict):
    """monsters: dict[MonsterId, MonsterAggregate]"""
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.side_effect = lambda mid: monsters.get(mid)
    player_repo = MagicMock()
    player_repo.find_by_id.return_value = None
    return SpotMonsterBehaviorTickService(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        attack_orchestrator=SpotAttackOrchestrator(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
        ),
    )


class TestPredationViaTick:
    """tick 駆動で捕食が発火する。"""

    def test_hungry_wolf_が_rabbit_を捕食する(self) -> None:
        """1 tick で hunger が forage_threshold を超え、prey 種族の rabbit を狩る。"""
        wolf = _make_monster(_wolf_template(), 1)
        rabbit = _make_monster(_rabbit_template(), 2)
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)
        graph.clear_events()

        svc = _make_svc(graph, {wolf.monster_id: wolf, rabbit.monster_id: rabbit})
        outcomes = svc.tick(WorldTick(10))

        # 捕食 event が積まれた
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterPredatedMonsterInSpotEvent)
        ]
        assert len(events) == 1
        # rabbit に attack 記録
        assert rabbit.last_attacked_tick == WorldTick(10)


class TestPreyRacesGate:
    """prey_races 不設定では捕食しない。"""

    def test_prey_races_空では捕食しない(self) -> None:
        """prey_races が空なら hungry でも捕食発火しない。"""
        wolf = _make_monster(_wolf_template(prey=frozenset()), 1)
        rabbit = _make_monster(_rabbit_template(), 2)
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)
        graph.clear_events()

        svc = _make_svc(graph, {wolf.monster_id: wolf, rabbit.monster_id: rabbit})
        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterPredatedMonsterInSpotEvent)
        ]
        assert events == []
        # rabbit に attack 記録もない
        assert rabbit.last_attacked_tick is None


class TestHungerThresholdGate:
    """hunger 未閾値では捕食しない。"""

    def test_forage_threshold_未満では捕食しない(self) -> None:
        """hunger_increase_per_tick=0.1 で forage_threshold=0.5 に届かない。"""
        wolf_template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Wolf",
            base_stats=BaseStats(
                max_hp=20, max_mp=0, attack=5,
                defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
            ),
            reward_info=RewardInfo(exp=1, gold=1),
            respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.NEUTRAL,
            description="A patient wolf.",
            prey_races=frozenset({Race.BEAST}),
            starvation_ticks=100,
            hunger_increase_per_tick=0.1,  # 閾値届かない
            hunger_starvation_threshold=1.0,
            forage_threshold=0.5,
            idle_wander_chance=0.0,
        )
        wolf = _make_monster(wolf_template, 1)
        rabbit = _make_monster(_rabbit_template(), 2)
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)
        graph.clear_events()

        svc = _make_svc(graph, {wolf.monster_id: wolf, rabbit.monster_id: rabbit})
        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterPredatedMonsterInSpotEvent)
        ]
        assert events == []


class TestPlayerAttackPriority:
    """player attack > predation の priority chain。"""

    def test_player_が_priority_を奪う(self) -> None:
        """ENEMY 設定の wolf がプレイヤーと prey を同 spot に持つとき、
        プレイヤー攻撃が優先される。"""
        # ENEMY faction の wolf
        enemy_wolf_template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Wolf",
            base_stats=BaseStats(
                max_hp=20, max_mp=0, attack=5,
                defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
            ),
            reward_info=RewardInfo(exp=1, gold=1),
            respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,  # ← player を攻撃する設定
            description="An enemy wolf.",
            prey_races=frozenset({Race.BEAST}),
            starvation_ticks=10,
            hunger_increase_per_tick=0.6,
            hunger_starvation_threshold=1.0,
            forage_threshold=0.5,
            idle_wander_chance=0.0,
        )
        wolf = _make_monster(enemy_wolf_template, 1)
        rabbit = _make_monster(_rabbit_template(), 2)
        graph = _make_graph()
        graph.place_monster(wolf.monster_id, SPOT_A)
        graph.place_monster(rabbit.monster_id, SPOT_A)

        # プレイヤーを spot に配置
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        # プレイヤー attack 用の mock
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        player = MagicMock()
        player.player_id = PlayerId(1)
        state = {"down": False}
        type(player).is_down = property(lambda self: state["down"])
        player.apply_damage.side_effect = lambda d: None

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.side_effect = lambda mid: (
            wolf if mid == wolf.monster_id else rabbit
        )
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )
        svc.tick(WorldTick(10))

        # rabbit ではなく player が攻撃された
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            MonsterAttackedPlayerInSpotEvent,
        )
        attack_events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        predation_events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterPredatedMonsterInSpotEvent)
        ]
        assert len(attack_events) == 1  # プレイヤー攻撃成立
        assert predation_events == []   # 捕食はスキップ
        # rabbit に attack 記録もない
        assert rabbit.last_attacked_tick is None
