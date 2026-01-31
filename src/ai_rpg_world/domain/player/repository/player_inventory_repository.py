from abc import abstractmethod
from typing import Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerInventoryRepository(Repository[PlayerInventoryAggregate, PlayerId]):
    """プレイヤーインベントリリポジトリインターフェース"""
    pass
