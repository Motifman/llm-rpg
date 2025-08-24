from typing import TYPE_CHECKING, Set, Dict
from src.domain.common.aggregate_root import AggregateRoot

if TYPE_CHECKING:
    from src.domain.spot.spot import Spot

class Area(AggregateRoot):
    def __init__(
        self,
        area_id: int,
        name: str,
        description: str,
    ):
        super().__init__()
        self._area_id = area_id
        self._name = name
        self._description = description
        self._spot_ids = set()
    
    @property
    def area_id(self) -> int:
        return self._area_id

    # エリア内のスポット管理
    def add_spot(self, spot_id: int):
        """エリアにスポットを追加"""
        self.spot_ids.add(spot_id)
    
    def remove_spot(self, spot_id: int):
        """エリアからスポットを削除"""
        self.spot_ids.discard(spot_id)
    
    def contains_spot(self, spot_id: int) -> bool:
        """指定されたスポットがエリア内にあるかチェック"""
        return spot_id in self.spot_ids
    
    def get_spot_count(self) -> int:
        """エリア内のスポット数を取得"""
        return len(self.spot_ids)
    
    def is_empty(self) -> bool:
        """エリアが空かどうかチェック"""
        return len(self.spot_ids) == 0
    
    # プレイヤー管理（エリア全体での状況把握）
    def get_player_count_in_area(self, spots: Dict[int, "Spot"]) -> int:
        """エリア内の全プレイヤー数を取得"""
        total_players = 0
        for spot_id in self.spot_ids:
            if spot_id in spots:
                total_players += spots[spot_id].get_current_player_count()
        return total_players
    
    def get_all_players_in_area(self, spots: Dict[int, "Spot"]) -> Set[int]:
        """エリア内の全プレイヤーIDを取得"""
        all_players = set()
        for spot_id in self.spot_ids:
            if spot_id in spots:
                all_players.update(spots[spot_id].get_current_player_ids())
        return all_players
    
    def is_player_in_area(self, player_id: int, spots: Dict[int, "Spot"]) -> bool:
        """指定されたプレイヤーがエリア内にいるかチェック"""
        for spot_id in self.spot_ids:
            if spot_id in spots and spots[spot_id].is_player_in_spot(player_id):
                return True
        return False