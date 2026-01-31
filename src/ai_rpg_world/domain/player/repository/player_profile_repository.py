from abc import abstractmethod
from typing import Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName


class PlayerProfileRepository(Repository[PlayerProfileAggregate, PlayerId]):
    """プレイヤープロフィールリポジトリインターフェース"""

    @abstractmethod
    def find_by_name(self, name: PlayerName) -> Optional[PlayerProfileAggregate]:
        """名前でプレイヤープロフィールを検索"""
        pass

    @abstractmethod
    def exists_name(self, name: PlayerName) -> bool:
        """指定した名前のプレイヤーが存在するかどうかをチェック"""
        pass

    @abstractmethod
    def generate_id(self) -> PlayerId:
        """プレイヤーIDを生成"""
        pass
