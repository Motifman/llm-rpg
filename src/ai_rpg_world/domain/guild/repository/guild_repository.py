from abc import abstractmethod

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId


class GuildRepository(Repository[GuildAggregate, GuildId]):
    """ギルドリポジトリインターフェース"""

    @abstractmethod
    def generate_guild_id(self) -> GuildId:
        """新規ギルドIDを生成"""
        pass
