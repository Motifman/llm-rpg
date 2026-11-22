from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.being.contract import Observation, TextWithPeople
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception
from ai_rpg_world.game_world.application.deliver_perception_of_committed_events import (
    DeliverPerceptionOfCommittedEvents,
)
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.settle_world_conditions import (
    SettleWorldConditions,
    SettleWorldConditionsCommand,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.condition.subject import NamedPerson
from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.spot.unchanged import Unchanged
from ai_rpg_world.game_world.domain.declaration.verb import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import SightAt, SoundFrom
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import SequenceEffect
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.membership_and_outcome_effects import SetOutcomeEffect
from ai_rpg_world.game_world.domain.effect.spot_and_passage_effects import ChangeAtmosphereEffect
from ai_rpg_world.game_world.domain.effect.whereabouts_effects import TeleportEffect
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Notable
from ai_rpg_world.game_world.domain.perception.delivery_rank import Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDeliveryResult
from ai_rpg_world.game_world.domain.sound import Loudness
from ai_rpg_world.game_world.domain.value_object import DisplayName, OutcomeId, PersonId, WorldId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.perception_reports import PerceptionReportsReceived
from tests.game_world.support.verb_declarations_for_tests import seen_clearly_only
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import (
    character,
    clock_wording,
    compose_world,
    half_hour_ticks_from_midnight,
    nouns,
    passage,
    spot,
)

_WORLD = WorldId("place_notice_world")
_NORTH_SHAFT, _ENTRANCE, _DEEP_MINE = spot("north_shaft"), spot("entrance"), spot("deep_mine")
_POWER_ROOM = replace(
    spot("power_room"), atmosphere=replace(spot("power_room").atmosphere, lighting=Lighting.PITCH_DARK)
)
_GEN, _AKI, _KEN = character("gen", "north_shaft"), character("aki", "north_shaft"), character("ken", "north_shaft")
_HARU = character("haru", "entrance")
_NATSU = character("natsu", "deep_mine")
_SAYO = character("sayo", "power_room")
_EVERYONE = (_GEN, _AKI, _KEN, _HARU, _NATSU, _SAYO)
_BURIED = OutcomeDeclaration(
    outcome_id=OutcomeId("buried"),
    name=DisplayName("埋もれた"),
    announcement=TextWithUnassignedPeople("{each_person}は崩れた坑道に埋もれた。"),
)


def _text(template: str) -> TextWithUnassignedPeople:
    return TextWithUnassignedPeople(template)


def _moved_to(spot_: SpotDeclaration, *people: CharacterDeclaration) -> tuple[Effect, ...]:
    return tuple(TeleportEffect(who=NamedPerson(person), to=spot_) for person in people)


_COLLAPSE_EFFECT = SequenceEffect(
    (
        *_moved_to(_ENTRANCE, _GEN, _AKI),
        *_moved_to(_NORTH_SHAFT, _NATSU),
        SetOutcomeEffect(who=NamedPerson(_KEN), outcome=_BURIED),
    )
)
_LIGHTS_ON = ChangeAtmosphereEffect(
    spot=_POWER_ROOM, lighting=Lighting.BRIGHT, temperature=Unchanged(), ambient_sound=Unchanged(), smell=Unchanged()
)
_COLLAPSE_SEEN = SightAt(spot=_NORTH_SHAFT, texts=seen_clearly_only("天井が崩れ落ちた。"), salience=Notable())
_COLLAPSE_HEARD = SoundFrom(
    spot=_NORTH_SHAFT,
    sound=SoundDeclaration(
        Loudness.NORMAL, clear=_text("天井が崩れる音がした。"), muffled=_text("何かが崩れる音がした。")
    ),
    salience=Notable(),
)


def _collapse(notice: SightAt | SoundFrom) -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId("collapse"), condition=AlwaysHolds(), effect=_COLLAPSE_EFFECT, once=True, notice=notice
    )


def _generator_started() -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId("generator"),
        condition=AlwaysHolds(),
        effect=_LIGHTS_ON,
        once=True,
        notice=SightAt(
            spot=_POWER_ROOM, texts=seen_clearly_only("発電機が唸りを上げ、灯りがともった。"), salience=Notable()
        ),
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
    for declared in _EVERYONE:
        session.people_register().name(declared.person_id, DisplayName(declared.person_id.value))


class _World:
    """北の坑道にゲンとアキとケン、坑道とつながる入口にハル、どことも道のつながらない坑道の奥にナツ、真っ暗な発電機室にサヨがいる。

    作者の出来事が 1 つあり、落ち着かせると発火して、確定したイベントが刺激になって人に届く。
    """

    def __init__(self, happening: HappeningDeclaration) -> None:
        self.design = compose_world(
            nouns(
                spots=[_NORTH_SHAFT, _ENTRANCE, _DEEP_MINE, _POWER_ROOM],
                outcomes=[_BURIED],
                passages=[passage("shaft_entrance", ("north_shaft", "entrance"))],
                characters=list(_EVERYONE),
            ),
            happenings=[happening],
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="place_notice_world",
            scenario_hash="place_notice_world",
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
        self.scope.run(_name_everyone)

    def settles(self) -> None:
        SettleWorldConditions(self.scope, self.design)(SettleWorldConditionsCommand(SettlingOccasion.AFTER_COMMAND))

    def missed_by(self) -> dict[PersonId, NotPerceivedReason]:
        return dict(self._place_notice().missed_by)

    def listed(self) -> set[PersonId]:
        result = self._place_notice()
        return {*result.perceived_by, *result.kept_for, *result.missed_by}

    def _place_notice(self) -> StimulusDeliveryResult:
        (result,) = (
            result for result in self.reports.reports[0].stimuli if result.stimulus.sense is not Sense.ANNOUNCEMENT
        )
        return result


class TestPlaceSightReachesWhoWasThereBeforeTheEffect:
    """出来事の場所の見える知らせ (SightAt) は、効果の前の居場所で居合わせたかを決め、効果の後の明るさで見えることを保証する (D2207)。"""

    def test_people_pushed_out_by_the_collapse_see_it(self) -> None:
        """崩落で北の坑道のゲンとアキが入口へ押し出されても、二人に「天井が崩れ落ちた」が届く。"""
        world = _World(_collapse(_COLLAPSE_SEEN))

        world.settles()

        assert world.observations.templates_of(_GEN.person_id) == ["天井が崩れ落ちた。"]
        assert world.observations.templates_of(_AKI.person_id) == ["天井が崩れ落ちた。"]

    def test_person_pushed_in_by_the_collapse_does_not_see_it(self) -> None:
        """崩落で坑道の奥から北の坑道へ押し込まれたナツには「天井が崩れ落ちた」が届かず、記録にも並ばない。"""
        world = _World(_collapse(_COLLAPSE_SEEN))

        world.settles()

        assert world.observations.templates_of(_NATSU.person_id) == []
        assert _NATSU.person_id not in world.listed()

    def test_person_who_left_the_world_by_the_collapse_is_listed_as_left(self) -> None:
        """崩落の前に北の坑道にいて、崩落で埋もれて世界から外れたケンは、記録に理由「世界から外れた」で残る。"""
        world = _World(_collapse(_COLLAPSE_SEEN))

        world.settles()

        assert world.missed_by()[_KEN.person_id] is NotPerceivedReason.LEFT_THE_WORLD

    def test_sight_is_seen_in_the_light_after_the_effect(self) -> None:
        """真っ暗な発電機室で発電機が回って灯りがともると、その場にいたサヨに、ともった後の明るさで知らせが見える。"""
        world = _World(_generator_started())

        world.settles()

        assert world.observations.templates_of(_SAYO.person_id) == ["発電機が唸りを上げ、灯りがともった。"]


class TestPlaceSoundIsHeardFromWhereEachPersonWasBeforeTheEffect:
    """出来事の場所の音の知らせ (SoundFrom) は、効果の前の居場所で、効果の後の通路を通して聞くことを保証する (D2207)。"""

    def test_people_pushed_out_by_the_collapse_hear_it_as_if_still_inside(self) -> None:
        """崩落で北の坑道のゲンとアキが入口へ押し出されても、北の坑道で聞いたことになり、崩れる音がくぐもらずに届く。入口に元からいたハルにはくぐもって届く。"""
        world = _World(_collapse(_COLLAPSE_HEARD))

        world.settles()

        assert world.observations.templates_of(_GEN.person_id) == ["天井が崩れる音がした。"]
        assert world.observations.templates_of(_AKI.person_id) == ["天井が崩れる音がした。"]
        assert world.observations.templates_of(_HARU.person_id) == ["何かが崩れる音がした。"]

    def test_person_pushed_in_from_beyond_earshot_does_not_hear_it_and_is_listed_as_far(self) -> None:
        """崩落の前に音の届かない坑道の奥にいたナツは、北の坑道へ押し込まれても崩れる音を受け取らず、記録に理由「遠い」で残る。"""
        world = _World(_collapse(_COLLAPSE_HEARD))

        world.settles()

        assert world.observations.templates_of(_NATSU.person_id) == []
        assert world.missed_by()[_NATSU.person_id] is NotPerceivedReason.OUT_OF_EARSHOT

    def test_person_who_left_the_world_by_the_collapse_is_listed_as_left(self) -> None:
        """崩落の前に北の坑道にいて、崩落で埋もれて世界から外れたケンは、崩れる音の記録に理由「世界から外れた」で残る。"""
        world = _World(_collapse(_COLLAPSE_HEARD))

        world.settles()

        assert world.missed_by()[_KEN.person_id] is NotPerceivedReason.LEFT_THE_WORLD
