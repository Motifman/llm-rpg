import pytest
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.player.message_box import MessageBox
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.infrastructure.repository.action_repository_impl import InMemoryActionRepository
from src.domain.common.value_object import Exp, Gold, Level


class TestPlayerActions:
    def setup_method(self):
        self.action_repository = InMemoryActionRepository()

    def create_test_player(self, learned_action_ids=None):
        """テスト用Playerを作成"""
        base_status = BaseStatus(attack=10, defense=10, speed=10, critical_rate=0.1, evasion_rate=0.1)
        dynamic_status = DynamicStatus(
            hp=Hp(100, 100),
            mp=Mp(50, 50),
            exp=Exp(0),
            gold=Gold(0),
            level=Level(1)
        )
        inventory = Inventory([], 20)  # 空のスロット、最大20スロット
        equipment_set = EquipmentSet()
        message_box = MessageBox()

        return Player(
            player_id=1,
            name="TestPlayer",
            role=Role.ADVENTURER,
            current_spot_id=1,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box,
            learned_action_ids=learned_action_ids
        )

    def test_default_actions(self):
        """デフォルトでActionが空であること"""
        player = self.create_test_player()
        assert len(player.learned_action_ids) == 0

    def test_get_available_action_ids(self):
        """利用可能なAction IDを取得できること"""
        player = self.create_test_player()
        action_ids = player.get_available_action_ids()
        assert len(action_ids) == 0

    def test_learn_action(self):
        """Actionを学習できること"""
        player = self.create_test_player()

        result = player.learn_action(3)  # 魔法攻撃
        assert result is True
        assert 3 in player.learned_action_ids

    def test_learn_duplicate_action(self):
        """既に学習済みのActionを学習しようとするとFalseが返ること"""
        player = self.create_test_player()
        player.learn_action(1)  # 基本攻撃を学習

        result = player.learn_action(1)  # 同じものを学習しようとする
        assert result is False  # 既に学習済み

    def test_can_use_action(self):
        """Actionが使用可能かどうか確認できること"""
        player = self.create_test_player()

        assert player.can_use_action(1) is False  # まだ学習していない

        player.learn_action(1)  # 基本攻撃を学習
        assert player.can_use_action(1) is True

    def test_custom_actions(self):
        """カスタムActionを設定できること"""
        custom_actions = [3, 4]  # 魔法攻撃と回復魔法
        player = self.create_test_player(learned_action_ids=custom_actions)

        assert len(player.learned_action_ids) == 2
        assert 3 in player.learned_action_ids
        assert 4 in player.learned_action_ids
