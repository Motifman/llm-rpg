from abc import abstractmethod
from typing import Optional

from src.domain.common.repository import Repository
from src.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.player_name import PlayerName


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
