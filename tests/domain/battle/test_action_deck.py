import pytest
from src.domain.battle.action_deck import ActionDeck
from src.domain.battle.action_slot import ActionSlot
from src.domain.battle.skill_capacity import SkillCapacity


class TestActionSlot:
    def test_create_action_slot(self):
        """ActionSlotの正常作成"""
        slot = ActionSlot(1, 2, 3)
        assert slot.action_id == 1
        assert slot.level == 2
        assert slot.cost == 3
    
    def test_create_action_slot_with_defaults(self):
        """デフォルト値でのActionSlot作成"""
        slot = ActionSlot(1)
        assert slot.action_id == 1
        assert slot.level == 1
        assert slot.cost == 1
    
    def test_invalid_action_id(self):
        """無効なaction_idでの作成"""
        with pytest.raises(ValueError):
            ActionSlot(0)
        with pytest.raises(ValueError):
            ActionSlot(-1)
    
    def test_invalid_level(self):
        """無効なlevelでの作成"""
        with pytest.raises(ValueError):
            ActionSlot(1, 0)
        with pytest.raises(ValueError):
            ActionSlot(1, -1)
    
    def test_invalid_cost(self):
        """無効なcostでの作成"""
        with pytest.raises(ValueError):
            ActionSlot(1, 1, 0)
        with pytest.raises(ValueError):
            ActionSlot(1, 1, -1)
    
    def test_with_level(self):
        """レベル変更"""
        slot = ActionSlot(1, 2, 3)
        new_slot = slot.with_level(5)
        assert new_slot.action_id == 1
        assert new_slot.level == 5
        assert new_slot.cost == 3
        # 元のスロットは変更されない
        assert slot.level == 2
    
    def test_with_cost(self):
        """コスト変更"""
        slot = ActionSlot(1, 2, 3)
        new_slot = slot.with_cost(5)
        assert new_slot.action_id == 1
        assert new_slot.level == 2
        assert new_slot.cost == 5
        # 元のスロットは変更されない
        assert slot.cost == 3


class TestSkillCapacity:
    def test_create_skill_capacity(self):
        """SkillCapacityの正常作成"""
        capacity = SkillCapacity(10)
        assert capacity.max_capacity == 10
    
    def test_invalid_max_capacity(self):
        """無効なmax_capacityでの作成"""
        with pytest.raises(ValueError):
            SkillCapacity(-1)
    
    def test_can_accommodate(self):
        """キャパシティ収容判定"""
        capacity = SkillCapacity(10)
        assert capacity.can_accommodate(5, 3) == True  # 3 + 5 = 8 <= 10
        assert capacity.can_accommodate(8, 3) == False  # 3 + 8 = 11 > 10
        assert capacity.can_accommodate(7, 3) == True  # 3 + 7 = 10 <= 10
    
    def test_can_accommodate_invalid_params(self):
        """無効なパラメータでの収容判定"""
        capacity = SkillCapacity(10)
        with pytest.raises(ValueError):
            capacity.can_accommodate(-1, 3)
        with pytest.raises(ValueError):
            capacity.can_accommodate(5, -1)
    
    def test_calculate_remaining(self):
        """残りキャパシティ計算"""
        capacity = SkillCapacity(10)
        assert capacity.calculate_remaining(3) == 7
        assert capacity.calculate_remaining(10) == 0
        assert capacity.calculate_remaining(12) == 0  # 負にならない
    
    def test_is_full(self):
        """満杯判定"""
        capacity = SkillCapacity(10)
        assert capacity.is_full(9) == False
        assert capacity.is_full(10) == True
        assert capacity.is_full(11) == True


class TestActionDeck:
    def test_create_empty_deck(self):
        """空のデッキ作成"""
        capacity = SkillCapacity(10)
        deck = ActionDeck([], capacity)
        assert deck.current_capacity_usage() == 0
        assert deck.remaining_capacity() == 10
        assert deck.is_empty() == True
        assert deck.slot_count() == 0
    
    def test_create_deck_with_slots(self):
        """スロット付きデッキ作成"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3), ActionSlot(2, 1, 2)]
        deck = ActionDeck(slots, capacity)
        assert deck.current_capacity_usage() == 5
        assert deck.remaining_capacity() == 5
        assert deck.slot_count() == 2
    
    def test_duplicate_action_ids(self):
        """重複するaction_idでの作成"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3), ActionSlot(1, 1, 2)]  # 同じaction_id
        with pytest.raises(ValueError):
            ActionDeck(slots, capacity)
    
    def test_exceed_capacity(self):
        """キャパシティ超過での作成"""
        capacity = SkillCapacity(5)
        slots = [ActionSlot(1, 1, 3), ActionSlot(2, 1, 3)]  # 合計6 > 5
        with pytest.raises(ValueError):
            ActionDeck(slots, capacity)
    
    def test_can_add_action(self):
        """アクション追加可能判定"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        
        # 追加可能
        assert deck.can_add_action(ActionSlot(2, 1, 5)) == True
        # キャパシティ不足
        assert deck.can_add_action(ActionSlot(2, 1, 8)) == False
        # 重複するaction_id
        assert deck.can_add_action(ActionSlot(1, 1, 2)) == False
    
    def test_add_action(self):
        """アクション追加"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        
        new_slot = ActionSlot(2, 1, 5)
        new_deck = deck.add_action(new_slot)
        
        assert new_deck.slot_count() == 2
        assert new_deck.current_capacity_usage() == 8
        assert new_deck.has_action(2) == True
        
        # 元のデッキは変更されない
        assert deck.slot_count() == 1
    
    def test_add_action_invalid(self):
        """無効なアクション追加"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        
        # キャパシティ不足
        with pytest.raises(ValueError):
            deck.add_action(ActionSlot(2, 1, 8))
        
        # 重複するaction_id
        with pytest.raises(ValueError):
            deck.add_action(ActionSlot(1, 1, 2))
    
    def test_remove_action(self):
        """アクション削除"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3), ActionSlot(2, 1, 2)]
        deck = ActionDeck(slots, capacity)
        
        new_deck = deck.remove_action(1)
        
        assert new_deck.slot_count() == 1
        assert new_deck.current_capacity_usage() == 2
        assert new_deck.has_action(1) == False
        assert new_deck.has_action(2) == True
        
        # 元のデッキは変更されない
        assert deck.slot_count() == 2
    
    def test_remove_action_not_found(self):
        """存在しないアクションの削除"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        
        with pytest.raises(ValueError):
            deck.remove_action(2)
    
    def test_update_action_slot(self):
        """アクションスロット更新"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3), ActionSlot(2, 1, 2)]
        deck = ActionDeck(slots, capacity)
        
        new_slot = ActionSlot(1, 3, 4)  # レベルとコストを変更
        new_deck = deck.update_action_slot(1, new_slot)
        
        updated_slot = new_deck.get_action_slot(1)
        assert updated_slot.level == 3
        assert updated_slot.cost == 4
        assert new_deck.current_capacity_usage() == 6  # 4 + 2
    
    def test_update_action_slot_invalid_action_id(self):
        """異なるaction_idでの更新"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        
        with pytest.raises(ValueError):
            deck.update_action_slot(1, ActionSlot(2, 1, 3))
    
    def test_update_action_slot_capacity_exceed(self):
        """キャパシティ超過での更新"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3), ActionSlot(2, 1, 2)]
        deck = ActionDeck(slots, capacity)
        
        with pytest.raises(ValueError):
            deck.update_action_slot(1, ActionSlot(1, 1, 9))  # 9 + 2 = 11 > 10
    
    def test_get_action_ids(self):
        """アクションIDリスト取得"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3), ActionSlot(3, 1, 2), ActionSlot(2, 1, 1)]
        deck = ActionDeck(slots, capacity)
        
        action_ids = deck.get_action_ids()
        assert set(action_ids) == {1, 2, 3}
        assert len(action_ids) == 3
    
    def test_get_action_slot(self):
        """アクションスロット取得"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 2, 3)]
        deck = ActionDeck(slots, capacity)
        
        slot = deck.get_action_slot(1)
        assert slot.action_id == 1
        assert slot.level == 2
        assert slot.cost == 3
        
        # 存在しないaction_id
        assert deck.get_action_slot(2) is None
    
    def test_has_action(self):
        """アクション所有判定"""
        capacity = SkillCapacity(10)
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        
        assert deck.has_action(1) == True
        assert deck.has_action(2) == False
    
    def test_is_full(self):
        """満杯判定"""
        capacity = SkillCapacity(5)
        
        # 満杯でない
        slots = [ActionSlot(1, 1, 3)]
        deck = ActionDeck(slots, capacity)
        assert deck.is_full() == False
        
        # 満杯
        slots = [ActionSlot(1, 1, 3), ActionSlot(2, 1, 2)]
        deck = ActionDeck(slots, capacity)
        assert deck.is_full() == True
