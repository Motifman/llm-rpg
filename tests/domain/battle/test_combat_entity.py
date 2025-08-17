import pytest
from src.domain.battle.combat_entity import CombatEntity
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import StatusEffectType, Element


class TestCombatEntity(CombatEntity):
    """テスト用のCombatEntityの具象クラス"""
    pass


class TestCombatEntityMPMethods:
    """CombatEntityのMP関連メソッドのテスト"""
    
    def setup_method(self):
        """テスト用のCombatEntityを作成"""
        base_status = BaseStatus(
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.1,
            evasion_rate=0.05
        )
        dynamic_status = DynamicStatus(
            hp=50,
            max_hp=100,
            mp=30,
            max_mp=50,
            exp=0,
            level=1,
            gold=0
        )
        
        self.entity = TestCombatEntity(
            name="テストエンティティ",
            race=Race.HUMAN,
            element=Element.NEUTRAL,
            current_spot_id=1,
            base_status=base_status,
            dynamic_status=dynamic_status
        )
    
    def test_recover_mp(self):
        """MP回復のテスト"""
        initial_mp = self.entity.mp
        assert initial_mp == 30
        
        # 通常の回復
        self.entity.recover_mp(10)
        assert self.entity.mp == 40
        
        # 最大値を超える回復（キャップされる）
        self.entity.recover_mp(20)
        assert self.entity.mp == 50  # max_mpでキャップされる
    
    def test_recover_mp_invalid_amount(self):
        """MP回復で無効な値を指定した場合のエラーテスト"""
        with pytest.raises(AssertionError, match="amount must be greater than 0"):
            self.entity.recover_mp(0)
        
        with pytest.raises(AssertionError, match="amount must be greater than 0"):
            self.entity.recover_mp(-5)
    
    def test_consume_mp(self):
        """MP消費のテスト"""
        initial_mp = self.entity.mp
        assert initial_mp == 30
        
        # 通常の消費
        self.entity.consume_mp(10)
        assert self.entity.mp == 20
        
        # 残りMPより多く消費（0でキャップされる）
        self.entity.consume_mp(25)
        assert self.entity.mp == 0
    
    def test_consume_mp_invalid_amount(self):
        """MP消費で無効な値を指定した場合のエラーテスト"""
        with pytest.raises(AssertionError, match="amount must be greater than 0"):
            self.entity.consume_mp(0)
        
        with pytest.raises(AssertionError, match="amount must be greater than 0"):
            self.entity.consume_mp(-3)
    
    def test_can_consume_mp(self):
        """MP消費可能かどうかのテスト"""
        assert self.entity.mp == 30
        
        # 十分なMPがある場合
        assert self.entity.can_consume_mp(10) is True
        assert self.entity.can_consume_mp(30) is True
        
        # MPが足りない場合
        assert self.entity.can_consume_mp(31) is False
        assert self.entity.can_consume_mp(50) is False
        
        # 境界値テスト
        assert self.entity.can_consume_mp(0) is True  # 0は常にTrue
        
        # MP消費後のテスト
        self.entity.consume_mp(20)
        assert self.entity.mp == 10
        assert self.entity.can_consume_mp(10) is True
        assert self.entity.can_consume_mp(11) is False
    
    def test_mp_methods_integration(self):
        """MP関連メソッドの統合テスト"""
        assert self.entity.mp == 30
        assert self.entity.max_mp == 50
        
        # MP消費 -> 回復のサイクル
        self.entity.consume_mp(15)
        assert self.entity.mp == 15
        
        self.entity.recover_mp(20)
        assert self.entity.mp == 35
        
        # 最大MPまで回復
        self.entity.recover_mp(20)
        assert self.entity.mp == 50
        
        # 全MP消費
        self.entity.consume_mp(50)
        assert self.entity.mp == 0
        
        # 0からの回復
        self.entity.recover_mp(25)
        assert self.entity.mp == 25
