from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration, Finding
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.world_records_exception import DiscoverableElsewhereException
from ai_rpg_world.game_world.domain.objects_and_items import (
    DiscoverableFoundEvent,
    SpotSearchedEvent,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId

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


def _discoverable(discoverable_id: str, finding: Finding, *, spot: SpotId = _CAVE) -> DiscoverableDeclaration:
    return DiscoverableDeclaration(
        discoverable_id=DiscoverableId(discoverable_id),
        spot_id=spot,
        found_text=TextWithUnassignedPeople("岩の隙間に何か光る物がある"),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        when_found=NoEffect(),
        finding=finding,
    )


_SHARED_CHEST = _discoverable("old_chest", Finding.ONCE_IN_WORLD)
_PERSONAL_HINT = _discoverable("wall_carving", Finding.ONCE_PER_PERSON)


class TestSpotSearchProgressFinding:
    """SpotSearchProgress.mark_found / is_found が、見つかる物の見つけ方 (Finding) に従って、誰にとって見つかったかを答えることを保証する。"""

    def test_nothing_is_found_at_first(self) -> None:
        """作った直後は、どの見つかる物も誰にとっても見つかっていない。"""
        progress = SpotSearchProgress(_CAVE)

        assert not progress.is_found(_SHARED_CHEST, _ALICE)
        assert not progress.is_found(_PERSONAL_HINT, _ALICE)

    def test_once_in_world_discoverable_found_by_someone_is_found_for_everyone(self) -> None:
        """ONCE_IN_WORLD の見つかる物は、alice が見つけたら、まだ探していない bob にとっても見つかったことになる。"""
        progress = SpotSearchProgress(_CAVE)

        progress.mark_found(_SHARED_CHEST, _ALICE)

        assert progress.is_found(_SHARED_CHEST, _ALICE)
        assert progress.is_found(_SHARED_CHEST, _BOB)

    def test_once_per_person_discoverable_found_by_someone_stays_unfound_for_others(self) -> None:
        """ONCE_PER_PERSON の見つかる物は、alice が見つけても、bob にとっては見つかっていないまま。"""
        progress = SpotSearchProgress(_CAVE)

        progress.mark_found(_PERSONAL_HINT, _ALICE)

        assert progress.is_found(_PERSONAL_HINT, _ALICE)
        assert not progress.is_found(_PERSONAL_HINT, _BOB)

    def test_finding_one_discoverable_leaves_others_unfound(self) -> None:
        """宝箱を見つけても、同じ場所の別の見つかる物は見つかっていないまま。"""
        progress = SpotSearchProgress(_CAVE)

        progress.mark_found(_SHARED_CHEST, _ALICE)

        assert not progress.is_found(_PERSONAL_HINT, _ALICE)

    def test_mark_found_records_event_with_discoverable_and_finder(self) -> None:
        """mark_found は、場所・見つかる物・見つけた人を持つ DiscoverableFoundEvent をためる。"""
        progress = SpotSearchProgress(_CAVE)

        progress.mark_found(_SHARED_CHEST, _ALICE)

        [event] = progress.get_events()
        assert isinstance(event, DiscoverableFoundEvent)
        assert (event.spot_id, event.discoverable_id, event.finder) == (_CAVE, DiscoverableId("old_chest"), _ALICE)

    def test_marking_already_found_discoverable_again_changes_nothing(self) -> None:
        """ONCE_IN_WORLD の宝箱を alice が見つけたあと bob に mark_found しても、断らず、イベントもためない。"""
        progress = SpotSearchProgress(_CAVE)
        progress.mark_found(_SHARED_CHEST, _ALICE)
        progress.clear_events()

        progress.mark_found(_SHARED_CHEST, _BOB)

        assert progress.get_events() == []

    def test_same_person_finding_personal_discoverable_again_changes_nothing(self) -> None:
        """ONCE_PER_PERSON の見つかる物を同じ人がもう一度 mark_found しても、断らず、イベントもためない。"""
        progress = SpotSearchProgress(_CAVE)
        progress.mark_found(_PERSONAL_HINT, _ALICE)
        progress.clear_events()

        progress.mark_found(_PERSONAL_HINT, _ALICE)

        assert progress.get_events() == []

    def test_mark_found_rejects_discoverable_of_another_spot(self) -> None:
        """別の場所に置いた見つかる物を mark_found すると DiscoverableElsewhereException を投げ、見つかったことにならない。"""
        progress = SpotSearchProgress(_CAVE)
        elsewhere = _discoverable("buried_coin", Finding.ONCE_IN_WORLD, spot=SpotId("beach"))

        with pytest.raises(DiscoverableElsewhereException):
            progress.mark_found(elsewhere, _ALICE)

        assert not progress.is_found(elsewhere, _ALICE)
