"""In-memory repository for skill deck progress aggregates."""

from __future__ import annotations

from typing import Dict, List, Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import (
    SkillDeckProgressAggregate,
)
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
)
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import (
    SkillDeckProgressId,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    InMemoryRepositoryBase,
)


class InMemorySkillDeckProgressRepository(
    SkillDeckProgressRepository, InMemoryRepositoryBase
):
    """スキルデッキ進行集約の InMemory 実装。"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ) -> None:
        super().__init__(data_store, unit_of_work)

    @property
    def _progresses(self) -> Dict[SkillDeckProgressId, SkillDeckProgressAggregate]:
        return self._data_store.skill_deck_progresses

    def find_by_id(
        self, entity_id: SkillDeckProgressId
    ) -> Optional[SkillDeckProgressAggregate]:
        pending = self._get_pending_aggregate(entity_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._progresses.get(entity_id))

    def find_by_ids(
        self, entity_ids: List[SkillDeckProgressId]
    ) -> List[SkillDeckProgressAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillDeckProgressAggregate]:
        return [self._clone(progress) for progress in self._progresses.values()]

    def save(self, entity: SkillDeckProgressAggregate) -> SkillDeckProgressAggregate:
        cloned = self._clone(entity)

        def operation() -> SkillDeckProgressAggregate:
            self._progresses[cloned.progress_id] = cloned
            return cloned

        self._register_aggregate(entity)
        self._register_pending_if_uow(entity.progress_id, entity)
        return self._execute_operation(operation)

    def delete(self, entity_id: SkillDeckProgressId) -> bool:
        def operation() -> bool:
            if entity_id in self._progresses:
                del self._progresses[entity_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_by_owner_id(self, owner_id: int) -> SkillDeckProgressAggregate | None:
        for progress in self._progresses.values():
            if progress.owner_id == owner_id:
                return self._clone(progress)
        return None


__all__ = ["InMemorySkillDeckProgressRepository"]
