from __future__ import annotations

from collections.abc import Callable

import pytest

from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    OccupantAlreadyInSectionException,
    OccupantAlreadyPlacedException,
    OccupantNotAtRouteStartException,
    OccupantNotAtSectionSpotException,
    OccupantNotInSectionException,
    OccupantNotPlacedException,
    OccupantNotTravellingException,
    SectionFullException,
    TicksLeftOutsidePassageException,
    TravelNotDepartedFromPassageStartException,
    TravelPositionOutsideRouteException,
)
from ai_rpg_world.game_world.domain.value_object import PassageId, PersonId, SpotId, SpotSectionId, Ticks
from ai_rpg_world.game_world.domain.whereabouts import (
    AtSpot,
    DepartedPerson,
    OccupantEnteredSectionEvent,
    OccupantEnteredSpotEvent,
    OccupantLeftSectionEvent,
    OccupantLeftSpotEvent,
    OccupantLocation,
    OccupantPlacedEvent,
    OccupantRemovedEvent,
    OccupantTeleportedEvent,
    OpenArea,
    PersonBody,
    Route,
    TravelBlockedEvent,
    TravelCancelledEvent,
    TravelInProgress,
    TravelPosition,
    TravelStartedEvent,
    Whereabouts,
    WhereaboutsMemento,
)
from tests.game_world.domain.whereabouts._builders import WORLD, path, section, spot, thing
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import access_to, compose_world, nouns

ALICE = PersonBody(PersonId("alice"))
BOB = PersonBody(PersonId("bob"))
CAROL = PersonBody(PersonId("carol"))

PLAZA = spot("plaza")
WELL = spot("well")
MINE = spot("mine_entrance")
LIFT = section("lift_cage", "plaza", capacity=1, reachable=("lift_lever",))
BENCH = section("bench", "plaza")
STREET = path("street", "plaza", "well", ticks=2)
LANE = path("lane", "well", "mine_entrance", ticks=1)
NOBODY_DOWN: frozenset[PersonId] = frozenset()
DESIGN = compose_world(
    nouns(
        spots=(PLAZA, WELL, MINE),
        passages=(STREET, LANE),
        objects=(thing("lift_lever", "plaza"),),
        sections=(LIFT, BENCH),
    ),
    section_accesses=(access_to(LIFT), access_to(BENCH)),
)


def _whereabouts(*placed: tuple[PersonBody | DepartedPerson, str]) -> Whereabouts:
    whereabouts = Whereabouts.start(WORLD)
    for occupant, at in placed:
        whereabouts.place(occupant, spot(at))
    whereabouts.clear_events()
    return whereabouts


def _kinds(whereabouts: Whereabouts) -> list[type]:
    return [type(event) for event in whereabouts.get_events()]


class TestWhereaboutsPlaceAndRemove:
    """place で世界に置き、remove で世界から外すことを保証する。"""

    def test_world_id_is_the_given_world(self) -> None:
        """作るときに渡した WorldId を自分の ID として持つ。"""
        assert Whereabouts.start(WORLD).world_id == WORLD

    def test_place_puts_the_occupant_outside_any_section_of_the_spot(self) -> None:
        """place すると、その場所の区画の外 (OpenArea) にいることになり、OccupantPlacedEvent を 1 件ためる。"""
        whereabouts = Whereabouts.start(WORLD)

        whereabouts.place(ALICE, PLAZA)

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("plaza"), section=OpenArea())
        [event] = whereabouts.get_events()
        assert isinstance(event, OccupantPlacedEvent)
        assert (event.world_id, event.occupant, event.spot) == (WORLD, ALICE, SpotId("plaza"))

    def test_place_twice_is_rejected_without_events(self) -> None:
        """置いてある人をもう一度 place すると OccupantAlreadyPlacedException を投げ、居場所もイベントも変えない。"""
        whereabouts = _whereabouts((ALICE, "plaza"))

        with pytest.raises(OccupantAlreadyPlacedException):
            whereabouts.place(ALICE, WELL)

        assert whereabouts.is_at(ALICE, PLAZA)
        assert whereabouts.get_events() == []

    def test_body_and_departed_person_of_the_same_person_are_separate_occupants(self) -> None:
        """同じ人の体 (PersonBody) と去った人 (DepartedPerson) は、別々の居場所を持てる。"""
        departed = DepartedPerson(PersonId("alice"))
        whereabouts = _whereabouts((ALICE, "plaza"))

        whereabouts.place(departed, WELL)

        assert (whereabouts.is_at(ALICE, PLAZA), whereabouts.is_at(departed, WELL)) == (True, True)

    def test_remove_takes_the_occupant_out_of_the_world_and_records_the_last_location(self) -> None:
        """remove すると居場所が無くなり、最後の居場所を持つ OccupantRemovedEvent を 1 件ためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))

        whereabouts.remove(ALICE)

        with pytest.raises(OccupantNotPlacedException):
            whereabouts.location_of(ALICE)
        [event] = whereabouts.get_events()
        assert isinstance(event, OccupantRemovedEvent)
        assert event.last_location == AtSpot(spot=SpotId("plaza"), section=OpenArea())

    def test_remove_of_an_occupant_not_placed_is_rejected(self) -> None:
        """置いていない人を remove すると OccupantNotPlacedException を投げる。"""
        with pytest.raises(OccupantNotPlacedException):
            Whereabouts.start(WORLD).remove(ALICE)


class TestWhereaboutsEnterSection:
    """enter_section が、その場所にいる人だけを、定員の空いた区画に入れることを保証する。"""

    def test_enter_section_puts_the_occupant_inside(self) -> None:
        """広場にいる人が籠に入ると is_in_section が真になり、OccupantEnteredSectionEvent を 1 件ためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))

        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        assert whereabouts.is_in_section(ALICE, LIFT)
        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("plaza"), section=SpotSectionId("lift_cage"))
        [event] = whereabouts.get_events()
        assert isinstance(event, OccupantEnteredSectionEvent)
        assert event.section == SpotSectionId("lift_cage")

    def test_full_section_is_rejected_without_events(self) -> None:
        """定員 1 の籠に起きている人がいると、次の人の enter_section は SectionFullException を投げ、居場所もイベントも変えない。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)
        whereabouts.clear_events()

        with pytest.raises(SectionFullException):
            whereabouts.enter_section(BOB, LIFT, NOBODY_DOWN)

        assert whereabouts.location_of(BOB) == AtSpot(spot=SpotId("plaza"), section=OpenArea())
        assert whereabouts.get_events() == []

    def test_full_section_rejected_from_another_section_keeps_the_occupant_where_it_was(self) -> None:
        """長椅子にいる人が満員の籠に入ろうとして断られると、長椅子に残り、区画を出たイベントも出さない。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)
        whereabouts.enter_section(BOB, BENCH, NOBODY_DOWN)
        whereabouts.clear_events()

        with pytest.raises(SectionFullException):
            whereabouts.enter_section(BOB, LIFT, NOBODY_DOWN)

        assert whereabouts.is_in_section(BOB, BENCH)
        assert whereabouts.get_events() == []

    def test_fallen_or_dead_bodies_are_not_counted_toward_capacity(self) -> None:
        """籠の中の体が not_counted (倒れた人・死んだ人) に入っていれば定員に数えず、定員 1 の籠に次の人が入れる。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        whereabouts.enter_section(BOB, LIFT, frozenset({PersonId("alice")}))

        assert whereabouts.is_in_section(BOB, LIFT)

    def test_departed_person_is_counted_toward_capacity(self) -> None:
        """去った人 (DepartedPerson) は、その人が not_counted に入っていても定員に数える。"""
        departed = DepartedPerson(PersonId("alice"))
        whereabouts = _whereabouts((departed, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(departed, LIFT, NOBODY_DOWN)

        with pytest.raises(SectionFullException):
            whereabouts.enter_section(BOB, LIFT, frozenset({PersonId("alice")}))

    def test_section_without_capacity_takes_anyone(self) -> None:
        """定員の無い区画 (NoCapacity) には何人でも入れる。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"), (CAROL, "plaza"))

        for occupant in (ALICE, BOB, CAROL):
            whereabouts.enter_section(occupant, BENCH, NOBODY_DOWN)

        assert all(whereabouts.is_in_section(occupant, BENCH) for occupant in (ALICE, BOB, CAROL))

    def test_enter_section_of_another_spot_is_rejected(self) -> None:
        """井戸にいる人が広場の籠に入ろうとすると OccupantNotAtSectionSpotException を投げる。"""
        whereabouts = _whereabouts((ALICE, "well"))

        with pytest.raises(OccupantNotAtSectionSpotException):
            whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

    def test_entering_another_section_leaves_the_current_one_first(self) -> None:
        """長椅子にいる人が籠に入ると、長椅子から出たイベントのあとに籠に入ったイベントをためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.enter_section(ALICE, BENCH, NOBODY_DOWN)
        whereabouts.clear_events()

        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        left, entered = whereabouts.get_events()
        assert isinstance(left, OccupantLeftSectionEvent) and left.section == SpotSectionId("bench")
        assert isinstance(entered, OccupantEnteredSectionEvent) and entered.section == SpotSectionId("lift_cage")

    def test_entering_the_section_already_in_is_rejected(self) -> None:
        """入っている区画にもう一度 enter_section すると OccupantAlreadyInSectionException を投げる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        with pytest.raises(OccupantAlreadyInSectionException):
            whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)


class TestWhereaboutsLeaveSection:
    """leave_section が区画の中の人を区画の外へ出すことを保証する。"""

    def test_leave_section_moves_the_occupant_to_the_open_area(self) -> None:
        """籠から出ると区画の外にいることになり、OccupantLeftSectionEvent を 1 件ためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)
        whereabouts.clear_events()

        whereabouts.leave_section(ALICE)

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("plaza"), section=OpenArea())
        assert _kinds(whereabouts) == [OccupantLeftSectionEvent]

    def test_leave_section_outside_any_section_is_rejected(self) -> None:
        """区画の外にいる人が leave_section すると OccupantNotInSectionException を投げる。"""
        with pytest.raises(OccupantNotInSectionException):
            _whereabouts((ALICE, "plaza")).leave_section(ALICE)


class TestWhereaboutsStartTravel:
    """start_travel が出発点にいる人を移動中にし、区画からも出すことを保証する。"""

    def test_start_travel_also_leaves_the_section(self) -> None:
        """籠の中から移動を始めると、区画から出た・移動を始めた・場所を出たの順にイベントをため、最初の区間を歩き始める。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)
        whereabouts.clear_events()
        route = Route(start=SpotId("plaza"), passages=(STREET,))

        whereabouts.start_travel(ALICE, route)

        assert whereabouts.location_of(ALICE) == TravelInProgress(
            route=route, passage_index=0, ticks_left_on_passage=Ticks(2), departed_from=SpotId("plaza")
        )
        assert _kinds(whereabouts) == [OccupantLeftSectionEvent, TravelStartedEvent, OccupantLeftSpotEvent]

    def test_start_travel_away_from_the_route_start_is_rejected(self) -> None:
        """Route の出発点と違う場所にいる人が start_travel すると OccupantNotAtRouteStartException を投げる。"""
        whereabouts = _whereabouts((ALICE, "well"))

        with pytest.raises(OccupantNotAtRouteStartException):
            whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET,)))

    def test_traveller_is_not_at_any_spot(self) -> None:
        """移動中の人は、出発した場所にもいないことになり、occupants_at にも出ない。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))

        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET,)))

        assert whereabouts.is_at(ALICE, PLAZA) is False
        assert whereabouts.occupants_at(PLAZA) == (BOB,)


class TestWhereaboutsAdvanceTravels:
    """advance_travels が移動を 1 tick ぶん進め、着く・止まるを決めることを保証する。"""

    def test_traveller_arrives_when_the_last_passage_runs_out_of_ticks(self) -> None:
        """2 tick の区間は、1 回目の advance_travels では残り 1 tick で移動中、2 回目で着き、OccupantEnteredSpotEvent をためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        route = Route(start=SpotId("plaza"), passages=(STREET,))
        whereabouts.start_travel(ALICE, route)
        whereabouts.clear_events()

        whereabouts.advance_travels(frozenset())
        halfway = whereabouts.location_of(ALICE)
        whereabouts.advance_travels(frozenset())

        assert halfway == TravelInProgress(
            route=route, passage_index=0, ticks_left_on_passage=Ticks(1), departed_from=SpotId("plaza")
        )
        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("well"), section=OpenArea())
        [event] = whereabouts.get_events()
        assert isinstance(event, OccupantEnteredSpotEvent) and event.spot == SpotId("well")

    def test_passing_an_intermediate_spot_starts_the_next_passage_without_events(self) -> None:
        """途中の場所を通り過ぎると、次の区間を歩き始め、departed_from が途中の場所になる。イベントはためない。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        route = Route(start=SpotId("plaza"), passages=(STREET, LANE))
        whereabouts.start_travel(ALICE, route)
        whereabouts.clear_events()

        whereabouts.advance_travels(frozenset())
        whereabouts.advance_travels(frozenset())

        assert whereabouts.location_of(ALICE) == TravelInProgress(
            route=route, passage_index=1, ticks_left_on_passage=Ticks(1), departed_from=SpotId("well")
        )
        assert whereabouts.get_events() == []

    def test_passage_without_travel_ticks_is_walked_in_the_same_tick(self) -> None:
        """travel_ticks が 0 の区間は、前の区間を歩き終えたのと同じ advance_travels で歩き終える。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        step = path("step", "plaza", "well", ticks=1)
        doorway = path("doorway", "well", "mine_entrance", ticks=0)
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(step, doorway)))

        whereabouts.advance_travels(frozenset())

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("mine_entrance"), section=OpenArea())

    def test_passage_without_travel_ticks_leaves_the_tick_for_the_next_passage(self) -> None:
        """最初の区間の travel_ticks が 0 なら、その tick を使わずに次の 1 tick の区間も歩き終え、1 回の advance_travels で着く。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        doorway = path("doorway", "plaza", "well", ticks=0)
        step = path("step", "well", "mine_entrance", ticks=1)
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(doorway, step)))

        whereabouts.advance_travels(frozenset())

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("mine_entrance"), section=OpenArea())

    def test_travel_on_a_closed_passage_stops_back_at_the_start_of_that_passage(self) -> None:
        """歩いている区間の通路が閉じていると、その区間の出発点に戻って止まり、TravelBlockedEvent と OccupantEnteredSpotEvent をためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET,)))
        whereabouts.clear_events()

        whereabouts.advance_travels(frozenset({PassageId("street")}))

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("plaza"), section=OpenArea())
        blocked, entered = whereabouts.get_events()
        assert isinstance(blocked, TravelBlockedEvent)
        assert (blocked.passage, blocked.stopped_at) == (PassageId("street"), SpotId("plaza"))
        assert isinstance(entered, OccupantEnteredSpotEvent) and entered.spot == SpotId("plaza")

    def test_travel_stops_at_the_intermediate_spot_when_the_next_passage_is_closed(self) -> None:
        """区間を歩き終えて次の区間に差しかかったとき、その通路が閉じていれば途中の場所で止まる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET, LANE)))
        whereabouts.advance_travels(frozenset())
        whereabouts.clear_events()

        whereabouts.advance_travels(frozenset({PassageId("lane")}))

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("well"), section=OpenArea())
        assert _kinds(whereabouts) == [TravelBlockedEvent, OccupantEnteredSpotEvent]

    def test_occupants_not_travelling_are_left_as_they_are(self) -> None:
        """移動中でない人の居場所は advance_travels で変わらない。"""
        whereabouts = _whereabouts((ALICE, "plaza"))

        whereabouts.advance_travels(frozenset())

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("plaza"), section=OpenArea())
        assert whereabouts.get_events() == []


class TestWhereaboutsCancelTravel:
    """cancel_travel が移動をやめさせ、歩いていた区間の出発点に戻すことを保証する。"""

    def test_cancel_travel_returns_to_the_start_of_the_current_passage(self) -> None:
        """2 本目の区間を歩いている人の移動をやめると、途中の場所に戻り、TravelCancelledEvent と OccupantEnteredSpotEvent をためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET, LANE)))
        whereabouts.advance_travels(frozenset())
        whereabouts.advance_travels(frozenset())
        whereabouts.clear_events()

        whereabouts.cancel_travel(ALICE)

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("well"), section=OpenArea())
        cancelled, entered = whereabouts.get_events()
        assert isinstance(cancelled, TravelCancelledEvent) and cancelled.returned_to == SpotId("well")
        assert isinstance(entered, OccupantEnteredSpotEvent)

    def test_cancel_travel_of_someone_not_travelling_is_rejected(self) -> None:
        """移動中でない人の cancel_travel は OccupantNotTravellingException を投げる。"""
        with pytest.raises(OccupantNotTravellingException):
            _whereabouts((ALICE, "plaza")).cancel_travel(ALICE)


class TestWhereaboutsTeleport:
    """teleport が、区画の中でも移動中でも、別の場所の区画の外へ移すことを保証する。"""

    def test_teleport_from_a_section_leaves_it_and_arrives_outside_any_section(self) -> None:
        """籠の中から teleport すると、区画から出た・テレポートした・場所に入ったの順にイベントをためる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)
        whereabouts.clear_events()

        whereabouts.teleport(ALICE, MINE)

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("mine_entrance"), section=OpenArea())
        assert _kinds(whereabouts) == [OccupantLeftSectionEvent, OccupantTeleportedEvent, OccupantEnteredSpotEvent]
        teleported = whereabouts.get_events()[1]
        assert isinstance(teleported, OccupantTeleportedEvent)
        assert (teleported.before, teleported.after) == (
            AtSpot(spot=SpotId("plaza"), section=SpotSectionId("lift_cage")),
            SpotId("mine_entrance"),
        )

    def test_teleport_during_travel_ends_the_travel(self) -> None:
        """移動中に teleport すると移動は終わり、OccupantTeleportedEvent の before は移動中の居場所になる。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET,)))
        whereabouts.clear_events()

        whereabouts.teleport(ALICE, MINE)
        whereabouts.advance_travels(frozenset())

        assert whereabouts.location_of(ALICE) == AtSpot(spot=SpotId("mine_entrance"), section=OpenArea())
        teleported = whereabouts.get_events()[0]
        assert isinstance(teleported, OccupantTeleportedEvent)
        assert isinstance(teleported.before, TravelInProgress)

    def test_teleport_of_an_occupant_not_placed_is_rejected(self) -> None:
        """置いていない人を teleport すると OccupantNotPlacedException を投げる。"""
        with pytest.raises(OccupantNotPlacedException):
            Whereabouts.start(WORLD).teleport(ALICE, MINE)


class TestWhereaboutsTogetherness:
    """occupants_at・are_together・is_at が、同じ場所にいるかを区画を問わずに答えることを保証する。"""

    def test_occupants_at_lists_occupants_in_the_order_they_were_placed(self) -> None:
        """occupants_at は、その場所にいる人を置いた順に返す。区画の中の人も入る。"""
        whereabouts = _whereabouts((BOB, "plaza"), (ALICE, "plaza"), (CAROL, "well"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        assert whereabouts.occupants_at(PLAZA) == (BOB, ALICE)

    def test_occupants_in_and_out_of_a_section_of_the_same_spot_are_together(self) -> None:
        """籠の中の人と籠の外の人は、同じ場所にいるので一緒にいる。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        assert whereabouts.are_together(ALICE, BOB) is True

    def test_occupants_at_different_spots_or_travelling_are_not_together(self) -> None:
        """別の場所にいる人どうし、移動中の人と出発した場所の人は一緒にいない。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "well"), (CAROL, "plaza"))
        whereabouts.start_travel(CAROL, Route(start=SpotId("plaza"), passages=(STREET,)))

        assert whereabouts.are_together(ALICE, BOB) is False
        assert whereabouts.are_together(ALICE, CAROL) is False

    def test_questions_about_an_occupant_not_placed_are_answered_false(self) -> None:
        """置いていない人について is_at・is_in_section・are_together を聞くと、どれも偽を返す。"""
        whereabouts = _whereabouts((BOB, "plaza"))

        assert (
            whereabouts.is_at(ALICE, PLAZA),
            whereabouts.is_in_section(ALICE, LIFT),
            whereabouts.are_together(ALICE, BOB),
        ) == (False, False, False)

    def test_location_of_an_occupant_not_placed_is_rejected(self) -> None:
        """置いていない人の location_of は OccupantNotPlacedException を投げる。"""
        with pytest.raises(OccupantNotPlacedException):
            Whereabouts.start(WORLD).location_of(ALICE)


class TestWhereaboutsCanReach:
    """can_reach が、区画の reachable_objects の物には区画の中からだけ届き、ほかの物にはその場所から届くことを保証する。"""

    LEVER = thing("lift_lever", "plaza")
    NOTICE_BOARD = thing("notice_board", "plaza")

    def test_object_reachable_only_from_a_section_is_reached_from_inside(self) -> None:
        """籠の中にいる人は、籠の reachable_objects に入っているレバーに届く。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        assert whereabouts.can_reach(ALICE, self.LEVER, (LIFT, BENCH)) is True

    def test_object_reachable_only_from_a_section_is_not_reached_from_outside(self) -> None:
        """籠の外にいる人は、同じ場所にいても籠のレバーに届かない。別の区画の中からも届かない。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(BOB, BENCH, NOBODY_DOWN)

        assert whereabouts.can_reach(ALICE, self.LEVER, (LIFT, BENCH)) is False
        assert whereabouts.can_reach(BOB, self.LEVER, (LIFT, BENCH)) is False

    def test_object_outside_every_section_is_reached_from_anywhere_in_its_spot(self) -> None:
        """どの区画の reachable_objects にも無い物には、その場所にいれば区画の中からも外からも届く。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)

        assert whereabouts.can_reach(ALICE, self.NOTICE_BOARD, (LIFT, BENCH)) is True
        assert whereabouts.can_reach(BOB, self.NOTICE_BOARD, (LIFT, BENCH)) is True

    def test_object_at_another_spot_or_while_travelling_is_out_of_reach(self) -> None:
        """別の場所にいる人と移動中の人は、物に届かない。"""
        whereabouts = _whereabouts((ALICE, "well"), (BOB, "plaza"))
        whereabouts.start_travel(BOB, Route(start=SpotId("plaza"), passages=(STREET,)))

        assert whereabouts.can_reach(ALICE, self.NOTICE_BOARD, (LIFT, BENCH)) is False
        assert whereabouts.can_reach(BOB, self.NOTICE_BOARD, (LIFT, BENCH)) is False


class TestWhereaboutsRefusalLeavesNothingBehind:
    """断る操作が、例外を投げたあと誰の居場所も変えず、イベントもためないことを保証する。"""

    @pytest.mark.parametrize(
        ("refuse", "expected"),
        [
            (lambda w: w.enter_section(BOB, LIFT, NOBODY_DOWN), OccupantNotAtSectionSpotException),
            (lambda w: w.enter_section(ALICE, BENCH, NOBODY_DOWN), OccupantAlreadyInSectionException),
            (lambda w: w.leave_section(BOB), OccupantNotInSectionException),
            (
                lambda w: w.start_travel(BOB, Route(start=SpotId("plaza"), passages=(STREET,))),
                OccupantNotAtRouteStartException,
            ),
            (lambda w: w.cancel_travel(ALICE), OccupantNotTravellingException),
            (lambda w: w.teleport(CAROL, MINE), OccupantNotPlacedException),
            (lambda w: w.remove(CAROL), OccupantNotPlacedException),
            (lambda w: w.place(ALICE, WELL), OccupantAlreadyPlacedException),
        ],
    )
    def test_refused_operation_changes_no_location_and_records_no_event(
        self, refuse: Callable[[Whereabouts], None], expected: type[Exception]
    ) -> None:
        """広場の長椅子にいる人と井戸にいる人がいる世界で、断られる操作のあとも 2 人の居場所は元のままで、イベントは 0 件。"""
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "well"))
        whereabouts.enter_section(ALICE, BENCH, NOBODY_DOWN)
        whereabouts.clear_events()
        before = (whereabouts.location_of(ALICE), whereabouts.location_of(BOB))

        with pytest.raises(expected):
            refuse(whereabouts)

        assert (whereabouts.location_of(ALICE), whereabouts.location_of(BOB)) == before
        assert whereabouts.get_events() == []


class TestWhereaboutsMemento:
    """Whereabouts を memento から作り直すと、区画の中にいる人も、移動の途中の人も元の居場所から続くことを保証する。"""

    def test_traveller_rebuilt_halfway_continues_on_the_same_passage(self) -> None:
        """2 tick の通りを 1 tick 歩いた人を作り直すと、通りの残り 1 tick から続き、次の小道を歩いて鉱山の入口に着く。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        route = Route(start=SpotId("plaza"), passages=(STREET, LANE))
        whereabouts.start_travel(ALICE, route)
        whereabouts.advance_travels(frozenset())

        rebuilt = rebuilt_from_memento(whereabouts, DESIGN)

        assert rebuilt.location_of(ALICE) == TravelInProgress(
            route=route, passage_index=0, ticks_left_on_passage=Ticks(1), departed_from=SpotId("plaza")
        )
        rebuilt.advance_travels(frozenset())
        assert rebuilt.location_of(ALICE) == TravelInProgress(
            route=route, passage_index=1, ticks_left_on_passage=Ticks(1), departed_from=SpotId("well")
        )
        rebuilt.advance_travels(frozenset())
        assert rebuilt.is_at(ALICE, MINE)

    def test_traveller_rebuilt_on_the_second_passage_stays_on_it(self) -> None:
        """通りを歩き終えて小道に入った人を作り直すと、小道の上の残り 1 tick にいて、次の tick に鉱山の入口に着く。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        route = Route(start=SpotId("plaza"), passages=(STREET, LANE))
        whereabouts.start_travel(ALICE, route)
        whereabouts.advance_travels(frozenset())
        whereabouts.advance_travels(frozenset())

        rebuilt = rebuilt_from_memento(whereabouts, DESIGN)

        assert rebuilt.location_of(ALICE) == TravelInProgress(
            route=route, passage_index=1, ticks_left_on_passage=Ticks(1), departed_from=SpotId("well")
        )
        rebuilt.advance_travels(frozenset())
        assert rebuilt.is_at(ALICE, MINE)

    def test_rebuilt_whereabouts_answer_the_same(self) -> None:
        """籠の中の人・移動中の人・去った人のいる居場所を作り直すと、memento も居場所の答えも元と同じになる。"""
        departed = DepartedPerson(PersonId("carol"))
        whereabouts = _whereabouts((ALICE, "plaza"), (BOB, "plaza"), (departed, "well"))
        whereabouts.enter_section(ALICE, LIFT, NOBODY_DOWN)
        whereabouts.start_travel(BOB, Route(start=SpotId("plaza"), passages=(STREET,)))

        rebuilt = rebuilt_from_memento(whereabouts, DESIGN)

        assert rebuilt.memento() == whereabouts.memento()
        assert rebuilt.is_in_section(ALICE, LIFT)
        assert rebuilt.location_of(BOB) == whereabouts.location_of(BOB)
        assert rebuilt.is_at(departed, WELL)
        assert rebuilt.world_id == WORLD

    def test_rebuilding_records_no_event(self) -> None:
        """移動を始めたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        whereabouts = _whereabouts((ALICE, "plaza"))
        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(STREET,)))

        assert rebuilt_from_memento(whereabouts, DESIGN).get_events() == []

    def test_memento_travelling_an_undeclared_passage_is_rejected(self) -> None:
        """宣言に無い通路 tunnel を歩いている途中の memento から作り直すと UndeclaredNounException を投げる。"""
        position = TravelPosition(
            route_start=SpotId("plaza"),
            route_passages=(PassageId("tunnel"),),
            passage_index=0,
            ticks_left_on_passage=Ticks(1),
            departed_from=SpotId("plaza"),
        )
        memento = WhereaboutsMemento(world_id=WORLD, locations=frozenset({OccupantLocation(ALICE, position)}))

        with pytest.raises(UndeclaredNounException):
            Whereabouts.from_memento(memento, DESIGN)

    @pytest.mark.parametrize(
        "location",
        [
            AtSpot(spot=SpotId("attic"), section=OpenArea()),
            AtSpot(spot=SpotId("plaza"), section=SpotSectionId("trapdoor")),
            TravelPosition(
                route_start=SpotId("plaza"),
                route_passages=(PassageId("street"),),
                passage_index=0,
                ticks_left_on_passage=Ticks(1),
                departed_from=SpotId("attic"),
            ),
        ],
        ids=["undeclared_spot", "undeclared_section", "departed_from_undeclared_spot"],
    )
    def test_memento_at_an_undeclared_place_is_rejected(self, location: AtSpot | TravelPosition) -> None:
        """宣言に無い場所 attic・宣言に無い区画 trapdoor・attic を出たことになっている移動のどれかを持つ memento から作り直すと UndeclaredNounException を投げる。"""
        memento = WhereaboutsMemento(world_id=WORLD, locations=frozenset({OccupantLocation(ALICE, location)}))

        with pytest.raises(UndeclaredNounException):
            Whereabouts.from_memento(memento, DESIGN)

    def test_memento_in_a_section_of_another_spot_is_rejected(self) -> None:
        """広場の区画 bench に井戸でいることになっている memento から作り直すと OccupantNotAtSectionSpotException を投げる。"""
        location = AtSpot(spot=SpotId("well"), section=SpotSectionId("bench"))
        memento = WhereaboutsMemento(world_id=WORLD, locations=frozenset({OccupantLocation(ALICE, location)}))

        with pytest.raises(OccupantNotAtSectionSpotException):
            Whereabouts.from_memento(memento, DESIGN)

    @pytest.mark.parametrize(
        ("passage_index", "ticks_left", "departed_from", "expected"),
        [
            (2, 1, "mine_entrance", TravelPositionOutsideRouteException),
            (0, 1, "well", TravelNotDepartedFromPassageStartException),
            (1, 1, "plaza", TravelNotDepartedFromPassageStartException),
            (0, 3, "plaza", TicksLeftOutsidePassageException),
            (0, 0, "plaza", TicksLeftOutsidePassageException),
        ],
        ids=[
            "beyond_the_last_passage",
            "departed_from_the_far_end_of_the_first_passage",
            "departed_from_the_route_start_on_the_second_passage",
            "more_ticks_left_than_the_passage_takes",
            "no_ticks_left_on_a_passage_that_takes_ticks",
        ],
    )
    def test_memento_of_a_travel_that_operations_never_leave_is_rejected(
        self, passage_index: int, ticks_left: int, departed_from: str, expected: type[Exception]
    ) -> None:
        """広場から通り (2 tick)・小道 (1 tick) と歩く途中で、3 本目にいる・出た場所が今の通路の手前ではない・残り tick が通路の所要を超えるか 0 のどれかの memento から作り直すと、それぞれの例外を投げる。"""
        position = TravelPosition(
            route_start=SpotId("plaza"),
            route_passages=(PassageId("street"), PassageId("lane")),
            passage_index=passage_index,
            ticks_left_on_passage=Ticks(ticks_left),
            departed_from=SpotId(departed_from),
        )
        memento = WhereaboutsMemento(world_id=WORLD, locations=frozenset({OccupantLocation(ALICE, position)}))

        with pytest.raises(expected):
            Whereabouts.from_memento(memento, DESIGN)

    def test_travel_started_on_a_passage_that_takes_no_ticks_has_none_left(self) -> None:
        """所要 0 tick の通路を 1 本目に歩き始めた人は、残り 0 tick の移動の途中にいる。"""
        instant = path("plank", "plaza", "well", ticks=0)
        whereabouts = _whereabouts((ALICE, "plaza"))

        whereabouts.start_travel(ALICE, Route(start=SpotId("plaza"), passages=(instant,)))

        location = whereabouts.location_of(ALICE)
        assert isinstance(location, TravelInProgress) and location.ticks_left_on_passage == Ticks(0)

    def test_memento_with_one_occupant_at_two_places_is_rejected(self) -> None:
        """同じ人が広場と井戸の 2 か所にいる memento は、作るときに RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            WhereaboutsMemento(
                world_id=WORLD,
                locations=frozenset(
                    {
                        OccupantLocation(ALICE, AtSpot(spot=SpotId("plaza"), section=OpenArea())),
                        OccupantLocation(ALICE, AtSpot(spot=SpotId("well"), section=OpenArea())),
                    }
                ),
            )
