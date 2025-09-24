import pytest
from src.domain.battle.action_mastery import ActionMastery


class TestActionMastery:
    def test_create_action_mastery(self):
        """ActionMasteryの正常作成"""
        mastery = ActionMastery(1, 100, 3)
        assert mastery.action_id == 1
        assert mastery.experience == 100
        assert mastery.level == 3
    
    def test_create_action_mastery_with_defaults(self):
        """デフォルト値でのActionMastery作成"""
        mastery = ActionMastery(1)
        assert mastery.action_id == 1
        assert mastery.experience == 0
        assert mastery.level == 1
    
    def test_invalid_action_id(self):
        """無効なaction_idでの作成"""
        with pytest.raises(ValueError):
            ActionMastery(0)
        with pytest.raises(ValueError):
            ActionMastery(-1)
    
    def test_invalid_experience(self):
        """無効なexperienceでの作成"""
        with pytest.raises(ValueError):
            ActionMastery(1, -1)
    
    def test_invalid_level(self):
        """無効なlevelでの作成"""
        with pytest.raises(ValueError):
            ActionMastery(1, 0, 0)
        with pytest.raises(ValueError):
            ActionMastery(1, 0, -1)
    
    def test_gain_experience(self):
        """経験値獲得"""
        mastery = ActionMastery(1, 50, 2)
        new_mastery = mastery.gain_experience(30)
        
        assert new_mastery.action_id == 1
        assert new_mastery.experience == 80
        assert new_mastery.level == 2  # レベルは変わらない
        
        # 元の習熟度は変更されない
        assert mastery.experience == 50
    
    def test_gain_experience_invalid(self):
        """無効な経験値獲得"""
        mastery = ActionMastery(1, 50, 2)
        with pytest.raises(ValueError):
            mastery.gain_experience(-10)
    
    def test_level_up(self):
        """レベルアップ"""
        mastery = ActionMastery(1, 100, 2)
        new_mastery = mastery.level_up()
        
        assert new_mastery.action_id == 1
        assert new_mastery.experience == 100  # 経験値は変わらない
        assert new_mastery.level == 3
        
        # 元の習熟度は変更されない
        assert mastery.level == 2
    
    def test_can_evolve(self):
        """進化可能判定"""
        mastery = ActionMastery(1, 100, 3)
        
        # 進化可能
        assert mastery.can_evolve(80, 2) == True  # 100 >= 80 and 3 >= 2
        assert mastery.can_evolve(100, 3) == True  # 100 >= 100 and 3 >= 3
        
        # 進化不可能
        assert mastery.can_evolve(120, 3) == False  # 100 < 120
        assert mastery.can_evolve(100, 4) == False  # 3 < 4
        assert mastery.can_evolve(120, 4) == False  # 両方とも不足
    
    def test_can_evolve_invalid_params(self):
        """無効なパラメータでの進化判定"""
        mastery = ActionMastery(1, 100, 3)
        
        with pytest.raises(ValueError):
            mastery.can_evolve(-10, 2)
        
        with pytest.raises(ValueError):
            mastery.can_evolve(100, 0)
    
    def test_reset_for_evolution(self):
        """進化時のリセット"""
        mastery = ActionMastery(1, 150, 5)
        reset_mastery = mastery.reset_for_evolution()
        
        assert reset_mastery.action_id == 1  # action_idは同じ
        assert reset_mastery.experience == 0
        assert reset_mastery.level == 1
        
        # 元の習熟度は変更されない
        assert mastery.experience == 150
        assert mastery.level == 5
