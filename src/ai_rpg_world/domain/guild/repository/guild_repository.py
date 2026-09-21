from abc import abstractmethod

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class GuildRepository(Repository[GuildAggregate, GuildId]):
    """ギルドリポジトリインターフェース"""

    @abstractmethod
    def generate_guild_id(self) -> GuildId:
        """新規ギルドIDを生成"""
        pass

    @abstractmethod
    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> GuildAggregate | None:
        """指定ロケーションのギルドを取得（1ロケーション1ギルド）"""
        pass

    @abstractmethod
    def find_guilds_by_player_id(self, player_id: PlayerId) -> list[GuildAggregate]:
        """プレイヤーが所属するギルド一覧を取得"""
        pass
