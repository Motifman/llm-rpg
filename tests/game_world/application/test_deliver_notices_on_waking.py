from __future__ import annotations

from ai_rpg_world.being.contract import EnvironmentNotice, Observation, ObservedTime, OwnBodyState, TextWithPeople
from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_notices_on_waking import (
    DeliverNoticesOnWaking,
    DeliverNoticesOnWakingCommand,
)
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception
from ai_rpg_world.game_world.application.deliver_surroundings import DeliverSurroundings
from ai_rpg_world.game_world.application.look_around import LookAround
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.perception.handlers.deliver_notices_on_waking_handler import (
    DeliverNoticesOnWakingHandler,
)
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.person import PersonRevivedEvent
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, HitPoints, PersonId, Rate, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_WORLD = WorldId("waking_world")
_ALICE, _BOB = PersonId("alice"), PersonId("bob")
_FELL_AT = WorldTick(5)
_WOKE_AT = WorldTick(9)


class _ObservationsReceived:
    def __init__(self) -> None:
        self.by_person: dict[PersonId, list[Observation]] = {}

    def receive(self, person: PersonId, observation: Observation) -> None:
        self.by_person.setdefault(person, []).append(observation)

    def templates_of(self, person: PersonId) -> list[str]:
        return [_template(observation) for observation in self.by_person.get(person, [])]


def _template(observation: Observation) -> str:
    assert isinstance(observation.body, TextWithPeople)
    return observation.body.template


class _World:
    """明るい洞窟に alice と bob がいる。alice は tick 5 に倒れ、倒れている間に知らせが 2 つたまっている。"""

    def __init__(self) -> None:
        design = compose_world(
            nouns(spots=[spot("cave")], characters=[character("alice", "cave"), character("bob", "cave")])
        )
        self._store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="waking_world",
            scenario_hash="waking_world",
            design=design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self._store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self._scope = CommandScope(self._store, CommittedEventsDistributor())
        self.received = _ObservationsReceived()
        exit = ObservationExit(_WORLD, self.received)
        self.deliver = DeliverNoticesOnWaking(
            self._scope,
            design,
            DeliverPerception(self._scope, exit),
            DeliverSurroundings(LookAround(self._scope, design), design, exit),
            exit,
        )
        self._scope.run(self._falls_and_misses_two_notices)

    def _falls_and_misses_two_notices(self, session: WorldSession) -> None:
        aggregates = session.aggregates()
        aggregates.vitals(_ALICE).take_damage(Damage(999), _FELL_AT, WorldHappening())
        missed = aggregates.missed_notices(_ALICE)
        missed.keep(
            MissedNotice(text=TextWithAssignedPeople("気がつくと、扉が開いていた", {}), happened_at=WorldTick(6))
        )
        missed.keep(
            MissedNotice(text=TextWithAssignedPeople("気がつくと、灯りが消えていた", {}), happened_at=WorldTick(8))
        )

    def revives(self, person: PersonId) -> None:
        self._scope.run(lambda session: session.aggregates().vitals(person).revive(Rate(0.5), _WOKE_AT))

    def missed_notices_of(self, person: PersonId) -> tuple[MissedNotice, ...]:
        session = self._store.session()
        notices = session.facts().missed_notices(person).notices()
        session.roll_back()
        return notices


class TestDeliverNoticesOnWaking:
    """DeliverNoticesOnWaking が、目覚めた本人へ、目が覚めた → たまった知らせ (ためた順) → 場面 の順に渡し、たまった知らせを空にすることを保証する。

    たまった知らせも、目が覚めた時刻の観測として渡す。Being の短期記憶は同じ環境の観測を時刻 (OccurrenceOrder) で
    安定に並べ直すので、倒れている間の時刻のまま渡すと「目が覚めた」より前に記憶に入ってしまうため。
    """

    def test_waking_then_missed_notices_then_surroundings_arrive_in_order(self) -> None:
        """alice には「目が覚めた。」、扉、灯り、bob のいる場面の順に観測が届く。"""
        world = _World()
        world.revives(_ALICE)

        world.deliver(DeliverNoticesOnWakingCommand(person=_ALICE, at=_WOKE_AT))

        assert world.received.templates_of(_ALICE) == [
            "目が覚めた。",
            "気がつくと、扉が開いていた",
            "気がつくと、灯りが消えていた",
            "ここには{person_1}がいる。",
        ]

    def test_only_waking_calls_attention_and_notices_come_as_environment_notices(self) -> None:
        """目立つのは本人の体の「目が覚めた。」だけで、たまった知らせは環境からの知らせとして目立たずに届く。"""
        world = _World()
        world.revives(_ALICE)

        world.deliver(DeliverNoticesOnWakingCommand(person=_ALICE, at=_WOKE_AT))

        waking, *notices, _ = world.received.by_person[_ALICE]
        assert (waking.route, waking.wants_wake) == (OwnBodyState(), True)
        assert [(notice.route, notice.wants_wake) for notice in notices] == [(EnvironmentNotice(), False)] * 2

    def test_every_observation_has_the_time_of_waking(self) -> None:
        """たまった知らせも含め、届く観測はすべて目が覚めた tick 9 の時刻と順を持つ。"""
        world = _World()
        world.revives(_ALICE)

        world.deliver(DeliverNoticesOnWakingCommand(person=_ALICE, at=_WOKE_AT))

        observations = world.received.by_person[_ALICE]
        assert {observation.time for observation in observations} == {ObservedTime(display="tick 9")}
        assert {observation.order.value for observation in observations if observation.order} == {9}

    def test_missed_notices_are_cleared(self) -> None:
        """渡したあと、alice のたまった知らせは空になる。"""
        world = _World()
        world.revives(_ALICE)

        world.deliver(DeliverNoticesOnWakingCommand(person=_ALICE, at=_WOKE_AT))

        assert world.missed_notices_of(_ALICE) == ()


class TestDeliverNoticesOnWakingHandler:
    """DeliverNoticesOnWakingHandler が、起き上がった本人について、起き上がった時刻で DeliverNoticesOnWaking を呼ぶことを保証する。"""

    def test_revived_person_gets_the_notices_at_the_time_of_revival(self) -> None:
        """alice が tick 9 に起き上がったイベントで、alice にだけ tick 9 の「目が覚めた。」から届く。"""
        world = _World()
        world.revives(_ALICE)
        revived = PersonRevivedEvent(
            **new_event_stamp(), person=_ALICE, revived_at=_WOKE_AT, hp_after=HitPoints(50, 100)
        )

        DeliverNoticesOnWakingHandler(world.deliver).handle(revived)

        assert set(world.received.by_person) == {_ALICE}
        assert world.received.by_person[_ALICE][0].time == ObservedTime(display="tick 9")
