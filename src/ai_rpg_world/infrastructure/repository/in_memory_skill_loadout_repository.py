"""In-memory repository for skill loadout aggregates."""

from __future__ import annotations

from typing import Dict, List, Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    InMemoryRepositoryBase,
)


class InMemorySkillLoadoutRepository(SkillLoadoutRepository, InMemoryRepositoryBase):
    """スキルロードアウト集約の InMemory 実装。"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ) -> None:
        super().__init__(data_store, unit_of_work)

    @property
    def _loadouts(self) -> Dict[SkillLoadoutId, SkillLoadoutAggregate]:
        return self._data_store.skill_loadouts

    def find_by_id(self, entity_id: SkillLoadoutId) -> Optional[SkillLoadoutAggregate]:
        pending = self._get_pending_aggregate(entity_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._loadouts.get(entity_id))

    def find_by_ids(self, entity_ids: List[SkillLoadoutId]) -> List[SkillLoadoutAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillLoadoutAggregate]:
        return [self._clone(loadout) for loadout in self._loadouts.values()]

    def save(self, entity: SkillLoadoutAggregate) -> SkillLoadoutAggregate:
        cloned = self._clone(entity)

        def operation() -> SkillLoadoutAggregate:
            self._loadouts[cloned.loadout_id] = cloned
            return cloned

        self._register_aggregate(entity)
        self._register_pending_if_uow(entity.loadout_id, entity)
        return self._execute_operation(operation)

    def delete(self, entity_id: SkillLoadoutId) -> bool:
        def operation() -> bool:
            if entity_id in self._loadouts:
                del self._loadouts[entity_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_by_owner_id(self, owner_id: int) -> SkillLoadoutAggregate | None:
        for loadout in self._loadouts.values():
            if loadout.owner_id == owner_id:
                return self._clone(loadout)
        return None


__all__ = ["InMemorySkillLoadoutRepository"]
