"""MonsterAggregate.take_environmental_damage の単体テスト (Phase 4-O B)。

検証対象:
- HP 減少 + MonsterDamagedEvent 発火 (attacker_id=None)
- 致命ダメージで MonsterDiedEvent.cause = ENVIRONMENT として死亡
- DEAD 状態で呼ぶと MonsterAlreadyDeadException
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    DeathCauseEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterDamagedEvent,
    MonsterDiedEvent,
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterAlreadyDeadException,
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
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _aggregate(*, max_hp: int = 20) -> MonsterAggregate:
    template = MonsterTemplate(
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
    )
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


class TestNonLethal:
    """致命でないダメージで HP 減少 + Damaged event 発火。"""

    def test_hp_event_trigger(self) -> None:
        """HP 減 event 発火。"""
        agg = _aggregate(max_hp=20)
        agg.clear_events()
        agg.take_environmental_damage(damage=3, current_tick=WorldTick(10))

        assert agg.hp.value == 17
        events = [e for e in agg.get_events() if isinstance(e, MonsterDamagedEvent)]
        assert len(events) == 1
        assert events[0].damage == 3
        assert events[0].attacker_id is None  # 環境ダメージ
        # まだ生存
        died_events = [e for e in agg.get_events() if isinstance(e, MonsterDiedEvent)]
        assert died_events == []


class TestLethal:
    """致命ダメージで cause=ENVIRONMENT の MonsterDiedEvent。"""

    def test_hp_cause_environment_dead(self) -> None:
        """HP 削り切ると cause ENVIRONMENT で死亡。"""
        agg = _aggregate(max_hp=5)
        agg.clear_events()
        agg.take_environmental_damage(damage=10, current_tick=WorldTick(20))

        assert agg.status != MonsterStatusEnum.ALIVE
        died_events = [
            e for e in agg.get_events() if isinstance(e, MonsterDiedEvent)
        ]
        assert len(died_events) == 1
        assert died_events[0].cause == DeathCauseEnum.ENVIRONMENT
        # killer 情報は無し
        assert died_events[0].killer_player_id is None
        assert died_events[0].killer_world_object_id is None


class TestAlreadyDead:
    """DEAD 状態で呼ぶと例外。"""

    def test_dead_take_environmental_damage_raises_exception(self) -> None:
        """DEAD 状態で takeenvironmentaldamage は例外。"""
        agg = _aggregate()
        # DEAD 状態に強制遷移
        agg._lifecycle_state = MonsterLifecycleState(
            hp=agg._lifecycle_state.hp,
            mp=agg._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(1),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        with pytest.raises(MonsterAlreadyDeadException):
            agg.take_environmental_damage(damage=5, current_tick=WorldTick(10))
