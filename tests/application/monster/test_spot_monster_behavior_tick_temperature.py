"""SpotMonsterBehaviorTickService の温度不快 tick テスト (Phase 4-O B)。

検証対象:
- 寒すぎる spot で毎 tick HP 減少 + 観測 event 発火
- 暑すぎる spot で同様 (kind=too_hot)
- 快適範囲内では event 発火しない
- 致命温度ダメージで monster が DEAD になり、以降の行動 (reaction/wander) はスキップ
- damage=0 のテンプレでは効果無効化
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
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterFeltTemperatureDiscomfortInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _node_with_temperature(temp: TemperatureEnum) -> SpotNode:
    return SpotNode(
        spot_id=SPOT_A,
        name="spot_a", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient=None,
            temperature=temp,
            smell=None,
        ),
    )


def _graph_with_temperature(temp: TemperatureEnum) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node_with_temperature(temp))
    return g


def _template(
    *,
    min_temp: TemperatureEnum = TemperatureEnum.COLD,
    max_temp: TemperatureEnum = TemperatureEnum.WARM,
    discomfort_damage: int = 1,
    max_hp: int = 20,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=max_hp, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
        min_comfortable_temperature=min_temp,
        max_comfortable_temperature=max_temp,
        temperature_discomfort_damage_per_tick=discomfort_damage,
    )


def _monster(template: MonsterTemplate) -> MonsterAggregate:
    return MonsterAggregate(
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


def _make_service(graph, monster):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.return_value = monster
    player_repo = MagicMock()
    orch = SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
    )
    svc = SpotMonsterBehaviorTickService(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        attack_orchestrator=orch,
    )
    return svc, spot_repo, monster_repo


def _events_of_type(graph, evt_type):
    return [e for e in graph.get_events() if isinstance(e, evt_type)]


class TestComfortableTemperature:
    """快適範囲内では効果無し。"""

    def test_NORMAL_spot_では_event_発火_しない(self) -> None:
        graph = _graph_with_temperature(TemperatureEnum.NORMAL)
        monster = _monster(_template())  # COLD-WARM 快適
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(1))

        events = _events_of_type(
            graph, MonsterFeltTemperatureDiscomfortInSpotEvent,
        )
        assert events == []
        # HP も減らない
        assert monster.hp.value == 20


class TestTooCold:
    """寒すぎる spot で HP 減少 + too_cold event。"""

    def test_FREEZING_spot_で_HP_減_event_発火(self) -> None:
        graph = _graph_with_temperature(TemperatureEnum.FREEZING)
        monster = _monster(_template(discomfort_damage=2))
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(1))

        events = _events_of_type(
            graph, MonsterFeltTemperatureDiscomfortInSpotEvent,
        )
        assert len(events) == 1
        assert events[0].kind == "too_cold"
        assert events[0].damage_dealt == 2
        assert monster.hp.value == 18


class TestTooHot:
    """暑すぎる spot で HP 減少 + too_hot event。"""

    def test_HOT_spot_で_HP_減_event_発火(self) -> None:
        graph = _graph_with_temperature(TemperatureEnum.HOT)
        monster = _monster(_template(discomfort_damage=3))
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(1))

        events = _events_of_type(
            graph, MonsterFeltTemperatureDiscomfortInSpotEvent,
        )
        assert len(events) == 1
        assert events[0].kind == "too_hot"
        assert events[0].damage_dealt == 3
        assert monster.hp.value == 17


class TestLethalDamage:
    """温度ダメージで monster が DEAD になる経路。"""

    def test_HP_を_削り切ると_DEAD_に_遷移(self) -> None:
        graph = _graph_with_temperature(TemperatureEnum.FREEZING)
        # max_hp=5、damage=10 で 1 tick で死亡
        monster = _monster(_template(discomfort_damage=10, max_hp=5))
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(1))

        # event は発火し、monster は DEAD
        events = _events_of_type(
            graph, MonsterFeltTemperatureDiscomfortInSpotEvent,
        )
        assert len(events) == 1
        assert monster.status != MonsterStatusEnum.ALIVE


class TestDisabled:
    """damage=0 のテンプレでは効果無効化。"""

    def test_damage_0_テンプレ_では_event_発火_しない(self) -> None:
        graph = _graph_with_temperature(TemperatureEnum.FREEZING)
        # NORMAL のみ快適だが damage=0 で無効
        monster = _monster(
            _template(
                min_temp=TemperatureEnum.NORMAL,
                max_temp=TemperatureEnum.NORMAL,
                discomfort_damage=0,
            ),
        )
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(1))

        events = _events_of_type(
            graph, MonsterFeltTemperatureDiscomfortInSpotEvent,
        )
        assert events == []
        assert monster.hp.value == 20
