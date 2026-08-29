"""monster spawn commandが同じtransactionで使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillLoadoutRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)


class MonsterSpawnCommandRepositoryProviderPort(Protocol):
    """spawnスロット1件の更新に必要なrepositoryだけを公開する。"""

    @property
    def monsters(self) -> MonsterRepository: ...

    @property
    def skill_loadouts(self) -> SkillLoadoutRepository: ...

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...


__all__ = ["MonsterSpawnCommandRepositoryProviderPort"]
