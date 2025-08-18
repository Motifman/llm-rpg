import pytest
from src.domain.item.item_effect import ItemEffect
from src.domain.battle.battle_enum import StatusEffectType


class TestItemEffect:
    """ItemEffectクラスのテスト"""
    
    def test_create_empty_effect(self):
        """空の効果を作成"""
        effect = ItemEffect()
        assert effect.hp_delta == 0
        assert effect.mp_delta == 0
        assert effect.gold_delta == 0
        assert effect.exp_delta == 0
        assert effect.status_effects == []
    
    def test_create_effect_with_basic_values(self):
        """基本値を持つエフェクトを作成"""
        effect = ItemEffect(
            hp_delta=50,
            mp_delta=30,
            gold_delta=100,
            exp_delta=25
        )
        assert effect.hp_delta == 50
        assert effect.mp_delta == 30
        assert effect.gold_delta == 100
        assert effect.exp_delta == 25
        assert effect.status_effects == []
    
    def test_create_effect_with_negative_values(self):
        """負の値を持つエフェクトを作成"""
        effect = ItemEffect(
            hp_delta=-10,
            mp_delta=-5,
            gold_delta=-50,
            exp_delta=-15
        )
        assert effect.hp_delta == -10
        assert effect.mp_delta == -5
        assert effect.gold_delta == -50
        assert effect.exp_delta == -15
    
    def test_create_effect_with_status_effects(self):
        """状態異常効果を持つエフェクトを作成"""
        status_effects = [
            StatusEffectType.POISON,
            StatusEffectType.BURN
        ]
        effect = ItemEffect(
            hp_delta=20,
            status_effects=status_effects
        )
        assert effect.hp_delta == 20
        assert len(effect.status_effects) == 2
        assert effect.status_effects[0] == StatusEffectType.POISON
        assert effect.status_effects[1] == StatusEffectType.BURN
    
    def test_get_effect_summary_empty(self):
        """空の効果の要約文字列"""
        effect = ItemEffect()
        assert effect.get_effect_summary() == "効果なし"
    
    def test_get_effect_summary_positive_values(self):
        """正の値の効果の要約文字列"""
        effect = ItemEffect(
            hp_delta=50,
            mp_delta=30,
            gold_delta=100,
            exp_delta=25
        )
        summary = effect.get_effect_summary()
        assert "効果: " in summary
        assert "HP+50" in summary
        assert "MP+30" in summary
        assert "所持金+100" in summary
        assert "経験値+25" in summary
    
    def test_get_effect_summary_negative_values(self):
        """負の値の効果の要約文字列"""
        effect = ItemEffect(
            hp_delta=-10,
            mp_delta=-5,
            gold_delta=-50,
            exp_delta=-15
        )
        summary = effect.get_effect_summary()
        assert "効果: " in summary
        assert "HP-10" in summary
        assert "MP-5" in summary
        assert "所持金-50" in summary
        assert "経験値-15" in summary
    
    def test_get_effect_summary_mixed_values(self):
        """正と負の値が混在する効果の要約文字列"""
        effect = ItemEffect(
            hp_delta=30,
            mp_delta=-10,
            gold_delta=0,  # 0の値は表示されない
            exp_delta=50
        )
        summary = effect.get_effect_summary()
        assert "効果: " in summary
        assert "HP+30" in summary
        assert "MP-10" in summary
        assert "所持金" not in summary  # 0なので表示されない
        assert "経験値+50" in summary
    
    def test_get_effect_summary_with_status_effects(self):
        """状態異常効果を含む要約文字列"""
        status_effects = [
            StatusEffectType.POISON,
            StatusEffectType.BURN
        ]
        effect = ItemEffect(
            hp_delta=20,
            status_effects=status_effects
        )
        summary = effect.get_effect_summary()
        assert "効果: " in summary
        assert "HP+20" in summary
        assert "poison" in summary
        assert "burn" in summary
    
    def test_get_effect_summary_only_status_effects(self):
        """状態異常効果のみの要約文字列"""
        status_effects = [
            StatusEffectType.BLESSING
        ]
        effect = ItemEffect(status_effects=status_effects)
        summary = effect.get_effect_summary()
        assert "効果: " in summary
        assert "blessing" in summary
        assert "HP" not in summary
        assert "MP" not in summary
    
    def test_immutable(self):
        """イミュータブルなオブジェクトであることを確認"""
        effect = ItemEffect(hp_delta=50)
        with pytest.raises(Exception):
            effect.hp_delta = 100
