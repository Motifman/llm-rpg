import pytest
from src.domain.battle.combat_state import CombatState
from src.domain.player.player import Player
from src.domain.monster.monster import Monster
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.player.message_box import MessageBox
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.monster.drop_reward import EMPTY_REWARD
from src.domain.battle.battle_enum import Element, Race, ParticipantType
from src.infrastructure.repository.action_repository_impl import InMemoryActionRepository
from src.domain.common.value_object import Exp, Gold, Level


class TestCombatStateActions:
    def setup_method(self):
        self.action_repository = InMemoryActionRepository()

    def create_test_player(self):
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

        player = Player(
            player_id=1,
            name="TestPlayer",
            role=Role.ADVENTURER,
            current_spot_id=1,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box,
            learned_action_ids=[1, 2]  # 基本攻撃と防御
        )
        return player

    def create_test_monster(self):
        """テスト用Monsterを作成"""
        base_status = BaseStatus(attack=8, defense=8, speed=8, critical_rate=0.05, evasion_rate=0.05)

        monster = Monster(
            monster_type_id=1,
            name="TestMonster",
            description="テスト用モンスター",
            race=Race.GOBLIN,
            element=Element.NEUTRAL,
            base_status=base_status,
            max_hp=80,
            max_mp=30,
            available_action_ids=[1, 2],  # 基本攻撃と防御
            drop_reward=EMPTY_REWARD,
            allowed_areas=[1]
        )
        return monster

    def test_from_player_with_actions(self):
        """PlayerからCombatStateを作成するとActionデッキが設定されること"""
        player = self.create_test_player()
        actions = self.action_repository.find_by_ids(player.get_available_action_ids())
        combat_state = CombatState.from_player(player, 1, actions)

        assert combat_state.entity_id == 1
        assert combat_state.participant_type == ParticipantType.PLAYER
        assert len(combat_state.available_actions) == 2
        action_names = [action.name for action in combat_state.available_actions]
        assert "基本攻撃" in action_names
        assert "防御" in action_names

    def test_from_monster_with_actions(self):
        """MonsterからCombatStateを作成するとActionデッキが設定されること"""
        monster = self.create_test_monster()
        actions = self.action_repository.find_by_ids(monster.get_available_action_ids())
        combat_state = CombatState.from_monster(monster, 1, actions)

        assert combat_state.entity_id == 1
        assert combat_state.participant_type == ParticipantType.MONSTER
        assert len(combat_state.available_actions) == 2
        action_names = [action.name for action in combat_state.available_actions]
        assert "基本攻撃" in action_names
        assert "防御" in action_names
