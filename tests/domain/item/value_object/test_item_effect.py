import pytest

from ai_rpg_world.domain.item.exception import ItemEffectValidationException
from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ExpEffect,
    GoldEffect,
    HealEffect,
    ItemEffect,
    RecoverMpEffect,
)


class TestHealEffect:
    """HealEffectのテスト"""

    def test_create_valid_heal_effect(self):
        """正常なHealEffect作成のテスト"""
        effect = HealEffect(amount=50)
        assert effect.amount == 50

    def test_create_with_zero_amount(self):
        """0回復のテスト"""
        effect = HealEffect(amount=0)
        assert effect.amount == 0

    def test_invalid_negative_amount(self):
        """無効な負の回復量のテスト"""
        with pytest.raises(ItemEffectValidationException) as exc_info:
            HealEffect(amount=-1)
        assert "Heal effect: amount must be >= 0, got -1" in str(exc_info.value)


class TestRecoverMpEffect:
    """RecoverMpEffectのテスト"""

    def test_create_valid_recover_mp_effect(self):
        """正常なRecoverMpEffect作成のテスト"""
        effect = RecoverMpEffect(amount=30)
        assert effect.amount == 30

    def test_create_with_zero_amount(self):
        """0MP回復のテスト"""
        effect = RecoverMpEffect(amount=0)
        assert effect.amount == 0

    def test_invalid_negative_amount(self):
        """無効な負のMP回復量のテスト"""
        with pytest.raises(ItemEffectValidationException) as exc_info:
            RecoverMpEffect(amount=-5)
        assert "Recover MP effect: amount must be >= 0, got -5" in str(exc_info.value)


class TestGoldEffect:
    """GoldEffectのテスト"""

    def test_create_valid_gold_effect(self):
        """正常なGoldEffect作成のテスト"""
        effect = GoldEffect(amount=100)
        assert effect.amount == 100

    def test_create_with_zero_amount(self):
        """0ゴールドのテスト"""
        effect = GoldEffect(amount=0)
        assert effect.amount == 0

    def test_invalid_negative_amount(self):
        """無効な負のゴールド量のテスト"""
        with pytest.raises(ItemEffectValidationException) as exc_info:
            GoldEffect(amount=-10)
        assert "Gold effect: amount must be >= 0, got -10" in str(exc_info.value)


class TestExpEffect:
    """ExpEffectのテスト"""

    def test_create_valid_exp_effect(self):
        """正常なExpEffect作成のテスト"""
        effect = ExpEffect(amount=100)
        assert effect.amount == 100

    def test_create_with_zero_amount(self):
        """0経験値のテスト"""
        effect = ExpEffect(amount=0)
        assert effect.amount == 0

    def test_invalid_negative_amount(self):
        """無効な負の経験値量のテスト"""
        with pytest.raises(ItemEffectValidationException) as exc_info:
            ExpEffect(amount=-25)
        assert "Exp effect: amount must be >= 0, got -25" in str(exc_info.value)


class TestCompositeItemEffect:
    """CompositeItemEffectのテスト"""

    def test_create_composite_effect(self):
        """複合効果の作成テスト（リストでもタプルでも受け付ける）"""
        heal_effect = HealEffect(amount=50)
        gold_effect = GoldEffect(amount=25)
        effects = [heal_effect, gold_effect]

        composite = CompositeItemEffect(effects=effects)
        assert composite.effects == (heal_effect, gold_effect)

    def test_create_with_empty_effects(self):
        """空の効果リストでの作成テスト"""
        composite = CompositeItemEffect(effects=[])
        assert composite.effects == ()

    def test_create_with_tuple(self):
        """タプルで渡した場合もそのまま受け付ける"""
        heal_effect = HealEffect(amount=30)
        composite = CompositeItemEffect(effects=(heal_effect,))
        assert composite.effects == (heal_effect,)

    def test_effects_none_raises(self):
        """effects が None の場合は ItemEffectValidationException"""
        with pytest.raises(ItemEffectValidationException) as exc_info:
            CompositeItemEffect(effects=None)  # type: ignore[arg-type]
        assert "effects must not be None" in str(exc_info.value)

    def test_effects_contains_non_item_effect_raises(self):
        """effects に ItemEffect 以外が含まれる場合は ItemEffectValidationException"""
        heal_effect = HealEffect(amount=50)
        with pytest.raises(ItemEffectValidationException) as exc_info:
            CompositeItemEffect(effects=(heal_effect, "invalid"))  # type: ignore[arg-type]
        assert "must be ItemEffect" in str(exc_info.value)
        assert "effects[1]" in str(exc_info.value)

    def test_effects_contains_int_raises(self):
        """effects に int が含まれる場合は ItemEffectValidationException"""
        heal_effect = HealEffect(amount=50)
        with pytest.raises(ItemEffectValidationException) as exc_info:
            CompositeItemEffect(effects=(heal_effect, 1))  # type: ignore[arg-type]
        assert "must be ItemEffect" in str(exc_info.value)

    def test_nested_composite_effect(self):
        """CompositeItemEffect がネストされていても正しく作成される"""
        inner = CompositeItemEffect(effects=(HealEffect(amount=10), GoldEffect(amount=5)))
        outer = CompositeItemEffect(effects=(inner, ExpEffect(amount=20)))
        assert len(outer.effects) == 2
        assert outer.effects[0] == inner
        assert outer.effects[1].amount == 20


class TestItemEffectAbstract:
    """ItemEffect抽象クラスのテスト"""

    def test_item_effect_is_abstract(self):
        """ItemEffectが抽象クラスであることを確認"""
        # 直接インスタンス化できない
        with pytest.raises(TypeError):
            ItemEffect()
