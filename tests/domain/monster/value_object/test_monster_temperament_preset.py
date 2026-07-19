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
    """全 TemperamentEnum に対して preset が定義され、apply_temperament で
    `MonsterTemplate.__post_init__` のバリデーションを通過する。"""

    @pytest.mark.parametrize("temperament", list(TemperamentEnum))
    def test_succeeds_all_temperament_enum_apply_temperament(
        self, temperament: TemperamentEnum,
    ) -> None:
        """全 enum 値で apply_temperament が KeyError も
        ValidationException も投げず MonsterTemplate を返す。
        これにより `__post_init__` 再実行も含めて preset 値が valid である
        ことが保証される (HIGH #1: _PRESETS 網羅性 + MEDIUM: __post_init__
        再実行検証を兼ねる)。"""
        result = apply_temperament(_base_template(), temperament)
        assert isinstance(result, MonsterTemplate)
        # 6 フィールドが書き換わっている (default と異なる値か、もしくは
        # 明示的に default 値が設定されている)
        assert result.reaction_to_attack is not None
        assert result.flee_grace_ticks >= 0
        assert 0.0 <= result.flee_threshold <= 1.0
        assert result.chase_max_distance >= 0
        assert result.chase_max_ticks >= 0
        assert result.chase_search_ticks >= 0


class TestPassiveBeast:
    """PASSIVE_BEAST: 攻撃しない平和な動物。"""

    def test_passive_beast_all_zero(self) -> None:
        """PASSIVEBEAST は反応無し全パラメータ 0。"""
        result = apply_temperament(_base_template(), TemperamentEnum.PASSIVE_BEAST)
        assert result.reaction_to_attack == ReactionPolicyEnum.PASSIVE
        assert result.flee_grace_ticks == 0
        assert result.chase_max_distance == 0
        assert result.chase_max_ticks == 0
        assert result.chase_search_ticks == 0


class TestCoward:
    """COWARD: 弱気、被弾即逃走、追跡しない。"""

    def test_coward_always_flee(self) -> None:
        """COWARD は ALWAYS FLEE 追跡無し。"""
        result = apply_temperament(_base_template(), TemperamentEnum.COWARD)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_FLEE
        assert result.flee_grace_ticks == 5
        assert result.chase_max_distance == 0
        assert result.chase_search_ticks == 0


class TestWary:
    """WARY: HP 低いと逃げ、HP 余裕なら短距離追跡。"""

    def test_wary_flee_when_low_hp(self) -> None:
        """WARY は FLEE WHEN LOW HP 短距離追跡。"""
        result = apply_temperament(_base_template(), TemperamentEnum.WARY)
        assert result.reaction_to_attack == ReactionPolicyEnum.FLEE_WHEN_LOW_HP
        assert result.flee_threshold == 0.3
        assert result.chase_max_distance == 2
        assert result.chase_max_ticks == 10
        assert result.chase_search_ticks == 2


class TestAggressive:
    """AGGRESSIVE: 普通の敵、中距離追跡。"""

    def test_aggressive_always_retaliate(self) -> None:
        """AGGRESSIVE は ALWAYS RETALIATE 中距離追跡。"""
        result = apply_temperament(_base_template(), TemperamentEnum.AGGRESSIVE)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert result.flee_grace_ticks == 5
        assert result.chase_max_distance == 5
        assert result.chase_max_ticks == 20
        assert result.chase_search_ticks == 3


class TestFerocious:
    """FEROCIOUS: 執念深い長距離追跡。"""

    def test_ferocious(self) -> None:
        """FEROCIOUS は長距離長時間追跡。"""
        result = apply_temperament(_base_template(), TemperamentEnum.FEROCIOUS)
        assert result.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert result.flee_grace_ticks == 10
        assert result.chase_max_distance == 15
        assert result.chase_max_ticks == 60
        assert result.chase_search_ticks == 8


class TestBerserker:
    """BERSERKER: 距離 / tick 無制限。"""

    def test_berserker_chase_max_distance_max_ticks_zero(
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

    def test_hp_attack_race_faction(self) -> None:
        """HP attack race faction 等は 変わらない。"""
        base = _base_template()
        result = apply_temperament(base, TemperamentEnum.AGGRESSIVE)
        assert result.template_id == base.template_id
        assert result.name == base.name
        assert result.base_stats.max_hp == base.base_stats.max_hp
        assert result.base_stats.attack == base.base_stats.attack
        assert result.race == base.race
        assert result.faction == base.faction
        assert result.description == base.description

    def test_apply_around_base_template(self) -> None:
        """`apply_temperament` は新しい template を返し、base は不変。"""
        base = _base_template()
        original_reaction = base.reaction_to_attack
        apply_temperament(base, TemperamentEnum.FEROCIOUS)
        # base はそのまま (immutable な dataclass)
        assert base.reaction_to_attack == original_reaction


class TestPostApplyOverride:
    """apply 後に dataclasses.replace で個別パラメータを上書きできる。"""

    def test_apply_after_chase_max_distance_can_override(self) -> None:
        """apply 後に chase max distance だけ 上書きできる。"""
        result = apply_temperament(_base_template(), TemperamentEnum.AGGRESSIVE)
        custom = replace(result, chase_max_distance=99)
        assert custom.chase_max_distance == 99
        # 他の AGGRESSIVE プリセット値は維持
        assert custom.reaction_to_attack == ReactionPolicyEnum.ALWAYS_RETALIATE
        assert custom.chase_max_ticks == 20


class TestIndependentApplications:
    """同じ base に異なる temperament を適用すると独立した結果。"""

    def test_returns_aggressive_coward_template(self) -> None:
        """AGGRESSIVE と COWARD は異なる template を返す。"""
        base = _base_template()
        a = apply_temperament(base, TemperamentEnum.AGGRESSIVE)
        c = apply_temperament(base, TemperamentEnum.COWARD)
        assert a.reaction_to_attack != c.reaction_to_attack
        assert a is not c
