import pytest
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.player.message_box import MessageBox
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import Element


class TestPlayerSimple:
    """Playerクラスの基本機能テスト"""
    
    @pytest.fixture
    def sample_player(self):
        """サンプルプレイヤーを作成"""
        base_status = BaseStatus(
            attack=10,
            defense=8,
            speed=6,
            critical_rate=0.1,
            evasion_rate=0.05
        )
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
    
    def test_player_creation(self, sample_player):
        """プレイヤーの作成テスト"""
        assert sample_player._player_id == 1
        assert sample_player._name == "テストプレイヤー"
        assert sample_player._role == Role.ADVENTURER
        assert sample_player._current_spot_id == 1
        assert sample_player._race == Race.HUMAN
        assert sample_player._element == Element.NEUTRAL

    def test_player_status_calculation(self, sample_player):
        """プレイヤーのステータス計算テスト"""
        calculated_status = sample_player.calculate_status()
        
        # 装備なしの場合はベースステータスのまま
        assert calculated_status.attack == 10
        assert calculated_status.defense == 8
        assert calculated_status.speed == 6
        assert calculated_status.critical_rate == 0.1
        assert calculated_status.evasion_rate == 0.05

    def test_player_inventory_access(self, sample_player):
        """プレイヤーのインベントリアクセステスト"""
        # 初期状態では空
        assert len([slot for slot in sample_player._inventory.slots if not slot.is_empty()]) == 0
        
        # インベントリのサイズ確認
        assert sample_player._inventory.max_slots == 20

    def test_player_equipment_access(self, sample_player):
        """プレイヤーの装備アクセステスト"""
        # 初期状態では何も装備していない
        assert sample_player._equipment._weapon is None
        assert sample_player._equipment._helmet is None
        assert sample_player._equipment._chest is None
        assert sample_player._equipment._gloves is None
        assert sample_player._equipment._shoes is None
