from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.being.contract import Observation, TextWithPeople
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.interact_with_object import (
    InteractWithObject,
    InteractWithObjectCommand,
)
from ai_rpg_world.game_world.application.action.speak import Speak, SpeakCommand
from ai_rpg_world.game_world.application.action.start_travel import StartTravel, StartTravelCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_notices_on_leaving import DeliverNoticesOnLeaving
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception
from ai_rpg_world.game_world.application.deliver_perception_of_committed_events import (
    DeliverPerceptionOfCommittedEvents,
)
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime, PassWorldTimeCommand
from ai_rpg_world.game_world.application.perception.handlers.deliver_notices_on_leaving_handler import (
    DeliverNoticesOnLeavingHandler,
)
from ai_rpg_world.game_world.application.settle_world_conditions import (
    SettleWorldConditions,
    SettleWorldConditionsCommand,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_arguments import ChosenArguments
from ai_rpg_world.game_world.domain.action.built_in_attempts import SpeechAttempt, TravelAttempt
from ai_rpg_world.game_world.domain.action.interaction_attempts import ObjectInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, SpeechContent
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.declaration.verb import AnnouncementTo, HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.noun_interaction_declarations import ObjectInteractionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Notable
from ai_rpg_world.game_world.domain.perception.delivery_rank import Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perception_cause import ActionTaken, HappeningFiring, TimePassed
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDescription
from ai_rpg_world.game_world.domain.person import DeclaredOutcome
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.person.person_outcomes import PersonOutcomeDecidedEvent
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.sound import Loudness
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DisplayName,
    InteractionId,
    OutcomeId,
    PersonId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.perception_reports import PerceptionReportsReceived
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly, pull_lever, seen_clearly_only
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds, ChangesNothing
from tests.game_world.support.world_design_for_tests import (
    built_in_action_perceptions,
    character,
    clock_wording,
    compose_world,
    half_hour_ticks_from_midnight,
    nouns,
    obj,
    passage,
    spot,
)

_WORLD = WorldId("committed_perception_world")
_HARU, _SAYO, _GEN, _AKI, _NATSU, _FUYU = (PersonId(name) for name in ("haru", "sayo", "gen", "aki", "natsu", "fuyu"))
_SQUARE, _HALL, _DEEP_MINE = spot("square"), spot("hall"), spot("deep_mine")
_DOOR = obj("door", "square")
_STRANDED = OutcomeDeclaration(
    outcome_id=OutcomeId("stranded"),
    name=DisplayName("取り残された"),
    announcement=TextWithUnassignedPeople("{each_person}は坑道に取り残された。"),
)


def _text(template: str) -> TextWithUnassignedPeople:
    return TextWithUnassignedPeople(template)


_BREAK_DOOR = replace(
    pull_lever(()),
    interaction_id=InteractionId("break_door"),
    display_label=DisplayName("break_door"),
    perceived_as=replace(
        lever_pulled_quietly(),
        witness=seen_clearly_only("{actor}が扉を壊した。"),
        sound=SoundDeclaration(
            Loudness.LOUD, clear=_text("扉が壊れる音がした。"), muffled=_text("何かが壊れる音がした。")
        ),
    ),
)


def _bell(name: str, text: str) -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId(name),
        condition=AlwaysHolds(),
        effect=ChangesNothing(),
        once=True,
        notice=AnnouncementTo(audience=PeopleSelection(where=AlwaysHolds()), text=_text(text), salience=Notable()),
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


def _name_everyone(session: WorldSession) -> None:
    for person in (_HARU, _SAYO, _GEN, _AKI, _NATSU, _FUYU):
        session.people_register().name(person, DisplayName(person.value))


class _World:
    """広場にハルとサヨ、隣の広間にゲンとナツとフユ、どことも道のつながらない坑道の奥にアキがいる。

    確定したイベントを、刺激に変えて人に届ける受け手 (DeliverPerceptionOfCommittedEvents) が配線されている。
    """

    def __init__(self) -> None:
        self.design = compose_world(
            nouns(
                spots=[_SQUARE, _HALL, _DEEP_MINE],
                passages=[passage("square_hall", ("square", "hall"))],
                objects=[_DOOR],
                outcomes=[_STRANDED],
                characters=[
                    character("haru", "square"),
                    character("sayo", "square"),
                    character("gen", "hall"),
                    character("natsu", "hall"),
                    character("fuyu", "hall"),
                    character("aki", "deep_mine"),
                ],
            ),
            object_interactions=[ObjectInteractionDeclaration(obj=_DOOR, interaction=_BREAK_DOOR)],
            happenings=[_bell("bell", "鐘が鳴った。"), _bell("gong", "銅鑼が鳴った。")],
            built_in_action_perceptions_=replace(
                built_in_action_perceptions(without=(ActionKind.TEND,)),
                ordinary_voice=replace(
                    lever_pulled_quietly(),
                    witness=seen_clearly_only("{actor}が話した。"),
                    sound=SoundDeclaration(
                        Loudness.NORMAL, clear=_text("{actor}の声がした。"), muffled=_text("話し声がした。")
                    ),
                ),
                arrival=replace(lever_pulled_quietly(), witness=seen_clearly_only("{actor}が着いた。")),
            ),
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="committed_perception_world",
            scenario_hash="committed_perception_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=self.design))
        distributor = CommittedEventsDistributor()
        self.scope = CommandScope(self.store, distributor)
        self.observations = _Observations()
        self.reports = PerceptionReportsReceived()
        exit = ObservationExit(_WORLD, half_hour_ticks_from_midnight(), clock_wording(), self.observations)
        distributor.register_receiver(
            DeliverPerceptionOfCommittedEvents(self.design, DeliverPerception(self.scope, exit, self.reports))
        )
        distributor.register_handler(
            PersonOutcomeDecidedEvent, DeliverNoticesOnLeavingHandler(DeliverNoticesOnLeaving(self.scope, exit))
        )
        self._carry_out = CarryOutAction(self.scope, self.design)
        self.scope.run(_name_everyone)

    def breaks_the_door(self, actor: PersonId) -> None:
        attempt = ObjectInteractionAttempt(actor, _DOOR, _BREAK_DOOR, ChosenArguments(), Openly())
        InteractWithObject(self._carry_out, self.design)(InteractWithObjectCommand(attempt))

    def says(self, actor: PersonId, text: str) -> None:
        Speak(self._carry_out)(SpeakCommand(SpeechAttempt(actor, OrdinaryVoice(), SpeechContent(text))))

    def walks_to_the_square(self, actor: PersonId) -> None:
        StartTravel(self._carry_out, self.design)(StartTravelCommand(TravelAttempt(actor, _SQUARE)))

    def passes_one_tick(self) -> None:
        PassWorldTime(self.scope)(PassWorldTimeCommand())

    def settles(self) -> None:
        SettleWorldConditions(self.scope, self.design)(SettleWorldConditionsCommand(SettlingOccasion.AFTER_COMMAND))

    def faints(self, person: PersonId) -> None:
        self.scope.run(
            lambda session: session.aggregates().vitals(person).take_damage(Damage(999), WorldTick(0), WorldHappening())
        )

    def dies(self, person: PersonId) -> None:
        def die(session: WorldSession) -> None:
            facts = session.facts()
            vitals = session.aggregates().vitals(person)
            vitals.take_damage(Damage(999), facts.now(), WorldHappening())
            vitals.pass_time(facts.now() + facts.rules().death.grace, facts.rules().death, facts.rules().hunger)

        self.scope.run(die)

    def is_stranded(self, person: PersonId) -> None:
        def leave(session: WorldSession) -> None:
            now = session.facts().now()
            session.aggregates().outcomes().decide(person, DeclaredOutcome(_STRANDED), now)
            session.aggregates().whereabouts().remove(PersonBody(person))

        self.scope.run(leave)


class TestStimuliOfOneActionAreDeliveredTogether:
    """1 つの行為で出たイベントを 1 つのまとまりとして届け、同じ tick の別の行為は別のまとまりにすることを保証する。"""

    def test_breaking_the_door_shows_sayo_the_sight_and_lets_gen_hear_only_the_sound(self) -> None:
        """ハルが扉を壊すと、同じ広場のサヨには壊す様子だけが、隣の広間のゲンには壊れる音だけが届く。"""
        world = _World()

        world.breaks_the_door(_HARU)

        assert world.observations.templates_of(_SAYO) == ["{actor}が扉を壊した。"]
        assert world.observations.templates_of(_GEN) == ["扉が壊れる音がした。"]

    def test_another_action_in_the_same_tick_is_delivered_apart(self) -> None:
        """扉が壊れたのと同じ tick にサヨが話すと、ゲンには壊れる音に続けて、別のまとまりとして話し声も届く。"""
        world = _World()

        world.breaks_the_door(_HARU)
        world.says(_SAYO, "何の音?")

        assert world.observations.templates_of(_GEN) == ["扉が壊れる音がした。", "話し声がした。"]
        assert [report.cause for report in world.reports.reports] == [
            ActionTaken(actor=_HARU, kind=ActionKind.INTERACT_WITH_OBJECT),
            ActionTaken(actor=_SAYO, kind=ActionKind.SPEAK),
        ]


class TestReportOfDelivery:
    """届けるたびに作る記録 (PerceptionDeliveryReport) に、原因・tick・刺激・人ごとの結果が残ることを保証する。"""

    def test_report_carries_cause_tick_stimuli_and_results(self) -> None:
        """扉を壊した記録には、ハルの行為・tick 0・見える刺激と音の刺激が残り、見える刺激は広場のサヨに、音は広間のゲン・ナツ・フユに届く。壊したハル本人には届かず、理由「自分の行為」が残る。"""
        world = _World()

        world.breaks_the_door(_HARU)

        (report,) = world.reports.reports
        assert report.at == WorldTick(0)
        assert [result.stimulus for result in report.stimuli] == [
            StimulusDescription(
                sense=Sense.SIGHT, text="{actor}が扉を壊した。", where=_SQUARE.spot_id, addressed_to=frozenset()
            ),
            StimulusDescription(
                sense=Sense.SOUND, text="扉が壊れる音がした。", where=_SQUARE.spot_id, addressed_to=frozenset()
            ),
        ]
        sight, sound = report.stimuli
        assert set(sight.perceived_by) == {_SAYO}
        assert set(sound.perceived_by) == {_GEN, _NATSU, _FUYU}
        assert (sight.missed_by[_HARU], sound.missed_by[_HARU]) == (
            NotPerceivedReason.OWN_ACT,
            NotPerceivedReason.OWN_ACT,
        )

    def test_aki_far_away_does_not_hear_and_the_reason_is_far(self) -> None:
        """道のつながらない坑道の奥のアキには壊れる音が届かず、記録に理由「遠い」が残る。"""
        world = _World()

        world.breaks_the_door(_HARU)

        sound = world.reports.reports[0].stimuli[1]
        assert world.observations.templates_of(_AKI) == []
        assert sound.missed_by[_AKI] is NotPerceivedReason.OUT_OF_EARSHOT

    def test_sayo_who_saw_it_is_left_as_already_perceived_for_the_sound(self) -> None:
        """壊す様子を見たサヨには音が重ねて届かず、記録に理由「同じものをもう知った」が残る。"""
        world = _World()

        world.breaks_the_door(_HARU)

        sound = world.reports.reports[0].stimuli[1]
        assert sound.missed_by[_SAYO] is NotPerceivedReason.ALREADY_PERCEIVED

    def test_people_who_died_or_left_are_not_listed(self) -> None:
        """世界から外れたナツと死んだフユは居場所が無く、扉を壊した記録の見える刺激にも音にも並ばない。"""
        world = _World()
        world.is_stranded(_NATSU)
        world.dies(_FUYU)

        world.breaks_the_door(_HARU)

        for result in world.reports.reports[-1].stimuli:
            assert {_NATSU, _FUYU}.isdisjoint({*result.perceived_by, *result.kept_for, *result.missed_by})


class TestStimuliOfOneFiringAreDeliveredTogether:
    """作者の出来事は、1 回の確定に複数の発火があっても、発火 1 回ずつのまとまりとして届けることを保証する。"""

    def test_each_firing_gets_its_own_report(self) -> None:
        """1 回の落ち着かせで「鐘」と「銅鑼」が発火すると、記録は発火ごとに 2 つに分かれる。"""
        world = _World()

        world.settles()

        assert [report.cause for report in world.reports.reports] == [
            HappeningFiring(HappeningId("bell")),
            HappeningFiring(HappeningId("gong")),
        ]

    def test_a_fainted_person_is_kept_for_later(self) -> None:
        """気を失っているゲンには「鐘が鳴った」が届かずにたまり、記録に「ためた」が残る。"""
        world = _World()
        world.faints(_GEN)

        world.settles()

        bell = world.reports.reports[0].stimuli[0]
        assert world.observations.templates_of(_GEN) == []
        assert _GEN in bell.kept_for
        assert _GEN not in bell.perceived_by


class TestArrivalsInOneTickAreDeliveredApart:
    """時の経過では、刺激になるイベント 1 つずつを別のまとまりにすることを保証する。"""

    def test_two_people_arriving_in_the_same_tick_both_reach_sayo(self) -> None:
        """同じ tick に広場へ着いたナツとフユは、広場のサヨにどちらも届く。"""
        world = _World()
        world.walks_to_the_square(_NATSU)
        world.walks_to_the_square(_FUYU)

        world.passes_one_tick()

        assert world.observations.templates_of(_SAYO) == ["{actor}が着いた。", "{actor}が着いた。"]
        assert [report.cause for report in world.reports.reports[-2:]] == [TimePassed(), TimePassed()]


class TestPersonLeavingWhileFainted:
    """気を失ったまま結末が決まって世界から外れた人に、配線の上でも、たまった知らせ → 結末の知らせの順で渡ることを保証する。"""

    def test_notices_kept_while_fainted_come_before_the_outcome(self) -> None:
        """アキが気を失っている間に「鐘が鳴った」「銅鑼が鳴った」がたまり、「取り残された」に決まって外れると、アキにはその順で渡る。"""
        world = _World()
        world.faints(_AKI)
        world.settles()

        world.is_stranded(_AKI)

        assert world.observations.templates_of(_AKI) == [
            "鐘が鳴った。",
            "銅鑼が鳴った。",
            "{each_person}は坑道に取り残された。",
        ]
