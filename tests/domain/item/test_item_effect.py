import pytest
from src.domain.item.item_effect import (
    ItemEffect, HealEffect, RecoverMpEffect, GoldEffect, ExpEffect, CompositeItemEffect
)
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox
from src.domain.player.player_enum import Role
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import Element


class TestItemEffect:
    """ItemEffectクラスのテスト"""
    
    @pytest.fixture
    def sample_player(self):
        """テスト用のプレイヤーを作成"""
        base_status = BaseStatus(attack=10, defense=8, speed=6, critical_rate=0.1, evasion_rate=0.05)
        dynamic_status = DynamicStatus.new_game(max_hp=100, max_mp=50, max_exp=1000, initial_level=1)
        inventory = Inventory.create_empty(20)
        equipment_set = EquipmentSet()
        message_box = MessageBox()
        
        return Player(
            player_id=1,
            name="テストプレイヤー",
            role=Role.ADVENTURER,
            current_spot_id=1,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box,
            race=Race.HUMAN,
            element=Element.NEUTRAL
        )
    
    def test_heal_effect(self, sample_player):
        """回復効果のテスト"""
        # プレイヤーにダメージを与える
        sample_player.take_damage(30)
        initial_hp = sample_player._dynamic_status._hp.value
        
        # 回復効果を適用
        heal_effect = HealEffect(20)
        heal_effect.apply(sample_player)
        
        # HPが回復したことを確認
        assert sample_player._dynamic_status._hp.value == initial_hp + 20
    
    def test_heal_effect_validation(self):
        """回復効果のバリデーションテスト"""
        with pytest.raises(ValueError):
            HealEffect(-1)  # 負の値はエラー
    
    def test_recover_mp_effect(self, sample_player):
        """MP回復効果のテスト"""
        # プレイヤーのMPを消費
        sample_player._dynamic_status.consume_mp(20)
        initial_mp = sample_player._dynamic_status._mp.value
        
        # MP回復効果を適用
        mp_effect = RecoverMpEffect(15)
        mp_effect.apply(sample_player)
        
        # MPが回復したことを確認
        assert sample_player._dynamic_status._mp.value == initial_mp + 15
    
    def test_gold_effect(self, sample_player):
        """所持金増加効果のテスト"""
        initial_gold = sample_player._dynamic_status._gold.value
        
        # 所持金増加効果を適用
        gold_effect = GoldEffect(100)
        gold_effect.apply(sample_player)
        
        # 所持金が増加したことを確認
        assert sample_player._dynamic_status._gold.value == initial_gold + 100
    
    def test_exp_effect(self, sample_player):
        """経験値増加効果のテスト"""
        initial_exp = sample_player._dynamic_status._exp.value
        
        # 経験値増加効果を適用
        exp_effect = ExpEffect(50)
        exp_effect.apply(sample_player)
        
        # 経験値が増加したことを確認
        assert sample_player._dynamic_status._exp.value == initial_exp + 50
    
    def test_composite_effect(self, sample_player):
        """複合効果のテスト"""
        # プレイヤーにダメージを与える
        sample_player.take_damage(20)
        initial_hp = sample_player._dynamic_status._hp.value
        initial_gold = sample_player._dynamic_status._gold.value
        
        # 複合効果を作成（HP回復 + 所持金増加）
        heal_effect = HealEffect(15)
        gold_effect = GoldEffect(50)
        composite_effect = CompositeItemEffect([heal_effect, gold_effect])
        
        # 複合効果を適用
        composite_effect.apply(sample_player)
        
        # 両方の効果が適用されたことを確認
        assert sample_player._dynamic_status._hp.value == initial_hp + 15
        assert sample_player._dynamic_status._gold.value == initial_gold + 50
    
    def test_composite_effect_empty(self, sample_player):
        """空の複合効果のテスト"""
        initial_hp = sample_player._dynamic_status._hp.value
        
        # 空の複合効果を作成
        composite_effect = CompositeItemEffect([])
        
        # 効果を適用（何も変化しないはず）
        composite_effect.apply(sample_player)
        
        # 変化がないことを確認
        assert sample_player._dynamic_status._hp.value == initial_hp