from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.exception.world_records_exception import DiscoverableElsewhereException
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, SpotId
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration


@final
@dataclass(frozen=True, kw_only=True)
class SpotSearchedEvent(DomainEvent):
    spot_id: SpotId
    searcher: PersonId
    count_before: Count
    count_after: Count


@final
@dataclass(frozen=True, kw_only=True)
class DiscoverableFoundEvent(DomainEvent):
    spot_id: SpotId
    discoverable_id: DiscoverableId
    finder: PersonId


SpotSearchProgressEvent = SpotSearchedEvent | DiscoverableFoundEvent


class SpotSearchProgress(AggregateRoot[SpotSearchProgressEvent]):
    def __init__(self, spot_id: SpotId) -> None:
        super().__init__()
        self._spot_id = spot_id
        self._search_counts: dict[PersonId, Count] = {}
        self._finders: dict[DiscoverableId, frozenset[PersonId]] = {}

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    def record_search(self, searcher: PersonId) -> None:
        before = self.search_count(searcher)
        after = before + Count(1)
        self._search_counts[searcher] = after
        self.add_event(
            SpotSearchedEvent(
                **new_event_stamp(),
                spot_id=self._spot_id,
                searcher=searcher,
                count_before=before,
                count_after=after,
            )
        )

    def mark_found(self, discoverable: DiscoverableDeclaration, finder: PersonId) -> None:
        if discoverable.spot_id != self._spot_id:
            raise DiscoverableElsewhereException(
                f"{discoverable.discoverable_id.value} is at {discoverable.spot_id.value}, not {self._spot_id.value}"
            )
        if self.is_found(discoverable, finder):
            return
        self._finders[discoverable.discoverable_id] = self._finders_of(discoverable) | {finder}
        self.add_event(
            DiscoverableFoundEvent(
                **new_event_stamp(),
                spot_id=self._spot_id,
                discoverable_id=discoverable.discoverable_id,
                finder=finder,
            )
        )

    def search_count(self, person: PersonId) -> Count:
        return self._search_counts.get(person, Count(0))

    def is_found(self, discoverable: DiscoverableDeclaration, person: PersonId) -> bool:
        return discoverable.finding.is_found_by(person, self._finders_of(discoverable))

    def _finders_of(self, discoverable: DiscoverableDeclaration) -> frozenset[PersonId]:
        return self._finders.get(discoverable.discoverable_id, frozenset())
