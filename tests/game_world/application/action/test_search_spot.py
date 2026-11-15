from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone
from ai_rpg_world.game_world.domain.objects_and_items.spot_search_progress import (
    DiscoverableFoundEvent,
    SpotSearchedEvent,
)
from ai_rpg_world.game_world.domain.value_object import Count
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from tests.game_world.application.action.world_for_search_and_tend_tests import (
    ALICE,
    BOB,
    CAVE,
    KEY,
    PEBBLE,
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
