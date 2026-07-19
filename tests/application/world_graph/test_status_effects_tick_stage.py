"""StatusEffectsTickStageService の挙動検証 (PR #2)。

active_effects の継続適用 (BLEEDING で HP 漸減 / REGENERATION で回復) と
期限切れ掃除、HP 0 で PlayerDownedEvent が publish される連鎖を確認する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.status_effects_tick_stage_service import (
    StatusEffectsTickStageService,
)
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent


def _make_status(hp: int = 100) -> PlayerStatusAggregate:
    from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
    from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
    from ai_rpg_world.domain.player.value_object.gold import Gold
    from ai_rpg_world.domain.player.value_object.growth import Growth
    from ai_rpg_world.domain.player.value_object.hp import Hp
    from ai_rpg_world.domain.player.value_object.mp import Mp
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId
    from ai_rpg_world.domain.player.value_object.stamina import Stamina
    from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


class TestBleedingDamage:
    def test_bleeding_reduces_hp_by_one_each_tick(self) -> None:
        """BLEEDING は毎 tickHP1 減らす。"""
        status = _make_status(hp=100)
        status.add_status_effect(StatusEffect(
            effect_type=StatusEffectType.BLEEDING,
            value=1.0,
            expiry_tick=WorldTick(10),
        ))
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = StatusEffectsTickStageService(repo)

        stage.run(WorldTick(1))

        assert status.hp.value == 99


class TestRegenerationHeal:
    def test_regeneration_restores_hp_by_one_each_tick(self) -> None:
        """REGENERATION は毎 tickHP1 回復。"""
        status = _make_status(hp=50)
        status.add_status_effect(StatusEffect(
            effect_type=StatusEffectType.REGENERATION,
            value=1.0,
            expiry_tick=WorldTick(10),
        ))
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = StatusEffectsTickStageService(repo)

        stage.run(WorldTick(1))

        assert status.hp.value == 51


class TestPoisonStrongerThanBleeding:
    """POISON は BLEEDING より速い (毎 tick -2)。"""

    def test_poison_tick_hp_two(self) -> None:
        """POISON は毎 tickHP2 減らす。"""
        status = _make_status(hp=100)
        status.add_status_effect(StatusEffect(
            effect_type=StatusEffectType.POISON,
            value=1.0,
            expiry_tick=WorldTick(10),
        ))
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = StatusEffectsTickStageService(repo)

        stage.run(WorldTick(1))

        assert status.hp.value == 98


class TestExpiry:
    """期限切れの effect は active_effects から消える。"""

    def test_expiry_tick_cleanup(self) -> None:
        """expiry tick 到達で 最終ダメージが入ったあと cleanup される。"""
        status = _make_status(hp=100)
        status.add_status_effect(StatusEffect(
            effect_type=StatusEffectType.BLEEDING,
            value=1.0,
            expiry_tick=WorldTick(5),
        ))
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = StatusEffectsTickStageService(repo)

        # tick == expiry_tick は「最終ダメージが入る tick」として扱う (off-by-one 防止)。
        # その後に cleanup で active_effects から消える。
        stage.run(WorldTick(5))

        assert status.hp.value == 99
        assert len(status.active_effects) == 0

    def test_expiry_over_tick(self) -> None:
        """expiry を超えた tick ではダメージが入らない。"""
        status = _make_status(hp=100)
        status.add_status_effect(StatusEffect(
            effect_type=StatusEffectType.BLEEDING,
            value=1.0,
            expiry_tick=WorldTick(5),
        ))
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = StatusEffectsTickStageService(repo)

        stage.run(WorldTick(6))

        assert status.hp.value == 100
        assert len(status.active_effects) == 0


class TestDeathChain:
    """HP 0 で PlayerDownedEvent が publish_all に乗る → DEAD 連鎖。"""

    def test_bleeding_hp_zero_player_downed_event(self) -> None:
        """BLEEDING で HP0 になったら PlayerDownedEvent が流れる。"""
        status = _make_status(hp=1)
        status.add_status_effect(StatusEffect(
            effect_type=StatusEffectType.BLEEDING,
            value=1.0,
            expiry_tick=WorldTick(10),
        ))
        repo = MagicMock()
        repo.find_all.return_value = [status]
        publisher = MagicMock()
        stage = StatusEffectsTickStageService(repo, event_publisher=publisher)

        stage.run(WorldTick(1))

        # apply_damage(1) で HP 0 → PlayerDownedEvent が積まれる → publisher へ
        assert status.hp.value == 0
        publisher.publish_all.assert_called_once()
        published = publisher.publish_all.call_args[0][0]
        assert any(isinstance(ev, PlayerDownedEvent) for ev in published)


class TestNoEffectNoMutation:
    """active_effects が空のプレイヤーは触らない。"""

    def test_returns_empty_when_active_effects_save(self) -> None:
        """active effects 空なら save されない。"""
        status = _make_status(hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = StatusEffectsTickStageService(repo)

        stage.run(WorldTick(1))

        repo.save_all.assert_not_called()
