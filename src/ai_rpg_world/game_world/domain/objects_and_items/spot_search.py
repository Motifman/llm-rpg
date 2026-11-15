from __future__ import annotations

from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
class SpotSearch:
    def __init__(self, spot: SpotId, discoverables_here: tuple[DiscoverableDeclaration, ...]) -> None:
        self._spot = spot
        self._discoverables_here = discoverables_here

    def search_by(self, searcher: PersonId, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        progress = world.search_progress(self._spot)
        progress.record_search(searcher)
        for discoverable in self._discoverables_here:
            if progress.is_found(discoverable, searcher) or not discoverable.condition.holds(facts, trigger):
                continue
            progress.mark_found(discoverable, searcher)
            discoverable.when_found.apply(facts, world, trigger)
