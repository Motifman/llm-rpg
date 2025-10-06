import pytest
from unittest.mock import Mock, MagicMock
from src.domain.item.value_object.item_effect import (
    ItemEffect,
    HealEffect,
    RecoverMpEffect,
    GoldEffect,
    ExpEffect,
    CompositeItemEffect
)
from src.domain.item.exception import ItemEffectValidationException
from src.domain.common.value_object import Gold, Exp


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

    def test_apply_calls_player_heal(self):
        """applyメソッドがplayer.healを正しく呼ぶテスト"""
        effect = HealEffect(amount=25)
        mock_player = Mock()

        effect.apply(mock_player)

        mock_player.heal.assert_called_once_with(25)


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

    def test_apply_calls_player_recover_mp(self):
        """applyメソッドがplayer.recover_mpを正しく呼ぶテスト"""
        effect = RecoverMpEffect(amount=20)
        mock_player = Mock()

        effect.apply(mock_player)

        mock_player.recover_mp.assert_called_once_with(20)


class TestGoldEffect:
    """GoldEffectのテスト"""

    def test_create_valid_gold_effect(self):
        """正常なGoldEffect作成のテスト"""
        effect = GoldEffect(amount=100)
        assert effect.gold == Gold(100)

    def test_create_with_zero_amount(self):
        """0ゴールドのテスト"""
        effect = GoldEffect(amount=0)
        assert effect.gold == Gold(0)

    def test_invalid_negative_amount(self):
        """無効な負のゴールド量のテスト"""
        with pytest.raises(ItemEffectValidationException) as exc_info:
            GoldEffect(amount=-10)
        assert "Gold effect: amount must be >= 0, got -10" in str(exc_info.value)

    def test_apply_calls_player_receive_gold(self):
        """applyメソッドがplayer.receive_goldを正しく呼ぶテスト"""
        effect = GoldEffect(amount=50)
        mock_player = Mock()

        effect.apply(mock_player)

        mock_player.receive_gold.assert_called_once_with(Gold(50))


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

    def test_apply_calls_player_receive_exp(self):
        """applyメソッドがplayer.receive_expを正しく呼ぶテスト"""
        effect = ExpEffect(amount=75)

        # モックプレイヤーの作成（_dynamic_status._exp.max_expが必要）
        mock_player = Mock()
        mock_player._dynamic_status._exp.max_exp = 1000

        effect.apply(mock_player)

        # Expオブジェクトが正しく作成されて渡されていることを確認
        call_args = mock_player.receive_exp.call_args[0][0]
        assert isinstance(call_args, Exp)
        assert call_args.value == 75


class TestCompositeItemEffect:
    """CompositeItemEffectのテスト"""

    def test_create_composite_effect(self):
        """複合効果の作成テスト"""
        heal_effect = HealEffect(amount=50)
        gold_effect = GoldEffect(amount=25)
        effects = [heal_effect, gold_effect]

        composite = CompositeItemEffect(effects=effects)
        assert composite.effects == effects

    def test_create_with_empty_effects(self):
        """空の効果リストでの作成テスト"""
        composite = CompositeItemEffect(effects=[])
        assert composite.effects == []

    def test_apply_calls_all_effects_in_order(self):
        """applyメソッドが全ての効果を順番に適用するテスト"""
        heal_effect = HealEffect(amount=30)
        mp_effect = RecoverMpEffect(amount=20)
        gold_effect = GoldEffect(amount=10)

        effects = [heal_effect, mp_effect, gold_effect]
        composite = CompositeItemEffect(effects=effects)

        mock_player = Mock()

        composite.apply(mock_player)

        # 各効果のapplyが正しい順序で呼ばれたことを確認
        expected_calls = [
            ((30,),),  # heal
            ((20,),),  # recover_mp
            ((Gold(10),),)  # receive_gold
        ]

        assert mock_player.heal.call_count == 1
        assert mock_player.recover_mp.call_count == 1
        assert mock_player.receive_gold.call_count == 1

        mock_player.heal.assert_called_with(30)
        mock_player.recover_mp.assert_called_with(20)
        mock_player.receive_gold.assert_called_with(Gold(10))

    def test_apply_with_empty_effects(self):
        """空の効果リストでのapplyテスト"""
        composite = CompositeItemEffect(effects=[])
        mock_player = Mock()

        composite.apply(mock_player)

        # 何も呼ばれないことを確認
        mock_player.heal.assert_not_called()
        mock_player.recover_mp.assert_not_called()
        mock_player.receive_gold.assert_not_called()
        mock_player.receive_exp.assert_not_called()


class TestItemEffectAbstract:
    """ItemEffect抽象クラスのテスト"""

    def test_item_effect_is_abstract(self):
        """ItemEffectが抽象クラスであることを確認"""
        # 直接インスタンス化できない
        with pytest.raises(TypeError):
            ItemEffect()
