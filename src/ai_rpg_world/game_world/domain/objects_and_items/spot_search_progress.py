from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.world_records_exception import DiscoverableElsewhereException
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, SpotId
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


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


@final
@dataclass(frozen=True)
class PersonSearchCount:
    person: PersonId
    count: Count


@final
@dataclass(frozen=True)
class DiscoverableFinder:
    discoverable: DiscoverableId
    finder: PersonId


@final
@dataclass(frozen=True)
class SpotSearchProgressMemento:
    spot_id: SpotId
    search_counts: frozenset[PersonSearchCount]
    finders: frozenset[DiscoverableFinder]

    def __post_init__(self) -> None:
        people = [search_count.person for search_count in self.search_counts]
        if len(set(people)) != len(people):
            raise RepeatedMementoKeyException(f"someone has two search counts at {self.spot_id.value}")


class SpotSearchProgress(AggregateRoot[SpotSearchProgressEvent]):
    def __init__(self, spot_id: SpotId) -> None:
        super().__init__()
        self._spot_id = spot_id
        self._search_counts: dict[PersonId, Count] = {}
        self._finders: dict[DiscoverableId, frozenset[PersonId]] = {}

    @classmethod
    def from_memento(cls, memento: SpotSearchProgressMemento, design: WorldDesign) -> SpotSearchProgress:
        progress = cls(memento.spot_id)
        progress._search_counts = {search_count.person: search_count.count for search_count in memento.search_counts}
        for found in memento.finders:
            progress._finders[found.discoverable] = progress._finders.get(found.discoverable, frozenset()) | {
                found.finder
            }
        return progress

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    def memento(self) -> SpotSearchProgressMemento:
        return SpotSearchProgressMemento(
            spot_id=self._spot_id,
            search_counts=frozenset(PersonSearchCount(person, count) for person, count in self._search_counts.items()),
            finders=frozenset(
                DiscoverableFinder(discoverable, finder)
                for discoverable, finders in self._finders.items()
                for finder in finders
            ),
        )

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
