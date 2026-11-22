from __future__ import annotations

from ai_rpg_world.being.contract import Observation, ObservedTime, SeenOrHeard, TextWithPeople
from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_surroundings import DeliverSurroundings, DeliverSurroundingsCommand
from ai_rpg_world.game_world.application.look_around import LookAround
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.perception.handlers.deliver_surroundings_on_arrival_handler import (
    DeliverSurroundingsOnArrivalHandler,
)
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, PersonId, SpotId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import OccupantEnteredSpotEvent, PersonBody
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import (
    character,
    clock_wording,
    compose_world,
    half_hour_ticks_from_midnight,
    nouns,
    passage,
    spot,
)

_WORLD = WorldId("deliver_surroundings_world")
_ALICE, _BOB, _CAROL, _DAVE = (PersonId(name) for name in ("alice", "bob", "carol", "dave"))
_AT = WorldTick(3)


class _ObservationsReceived:
    def __init__(self) -> None:
        self.by_person: dict[PersonId, list[Observation]] = {}

    def receive(self, person: PersonId, observation: Observation) -> None:
        self.by_person.setdefault(person, []).append(observation)


class _World:
    """明るい洞窟に alice・bob・carol、小屋に dave だけがいる。洞窟と小屋が道でつながる。"""

    def __init__(self) -> None:
        design = compose_world(
            nouns(
                spots=[spot("cave"), spot("hut")],
                passages=[passage("cave_hut", ("cave", "hut"))],
                characters=[
                    character("alice", "cave"),
                    character("bob", "cave"),
                    character("carol", "cave"),
                    character("dave", "hut"),
                ],
            )
        )
        store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="deliver_surroundings_world",
            scenario_hash="deliver_surroundings_world",
            design=design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self._scope = CommandScope(store, CommittedEventsDistributor())
        self.received = _ObservationsReceived()
        self.deliver = DeliverSurroundings(
            LookAround(self._scope, design),
            design,
            ObservationExit(_WORLD, half_hour_ticks_from_midnight(), clock_wording(), self.received),
        )

    def delivers_surroundings_to(self, person: PersonId) -> None:
        self.deliver(DeliverSurroundingsCommand(person=person, at=_AT))

    def falls(self, person: PersonId) -> None:
        self._scope.run(
            lambda session: session.aggregates().vitals(person).take_damage(Damage(999), _AT, WorldHappening())
        )


class TestDeliverSurroundings:
    """DeliverSurroundings が、見渡した場面の人と倒れた体を 1 つの観測にして本人へ渡すことを保証する。

    人も倒れた体もいなければ観測を出さない。いる側の文だけを、人、倒れた体の順につなぐ。
    """

    def test_people_and_bodies_arrive_as_one_seen_observation(self) -> None:
        """洞窟の alice には、bob の文に倒れた carol の文が続く観測が 1 つだけ、見聞きした経路と渡した時刻で届く。"""
        world = _World()
        world.falls(_CAROL)

        world.delivers_surroundings_to(_ALICE)

        [observation] = world.received.by_person[_ALICE]
        assert isinstance(observation.body, TextWithPeople)
        assert observation.body.template == "ここには{person_1}がいる。{person_2}が倒れている。"
        assert (observation.route, observation.time) == (SeenOrHeard(), ObservedTime(display="Day 1 深夜 1:30"))
        assert set(world.received.by_person) == {_ALICE}

    def test_no_observation_when_no_one_else_is_there(self) -> None:
        """小屋に 1 人きりの dave には、観測が届かない。"""
        world = _World()

        world.delivers_surroundings_to(_DAVE)

        assert world.received.by_person == {}

    def test_no_observation_for_a_fallen_person(self) -> None:
        """倒れている carol には場面が無く、観測が届かない。"""
        world = _World()
        world.falls(_CAROL)

        world.delivers_surroundings_to(_CAROL)

        assert world.received.by_person == {}


class TestDeliverSurroundingsOnArrivalHandler:
    """DeliverSurroundingsOnArrivalHandler が、場所に着いた本人にだけ、着いた時刻で場面を渡すことを保証する。"""

    def test_only_the_arriving_person_gets_the_surroundings(self) -> None:
        """bob が小屋から洞窟に着くと、bob に着いた時刻の場面が届き、洞窟に元からいた alice と carol には届かない。"""
        world = _World()
        arrived = OccupantEnteredSpotEvent(
            **new_event_stamp(),
            world_id=_WORLD,
            occupant=PersonBody(_BOB),
            spot=SpotId("cave"),
            origin=SpotId("hut"),
            at=WorldTick(5),
        )

        DeliverSurroundingsOnArrivalHandler(world.deliver).handle(arrived)

        assert set(world.received.by_person) == {_BOB}
        assert [observation.time for observation in world.received.by_person[_BOB]] == [
            ObservedTime(display="Day 1 深夜 2:30")
        ]
