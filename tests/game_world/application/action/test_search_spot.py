from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import NotEnoughItemsOfSpecException
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import OccupantNotAtRouteStartException
from ai_rpg_world.game_world.domain.objects_and_items.spot_search_progress import (
    DiscoverableFoundEvent,
    SpotSearchedEvent,
)
from ai_rpg_world.game_world.domain.value_object import Count
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from tests.game_world.application.action.world_for_search_and_tend_tests import (
    ALICE,
    BOB,
    CAROL,
    CAVE,
    KEY,
    PEBBLE,
    SHORE,
    WorldForSearchAndTend,
)


def _found(world: WorldForSearchAndTend) -> list[tuple[DiscoverableId, object]]:
    return [
        (event.discoverable_id, event.finder)
        for event in world.events_received
        if isinstance(event, DiscoverableFoundEvent)
    ]


class TestSearchSpot:
    """SearchSpot が、調べた回数を数え、条件を満たした見つかる物を見つけさせ、その効果を起こすことを保証する。"""

    def test_search_adds_to_search_count_at_actors_spot(self) -> None:
        """洞窟で調べると ActionDone が返り、alice の洞窟での調べた回数が 1 になり、SpotSearchedEvent が配られる。"""
        world = WorldForSearchAndTend()

        reply = world.search(ALICE)

        assert reply == ActionDone()
        session = world.read()
        assert session.facts().search_progress(CAVE).search_count(ALICE) == Count(1)
        session.roll_back()
        assert any(isinstance(event, SpotSearchedEvent) for event in world.events_received)

    def test_discoverable_is_found_once_its_condition_holds(self) -> None:
        """「2 回調べたら」が条件の古い鍵は、1 回目では見つからず、2 回目で見つかって鍵が 1 つ荷に入る。"""
        world = WorldForSearchAndTend()

        world.search(ALICE)
        assert world.count_of(ALICE, KEY) == Count(0)
        world.pass_ticks(1)
        world.search(ALICE)

        assert world.count_of(ALICE, KEY) == Count(1)
        assert (DiscoverableId("old_key"), ALICE) in _found(world)

    def test_once_in_world_discoverable_is_not_found_again_by_anyone(self) -> None:
        """alice が見つけた古い鍵 (世界に 1 回) は、alice が調べ直しても bob が 2 回調べても見つからず、鍵は増えない。"""
        world = WorldForSearchAndTend()
        world.search(ALICE)
        world.pass_ticks(1)
        world.search(ALICE)

        world.pass_ticks(1)
        world.search(ALICE)
        world.search(BOB)
        world.pass_ticks(1)
        world.search(BOB)

        assert world.count_of(ALICE, KEY) == Count(1)
        assert world.count_of(BOB, KEY) == Count(0)
        assert [found for found in _found(world) if found[0] == DiscoverableId("old_key")] == [
            (DiscoverableId("old_key"), ALICE)
        ]

    def test_once_per_person_discoverable_is_found_once_by_each_person(self) -> None:
        """光る小石 (1 人に 1 回) は、alice と bob がそれぞれ 1 回ずつ見つけ、alice が調べ直しても 2 つ目は見つからない。"""
        world = WorldForSearchAndTend()

        world.search(ALICE)
        world.search(BOB)
        world.pass_ticks(1)
        world.search(ALICE)

        assert world.count_of(ALICE, PEBBLE) == Count(1)
        assert world.count_of(BOB, PEBBLE) == Count(1)

    def test_refused_when_found_effect_rolls_back_the_search(self) -> None:
        """見つけたときに鍵を取る効果が、鍵を持たない carol で断られると、浜で調べた回数は 0 のままで、見つけた記録も残らない。"""
        world = WorldForSearchAndTend()

        reply = world.search(CAROL)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(NotEnoughItemsOfSpecException.error_code))
        session = world.read()
        assert session.facts().search_progress(SHORE).search_count(CAROL) == Count(0)
        session.roll_back()
        assert _found(world) == []

    def test_person_on_the_way_is_refused_and_search_is_not_counted(self) -> None:
        """浜へ向かう道の途中にいる alice が調べると OCCUPANT_NOT_AT_ROUTE_START で断られ、洞窟で調べた回数は増えない。"""
        world = WorldForSearchAndTend()
        world.travel_to_shore(ALICE)
        world.pass_ticks(1)

        reply = world.search(ALICE)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(OccupantNotAtRouteStartException.error_code))
        session = world.read()
        assert session.facts().search_progress(CAVE).search_count(ALICE) == Count(0)
        session.roll_back()
