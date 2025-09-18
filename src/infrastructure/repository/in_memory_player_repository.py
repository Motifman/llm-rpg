"""
InMemoryPlayerRepository - 実際のPlayerクラスを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from src.domain.player.player_repository import PlayerRepository
from src.domain.player.player import Player
from src.domain.player.player_enum import Role, PlayerState
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory, InventorySlot
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.message_box import MessageBox
from src.domain.battle.action_deck import ActionDeck
from src.domain.battle.action_mastery import ActionMastery
from src.domain.battle.action_slot import ActionSlot
from src.domain.battle.skill_capacity import SkillCapacity
from src.domain.battle.battle_enum import Race, Element
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.common.value_object import Level, Exp, Gold


class InMemoryPlayerRepository(PlayerRepository):
    """実際のPlayerクラスを使用するインメモリリポジトリ"""
    
    def __init__(self):
        self._players: Dict[int, Player] = {}
        self._next_id = 1
        
        # サンプルプレイヤーデータを作成
        self._setup_sample_data()
    
    def _setup_sample_data(self):
        """サンプルプレイヤーデータのセットアップ"""
        # プレイヤー1: 冒険者
        player1 = self._create_sample_player(
            player_id=1,
            name="アリス",
            role=Role.ADVENTURER,
            spot_id=100,
            race=Race.HUMAN,
            element=Element.FIRE
        )
        self._players[1] = player1
        
        # プレイヤー2: 冒険者
        player2 = self._create_sample_player(
            player_id=2,
            name="ボブ",
            role=Role.ADVENTURER,
            spot_id=100,  # 同じスポットに配置
            race=Race.HUMAN,
            element=Element.WATER
        )
        self._players[2] = player2
        
        # プレイヤー3: 商人
        player3 = self._create_sample_player(
            player_id=3,
            name="チャーリー",
            role=Role.MERCHANT,
            spot_id=101,
            race=Race.HUMAN,
            element=Element.EARTH
        )
        self._players[3] = player3
        
        self._next_id = 4
    
    def _create_sample_player(
        self, 
        player_id: int, 
        name: str, 
        role: Role, 
        spot_id: int,
        race: Race = Race.HUMAN,
        element: Element = Element.NEUTRAL
    ) -> Player:
        """サンプルプレイヤーを作成"""
        # 基礎ステータス
        base_status = BaseStatus(
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )
        
        # 動的ステータス
        dynamic_status = DynamicStatus(
            level=Level(5),
            exp=Exp(100),
            gold=Gold(1000),
            hp=Hp(100, 100),
            mp=Mp(50, 50)
        )
        
        # インベントリ（空のスロットで初期化）
        empty_slots = [InventorySlot.create_empty(i) for i in range(50)]
        inventory = Inventory(slots=empty_slots, max_slots=50)
        
        # 装備セット（空）
        equipment_set = EquipmentSet()
        
        # メッセージボックス（空）
        message_box = MessageBox()
        
        # アクションデッキ（基本攻撃のみ）
        capacity = SkillCapacity(max_capacity=10)
        basic_attack_slot = ActionSlot(action_id=1, level=1, cost=1)  # 基本攻撃
        action_deck = ActionDeck(slots=[basic_attack_slot], capacity=capacity)
        
        # アクション習熟度
        action_masteries = {
            1: ActionMastery(action_id=1, experience=0, level=1)
        }
        
        return Player(
            player_id=player_id,
            name=name,
            role=role,
            current_spot_id=spot_id,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box,
            action_deck=action_deck,
            action_masteries=action_masteries,
            race=race,
            element=element
        )
    
    def find_by_id(self, player_id: int) -> Optional[Player]:
        """プレイヤーIDでプレイヤーを検索"""
        return self._players.get(player_id)
    
    def find_by_name(self, name: str) -> Optional[Player]:
        """名前でプレイヤーを検索"""
        for player in self._players.values():
            if player.name == name:
                return player
        return None
    
    def find_by_spot_id(self, spot_id: int) -> List[Player]:
        """指定されたスポットにいるプレイヤーを検索"""
        return [player for player in self._players.values()
                if player.current_spot_id == spot_id]
    
    def find_by_battle_id(self, battle_id: int) -> List[Player]:
        """指定された戦闘に参加しているプレイヤーを検索"""
        # 簡易実装: 戦闘状態のプレイヤーを返す
        return [player for player in self._players.values()
                if player.player_state == PlayerState.BATTLE]
    
    def find_by_role(self, role: Role) -> List[Player]:
        """指定されたロールのプレイヤーを検索"""
        return [player for player in self._players.values() if player.role == role]
    
    def save(self, player: Player) -> Player:
        """プレイヤーを保存"""
        self._players[player.player_id] = player
        return player
    
    def delete(self, player_id: int) -> bool:
        """プレイヤーを削除"""
        if player_id in self._players:
            del self._players[player_id]
            return True
        return False
    
    def find_all(self) -> List[Player]:
        """全てのプレイヤーを取得"""
        return list(self._players.values())
    
    def exists_by_id(self, player_id: int) -> bool:
        """プレイヤーIDが存在するかチェック"""
        return player_id in self._players
    
    def exists_by_name(self, name: str) -> bool:
        """名前が存在するかチェック"""
        return any(player.name == name for player in self._players.values())
    
    def count(self) -> int:
        """プレイヤーの総数を取得"""
        return len(self._players)
    
    def find_by_ids(self, player_ids: List[int]) -> List[Player]:
        """複数のプレイヤーIDでプレイヤーを検索"""
        result = []
        for player_id in player_ids:
            player = self._players.get(player_id)
            if player:
                result.append(player)
        return result
    
    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのプレイヤーを削除（テスト用）"""
        self._players.clear()
        self._next_id = 1
    
    def generate_player_id(self) -> int:
        """新しいプレイヤーIDを生成"""
        player_id = self._next_id
        self._next_id += 1
        return player_id
