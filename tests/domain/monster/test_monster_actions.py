import pytest
from src.domain.monster.monster import Monster
from src.domain.player.base_status import BaseStatus
from src.domain.monster.drop_reward import EMPTY_REWARD
from src.domain.battle.battle_enum import Element, Race
from src.infrastructure.repository.action_repository_impl import InMemoryActionRepository


class TestMonsterActions:
    def setup_method(self):
        self.action_repository = InMemoryActionRepository()

    def create_test_monster(self, available_action_ids=None):
        """テスト用Monsterを作成"""
        base_status = BaseStatus(attack=8, defense=8, speed=8, critical_rate=0.05, evasion_rate=0.05)

        return Monster(
            monster_type_id=1,
            name="TestMonster",
            description="テスト用モンスター",
            race=Race.GOBLIN,
            element=Element.NEUTRAL,
            base_status=base_status,
            max_hp=80,
            max_mp=30,
            available_action_ids=available_action_ids,
            drop_reward=EMPTY_REWARD,
            allowed_areas=[1]
        )

    def test_default_actions(self):
        """デフォルトでActionが空であること"""
        monster = self.create_test_monster()
        assert len(monster.get_available_action_ids()) == 0

    def test_get_available_action_ids(self):
        """利用可能なAction IDを取得できること"""
        monster = self.create_test_monster()
        action_ids = monster.get_available_action_ids()
        assert len(action_ids) == 0

    def test_custom_actions(self):
        """カスタムActionを設定できること"""
        custom_actions = [3, 4]  # 魔法攻撃と回復魔法
        monster = self.create_test_monster(available_action_ids=custom_actions)

        assert len(monster.get_available_action_ids()) == 2
        assert 3 in monster.get_available_action_ids()
        assert 4 in monster.get_available_action_ids()
