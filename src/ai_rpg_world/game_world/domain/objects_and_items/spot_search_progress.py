from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, SpotId


@final
@dataclass(frozen=True, kw_only=True)
class SpotSearchedEvent(DomainEvent):
    spot_id: SpotId
    searcher: PersonId
    count_before: Count
    count_after: Count


class SpotSearchProgress(AggregateRoot[SpotSearchedEvent]):
    def __init__(self, spot_id: SpotId) -> None:
        super().__init__()
        self._spot_id = spot_id
        self._search_counts: dict[PersonId, Count] = {}

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

    def search_count(self, person: PersonId) -> Count:
        return self._search_counts.get(person, Count(0))
