from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

import pytest

from ai_rpg_world.being.contract import Observation, ObservedTime, TextWithPeople
from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import AggregateWithMemento, WorldSession
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Background,
    BodilyStimulus,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenWithoutActor,
    Salience,
    SightStimulus,
    SightTexts,
    SoundStimulus,
    Stimulus,
    Voice,
)
from ai_rpg_world.game_world.domain.perception.delivery_rank import DeliveryRank, Sense
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.sound_stimulus import NotWhispered
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.sound import Loudness
from ai_rpg_world.game_world.domain.value_object import Damage, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PersonBody, Route
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, passage, spot

_WORLD = WorldId("perception_world")
_ALICE, _BOB, _CAROL, _DAVE, _EVE, _FRANK = (
    PersonId(name) for name in ("alice", "bob", "carol", "dave", "eve", "frank")
)
_SQUARE = spot("square")
_HALL = spot("hall")
_CELLAR = spot("cellar")
_ATTIC = spot("attic")
_DARK_ROOM = replace(spot("dark_room"), atmosphere=replace(spot("dark_room").atmosphere, lighting=Lighting.DARK))
_SQUARE_HALL = passage("square_hall", ("square", "hall"))
_HALL_CELLAR = passage("hall_cellar", ("hall", "cellar"), travel_ticks=3)
_AT = WorldTick(0)


def _about(template: str, **people: PersonId) -> TextAboutPeople:
    return TextWithUnassignedPeople(template).about(people)


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
    """広場に alice と bob、広間に carol、地下室に dave、屋根裏に eve、暗い部屋に frank がいる。

    広場と広間、広間と地下室が道でつながり、屋根裏と暗い部屋はどこともつながっていない。
    """

    def __init__(self) -> None:
        design = compose_world(
            nouns(
                spots=[_SQUARE, _HALL, _CELLAR, _ATTIC, _DARK_ROOM],
                passages=[_SQUARE_HALL, _HALL_CELLAR],
                characters=[
                    character("alice", "square"),
                    character("bob", "square"),
                    character("carol", "hall"),
                    character("dave", "cellar"),
                    character("eve", "attic"),
                    character("frank", "dark_room"),
                ],
            )
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="perception_world",
            scenario_hash="perception_world",
            design=design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self.scope = CommandScope(self.store, CommittedEventsDistributor())
        self.received = _ObservationsReceived()
        self._deliver = DeliverPerception(self.scope, ObservationExit(_WORLD, self.received))

    def deliver_with_a_failing_commit(self, *, from_actions: tuple[Stimulus, ...]) -> None:
        scope = CommandScope(_CommitRefusingStore(self.store), CommittedEventsDistributor())
        deliver = DeliverPerception(scope, ObservationExit(_WORLD, self.received))
        deliver(DeliverPerceptionCommand(from_actions=from_actions, from_states=()))

    def deliver(self, *, from_actions: tuple[Stimulus, ...] = (), from_states: tuple[Stimulus, ...] = ()) -> None:
        self._deliver(DeliverPerceptionCommand(from_actions=from_actions, from_states=from_states))

    def fell(self, person: PersonId) -> None:
        self.scope.run(
            lambda session: session.aggregates().vitals(person).take_damage(Damage(999), _AT, WorldHappening())
        )

    def sets_out(self, person: PersonId, route: Route) -> None:
        self.scope.run(lambda session: session.aggregates().whereabouts().start_travel(PersonBody(person), route))

    def teleports(self, person: PersonId, to: SpotDeclaration) -> None:
        self.scope.run(lambda session: session.aggregates().whereabouts().teleport(PersonBody(person), to, _AT))

    def missed_notice_templates_of(self, person: PersonId) -> list[str]:
        session = self.store.session()
        templates = [notice.text.template for notice in session.facts().missed_notices(person).notices()]
        session.roll_back()
        return templates


def _sight(
    where: SpotDeclaration = _SQUARE,
    *,
    clear: str = "扉が開いた",
    dim: str = "何かが動いた",
    noticed_later: str | None = None,
    involved: tuple[PersonId, ...] = (),
    salience: Salience = Notable(),
    always_delivered: bool = False,
) -> SightStimulus:
    return SightStimulus(
        where=where.spot_id,
        witness=SightTexts(
            clear=_about(clear),
            dim=_about(dim),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater() if noticed_later is None else _about(noticed_later),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=involved,
        salience=salience,
        always_delivered=always_delivered,
        at=_AT,
    )


def _shout(where: SpotDeclaration = _SQUARE, *, loudness: Loudness = Loudness.LOUD) -> SoundStimulus:
    return SoundStimulus(
        origin=where.spot_id,
        loudness=loudness,
        clear=_about("「誰かいるか」と叫ぶ声がした"),
        muffled=_about("叫び声がした"),
        noticed_later=NotNoticedLater(),
        source=Voice(whispered_to=NotWhispered()),
        involved=(),
        salience=Notable(),
        at=_AT,
    )


def _ache(person: PersonId, text: str = "足が痛む") -> BodilyStimulus:
    return BodilyStimulus(person=person, text=_about(text), salience=Notable(), at=_AT)


class TestWhoPerceives:
    """DeliverPerception が、刺激ごとに知覚しうる人を刺激に聞いて、届いた人にだけ観測を渡すことを保証する。"""

    def test_sight_reaches_only_people_at_the_spot(self) -> None:
        """広場で扉が開くと、広場の alice と bob には見えた観測が届き、広間の carol には届かない。"""
        world = _World()

        world.deliver(from_actions=(_sight(_SQUARE),))

        assert world.received.templates_of(_ALICE) == ["扉が開いた"]
        assert world.received.templates_of(_BOB) == ["扉が開いた"]
        assert world.received.templates_of(_CAROL) == []

    def test_sound_reaches_spots_it_carries_to_and_not_beyond(self) -> None:
        """広場の大きい叫び声は、道でつながった広間の carol に届き、どこともつながらない屋根裏の eve には届かない。"""
        world = _World()

        world.deliver(from_actions=(_shout(_SQUARE),))

        assert world.received.templates_of(_CAROL) == ["「誰かいるか」と叫ぶ声がした"]
        assert world.received.templates_of(_EVE) == []

    def test_traveller_hears_a_loud_sound_at_an_end_of_the_passage_but_sees_nothing(self) -> None:
        """広間から地下室へ歩いている carol には、地下室の大きい叫び声が届き、広間で扉が開いたのは見えない。"""
        world = _World()
        world.sets_out(_CAROL, Route(start=_HALL.spot_id, passages=(_HALL_CELLAR,)))

        world.deliver(from_actions=(_shout(_CELLAR), _sight(_HALL, clear="広間の扉が開いた")))

        assert world.received.templates_of(_CAROL) == ["「誰かいるか」と叫ぶ声がした"]

    def test_sight_in_a_dark_spot_arrives_as_the_dim_text(self) -> None:
        """暗い部屋で扉が開くと、frank には dim の文「何かが動いた」が届く。"""
        world = _World()

        world.deliver(from_actions=(_sight(_DARK_ROOM),))

        assert world.received.templates_of(_FRANK) == ["何かが動いた"]


class TestReceiversChosenAfterTheEffect:
    """場所の見える刺激の受け手は、効果を当てて確定した後の世界から選ばれることを保証する (#1978 の 7e で確かめること)。

    出来事の効果が人を動かすと、動かされる前にその場所にいた人には、その場所の知らせが届かない。
    """

    def test_people_pushed_out_of_the_spot_miss_its_sight(self) -> None:
        """崩落で広場の alice と bob が広間へ押し出された後に広場の崩落の見える刺激を配ると、誰にも届かない。"""
        world = _World()
        world.teleports(_ALICE, _HALL)
        world.teleports(_BOB, _HALL)

        world.deliver(from_actions=(_sight(_SQUARE, clear="天井が崩れ落ちた"),))

        assert world.received.by_person == {}


class TestOnePerPerson:
    """1 つの確定から出た刺激は、決まった順に聞き、1 人には最初に知覚したもの 1 つだけを渡すことを保証する。"""

    def test_own_body_wins_over_sight(self) -> None:
        """見える刺激を先に渡しても、足の痛む alice には体の刺激だけが届き、bob には見えた観測が届く。"""
        world = _World()

        world.deliver(from_actions=(_sight(_SQUARE), _ache(_ALICE)))

        assert world.received.templates_of(_ALICE) == ["足が痛む"]
        assert world.received.templates_of(_BOB) == ["扉が開いた"]

    def test_stimulus_from_an_action_wins_over_one_from_a_state(self) -> None:
        """行為から作った見える刺激は、状態から作った本人の体の刺激より先に聞くので、alice には見えた観測だけが届く。"""
        world = _World()

        world.deliver(from_actions=(_sight(_SQUARE),), from_states=(_ache(_ALICE),))

        assert world.received.templates_of(_ALICE) == ["扉が開いた"]

    def test_notable_wins_over_background_of_the_same_sense(self) -> None:
        """目立たない見える刺激を先に渡しても、目立つ見える刺激が先に届く。"""
        world = _World()

        world.deliver(
            from_actions=(
                _sight(_SQUARE, clear="風で葉が揺れた", salience=Background()),
                _sight(_SQUARE, clear="扉が開いた", salience=Notable()),
            )
        )

        assert world.received.templates_of(_ALICE) == ["扉が開いた"]

    def test_stimuli_of_the_same_rank_keep_the_order_they_came_in(self) -> None:
        """種類も目立ち方も同じ見える刺激が 2 つあれば、先に渡したほうが届く。"""
        world = _World()

        world.deliver(from_actions=(_sight(_SQUARE, clear="扉が開いた"), _sight(_SQUARE, clear="窓が開いた")))

        assert world.received.templates_of(_ALICE) == ["扉が開いた"]

    def test_always_delivered_stimulus_counts_as_the_first_one(self) -> None:
        """ほかと重なっても届ける見える刺激を先に受けた alice には、そのあとの目立たない見える刺激は届かない。"""
        world = _World()

        world.deliver(
            from_actions=(
                _sight(_SQUARE, clear="bob が倒れた", always_delivered=True),
                _sight(_SQUARE, clear="風で葉が揺れた", salience=Background()),
            )
        )

        assert world.received.templates_of(_ALICE) == ["bob が倒れた"]

    def test_always_delivered_stimulus_arrives_on_top_of_another(self) -> None:
        """ほかと重なっても届ける見える刺激は、体の刺激を受けた alice にも重ねて届く。"""
        world = _World()

        world.deliver(from_actions=(_ache(_ALICE), _sight(_SQUARE, clear="bob が倒れた", always_delivered=True)))

        assert world.received.templates_of(_ALICE) == ["足が痛む", "bob が倒れた"]


class TestFallenPeople:
    """倒れている人の分は、出口に渡さずに MissedNotices にためることを保証する。"""

    def test_fallen_person_keeps_the_notice_and_gets_no_observation(self) -> None:
        """倒れている bob が関わる扉の破壊は、bob の MissedNotices に noticed_later の文でたまり、bob には観測が届かない。"""
        world = _World()
        world.fell(_BOB)

        world.deliver(from_actions=(_sight(_SQUARE, noticed_later="扉が壊れている", involved=(_BOB,)),))

        assert world.missed_notice_templates_of(_BOB) == ["扉が壊れている"]
        assert world.received.templates_of(_BOB) == []
        assert world.received.templates_of(_ALICE) == ["扉が開いた"]

    def test_fallen_person_keeps_only_the_first_notice_of_one_scope(self) -> None:
        """同じ確定から倒れている bob の関わる見える刺激が 2 つ出ても、bob の MissedNotices にたまるのは先の 1 つだけ。"""
        world = _World()
        world.fell(_BOB)

        world.deliver(
            from_actions=(
                _sight(_SQUARE, noticed_later="扉が壊れている", involved=(_BOB,)),
                _sight(_SQUARE, noticed_later="窓が割れている", involved=(_BOB,)),
            )
        )

        assert world.missed_notice_templates_of(_BOB) == ["扉が壊れている"]


class _CommitRefusingSession:
    def __init__(self, session: WorldSession) -> None:
        self._session = session

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)

    def commit(self) -> tuple[DomainEvent, ...]:
        raise _Refused("commit refused for the test")


class _CommitRefusingStore:
    def __init__(self, store: SqliteWorldStore) -> None:
        self._store = store

    def start_world(self, aggregates: Iterable[AggregateWithMemento]) -> None:
        self._store.start_world(aggregates)

    def session(self) -> WorldSession:
        return _CommitRefusingSession(self._store.session())  # type: ignore[return-value]


class _RefusedStimulus:
    """聞かれると、ドメインの決まりに反するとして断る刺激。"""

    always_delivered = True

    def delivery_rank(self) -> DeliveryRank:
        return DeliveryRank(sense=Sense.ANNOUNCEMENT, stands_back=True)

    def perceived_in(self, perceiver: Perceiver, senses: PerceptionSenses) -> PerceptionOutcome:
        raise _Refused("refused for the test")


class _Refused(GameWorldDomainException):
    error_code = "TEST.REFUSED"


class TestRefusedInTheScope:
    """確定の範囲の中で断られたら、観測を 1 つも出口に渡さず、ためた知らせも残さないことを保証する。観測は確定のあとにだけ渡る。"""

    def test_nothing_is_handed_over_or_kept_when_a_stimulus_is_refused(self) -> None:
        """見える刺激のあとに断る刺激が来ると、広場の alice にも観測が届かず、倒れている bob の MissedNotices も空のまま。"""
        world = _World()
        world.fell(_BOB)

        with pytest.raises(_Refused):
            world.deliver(
                from_actions=(
                    _sight(_SQUARE, noticed_later="扉が壊れている", involved=(_BOB,)),
                    _RefusedStimulus(),  # type: ignore[arg-type]
                )
            )

        assert world.received.by_person == {}
        assert world.missed_notice_templates_of(_BOB) == []

    def test_nothing_is_handed_over_when_the_commit_is_refused(self) -> None:
        """広場で扉が開いても、確定が断られれば、alice にも bob にも観測は届かない。"""
        world = _World()

        with pytest.raises(_Refused):
            world.deliver_with_a_failing_commit(from_actions=(_sight(_SQUARE),))

        assert world.received.by_person == {}


class TestObservationTime:
    """出口に渡る観測に、起きた tick の時刻の札が付くことを保証する。"""

    def test_observation_has_the_time_label_of_the_tick(self) -> None:
        """tick 0 に起きたことは、時刻の札「tick 0」を付けて届く。"""
        world = _World()

        world.deliver(from_actions=(_sight(_SQUARE),))

        assert [observation.time for observation in world.received.by_person[_ALICE]] == [ObservedTime("tick 0")]
