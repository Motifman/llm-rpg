"""
InMemoryGuildRepository - ギルドのインメモリリポジトリ
"""
from typing import List, Optional, Dict

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore


class InMemoryGuildRepository(GuildRepository, InMemoryRepositoryBase):
    """ギルドリポジトリのインメモリ実装"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _guilds(self) -> Dict[GuildId, GuildAggregate]:
        return self._data_store.guilds

    def find_by_id(self, guild_id: GuildId) -> Optional[GuildAggregate]:
        pending = self._get_pending_aggregate(guild_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._guilds.get(guild_id))

    def find_by_ids(self, guild_ids: List[GuildId]) -> List[GuildAggregate]:
        return [x for gid in guild_ids for x in [self.find_by_id(gid)] if x is not None]

    def save(self, guild: GuildAggregate) -> GuildAggregate:
        cloned = self._clone(guild)

        def operation():
            self._guilds[cloned.guild_id] = cloned
            return cloned

        self._register_aggregate(guild)
        self._register_pending_if_uow(guild.guild_id, guild)
        return self._execute_operation(operation)

    def delete(self, guild_id: GuildId) -> bool:
        def operation():
            if guild_id in self._guilds:
                del self._guilds[guild_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> List[GuildAggregate]:
        return [self._clone(g) for g in self._guilds.values()]

    def generate_guild_id(self) -> GuildId:
        gid = self._data_store.next_guild_id
        self._data_store.next_guild_id += 1
        return GuildId(gid)
