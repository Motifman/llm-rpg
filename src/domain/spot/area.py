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
        spawn_monster_type_ids: Set[int],
    ):
        super().__init__()
        self._area_id = area_id
        self._name = name
        self._description = description
        self._spot_ids: Set[int] = set()
        self._spawn_monster_type_ids: Set[int] = spawn_monster_type_ids

    @property
    def area_id(self) -> int:
        return self._area_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def spot_ids(self) -> Set[int]:
        return self._spot_ids

    # ===== エリア内のスポット管理 =====
    def add_spot(self, spot_id: int):
        """エリアにスポットを追加"""
        self._spot_ids.add(spot_id)
    
    def remove_spot(self, spot_id: int):
        """エリアからスポットを削除"""
        self._spot_ids.discard(spot_id)
    
    def contains_spot(self, spot_id: int) -> bool:
        """指定されたスポットがエリア内にあるかチェック"""
        return spot_id in self._spot_ids
    
    def get_spot_count(self) -> int:
        """エリア内のスポット数を取得"""
        return len(self._spot_ids)
    
    def is_empty(self) -> bool:
        """エリアが空かどうかチェック"""
        return len(self._spot_ids) == 0
    
    # ===== プレイヤー管理（エリア全体での状況把握） =====
    def get_player_count_in_area(self, spots: Dict[int, "Spot"]) -> int:
        """エリア内の全プレイヤー数を取得"""
        total_players = 0
        for spot_id in self._spot_ids:
            if spot_id in spots:
                total_players += spots[spot_id].get_current_player_count()
        return total_players
    
    def get_all_players_in_area(self, spots: Dict[int, "Spot"]) -> Set[int]:
        """エリア内の全プレイヤーIDを取得"""
        all_players = set()
        for spot_id in self._spot_ids:
            if spot_id in spots:
                all_players.update(spots[spot_id].get_current_player_ids())
        return all_players
    
    def is_player_in_area(self, player_id: int, spots: Dict[int, "Spot"]) -> bool:
        """指定されたプレイヤーがエリア内にいるかチェック"""
        for spot_id in self._spot_ids:
            if spot_id in spots and spots[spot_id].is_player_in_spot(player_id):
                return True
        return False
    
    # ===== モンスター管理 =====
    def get_spawn_monster_type_ids(self) -> Set[int]:
        """エリア内で出現するモンスターの種類IDを取得"""
        return self._spawn_monster_type_ids