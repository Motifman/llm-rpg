from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.being.contract import EnvironmentNotice, Observation, ObservedTime, OwnBodyState, TextWithPeople
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import Perception, ShortTermMemory
from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_notices_on_waking import (
    DeliverNoticesOnWaking,
    DeliverNoticesOnWakingCommand,
)
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.deliver_surroundings import DeliverSurroundings
from ai_rpg_world.game_world.application.look_around import LookAround
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.perception.handlers.deliver_notices_on_waking_handler import (
    DeliverNoticesOnWakingHandler,
)
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Notable,
    NoTarget,
    NotSeenWithoutActor,
    SightStimulus,
    SightTexts,
)
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perception_cause import TimePassed
from ai_rpg_world.game_world.domain.person import PersonRevivedEvent
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    HitPoints,
    PersonId,
    Rate,
    SpotId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.perception_reports import PerceptionReportsReceived
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_WORLD = WorldId("waking_world")
_ALICE, _BOB = PersonId("alice"), PersonId("bob")
_FELL_AT, _COLLAPSED_AT, _WOKE_AT = WorldTick(5), WorldTick(7), WorldTick(9)


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
        involved=(_ALICE,),
        salience=Notable(),
        always_delivered=False,
        at=_COLLAPSED_AT,
    )


class _Memories:
    def __init__(self) -> None:
        self.observations: dict[PersonId, list[Observation]] = {}
        self._memories: dict[PersonId, ShortTermMemory] = {}

    def receive(self, person: PersonId, observation: Observation) -> None:
        self.observations.setdefault(person, []).append(observation)
        memory = self._memories.setdefault(person, ShortTermMemory.empty(BeingId(person.value)))
        # 名前を埋めるのはこのテストの外 (Being の手前) なので、並び順だけを見られるよう文の型をそのまま覚えさせる。
        memory.perceive(replace(observation, body=_body_template(observation)), current_turn=1)

    def recalled_by(self, person: PersonId) -> list[str]:
        return [_template(experience) for experience in self._memories[person].recent()]


def _body_template(observation: Observation) -> str:
    assert isinstance(observation.body, TextWithPeople)
    return observation.body.template


def _template(experience: object) -> str:
    assert isinstance(experience, Perception)
    assert isinstance(experience.observation.body, str)
    return experience.observation.body


class _World:
    """明るい坑道に alice と bob がいる。alice は tick 5 に倒れ、tick 7 に倒れたまま崩落に巻き込まれ、その知らせが alice にたまる。"""

    def __init__(self) -> None:
        design = compose_world(
            nouns(spots=[spot("mine")], characters=[character("alice", "mine"), character("bob", "mine")])
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
        self.memories = _Memories()
        exit = ObservationExit(_WORLD, self.memories)
        deliver_perception = DeliverPerception(self._scope, exit, PerceptionReportsReceived())
        self.deliver = DeliverNoticesOnWaking(
            self._scope,
            design,
            deliver_perception,
            DeliverSurroundings(LookAround(self._scope, design), design, exit),
            exit,
        )
        self._scope.run(
            lambda session: session.aggregates().vitals(_ALICE).take_damage(Damage(999), _FELL_AT, WorldHappening())
        )
        deliver_perception(DeliverPerceptionCommand(cause=TimePassed(), from_actions=(_collapse(),), from_states=()))

    def revives_alice(self) -> None:
        self._scope.run(lambda session: session.aggregates().vitals(_ALICE).revive(Rate(0.5), _WOKE_AT))

    def missed_notices_of(self, person: PersonId) -> tuple[MissedNotice, ...]:
        session = self._store.session()
        notices = session.facts().missed_notices(person).notices()
        session.roll_back()
        return notices


def _wakes_alice() -> _World:
    world = _World()
    world.revives_alice()
    world.deliver(DeliverNoticesOnWakingCommand(person=_ALICE, at=_WOKE_AT))
    return world


class TestDeliverNoticesOnWaking:
    """DeliverNoticesOnWaking が、目覚めた本人へ、目が覚めた → たまった知らせ (ためた順) → 場面 の順に渡し、たまった知らせを空にすることを保証する。

    たまった知らせは、目が覚めた時刻に知ったものとして渡す。Being の短期記憶は同じ環境の観測を時刻 (OccurrenceOrder) で
    安定に並べ直すので、倒れている間の時刻のまま渡すと「目が覚めた」より前に記憶に入ってしまうため。
    """

    def test_memory_recalls_waking_then_the_collapse_then_the_surroundings(self) -> None:
        """tick 9 に起きた alice の記憶には、「目が覚めた。」→ 崩落の知らせ → bob のいる場面 の順に入る。"""
        world = _wakes_alice()

        assert world.memories.recalled_by(_ALICE) == [
            "目が覚めた。",
            "気がつくと、坑道の奥が崩れていた",
            "ここには{person_1}がいる。",
        ]

    def test_only_waking_calls_attention_and_the_notice_comes_as_an_environment_notice(self) -> None:
        """目立つのは本人の体の「目が覚めた。」だけで、崩落の知らせは環境からの知らせとして目立たずに届く。"""
        waking, collapse, _ = _wakes_alice().memories.observations[_ALICE]

        assert (waking.route, waking.wants_wake) == (OwnBodyState(), True)
        assert (collapse.route, collapse.wants_wake) == (EnvironmentNotice(), False)

    def test_every_observation_has_the_time_of_waking(self) -> None:
        """崩落の知らせも含め、届く観測はすべて目が覚めた tick 9 の時刻と順を持つ。"""
        observations = _wakes_alice().memories.observations[_ALICE]

        assert {observation.time for observation in observations} == {ObservedTime(display="tick 9")}
        assert {observation.order.value for observation in observations if observation.order} == {9}

    def test_missed_notices_are_cleared(self) -> None:
        """渡したあと、alice のたまった知らせは空になる。"""
        assert _wakes_alice().missed_notices_of(_ALICE) == ()


class TestDeliverNoticesOnWakingHandler:
    """DeliverNoticesOnWakingHandler が、起き上がった本人について、起き上がった時刻で DeliverNoticesOnWaking を呼ぶことを保証する。"""

    def test_revived_person_gets_the_notices_at_the_time_of_revival(self) -> None:
        """alice が tick 9 に起き上がったイベントで、alice にだけ tick 9 の「目が覚めた。」から届く。"""
        world = _World()
        world.revives_alice()
        revived = PersonRevivedEvent(
            **new_event_stamp(), person=_ALICE, revived_at=_WOKE_AT, hp_after=HitPoints(50, 100)
        )

        DeliverNoticesOnWakingHandler(world.deliver).handle(revived)

        assert world.memories.observations[_ALICE][0].time == ObservedTime(display="tick 9")
        assert [observation.time for observation in world.memories.observations[_BOB]] == [
            ObservedTime(display="tick 7")
        ]
