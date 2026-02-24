"""ギルド金庫リポジトリインターフェース"""
from abc import abstractmethod

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.guild.aggregate.guild_bank_aggregate import GuildBankAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId


class GuildBankRepository(Repository[GuildBankAggregate, GuildId]):
    """ギルド金庫リポジトリインターフェース（GuildId と 1:1）"""
