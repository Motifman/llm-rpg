from __future__ import annotations

from typing import cast, final

from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
class _FactsNotRead:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"this must not read the world: {name}")


FACTS_NOT_READ = cast(WorldFacts, _FactsNotRead())
