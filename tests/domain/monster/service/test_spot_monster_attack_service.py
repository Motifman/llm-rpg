"""SpotMonsterAttackService の単体テスト。

検証対象:
- 前提条件 (faction / cooldown / 視認 / target ダウン) の各分岐
- 攻撃成立時に player.apply_damage と monster.record_attack が両方呼ばれる
- 戻り値の MonsterAttackOutcome の中身（damage / target_incapacitated）
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.service.spot_monster_attack_service import (
    SpotMonsterAttackService,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)


def _make_monster(
    *,
    faction: MonsterFactionEnum = MonsterFactionEnum.ENEMY,
    can_attack: bool = True,
    has_dark_vision: bool = False,
    attack: int = 7,
    status: MonsterStatusEnum = MonsterStatusEnum.ALIVE,
):
    monster = MagicMock()
    monster.template.faction = faction
    monster.template.has_dark_vision = has_dark_vision
    monster.template.base_stats.attack = attack
    monster.status = status
    monster.can_attack_now.return_value = can_attack
    return monster


def _make_player(*, is_down_before: bool = False, is_down_after: bool = False):
    player = MagicMock()
    # is_down は呼び出し時点で参照される。apply_damage 後に True に変わる
    # ケースを再現するため、PropertyMock を使わずに side_effect で値を切り替える。
    states = {"down": is_down_before}

    def _get_is_down() -> bool:
        return states["down"]

    def _apply(damage: int) -> None:
        states["down"] = is_down_after

    type(player).is_down = property(lambda self: _get_is_down())
    player.apply_damage.side_effect = _apply
    return player


class TestNotHostile:
    """faction が ENEMY 以外なら攻撃しない。"""

    def test_neutral(self) -> None:
        """faction=NEUTRAL のモンスターは攻撃を試みない。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(faction=MonsterFactionEnum.NEUTRAL)
        player = _make_player()

        outcome = svc.try_attack(
            monster, player, LightingEnum.BRIGHT, WorldTick(10)
        )

        assert outcome.executed is False
        assert outcome.reason == "not_hostile"
        player.apply_damage.assert_not_called()
        monster.record_attack.assert_not_called()


class TestCannotAttack:
    """cooldown 中 / DEAD は攻撃不可。"""

    def test_can_attack_now_false(self) -> None:
        """can_attack_now が False のモンスターは攻撃せず cannot_attack 理由を返す。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(can_attack=False)
        player = _make_player()

        outcome = svc.try_attack(
            monster, player, LightingEnum.BRIGHT, WorldTick(10)
        )

        assert outcome.executed is False
        assert outcome.reason == "cannot_attack"
        player.apply_damage.assert_not_called()


class TestVisibility:
    """視認可否判定。"""

    def test_darkness_dark_vision_2(self) -> None:
        """DARK で dark_vision なし → not_visible。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(has_dark_vision=False)
        player = _make_player()

        outcome = svc.try_attack(
            monster, player, LightingEnum.DARK, WorldTick(10)
        )

        assert outcome.executed is False
        assert outcome.reason == "not_visible"

    def test_darkness_dark_vision(self) -> None:
        """DARK + dark_vision あり → 攻撃が通る。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(has_dark_vision=True, attack=12)
        player = _make_player()

        outcome = svc.try_attack(
            monster, player, LightingEnum.DARK, WorldTick(10)
        )

        assert outcome.executed is True
        assert outcome.damage == 12


class TestTargetAlreadyDown:
    """既にダウンしているターゲットは攻撃しない。"""

    def test_downed(self) -> None:
        """is_down=True のターゲットは executed=False。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster()
        player = _make_player(is_down_before=True)

        outcome = svc.try_attack(
            monster, player, LightingEnum.BRIGHT, WorldTick(10)
        )

        assert outcome.executed is False
        assert outcome.reason == "target_down"
        player.apply_damage.assert_not_called()


class TestSuccessfulAttack:
    """攻撃成立時のダメージ反映と cooldown 記録。"""

    def test_calls_apply_damage_record_attack(self) -> None:
        """成立時、player.apply_damage と monster.record_attack が両方呼ばれる。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(attack=8)
        player = _make_player()

        outcome = svc.try_attack(
            monster, player, LightingEnum.BRIGHT, WorldTick(20)
        )

        assert outcome.executed is True
        assert outcome.damage == 8
        assert outcome.target_incapacitated is False
        player.apply_damage.assert_called_once_with(8)
        monster.record_attack.assert_called_once_with(WorldTick(20))

    def test_attack_executed_false(self) -> None:
        """`base_stats.attack=0` のテンプレは event を発火させず cooldown も進めない。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(attack=0)
        player = _make_player()

        outcome = svc.try_attack(
            monster, player, LightingEnum.BRIGHT, WorldTick(10)
        )

        assert outcome.executed is False
        assert outcome.reason == "zero_damage"
        player.apply_damage.assert_not_called()
        monster.record_attack.assert_not_called()

    def test_downed_outcome(self) -> None:
        """apply_damage 後に is_down=True になったら target_incapacitated=True。"""
        svc = SpotMonsterAttackService()
        monster = _make_monster(attack=999)
        # apply_damage 後にダウンする player
        player = _make_player(is_down_before=False, is_down_after=True)

        outcome = svc.try_attack(
            monster, player, LightingEnum.BRIGHT, WorldTick(20)
        )

        assert outcome.executed is True
        assert outcome.target_incapacitated is True
