from __future__ import annotations

from ai_rpg_world.game_world.domain.objects_and_items import SpotSearchedEvent, SpotSearchProgress
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, SpotId

_CAVE = SpotId("cave")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")


class TestSpotSearchProgress:
    """SpotSearchProgress が、場所を探した回数を人ごとに数え、探すたびにイベントをためることを保証する。"""

    def test_nobody_has_searched_at_first(self) -> None:
        """作った直後は自分の場所の ID を持ち、誰の search_count も Count(0) を返す。"""
        progress = SpotSearchProgress(_CAVE)

        assert progress.spot_id == _CAVE
        assert progress.search_count(_ALICE) == Count(0)

    def test_record_search_counts_per_person(self) -> None:
        """record_search は探した人の回数だけを 1 つ増やし、ほかの人の回数は変えない。"""
        progress = SpotSearchProgress(_CAVE)

        progress.record_search(_ALICE)
        progress.record_search(_ALICE)
        progress.record_search(_BOB)

        assert progress.search_count(_ALICE) == Count(2)
        assert progress.search_count(_BOB) == Count(1)

    def test_record_search_records_event_with_counts_before_and_after(self) -> None:
        """record_search は、場所・探した人・探す前と後の回数を持つ SpotSearchedEvent をためる。"""
        progress = SpotSearchProgress(_CAVE)
        progress.record_search(_ALICE)
        progress.clear_events()

        progress.record_search(_ALICE)

        [event] = progress.get_events()
        assert isinstance(event, SpotSearchedEvent)
        assert (event.spot_id, event.searcher, event.count_before, event.count_after) == (
            _CAVE,
            _ALICE,
            Count(1),
            Count(2),
        )
