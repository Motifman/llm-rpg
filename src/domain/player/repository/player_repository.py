from abc import abstractmethod
from typing import Optional, List
from src.domain.common.repository import Repository
from src.domain.player.aggregate.player import Player


class PlayerRepository(Repository[Player]):
    """プレイヤーリポジトリインターフェース"""
    
    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Player]:
        """名前でプレイヤーを検索"""
        pass
    
    @abstractmethod
    def find_by_spot_id(self, spot_id: int) -> List[Player]:
        """指定されたスポットにいるプレイヤーを検索"""
        pass

    @abstractmethod
    def find_by_battle_id(self, battle_id: int) -> List[Player]:
        """指定された戦闘に参加しているプレイヤーを検索"""
        pass

    @abstractmethod
    def find_by_role(self, role) -> List[Player]:
        """指定されたロールのプレイヤーを検索"""
        pass

    @abstractmethod
    def generate_player_id(self) -> int:
        """プレイヤーIDを生成"""
        pass