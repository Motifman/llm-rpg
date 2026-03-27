"""In-memory repository for skill specs and writer port."""

from __future__ import annotations

import copy
from typing import Dict, List, Optional

from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillSpecRepository,
    SkillSpecWriter,
)
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


class InMemorySkillSpecRepository(SkillSpecRepository, SkillSpecWriter):
    """スキル定義の読み取りと投入を行う InMemory 実装。"""

    def __init__(self) -> None:
        self._specs: Dict[SkillId, SkillSpec] = {}

    def find_by_id(self, entity_id: SkillId) -> Optional[SkillSpec]:
        spec = self._specs.get(entity_id)
        return None if spec is None else copy.deepcopy(spec)

    def find_by_ids(self, entity_ids: List[SkillId]) -> List[SkillSpec]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillSpec]:
        return [copy.deepcopy(spec) for spec in self._specs.values()]

    def replace_spec(self, spec: SkillSpec) -> None:
        self._specs[spec.skill_id] = copy.deepcopy(spec)

    def delete_spec(self, skill_id: SkillId) -> bool:
        return self._specs.pop(skill_id, None) is not None


__all__ = ["InMemorySkillSpecRepository"]
