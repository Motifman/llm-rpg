from abc import abstractmethod
from typing import Optional, List
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerStatusRepository(Repository[PlayerStatusAggregate, PlayerId]):
    """プレイヤーステータスリポジトリインターフェース"""

    @abstractmethod
    def save_all(self, statuses: List[PlayerStatusAggregate]) -> None:
        """複数のプレイヤーステータスを一括保存"""
        pass
