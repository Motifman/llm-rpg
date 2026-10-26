"""SpotPlayerAttackService の単体テスト。

検証範囲:
- attacker がダウンしていれば不発
- target が DEAD なら不発
- damage=0 なら不発（PR #127 の対称ガード）
- 成立時に monster.apply_damage が呼ばれて MonsterDamagedEvent が発火する
- 致命攻撃で target_incapacitated=True になり MonsterDiedEvent が発火する
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterDamagedEvent,
    MonsterDiedEvent,
)
from ai_rpg_world.domain.monster.service.spot_player_attack_service import (
    SpotPlayerAttackService,
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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId


def _make_monster(*, hp_max: int = 30, attack: int = 5, alive: bool = True) -> MonsterAggregate:
    template = MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="灰色のオオカミ",
        base_stats=BaseStats(
            max_hp=hp_max,
            max_mp=0,
            attack=attack,
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
    return MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=template,
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            owner_id=101,
            normal_capacity=4,
            awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE if alive else MonsterStatusEnum.DEAD,
        spawned_at_tick=WorldTick(0) if alive else None,
    )


def _make_player(*, attack: int = 10, is_down: bool = False):
    """attacker player の最小 mock。"""
    player = MagicMock()
    player.player_id = PlayerId(1)
    player.base_stats = MagicMock(attack=attack)
    player.is_down = is_down
    return player


class TestAttackerDown:
    """ダウン中のプレイヤーは攻撃できない。"""

    def test_down_true_executed_false(self) -> None:
        """攻撃者がダウンしていれば不発となり、対象のHPと通知を変えない。"""
        svc = SpotPlayerAttackService()
        monster = _make_monster()
        assert monster.hp.value == 30
        assert monster.get_events() == []
        outcome = svc.try_attack(
            attacker=_make_player(is_down=True),
            target_monster=monster,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "attacker_down"
        assert monster.hp.value == 30
        assert monster.get_events() == []


class TestTargetDead:
    """既に死んでいるモンスターは攻撃できない。"""

    def test_status_dead_executed_false(self) -> None:
        """対象が未出現・死亡状態なら不発となり、対象のHPと通知を変えない。"""
        svc = SpotPlayerAttackService()
        # alive=False で構築すると status=DEAD + spawned_at_tick=None で
        # `MonsterAggregate.__init__` が unspawned 扱いとして lifecycle を作る。
        # この状態は domain 上 ALIVE 以外なので target_dead で弾かれる。
        monster = _make_monster(alive=False)
        assert monster.hp.value == 30
        assert monster.get_events() == []
        outcome = svc.try_attack(
            attacker=_make_player(),
            target_monster=monster,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "target_dead"
        assert monster.hp.value == 30
        assert monster.get_events() == []


class TestZeroDamage:
    """attack=0 のプレイヤーでは不発。"""

    def test_attack_executed_false(self) -> None:
        """攻撃力0なら不発となり、対象のHPと通知を変えない。"""
        svc = SpotPlayerAttackService()
        monster = _make_monster()
        assert monster.hp.value == 30
        assert monster.get_events() == []
        outcome = svc.try_attack(
            attacker=_make_player(attack=0),
            target_monster=monster,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is False
        assert outcome.reason == "zero_damage"
        assert monster.hp.value == 30
        assert monster.get_events() == []


class TestAttackHits:
    """成立時にダメージが入り MonsterDamagedEvent が発火する。"""

    def test_triggers_apply_damage_via_event(self) -> None:
        """成立時、monster aggregate に MonsterDamagedEvent が発火する。"""
        svc = SpotPlayerAttackService()
        monster = _make_monster(hp_max=30, attack=5)
        outcome = svc.try_attack(
            attacker=_make_player(attack=8),
            target_monster=monster,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is True
        assert outcome.damage == 8
        assert outcome.target_incapacitated is False

        events = [e for e in monster.get_events() if isinstance(e, MonsterDamagedEvent)]
        assert len(events) == 1
        assert events[0].damage == 8


class TestKillingBlow:
    """致命攻撃で target_incapacitated=True になり MonsterDiedEvent が発火する。"""

    def test_target_incapacitated_true(self) -> None:
        """attacker.attack >= monster.hp で target_incapacitated=True。"""
        svc = SpotPlayerAttackService()
        monster = _make_monster(hp_max=10, attack=5)
        outcome = svc.try_attack(
            attacker=_make_player(attack=999),
            target_monster=monster,
            current_tick=WorldTick(20),
        )
        assert outcome.executed is True
        assert outcome.target_incapacitated is True

        died_events = [e for e in monster.get_events() if isinstance(e, MonsterDiedEvent)]
        assert len(died_events) == 1
