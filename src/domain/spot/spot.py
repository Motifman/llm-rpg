from typing import Set, Optional
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.spot.spot_events import PlayerEnteredSpotEvent, PlayerExitedSpotEvent
from src.domain.spot.spot_exception import PlayerAlreadyInSpotException, PlayerNotInSpotException


class Spot(AggregateRoot):
    def __init__(
        self,
        spot_id: int,
        name: str,
        description: str,
        area_id: Optional[int] = None,
        current_player_ids: Optional[Set[int]] = None,
    ):
        super().__init__()
        self._spot_id = spot_id
        self._name = name
        self._description = description
        self._area_id = area_id
        self._current_player_ids: Set[int] = current_player_ids or set()
    
    @property
    def spot_id(self) -> int:
        return self._spot_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def area_id(self) -> Optional[int]:
        return self._area_id
    
    # ===== プレイヤー管理 =====
    def add_player(self, player_id: int):
        if player_id in self._current_player_ids:
            raise PlayerAlreadyInSpotException(f"Player {player_id} is already in the spot {self._spot_id}")
        self._current_player_ids.add(player_id)
        self.add_event(PlayerEnteredSpotEvent.create(
            aggregate_id=self._spot_id,
            aggregate_type="spot",
            player_id=player_id,
            spot_id=self._spot_id,
        ))

    def remove_player(self, player_id: int):
        if player_id not in self._current_player_ids:
            raise PlayerNotInSpotException(f"Player {player_id} is not in the spot {self._spot_id}")
        self._current_player_ids.discard(player_id)
        self.add_event(PlayerExitedSpotEvent.create(
            aggregate_id=self._spot_id,
            aggregate_type="spot",
            player_id=player_id,
            spot_id=self._spot_id,
        ))

    def get_current_player_ids(self) -> Set[int]:
        return self._current_player_ids
    
    def get_current_player_count(self) -> int:
        return len(self._current_player_ids)
    
    def is_player_in_spot(self, player_id: int) -> bool:
        return player_id in self._current_player_ids
    
    # ===== スポット間の繋がりを管理 =====
    def get_spot_summary(self) -> str:
        return f"{self._name} ({self._spot_id}) {self._description}"

    def get_spot_summary_with_area(self, area_name: Optional[str] = None) -> str:
        """エリア名を含むスポット概要を取得"""
        if area_name is None:
            return self.get_spot_summary()
        return f"{self._name} ({self._spot_id}) {self._description} (area:{area_name})"