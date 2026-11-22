from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.being.contract import Observation, TextWithPeople
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.interact_with_person import (
    InteractWithPerson,
    InteractWithPersonCommand,
)
from ai_rpg_world.game_world.application.action.start_travel import StartTravel, StartTravelCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception
from ai_rpg_world.game_world.application.deliver_perception_of_committed_events import (
    DeliverPerceptionOfCommittedEvents,
)
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import TravelAttempt
from ai_rpg_world.game_world.domain.action.interaction_attempts import PersonInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.subject import Target
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.built_in_action_perceptions import BuiltInActionPerceptions
from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import InteractionDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import SequenceEffect
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.membership_and_outcome_effects import SetOutcomeEffect
from ai_rpg_world.game_world.domain.effect.whereabouts_effects import TeleportEffect
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception.delivery_rank import Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDeliveryResult
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import DisplayName, InteractionId, OutcomeId, PersonId, WorldId
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.perception_reports import PerceptionReportsReceived
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly, pull_lever, seen_clearly_only
from tests.game_world.support.world_design_for_tests import (
    built_in_action_perceptions,
    character,
    compose_world,
    half_hour_ticks_from_midnight,
    nouns,
    passage,
    spot,
)

_WORLD = WorldId("cliff_world")
_CLIFF_TOP, _VALLEY, _TRAIL = spot("cliff_top"), spot("valley"), spot("trail")
_HARU, _GEN, _SAYO = PersonId("haru"), PersonId("gen"), PersonId("sayo")
_AKI = PersonId("aki")
_FELL_AWAY = OutcomeDeclaration(
    outcome_id=OutcomeId("fell_away"),
    name=DisplayName("谷底へ消えた"),
    announcement=TextWithUnassignedPeople("{each_person}は谷底へ消えた。"),
)
_PUSHED_SEEN = "{actor}が{target}を崖から突き落とした。"
_PUSHED_FELT = "{actor}に崖から突き落とされた。"
_SET_OFF_SEEN = "{actor}が{destination}へ向かった。"


def _push(effect: Effect) -> InteractionDeclaration:
    return replace(
        pull_lever(()),
        interaction_id=InteractionId("push_off_the_cliff"),
        effect=effect,
        perceived_as=replace(
            lever_pulled_quietly(),
            witness=seen_clearly_only(_PUSHED_SEEN),
            target=seen_clearly_only(_PUSHED_FELT),
        ),
        reaches_unseen=True,
    )


_PUSH_DOWN = _push(TeleportEffect(who=Target(), to=_VALLEY))
_PUSH_AWAY = _push(
    SequenceEffect((TeleportEffect(who=Target(), to=_VALLEY), SetOutcomeEffect(who=Target(), outcome=_FELL_AWAY)))
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
    for person in (_HARU, _GEN, _SAYO, _AKI):
        session.people_register().name(person, DisplayName(person.value))


def _perceptions_with_setting_off() -> BuiltInActionPerceptions:
    perceptions = built_in_action_perceptions()
    set_off = replace(lever_pulled_quietly(), witness=seen_clearly_only(_SET_OFF_SEEN))
    return replace(perceptions, by_kind={**perceptions.by_kind, ActionKind.TRAVEL: set_off})


class _Cliff:
    """崖の上にハルとゲンとサヨ、道のつながらない下の谷にアキがいる。崖の上からは山道へ道が続いている。

    ハルが行為を行うと、確定したイベントが刺激になって人に届く。
    """

    def __init__(self, push: InteractionDeclaration) -> None:
        self.push = push
        self.design = compose_world(
            nouns(
                spots=[_CLIFF_TOP, _VALLEY, _TRAIL],
                passages=[passage("trail_path", ("cliff_top", "trail"))],
                outcomes=[_FELL_AWAY],
                characters=[
                    character("haru", "cliff_top"),
                    character("gen", "cliff_top"),
                    character("sayo", "cliff_top"),
                    character("aki", "valley"),
                ],
            ),
            person_interactions=[push],
            built_in_action_perceptions_=_perceptions_with_setting_off(),
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="cliff_world",
            scenario_hash="cliff_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=self.design))
        distributor = CommittedEventsDistributor()
        self.scope = CommandScope(self.store, distributor)
        self.observations = _Observations()
        self.reports = PerceptionReportsReceived()
        exit = ObservationExit(_WORLD, half_hour_ticks_from_midnight(), self.observations)
        distributor.register_receiver(
            DeliverPerceptionOfCommittedEvents(self.design, DeliverPerception(self.scope, exit, self.reports))
        )
        self.scope.run(_name_everyone)

    def haru_pushes_gen(self) -> None:
        attempt = PersonInteractionAttempt(_HARU, _GEN, self.push, {}, Openly())
        InteractWithPerson(CarryOutAction(self.scope, self.design), self.design)(InteractWithPersonCommand(attempt))

    def haru_sets_off_to_the_trail(self) -> None:
        StartTravel(CarryOutAction(self.scope, self.design), self.design)(
            StartTravelCommand(TravelAttempt(_HARU, _TRAIL))
        )

    def seen_push(self) -> StimulusDeliveryResult:
        (result,) = (
            result
            for report in self.reports.reports
            for result in report.stimuli
            if result.stimulus.sense is Sense.SIGHT and result.stimulus.text == _PUSHED_SEEN
        )
        return result


class TestActNoticeReachesWhoWasThereBeforeTheEffect:
    """行為の見える知らせ (PersonActedEvent) は、効果の前の居場所で居合わせたかを決めることを保証する (D2216)。"""

    def test_person_pushed_down_feels_being_pushed(self) -> None:
        """ハルがゲンを崖から下の谷へ突き落とすと、ゲンに「ハルに崖から突き落とされた」が届く。"""
        cliff = _Cliff(_PUSH_DOWN)

        cliff.haru_pushes_gen()

        assert cliff.observations.templates_of(_GEN) == [_PUSHED_FELT]

    def test_bystander_on_the_cliff_sees_the_push(self) -> None:
        """ハルがゲンを突き落とすと、崖の上にいたサヨに「ハルがゲンを崖から突き落とした」が届く。"""
        cliff = _Cliff(_PUSH_DOWN)

        cliff.haru_pushes_gen()

        assert cliff.observations.templates_of(_SAYO) == [_PUSHED_SEEN]

    def test_person_already_in_the_valley_does_not_see_the_push(self) -> None:
        """下の谷にもともといたアキには、ゲンが谷へ落ちてきても崖の上の知らせは届かず、記録にも並ばない。"""
        cliff = _Cliff(_PUSH_DOWN)

        cliff.haru_pushes_gen()

        result = cliff.seen_push()
        assert cliff.observations.templates_of(_AKI) == []
        assert _AKI not in {*result.perceived_by, *result.kept_for, *result.missed_by}

    def test_person_pushed_out_of_the_world_is_listed_as_left(self) -> None:
        """突き落とされて世界から外れたゲンには突き落とされた知らせが届かず、記録に理由「世界から外れた」で残る。"""
        cliff = _Cliff(_PUSH_AWAY)

        cliff.haru_pushes_gen()

        assert _PUSHED_FELT not in cliff.observations.templates_of(_GEN)
        assert cliff.seen_push().missed_by[_GEN] is NotPerceivedReason.LEFT_THE_WORLD


class TestActorWhoMovesSeesTheirOwnAct:
    """行う人自身が動く行為でも、行う人は効果の前の居場所で自分の行為を知覚することを保証する (D2216)。"""

    def test_person_setting_off_sees_their_own_departure(self) -> None:
        """崖の上のハルが山道へ移動を始めると、もう崖の上にいなくても、ハルに「ハルが山道 (trail) へ向かった」が届く。"""
        cliff = _Cliff(_PUSH_DOWN)

        cliff.haru_sets_off_to_the_trail()

        assert cliff.observations.templates_of(_HARU) == ["{actor}がtrailへ向かった。"]
