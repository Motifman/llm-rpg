from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import PreconditionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import NoRouteToDestinationException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person.person_vitals_events import PersonBecameBusyEvent
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, OpenArea, PersonBody, TravelInProgress
from tests.game_world.application.action.world_for_action_tests import (
    ADIT,
    ALICE,
    CAGE,
    GALLERY,
    GATE_CLOSED_TEXT,
    LANDING,
    SHAFT,
    WorldForActions,
)


class TestStartTravelDone:
    """StartTravel が、通れる道で移動を始め、通る通路の時間のあいだ行う人を Busy にすることを保証する。"""

    def test_travel_puts_actor_on_the_way_and_notes_it(self) -> None:
        """隣の場所へ移動すると ActionDone が返り、居場所は移動中になり、LatestActions に TRAVEL が残る。"""
        world = WorldForActions()

        reply = world.travel(ALICE, SHAFT)

        assert reply == ActionDone()
        facts = world.read().facts()
        location = facts.whereabouts().location_of(PersonBody(ALICE))
        assert isinstance(location, TravelInProgress)
        assert location.route.destination == SHAFT.spot_id
        assert facts.latest_actions().last_done_at(ALICE, ActionKind.TRAVEL) == WorldTick(0)

    def test_travel_keeps_actor_busy_for_sum_of_passage_ticks(self) -> None:
        """通る通路の時間の合計 (梯子 3 + 横坑 1) のあいだ Busy になる。"""
        world = WorldForActions()

        world.travel(ALICE, ADIT)

        busy = [event for event in world.events() if isinstance(event, PersonBecameBusyEvent)]
        assert [event.until for event in busy] == [WorldTick(4)]

    def test_travel_from_inside_section_leaves_the_section(self) -> None:
        """区画の中から移動を始めると、区画を出て移動中になる。"""
        world = WorldForActions()
        world.enter_cage(ALICE)
        world.pass_ticks(1)

        world.travel(ALICE, SHAFT)

        assert world.read().facts().whereabouts().is_in_section(PersonBody(ALICE), CAGE) is False


class TestStartTravelRefused:
    """StartTravel が、道を塞ぐ通る条件や、道が無いことを理由に断ることを保証する。"""

    def test_passage_condition_blocking_the_only_route_refuses_with_its_failure_text(self) -> None:
        """唯一の道の通路の通る条件が偽なら、その条件の failure_text を持つ PreconditionRefusal で断られ、その場に残る。"""
        world = WorldForActions()

        reply = world.travel(ALICE, GALLERY)

        assert isinstance(reply, ActionRefused)
        assert isinstance(reply.refusal.reason, PreconditionRefusal)
        assert reply.refusal.text == TextAboutPeople(TextWithUnassignedPeople(GATE_CLOSED_TEXT), {})
        assert world.read().facts().whereabouts().location_of(PersonBody(ALICE)) == AtSpot(
            spot=LANDING.spot_id, section=OpenArea()
        )

    def test_travel_to_where_actor_is_refuses_with_no_route(self) -> None:
        """今いる場所を目的地にすると、NO_ROUTE の RefusalCode で断られる。"""
        world = WorldForActions()

        reply = world.travel(ALICE, LANDING)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(NoRouteToDestinationException.error_code))
