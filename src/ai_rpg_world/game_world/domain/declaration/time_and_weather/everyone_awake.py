from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.requirements import Requirements
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class EveryoneAwake:
    def select(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]:
        return frozenset(facts.people())

    def requirements(self) -> Requirements:
        # 時間帯の宣言は条件より先に読み込まれるので、モジュールの頭で import すると循環する。
        from ai_rpg_world.game_world.domain.condition.requirements import Requirements

        return Requirements.nothing()
