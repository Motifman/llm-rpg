"""TemperamentEnum と apply_temperament のテスト (Phase 4b PR d)。

検証対象:
- 全 TemperamentEnum 値に対応する preset が定義されている
- apply_temperament で 6 フィールドが上書きされる
- 他のフィールド (HP / race 等) は維持される
- 同じ template に異なる temperament を適用すると独立した template が返る
- BERSERKER の `0=無制限` 値が正しく設定される
- apply 後の dataclasses.replace で個別 override が可能
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    ReactionPolicyEnum,
    TemperamentEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.monster_temperament_preset import (
    apply_temperament,
    get_preset_values,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats


def _base_template() -> MonsterTemplate:
    """temperament 適用前の素の template。"""
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A wolf.",
    )


class TestPresetCoverage:
    """全 TemperamentEnum に対して preset が定義されている。"""

    @pytest.mark.parametrize("temperament", list(TemperamentEnum))
    def test_全_TemperamentEnum_に_preset_が_定義されている(
        self, temperament: TemperamentEnum,
    ) -> None:
        """get_preset_values が全 enum 値に対して KeyError を投げない。"""
        preset = get_preset_values(temperament)
        # 6 フィールド全てが取得できる
        assert preset.reaction_to_attack is not None
        assert preset.flee_grace_ticks >= 0
        assert 0.0 <= preset.flee_threshold <= 1.0
        assert preset.chase_max_distance >= 0
        assert preset.chase_max_ticks >= 0
        assert preset.chase_search_ticks >= 0


class TestPassiveBeast:
    """PASSIVE_BEAST: 攻撃しない平和な動物。"""

    def test_PASSIVE_BEAST_は_反応無し_全パラメータ_0(self) -> None:
        result = apply_temperament(_base_template(), TemperamentEnum.PASSIVE_BEAST)
        assert result.reaction_to_attack == ReactionPolicyEnum.PASSIVE
        assert result.flee_grace_ticks == 0
        assert result.chase_max_distance == 0
        assert result.chase_max_ticks == 0
        assert result.chase_search_ticks == 0


class TestCoward:
    """COWARD: 弱気、被弾即逃走、追跡しない。"""

    def test_COWARD_は_ALWAYS_FLEE_追跡無し(self) -> None:
        result = apply_temperament(_base_template(), TemperamentEnum.COWARD)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_FLEE
        assert result.flee_grace_ticks == 5
        assert result.chase_max_distance == 0
        assert result.chase_search_ticks == 0


class TestWary:
    """WARY: HP 低いと逃げ、HP 余裕なら短距離追跡。"""

    def test_WARY_は_FLEE_WHEN_LOW_HP_短距離追跡(self) -> None:
        result = apply_temperament(_base_template(), TemperamentEnum.WARY)
        assert result.reaction_to_attack == ReactionPolicyEnum.FLEE_WHEN_LOW_HP
        assert result.flee_threshold == 0.3
        assert result.chase_max_distance == 2
        assert result.chase_max_ticks == 10
        assert result.chase_search_ticks == 2


class TestAggressive:
    """AGGRESSIVE: 普通の敵、中距離追跡。"""

    def test_AGGRESSIVE_は_ALWAYS_RETALIATE_中距離追跡(self) -> None:
        result = apply_temperament(_base_template(), TemperamentEnum.AGGRESSIVE)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert result.flee_grace_ticks == 5
        assert result.chase_max_distance == 5
        assert result.chase_max_ticks == 20
        assert result.chase_search_ticks == 3


class TestFerocious:
    """FEROCIOUS: 執念深い長距離追跡。"""

    def test_FEROCIOUS_は_長距離_長時間_追跡(self) -> None:
        result = apply_temperament(_base_template(), TemperamentEnum.FEROCIOUS)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert result.flee_grace_ticks == 10
        assert result.chase_max_distance == 15
        assert result.chase_max_ticks == 60
        assert result.chase_search_ticks == 8


class TestBerserker:
    """BERSERKER: 距離 / tick 無制限。"""

    def test_BERSERKER_は_chase_max_distance_と_max_ticks_が_0(
        self,
    ) -> None:
        """0 は無制限を意味するため、BERSERKER は事実上どこまでも追ってくる。"""
        result = apply_temperament(_base_template(), TemperamentEnum.BERSERKER)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert result.chase_max_distance == 0  # 無制限
        assert result.chase_max_ticks == 0     # 無制限
        assert result.chase_search_ticks == 15
        assert result.flee_grace_ticks == 20


class TestBaseFieldsPreserved:
    """temperament 適用しても他フィールドは維持される。"""

    def test_HP_attack_race_faction_等は_変わらない(self) -> None:
        base = _base_template()
        result = apply_temperament(base, TemperamentEnum.AGGRESSIVE)
        assert result.template_id == base.template_id
        assert result.name == base.name
        assert result.base_stats.max_hp == base.base_stats.max_hp
        assert result.base_stats.attack == base.base_stats.attack
        assert result.race == base.race
        assert result.faction == base.faction
        assert result.description == base.description

    def test_apply_前後で_base_template_は_変更されない(self) -> None:
        """`apply_temperament` は新しい template を返し、base は不変。"""
        base = _base_template()
        original_reaction = base.reaction_to_attack
        apply_temperament(base, TemperamentEnum.FEROCIOUS)
        # base はそのまま (immutable な dataclass)
        assert base.reaction_to_attack == original_reaction


class TestPostApplyOverride:
    """apply 後に dataclasses.replace で個別パラメータを上書きできる。"""

    def test_apply_後に_chase_max_distance_だけ_上書きできる(self) -> None:
        result = apply_temperament(_base_template(), TemperamentEnum.AGGRESSIVE)
        custom = replace(result, chase_max_distance=99)
        assert custom.chase_max_distance == 99
        # 他の AGGRESSIVE プリセット値は維持
        assert custom.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert custom.chase_max_ticks == 20


class TestIndependentApplications:
    """同じ base に異なる temperament を適用すると独立した結果。"""

    def test_AGGRESSIVE_と_COWARD_は_異なる_template_を_返す(self) -> None:
        base = _base_template()
        a = apply_temperament(base, TemperamentEnum.AGGRESSIVE)
        c = apply_temperament(base, TemperamentEnum.COWARD)
        assert a.reaction_to_attack != c.reaction_to_attack
        assert a is not c
