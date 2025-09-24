import pytest
from src.infrastructure.repository.action_repository_impl import InMemoryActionRepository


class TestInMemoryActionRepository:
    def setup_method(self):
        self.repository = InMemoryActionRepository()

    def test_find_basic_attack(self):
        """基本攻撃を取得できること"""
        action = self.repository.find_by_id(1)
        assert action is not None
        assert action.name == "基本攻撃"
        assert action.action_id == 1

    def test_find_defend(self):
        """防御を取得できること"""
        action = self.repository.find_by_id(2)
        assert action is not None
        assert action.name == "防御"
        assert action.action_id == 2

    def test_find_by_ids(self):
        """複数のActionを取得できること"""
        action_ids = [1, 2]
        actions = self.repository.find_by_ids(action_ids)
        assert len(actions) == 2
        assert actions[0].action_id == 1
        assert actions[1].action_id == 2

    def test_get_basic_actions(self):
        """基本Actionを取得できること"""
        actions = self.repository.get_basic_actions()
        assert len(actions) == 2
        action_ids = [action.action_id for action in actions]
        assert 1 in action_ids  # 基本攻撃
        assert 2 in action_ids  # 防御

    def test_get_all_actions(self):
        """全てのActionを取得できること"""
        actions = self.repository.get_all_actions()
        assert len(actions) == 4  # 基本攻撃、防御、魔法攻撃、回復魔法

    def test_find_nonexistent_action(self):
        """存在しないActionを取得しようとするとNoneが返ること"""
        action = self.repository.find_by_id(999)
        assert action is None

    def test_find_by_ids_with_invalid_id(self):
        """無効なIDを含む場合、有効なActionのみ取得できること"""
        action_ids = [1, 999, 2]
        actions = self.repository.find_by_ids(action_ids)
        assert len(actions) == 2
        action_ids_result = [action.action_id for action in actions]
        assert 1 in action_ids_result
        assert 2 in action_ids_result
