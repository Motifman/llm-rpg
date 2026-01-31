from abc import abstractmethod
from typing import Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerStatusRepository(Repository[PlayerStatusAggregate, PlayerId]):
    """プレイヤーステータスリポジトリインターフェース"""
    pass
