from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.objects_and_items import (
    DiscoverableFinder,
    PersonSearchCount,
    SpotSearchProgressMemento,
)
from ai_rpg_world.game_world.domain.value_object import Count, SpotId
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_int,
    json_str,
    person_id_from_json,
)


def _search_count_from_json(raw: object) -> PersonSearchCount:
    fields = exact_fields(raw, ("person", "count"))
    return PersonSearchCount(person_id_from_json(fields["person"]), Count(json_int(fields["count"])))


def _finder_from_json(raw: object) -> DiscoverableFinder:
    fields = exact_fields(raw, ("discoverable", "finder"))
    return DiscoverableFinder(DiscoverableId(json_str(fields["discoverable"])), person_id_from_json(fields["finder"]))


@final
class SpotSearchProgressCodec:
    kind = "spot_search_progress"
    version = 1
    memento_type = SpotSearchProgressMemento

    def to_json(self, memento: SpotSearchProgressMemento) -> object:
        return {
            "spot_id": memento.spot_id.value,
            "search_counts": [
                {"person": search_count.person.value, "count": search_count.count.value}
                for search_count in sorted(memento.search_counts, key=lambda search_count: search_count.person.value)
            ],
            "finders": [
                {"discoverable": found.discoverable.value, "finder": found.finder.value}
                for found in sorted(memento.finders, key=lambda found: (found.discoverable.value, found.finder.value))
            ],
        }

    def from_json(self, raw: object) -> SpotSearchProgressMemento:
        fields = exact_fields(raw, ("spot_id", "search_counts", "finders"))
        return SpotSearchProgressMemento(
            spot_id=SpotId(json_str(fields["spot_id"])),
            search_counts=distinct_items(fields["search_counts"], _search_count_from_json),
            finders=distinct_items(fields["finders"], _finder_from_json),
        )
