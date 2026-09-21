"""
InMemoryGuildBankRepository - ギルド金庫のインメモリリポジトリ
"""

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.guild.aggregate.guild_bank_aggregate import GuildBankAggregate
from ai_rpg_world.domain.guild.repository.guild_bank_repository import GuildBankRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryGuildBankRepository(GuildBankRepository, InMemoryRepositoryBase):
    """ギルド金庫リポジトリのインメモリ実装"""

    def __init__(
        self,
        data_store: InMemoryDataStore | None = None,
        unit_of_work: UnitOfWork | None = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _guild_banks(self) -> dict[GuildId, GuildBankAggregate]:
        return self._data_store.guild_banks

    def find_by_id(self, guild_id: GuildId) -> GuildBankAggregate | None:
        pending = self._get_pending_aggregate(guild_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._guild_banks.get(guild_id))

    def find_by_ids(self, guild_ids: list[GuildId]) -> list[GuildBankAggregate]:
        return [x for gid in guild_ids for x in [self.find_by_id(gid)] if x is not None]

    def save(self, entity: GuildBankAggregate) -> GuildBankAggregate:
        cloned = self._clone(entity)

        def operation():
            self._guild_banks[cloned.guild_id] = cloned
            return cloned

        self._register_aggregate(entity)
        self._register_pending_if_uow(entity.guild_id, entity)
        return self._execute_operation(operation)

    def delete(self, entity_id: GuildId) -> bool:
        def operation():
            if entity_id in self._guild_banks:
                del self._guild_banks[entity_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> list[GuildBankAggregate]:
        return [self._clone(b) for b in self._guild_banks.values()]
