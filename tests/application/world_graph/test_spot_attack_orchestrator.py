"""SpotAttackOrchestrator の単体テスト。

検証範囲:
- `execute_monster_attack` 成立で MonsterAttackedPlayerInSpotEvent が graph に
  追加され、monster + player + graph の 3 集約が save される
- 不成立 (cooldown) では event 発火も save も無し
- `execute_player_attack` 成立で PlayerAttackedMonsterInSpotEvent が追加され
  3 集約が save される
- 暗闇 + dark_vision モンスター → 攻撃成立、target_visible=False で event 構築
- AttackOutcome.target_incapacitated が event の同名 field に直接渡される
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
    PlayerAttackedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _node(*, lighting: LightingEnum = LightingEnum.BRIGHT) -> SpotNode:
    return SpotNode(
        spot_id=SPOT_A,
        name="森",
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


def _make_graph(*, lighting: LightingEnum = LightingEnum.BRIGHT) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(lighting=lighting))
    return g


def _make_monster(
    *,
    monster_id_value: int = 101,
    can_attack: bool = True,
    has_dark_vision: bool = False,
    faction: MonsterFactionEnum = MonsterFactionEnum.ENEMY,
    attack: int = 5,
    status: MonsterStatusEnum = MonsterStatusEnum.ALIVE,
):
    monster = MagicMock()
    monster.monster_id = MonsterId.create(monster_id_value)
    monster.template.faction = faction
    monster.template.has_dark_vision = has_dark_vision
    monster.template.base_stats.attack = attack
    monster.status = status
    monster.can_attack_now.return_value = can_attack
    return monster


def _make_player(*, player_id_value: int = 1, is_down_before: bool = False, is_down_after: bool = False):
    player = MagicMock()
    player.player_id = PlayerId(player_id_value)
    state = {"down": is_down_before}

    def _apply(damage: int) -> None:
        state["down"] = is_down_after

    type(player).is_down = property(lambda self: state["down"])
    player.apply_damage.side_effect = _apply
    return player


def _make_orchestrator(graph: SpotGraphAggregate, monster, player):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.return_value = monster
    player_repo = MagicMock()
    player_repo.find_by_id.return_value = player
    return SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
    ), spot_repo, monster_repo, player_repo


class TestExecuteMonsterAttack:
    """モンスター → プレイヤー攻撃の orchestration。"""

    def test_成立で_event_発火と_3_集約_save(self) -> None:
        """成立で MonsterAttackedPlayerInSpotEvent が追加され、
        monster / player / graph がすべて save される。"""
        graph = _make_graph()
        monster = _make_monster(attack=7)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        orch, spot_repo, monster_repo, player_repo = _make_orchestrator(graph, monster, player)
        outcome = orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )

        assert outcome.executed is True
        assert outcome.damage == 7
        events = [e for e in graph.get_events() if isinstance(e, MonsterAttackedPlayerInSpotEvent)]
        assert len(events) == 1
        assert events[0].damage == 7
        assert events[0].target_visible is True
        monster_repo.save.assert_called_once_with(monster)
        player_repo.save.assert_called_once_with(player)
        spot_repo.save.assert_called_once_with(graph)

    def test_暗闇_かつ_dark_vision有りで_target_visible_false(self) -> None:
        """DARK + dark_vision あり → 攻撃成立、event.target_visible=False。"""
        graph = _make_graph(lighting=LightingEnum.DARK)
        monster = _make_monster(has_dark_vision=True)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        orch, *_ = _make_orchestrator(graph, monster, player)
        outcome = orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )

        assert outcome.executed is True
        events = [e for e in graph.get_events() if isinstance(e, MonsterAttackedPlayerInSpotEvent)]
        assert len(events) == 1
        assert events[0].target_visible is False

    def test_不成立では_event_も_save_も無し(self) -> None:
        """cooldown 中など executed=False では何も追加されず save されない。"""
        graph = _make_graph()
        monster = _make_monster(can_attack=False)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        orch, spot_repo, monster_repo, player_repo = _make_orchestrator(graph, monster, player)
        outcome = orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )

        assert outcome.executed is False
        events = [e for e in graph.get_events() if isinstance(e, MonsterAttackedPlayerInSpotEvent)]
        assert events == []
        monster_repo.save.assert_not_called()
        player_repo.save.assert_not_called()
        spot_repo.save.assert_not_called()

    def test_target_incapacitated_が_event_に直接そのまま渡される(self) -> None:
        """`AttackOutcome.target_incapacitated=True` → event.target_incapacitated=True。

        Phase B で event の field 名を統一したため翻訳が不要になった
        （以前は target_downed という別 field 名だった）。
        """
        graph = _make_graph()
        monster = _make_monster(attack=999)
        player = _make_player(is_down_before=False, is_down_after=True)  # 致命でダウン
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        orch, *_ = _make_orchestrator(graph, monster, player)
        outcome = orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )

        assert outcome.target_incapacitated is True
        events = [e for e in graph.get_events() if isinstance(e, MonsterAttackedPlayerInSpotEvent)]
        assert len(events) == 1
        assert events[0].target_incapacitated is True


class TestExecutePlayerAttack:
    """プレイヤー → モンスター攻撃の orchestration。"""

    def test_成立で_event_発火と_3_集約_save(self) -> None:
        """成立で PlayerAttackedMonsterInSpotEvent が graph に追加される。"""
        # 実 MonsterAggregate を使う（apply_damage 経路を踏ませるため）
        from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
            MonsterAggregate,
        )
        from ai_rpg_world.domain.monster.value_object.monster_template import (
            MonsterTemplate,
        )
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
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Wolf",
            base_stats=BaseStats(
                max_hp=30, max_mp=0, attack=2,
                defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
            ),
            reward_info=RewardInfo(exp=1, gold=1),
            respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A wolf.",
        )
        monster = MonsterAggregate(
            monster_id=MonsterId.create(101),
            template=template,
            world_object_id=WorldObjectId.create(9001),
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=101,
                normal_capacity=4, awakened_capacity=2,
            ),
            status=MonsterStatusEnum.ALIVE,
            spawned_at_tick=WorldTick(0),
        )

        attacker = MagicMock()
        attacker.player_id = PlayerId(1)
        attacker.is_down = False
        attacker.base_stats = MagicMock(attack=10)

        graph = _make_graph()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = attacker

        orch = SpotAttackOrchestrator(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
        )
        outcome = orch.execute_player_attack(
            attacker_player=attacker,
            target_monster=monster,
            graph=graph,
            current_tick=WorldTick(10),
        )

        assert outcome.executed is True
        events = [e for e in graph.get_events() if isinstance(e, PlayerAttackedMonsterInSpotEvent)]
        assert len(events) == 1
        assert events[0].damage == 10
        assert events[0].attacker_entity_id == EntityId.create(1)
        assert events[0].target_monster_id == MonsterId.create(101)
        monster_repo.save.assert_called_once_with(monster)
        player_repo.save.assert_called_once_with(attacker)
        spot_repo.save.assert_called_once_with(graph)
