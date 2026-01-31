from abc import abstractmethod
from typing import Optional
from src.domain.common.repository import Repository
from src.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from src.domain.player.value_object.player_id import PlayerId


class PlayerInventoryRepository(Repository[PlayerInventoryAggregate, PlayerId]):
    """プレイヤーインベントリリポジトリインターフェース"""
    pass
