from abc import abstractmethod
from typing import Optional
from src.domain.common.repository import Repository
from src.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from src.domain.player.value_object.player_id import PlayerId


class PlayerStatusRepository(Repository[PlayerStatusAggregate, PlayerId]):
    """プレイヤーステータスリポジトリインターフェース"""
    pass
