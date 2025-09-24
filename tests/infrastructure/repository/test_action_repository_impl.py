import pytest
from src.infrastructure.repository.action_repository_impl import ActionRepositoryImpl
from src.domain.player.player_enum import Role


class TestActionRepositoryImpl:
    def setup_method(self):
        """各テストメソッドの前に実行される"""
        self.repository = ActionRepositoryImpl()
    
    def test_get_action_cost(self):
        """アクションコスト取得"""
        # 設定済みのアクション
        assert self.repository.get_action_cost(1) == 1  # 基本攻撃
        assert self.repository.get_action_cost(4) == 2  # ファイアボール
        assert self.repository.get_action_cost(5) == 3  # メテオ
        
        # 未設定のアクション（デフォルト値）
        assert self.repository.get_action_cost(999) == 1
    
    def test_get_evolution_chain(self):
        """進化チェーン取得"""
        # ファイアボール -> メテオ
        chain = self.repository.get_evolution_chain(4)
        assert chain == [4, 5]
        
        # メテオ（最終形）
        chain = self.repository.get_evolution_chain(5)
        assert chain == [4, 5]
        
        # 進化チェーンが設定されていないアクション
        chain = self.repository.get_evolution_chain(999)
        assert chain == [999]  # 自分自身のみ
    
    def test_get_learnable_actions(self):
        """習得可能アクション取得"""
        # レベル1の錬金術師
        actions = self.repository.get_learnable_actions(1, Role.ALCHEMIST)
        assert set(actions) == {1, 2, 3, 4, 6}
        
        # レベル1の冒険者
        actions = self.repository.get_learnable_actions(1, Role.ADVENTURER)
        assert set(actions) == {1, 2, 3}
        
        # レベル5の錬金術師
        actions = self.repository.get_learnable_actions(5, Role.ALCHEMIST)
        assert set(actions) == {1, 2, 3, 4, 5, 6, 7}
        
        # 設定されていないレベル・職業
        actions = self.repository.get_learnable_actions(10, Role.ADVENTURER)
        assert set(actions) == {1, 2, 3}  # レベル1の内容のみ
    
    def test_get_evolution_requirements(self):
        """進化要件取得"""
        # ファイアボール -> メテオ
        requirements = self.repository.get_evolution_requirements(4)
        assert requirements == (100, 3)
        
        # ヒール -> フルヒール
        requirements = self.repository.get_evolution_requirements(6)
        assert requirements == (80, 2)
        
        # 進化できないアクション
        requirements = self.repository.get_evolution_requirements(1)
        assert requirements is None
    
    def test_get_evolved_action_id(self):
        """進化後アクションID取得"""
        # ファイアボール -> メテオ
        evolved_id = self.repository.get_evolved_action_id(4)
        assert evolved_id == 5
        
        # メテオ（最終形）
        evolved_id = self.repository.get_evolved_action_id(5)
        assert evolved_id is None
        
        # 進化チェーンが設定されていないアクション
        evolved_id = self.repository.get_evolved_action_id(999)
        assert evolved_id is None
    
    def test_is_basic_action(self):
        """基本アクション判定"""
        # 基本アクション
        assert self.repository.is_basic_action(1) == True
        assert self.repository.is_basic_action(2) == True
        assert self.repository.is_basic_action(3) == True
        
        # 基本アクションではない
        assert self.repository.is_basic_action(4) == False
        assert self.repository.is_basic_action(999) == False
    
    def test_add_learnable_action(self):
        """習得可能アクション追加（テスト用）"""
        # 新しい習得可能アクションを追加
        self.repository.add_learnable_action(2, Role.ADVENTURER, 10)
        
        actions = self.repository.get_learnable_actions(2, Role.ADVENTURER)
        assert 10 in actions
        
        # 重複追加しても問題ない
        self.repository.add_learnable_action(2, Role.ADVENTURER, 10)
        actions = self.repository.get_learnable_actions(2, Role.ADVENTURER)
        assert actions.count(10) == 1  # 1つだけ
    
    def test_set_evolution_requirement(self):
        """進化要件設定（テスト用）"""
        self.repository.set_evolution_requirement(10, 200, 5)
        requirements = self.repository.get_evolution_requirements(10)
        assert requirements == (200, 5)
    
    def test_add_evolution_chain(self):
        """進化チェーン追加（テスト用）"""
        self.repository.add_evolution_chain([10, 11, 12])
        
        # 各アクションから同じチェーンが取得される
        assert self.repository.get_evolution_chain(10) == [10, 11, 12]
        assert self.repository.get_evolution_chain(11) == [10, 11, 12]
        assert self.repository.get_evolution_chain(12) == [10, 11, 12]
        
        # 進化後のアクションIDも正しく取得される
        assert self.repository.get_evolved_action_id(10) == 11
        assert self.repository.get_evolved_action_id(11) == 12
        assert self.repository.get_evolved_action_id(12) is None  # 最終形
    
    def test_set_action_cost(self):
        """アクションコスト設定（テスト用）"""
        self.repository.set_action_cost(999, 5)
        assert self.repository.get_action_cost(999) == 5
