"""居場所と集団の決定の集約 (Whereabouts・PassageStates・SpotAtmospheres・GroupDecision) の memento が JSON を行き来し、知らない形の行を止めることを保証する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from ai_rpg_world.game_world.domain.declaration.spot import (
    NoAmbientSound,
    NoSmell,
    PassageDeclaration,
    PassageStateDeclaration,
    SpotAtmosphere,
    Temperature,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.sound import SoundLoss
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    GroupDecisionId,
    PassageId,
    PassageStateName,
    PersonId,
    SpotId,
    SpotSectionId,
    Ticks,
    WorldId,
)
from ai_rpg_world.game_world.domain.whereabouts import (
    AtmosphereAtSpot,
    AtSpot,
    DepartedPerson,
    OccupantLocation,
    OpenArea,
    PassageCondition,
    PassagePresence,
    PassageStates,
    PassageStatesMemento,
    PersonBody,
    Route,
    SpotAtmospheres,
    SpotAtmospheresMemento,
    TravelPosition,
    Whereabouts,
    WhereaboutsMemento,
)
from ai_rpg_world.game_world.domain.world_progress import (
    Abstain,
    Ballot,
    GroupDecision,
    GroupDecisionMemento,
    VoteFor,
)
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS, StoredMemento
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    StoredMementoUnreadableException,
)
from tests.game_world.support.world_design_for_tests import group_decision, passage, section, spot

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")
_DAVE = PersonId("dave")
_OPEN = PassageStateName("open")
_CLOSED = PassageStateName("closed")


def _door(name: str, *, hidden: bool) -> PassageDeclaration:
    return PassageDeclaration(
        passage_id=PassageId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の様子"),
        ends=(SpotId("beach"), SpotId("cave")),
        two_way=True,
        travel_ticks=Ticks(1),
        states=(
            PassageStateDeclaration(
                name=_OPEN, display_name=DisplayName("開いている"), traversable=True, sound_loss=SoundLoss(0)
            ),
            PassageStateDeclaration(
                name=_CLOSED, display_name=DisplayName("閉じている"), traversable=False, sound_loss=SoundLoss(20)
            ),
        ),
        initial_state=_OPEN,
        hidden_until_revealed=hidden,
    )


def _whereabouts() -> WhereaboutsMemento:
    whereabouts = Whereabouts.start(_WORLD)
    for person in (_ALICE, _BOB):
        whereabouts.place(PersonBody(person), spot("beach"))
    whereabouts.place(DepartedPerson(_CAROL), spot("cave"))
    whereabouts.enter_section(PersonBody(_ALICE), section("boat", "beach"), frozenset())
    whereabouts.start_travel(
        PersonBody(_BOB),
        Route(SpotId("beach"), (passage("shore", ("beach", "cave"), 3), passage("tunnel", ("cave", "mine"), 2))),
    )
    return whereabouts.memento()


def _passage_states() -> PassageStatesMemento:
    doors = (_door("gate", hidden=False), _door("crack", hidden=True), _door("bridge", hidden=False))
    states = PassageStates.start(_WORLD, doors)
    states.change_state(doors[0], _CLOSED)
    states.remove(doors[2])
    return states.memento()


def _atmospheres() -> SpotAtmospheresMemento:
    atmospheres = SpotAtmospheres.start(_WORLD, (spot("beach"), spot("cave")))
    atmospheres.change(
        spot("cave"),
        SpotAtmosphere(
            lighting=Lighting.PITCH_DARK,
            outdoor=False,
            temperature=Temperature.COLD,
            ambient_sound=DescriptionText("水の滴る音"),
            smell=DescriptionText("湿った土のにおい"),
        ),
    )
    return atmospheres.memento()


def _decision() -> GroupDecisionMemento:
    decision = GroupDecision.not_started(group_decision("exile_vote"))
    decision.start(frozenset({_ALICE, _BOB, _CAROL, _DAVE}), frozenset({_BOB, _CAROL}))
    decision.cast(_ALICE, VoteFor(_BOB))
    decision.cast(_DAVE, Abstain())
    return decision.memento()


_MEMENTOS = {
    "whereabouts": _whereabouts(),
    "passage_states": _passage_states(),
    "spot_atmospheres": _atmospheres(),
    "group_decision": _decision(),
}


def _round_trip(memento: object) -> object:
    return GAME_WORLD_CODECS.memento(GAME_WORLD_CODECS.stored(memento), type(memento))


def _with_nested(
    stored: StoredMemento, path: tuple[str | int, ...], change: Callable[[dict[str, Any]], None]
) -> StoredMemento:
    state = json.loads(stored.state)
    target = state
    for step in path:
        target = target[step]
    change(target)
    return replace(stored, state=json.dumps(state))


_NESTED_OBJECTS = [
    ("whereabouts", ("locations", 0, "occupant", "person_body"), "person"),
    ("whereabouts", ("locations", 0, "location", "at_spot"), "spot"),
    ("whereabouts", ("locations", 1, "location", "travel_position"), "departed_from"),
    ("passage_states", ("passages", 0), "presence"),
    ("spot_atmospheres", ("atmospheres", 0), "atmosphere"),
    ("spot_atmospheres", ("atmospheres", 0, "atmosphere"), "smell"),
    ("group_decision", ("ballots", 0), "choice"),
    ("group_decision", ("ballots", 0, "choice", "vote_for"), "person"),
]
_NESTED_IDS = [f"{kind}:{path[-1]}" for kind, path, _ in _NESTED_OBJECTS]


def _with_state(stored: StoredMemento, change: dict[str, object]) -> StoredMemento:
    state = json.loads(stored.state)
    state.update(change)
    return replace(stored, state=json.dumps(state))


class TestRoundTrip:
    """状態を変えたあとの memento を行にして読み戻すと、同じ memento になることを保証する。"""

    @pytest.mark.parametrize("kind", sorted(_MEMENTOS))
    def test_changed_memento_survives_a_round_trip(self, kind: str) -> None:
        """状態を変えた集約の memento を行にすると、その種類の行になり、読み戻すと同じ memento になる。"""
        memento = _MEMENTOS[kind]

        stored = GAME_WORLD_CODECS.stored(memento)
        restored = GAME_WORLD_CODECS.memento(stored, type(memento))

        assert (stored.kind, restored) == (kind, memento)

    @pytest.mark.parametrize(
        "entry",
        [
            OccupantLocation(PersonBody(_ALICE), AtSpot(SpotId("beach"), OpenArea())),
            OccupantLocation(PersonBody(_ALICE), AtSpot(SpotId("beach"), SpotSectionId("boat"))),
            OccupantLocation(
                DepartedPerson(_ALICE),
                TravelPosition(
                    route_start=SpotId("beach"),
                    route_passages=(PassageId("shore"), PassageId("tunnel")),
                    passage_index=1,
                    ticks_left_on_passage=Ticks(2),
                    departed_from=SpotId("cave"),
                ),
            ),
        ],
        ids=["person_body_in_open_area", "person_body_in_section", "departed_person_travelling"],
    )
    def test_every_occupant_and_location_survives_a_round_trip(self, entry: OccupantLocation) -> None:
        """体のある人・去った人、開けた場所・区画・移動中の、どの組み合わせも読み戻すと同じになる。"""
        memento = WhereaboutsMemento(_WORLD, frozenset({entry}))

        assert _round_trip(memento) == memento

    def test_travel_keeps_the_order_of_passages(self) -> None:
        """移動中の通路の列は、道順 (shore, tunnel) のまま書いて読む。"""
        state = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["whereabouts"]).state)

        [travel] = [entry["location"] for entry in state["locations"] if "travel_position" in entry["location"]]

        assert travel["travel_position"]["route_passages"] == ["shore", "tunnel"]

    @pytest.mark.parametrize("presence", list(PassagePresence))
    def test_every_passage_presence_survives_a_round_trip(self, presence: PassagePresence) -> None:
        """隠れている・ある・取り除かれた、のどの通路のありようも、名前で書いて読み戻すと同じになる。"""
        memento = PassageStatesMemento(_WORLD, frozenset({PassageCondition(PassageId("gate"), _OPEN, presence)}))

        state = json.loads(GAME_WORLD_CODECS.stored(memento).state)

        assert (state["passages"][0]["presence"], _round_trip(memento)) == (presence.name, memento)

    @pytest.mark.parametrize(
        ("ambient_sound", "smell"),
        [(NoAmbientSound(), NoSmell()), (DescriptionText("波の音"), DescriptionText("潮のにおい"))],
        ids=["none", "described"],
    )
    def test_every_ambient_sound_and_smell_survives_a_round_trip(
        self, ambient_sound: DescriptionText | NoAmbientSound, smell: DescriptionText | NoSmell
    ) -> None:
        """場所の音とにおいは、無いときも、書いてあるときも、読み戻すと同じになる。"""
        atmosphere = SpotAtmosphere(
            lighting=Lighting.DUSKY,
            outdoor=True,
            temperature=Temperature.WARM,
            ambient_sound=ambient_sound,
            smell=smell,
        )
        memento = SpotAtmospheresMemento(_WORLD, frozenset({AtmosphereAtSpot(SpotId("beach"), atmosphere)}))

        assert _round_trip(memento) == memento

    def test_values_are_written_under_their_tags(self) -> None:
        """どちらかの型の値は印で包んで書く。区画は spot_section_id、においは description_text、棄権は abstain の印になる。"""
        whereabouts = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["whereabouts"]).state)
        atmospheres = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["spot_atmospheres"]).state)
        decision = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["group_decision"]).state)

        assert whereabouts["locations"][0] == {
            "occupant": {"person_body": {"person": "alice"}},
            "location": {"at_spot": {"spot": "beach", "section": {"spot_section_id": "boat"}}},
        }
        assert atmospheres["atmospheres"][1]["atmosphere"]["smell"] == {"description_text": "湿った土のにおい"}
        assert atmospheres["atmospheres"][0]["atmosphere"]["ambient_sound"] == {"no_ambient_sound": {}}
        assert decision["ballots"] == [
            {"voter": "alice", "choice": {"vote_for": {"person": "bob"}}},
            {"voter": "dave", "choice": {"abstain": {}}},
        ]

    @pytest.mark.parametrize(
        ("memento", "listed", "sort_key"),
        [
            (
                WhereaboutsMemento(
                    _WORLD,
                    frozenset(
                        OccupantLocation(occupant(PersonId(f"p{n}")), AtSpot(SpotId("beach"), OpenArea()))
                        for n in range(4)
                        for occupant in (PersonBody, DepartedPerson)
                    ),
                ),
                "locations",
                lambda item: [(fields["person"], tag) for tag, fields in item["occupant"].items()],
            ),
            (
                PassageStatesMemento(
                    _WORLD,
                    frozenset(
                        PassageCondition(PassageId(f"passage_{n}"), _OPEN, PassagePresence.PRESENT) for n in range(8)
                    ),
                ),
                "passages",
                lambda item: item["passage"],
            ),
            (
                SpotAtmospheresMemento(
                    _WORLD,
                    frozenset(AtmosphereAtSpot(SpotId(f"spot_{n}"), spot("beach").atmosphere) for n in range(8)),
                ),
                "atmospheres",
                lambda item: item["spot"],
            ),
            (
                GroupDecisionMemento(
                    GroupDecisionId("exile_vote"),
                    open=True,
                    voters=frozenset(PersonId(f"p{n}") for n in range(9)),
                    choices=frozenset(),
                    ballots=frozenset(Ballot(PersonId(f"p{n}"), Abstain()) for n in range(8)),
                ),
                "ballots",
                lambda item: item["voter"],
            ),
        ],
        ids=["whereabouts", "passage_states", "spot_atmospheres", "group_decision_ballots"],
    )
    def test_sets_are_written_in_key_order(self, memento: object, listed: str, sort_key: Callable[[Any], Any]) -> None:
        """8 件の集合は、集合の走査順に依らず、持ち主のキーの昇順に並べて書く。同じ memento がいつも同じ JSON の文字列になる。"""
        state = json.loads(GAME_WORLD_CODECS.stored(memento).state)

        keys = [sort_key(item) for item in state[listed]]

        assert len(keys) == 8
        assert keys == sorted(keys)

    def test_voters_and_choices_are_written_in_order(self) -> None:
        """投票する人と選べる人の集合は、8 人ずつを、名前の昇順に並べて書く。"""
        people = frozenset(PersonId(f"p{n}") for n in range(8))
        memento = GroupDecisionMemento(
            GroupDecisionId("exile_vote"), open=False, voters=people, choices=people, ballots=frozenset()
        )

        state = json.loads(GAME_WORLD_CODECS.stored(memento).state)

        expected = [f"p{n}" for n in range(8)]
        assert (state["voters"], state["choices"]) == (expected, expected)


class TestUnreadableRows:
    """知らない形の行を、読み捨てずに止めることを保証する。"""

    @pytest.mark.parametrize("kind", sorted(_MEMENTOS))
    def test_row_with_an_unknown_key_is_refused(self, kind: str) -> None:
        """知らないキーのある行は、そのキーの名前を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_MEMENTOS[kind]), {"mood": "calm"})

        with pytest.raises(StoredMementoUnreadableException, match="mood"):
            GAME_WORLD_CODECS.memento(stored, type(_MEMENTOS[kind]))

    @pytest.mark.parametrize(("kind", "path", "key"), _NESTED_OBJECTS, ids=_NESTED_IDS)
    def test_nested_object_with_an_unknown_key_is_refused(
        self, kind: str, path: tuple[str | int, ...], key: str
    ) -> None:
        """入れ子のオブジェクト (占有者・居場所・移動中の位置・通路の状態・場所の様子・票) に知らないキーがあると、そのキーの名前を添えて止まる。"""
        stored = _with_nested(
            GAME_WORLD_CODECS.stored(_MEMENTOS[kind]), path, lambda target: target.update(mood="calm")
        )

        with pytest.raises(StoredMementoUnreadableException, match="mood"):
            GAME_WORLD_CODECS.memento(stored, type(_MEMENTOS[kind]))

    @pytest.mark.parametrize(("kind", "path", "key"), _NESTED_OBJECTS, ids=_NESTED_IDS)
    def test_nested_object_missing_a_key_is_refused(self, kind: str, path: tuple[str | int, ...], key: str) -> None:
        """入れ子のオブジェクトからキーが 1 つ欠けていると、欠けたキーの名前を添えて止まる。"""
        stored = _with_nested(GAME_WORLD_CODECS.stored(_MEMENTOS[kind]), path, lambda target: target.pop(key))

        with pytest.raises(StoredMementoUnreadableException, match=key):
            GAME_WORLD_CODECS.memento(stored, type(_MEMENTOS[kind]))

    def test_ballot_listed_twice_is_refused(self) -> None:
        """同じ票を 2 回並べた行は、重なりを数えて止まる。"""
        stored = GAME_WORLD_CODECS.stored(_MEMENTOS["group_decision"])
        ballots = json.loads(stored.state)["ballots"]
        stored = _with_state(stored, {"ballots": [ballots[0], ballots[0]]})

        with pytest.raises(StoredMementoUnreadableException, match="more than once"):
            GAME_WORLD_CODECS.memento(stored, GroupDecisionMemento)

    def test_unknown_location_is_refused(self) -> None:
        """知らない印の居場所は、その印を添えて止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_MEMENTOS["whereabouts"]),
            {"locations": [{"occupant": {"person_body": {"person": "alice"}}, "location": {"in_the_sky": {}}}]},
        )

        with pytest.raises(StoredMementoUnreadableException, match="in_the_sky"):
            GAME_WORLD_CODECS.memento(stored, WhereaboutsMemento)

    def test_unknown_passage_presence_is_refused(self) -> None:
        """PassagePresence のメンバーの名前でないありようは、その値を添えて止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_MEMENTOS["passage_states"]),
            {"passages": [{"passage": "gate", "state": "open", "presence": "collapsed"}]},
        )

        with pytest.raises(StoredMementoUnreadableException, match="collapsed"):
            GAME_WORLD_CODECS.memento(stored, PassageStatesMemento)

    def test_occupant_at_two_locations_is_refused(self) -> None:
        """同じ人が 2 つの居場所にいる行は、memento の決まりで止まる。"""
        at_beach = {
            "occupant": {"person_body": {"person": "alice"}},
            "location": {"at_spot": {"spot": "beach", "section": {"open_area": {}}}},
        }
        at_cave = {
            "occupant": {"person_body": {"person": "alice"}},
            "location": {"at_spot": {"spot": "cave", "section": {"open_area": {}}}},
        }
        stored = _with_state(GAME_WORLD_CODECS.stored(_MEMENTOS["whereabouts"]), {"locations": [at_beach, at_cave]})

        with pytest.raises(StoredMementoUnreadableException, match="two locations"):
            GAME_WORLD_CODECS.memento(stored, WhereaboutsMemento)
