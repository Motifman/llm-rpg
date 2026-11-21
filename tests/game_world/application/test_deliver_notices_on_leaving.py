from __future__ import annotations

from ai_rpg_world.being.contract import Observation, TextWithPeople
from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_notices_on_leaving import (
    DeliverNoticesOnLeaving,
    DeliverNoticesOnLeavingCommand,
)
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.perception.handlers.deliver_notices_on_leaving_handler import (
    DeliverNoticesOnLeavingHandler,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Notable, NoTarget, NotSeenWithoutActor, SightStimulus, SightTexts
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perception_cause import TimePassed
from ai_rpg_world.game_world.domain.person import DeclaredOutcome, Died, Outcome, PersonOutcomeDecidedEvent
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DisplayName,
    OutcomeId,
    PersonId,
    SpotId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.perception_reports import PerceptionReportsReceived
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_WORLD = WorldId("leaving_world")
_AKI, _GEN = PersonId("aki"), PersonId("gen")
_FELL_AT, _COLLAPSED_AT, _LEFT_AT = WorldTick(5), WorldTick(7), WorldTick(9)
_STRANDED = OutcomeDeclaration(
    outcome_id=OutcomeId("stranded"),
    name=DisplayName("取り残された"),
    announcement=TextWithUnassignedPeople("{each_person}は坑道に取り残された。"),
)


def _text(template: str) -> TextWithUnassignedPeople:
    return TextWithUnassignedPeople(template)


def _collapse() -> SightStimulus:
    return SightStimulus(
        where=SpotId("mine"),
        witness=SightTexts(
            clear=_text("坑道の奥が崩れ落ちた").about({}),
            dim=_text("奥で何かが崩れた").about({}),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=_text("気がつくと、坑道の奥が崩れていた").about({}),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=(_AKI,),
        salience=Notable(),
        always_delivered=False,
        at=_COLLAPSED_AT,
    )


class _Observations:
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
    """坑道にアキとゲンがいる。アキは tick 5 に気を失い、tick 7 に倒れたまま崩落に巻き込まれ、その知らせがアキにたまる。"""

    def __init__(self) -> None:
        design = compose_world(
            nouns(
                spots=[spot("mine")],
                characters=[character("aki", "mine"), character("gen", "mine")],
                outcomes=[_STRANDED],
            )
        )
        self._store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="leaving_world",
            scenario_hash="leaving_world",
            design=design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self._store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self._scope = CommandScope(self._store, CommittedEventsDistributor())
        self.observations = _Observations()
        exit = ObservationExit(_WORLD, self.observations)
        self._deliver_perception = DeliverPerception(self._scope, exit, PerceptionReportsReceived())
        self.deliver = DeliverNoticesOnLeaving(self._scope, exit)
        self._scope.run(lambda session: session.people_register().name(_AKI, DisplayName("アキ")))
        self._scope.run(lambda session: session.people_register().name(_GEN, DisplayName("ゲン")))
        self._scope.run(
            lambda session: session.aggregates().vitals(_AKI).take_damage(Damage(999), _FELL_AT, WorldHappening())
        )
        self._deliver_perception(
            DeliverPerceptionCommand(cause=TimePassed(), from_actions=(_collapse(),), from_states=())
        )

    def aki_is_stranded(self) -> None:
        self.is_stranded(_AKI)

    def is_stranded(self, person: PersonId) -> None:
        def leave(session: WorldSession) -> None:
            session.aggregates().outcomes().decide(person, DeclaredOutcome(_STRANDED), _LEFT_AT)
            session.aggregates().whereabouts().remove(PersonBody(person))

        self._scope.run(leave)
        announced = DeclaredOutcome(_STRANDED).announced_to(person, _LEFT_AT)
        self._deliver_perception(DeliverPerceptionCommand(cause=TimePassed(), from_actions=(), from_states=announced))

    def missed_notices_of(self, person: PersonId) -> tuple[MissedNotice, ...]:
        session = self._store.session()
        notices = session.facts().missed_notices(person).notices()
        session.roll_back()
        return notices


def _aki_leaves_fainted() -> _World:
    world = _World()
    world.aki_is_stranded()
    world.deliver(DeliverNoticesOnLeavingCommand(person=_AKI, outcome=DeclaredOutcome(_STRANDED), at=_LEFT_AT))
    return world


class TestOutcomeAnnouncementDelivered:
    """DeliverPerception が、結末の知らせを、世界から外れた本人だけに届けることを保証する。"""

    def test_person_who_left_awake_gets_the_outcome_at_once(self) -> None:
        """起きているゲンが「取り残された」に決まって外れると、ゲンにすぐ動き直させる知らせ「ゲンは坑道に取り残された。」が届く。"""
        world = _World()

        world.is_stranded(_GEN)

        [announced] = world.observations.by_person[_GEN][-1:]
        assert (_template(announced), announced.wants_wake) == ("{each_person}は坑道に取り残された。", True)

    def test_outcome_does_not_reach_anyone_else(self) -> None:
        """ゲンの結末の知らせは、同じ坑道で倒れているアキに届かず、アキにもたまらない。"""
        world = _World()

        world.is_stranded(_GEN)

        assert world.observations.templates_of(_AKI) == []
        assert [notice.text.template for notice in world.missed_notices_of(_AKI)] == [
            "気がつくと、坑道の奥が崩れていた"
        ]


class TestDeliverNoticesOnLeaving:
    """DeliverNoticesOnLeaving が、気を失ったまま結末が決まって外れた本人へ、たまった知らせと結末の知らせをためた順に渡し、空にすることを保証する。"""

    def test_fainted_person_who_left_gets_the_kept_notice_then_the_outcome(self) -> None:
        """気を失ったまま「取り残された」に決まったアキには、崩落の知らせ → 「アキは坑道に取り残された。」の順で届き、「目が覚めた」と場面は届かない。"""
        world = _aki_leaves_fainted()

        assert world.observations.templates_of(_AKI) == [
            "気がつくと、坑道の奥が崩れていた",
            "{each_person}は坑道に取り残された。",
        ]

    def test_outcome_of_one_person_does_not_reach_another(self) -> None:
        """アキの結末の知らせは、同じ坑道にいたゲンには届かない。"""
        world = _aki_leaves_fainted()

        assert "{each_person}は坑道に取り残された。" not in world.observations.templates_of(_GEN)

    def test_missed_notices_are_cleared(self) -> None:
        """渡したあと、アキのたまった知らせは空になる。"""
        assert _aki_leaves_fainted().missed_notices_of(_AKI) == ()

    def test_death_hands_over_nothing(self) -> None:
        """結末が死んだこと (Died) のときは、世界から外れないので、たまった崩落の知らせを渡さずに残す。"""
        world = _World()

        world.deliver(DeliverNoticesOnLeavingCommand(person=_AKI, outcome=Died(), at=_LEFT_AT))

        assert world.observations.templates_of(_AKI) == []
        assert [notice.text.template for notice in world.missed_notices_of(_AKI)] == [
            "気がつくと、坑道の奥が崩れていた"
        ]


class TestDeliverNoticesOnLeavingHandler:
    """DeliverNoticesOnLeavingHandler が、結末が決まった本人と結末と時刻で DeliverNoticesOnLeaving を呼ぶことを保証する。"""

    def test_decided_outcome_hands_over_the_notices_of_the_person(self) -> None:
        """アキの結末が決まったイベントで、アキにだけ、たまった知らせと結末の知らせが渡る。"""
        world = _World()
        world.aki_is_stranded()
        outcome: Outcome = DeclaredOutcome(_STRANDED)
        decided = PersonOutcomeDecidedEvent(
            **new_event_stamp(), world=_WORLD, person=_AKI, outcome=outcome, at=_LEFT_AT
        )

        DeliverNoticesOnLeavingHandler(world.deliver).handle(decided)

        assert world.observations.templates_of(_AKI) == [
            "気がつくと、坑道の奥が崩れていた",
            "{each_person}は坑道に取り残された。",
        ]
