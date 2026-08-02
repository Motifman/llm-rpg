"""モンスター攻撃時の状態異常宣言が、不正値を構築時に拒否することを保証する。"""

import pytest

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterTemplateValidationException,
)
from ai_rpg_world.domain.monster.value_object.attack_status_effect_chance import (
    AttackStatusEffectChance,
)


class TestAttackStatusEffectChance:
    """攻撃時状態異常の種別・確率・継続時間・強度の不変条件を固定する。"""

    def test_accepts_complete_declaration(self) -> None:
        """有効な4項目を渡すと、型を保った不変な宣言を構築できる。"""
        effect = AttackStatusEffectChance(
            effect_type=StatusEffectType.POISON,
            chance=0.6,
            duration_ticks=10,
            value=1.5,
        )

        assert effect.effect_type is StatusEffectType.POISON
        assert effect.chance == 0.6
        assert effect.duration_ticks == 10
        assert effect.value == 1.5

    @pytest.mark.parametrize("chance", [-0.01, 1.01, True, "0.5"])
    def test_rejects_invalid_chance(self, chance: object) -> None:
        """確率が数値の0以上1以下でなければ、テンプレート検証例外を投げる。"""
        with pytest.raises(MonsterTemplateValidationException, match="chance"):
            AttackStatusEffectChance(
                effect_type=StatusEffectType.BLEEDING,
                chance=chance,  # type: ignore[arg-type]
                duration_ticks=12,
            )

    @pytest.mark.parametrize("duration_ticks", [0, -1, True, 1.5])
    def test_rejects_non_positive_integer_duration(
        self, duration_ticks: object,
    ) -> None:
        """継続tickが正の整数でなければ、テンプレート検証例外を投げる。"""
        with pytest.raises(MonsterTemplateValidationException, match="duration_ticks"):
            AttackStatusEffectChance(
                effect_type=StatusEffectType.BLEEDING,
                chance=0.5,
                duration_ticks=duration_ticks,  # type: ignore[arg-type]
            )

    def test_rejects_effect_type_string(self) -> None:
        """状態異常種別の文字列を直接渡すと、enumへの変換漏れとして拒否する。"""
        with pytest.raises(MonsterTemplateValidationException, match="effect_type"):
            AttackStatusEffectChance(
                effect_type="bleeding",  # type: ignore[arg-type]
                chance=0.5,
                duration_ticks=12,
            )

    @pytest.mark.parametrize("value", [True, "1.0"])
    def test_rejects_non_numeric_value(self, value: object) -> None:
        """強度が真偽値または文字列なら、暗黙変換せず拒否する。"""
        with pytest.raises(MonsterTemplateValidationException, match="value"):
            AttackStatusEffectChance(
                effect_type=StatusEffectType.BLEEDING,
                chance=0.5,
                duration_ticks=12,
                value=value,  # type: ignore[arg-type]
            )
