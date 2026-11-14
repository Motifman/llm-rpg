"""世界の進行と記録の集約 (Weather・WorldEnding・WorldStage・LatestActions・MissedNotices・ScenarioProgress) の memento が JSON を行き来し、知らない形の行を止めることを保証する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from ai_rpg_world.game_world.domain.action.interaction_attempts import ObjectInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.subject import Anyone
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.time_and_weather import WeatherState, WeatherType
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.people.person_ref import NoVisibleName, PersonRef, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    InteractionId,
    PersonId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_progress import (
    Weather,
    WeatherMemento,
    WorldEnding,
    WorldStage,
)
from ai_rpg_world.game_world.domain.world_records import (
    ActionLastDoneAt,
    HappeningLastFiredAt,
    LatestActions,
    LatestActionsMemento,
    MissedNotices,
    MissedNoticesMemento,
    ReactionLastTruth,
    ScenarioProgress,
    ScenarioProgressMemento,
)
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS, StoredMemento
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    StoredMementoUnreadableException,
)
from tests.game_world.domain.whereabouts._builders import thing
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import InteractionForTests
from tests.game_world.support.world_design_for_tests import world_stage

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_PULL_LEVER = InteractionId("pull_lever")
_SEEN_ALICE = PersonRef(PersonHandle(1), DescriptionText("赤い外套の人"), DisplayName("アリス"))
_SEEN_STRANGER = PersonRef(PersonHandle(2), DescriptionText("背の高い人"), NoVisibleName())


def _weather() -> WeatherMemento:
    weather = Weather.from_memento(WeatherMemento(_WORLD, WeatherState(WeatherType.CLEAR)))
    weather.change(WeatherState(WeatherType.STORM))
    return weather.memento()


def _ending() -> object:
    ending = WorldEnding.start(_WORLD)
    ending.end(WorldTick(30))
    return ending.memento()


def _stage() -> object:
    stage = WorldStage.from_initial_stage(_WORLD, world_stage("dawn"), WorldTick(0))
    stage.enter(world_stage("night"), WorldTick(12))
    return stage.memento()


def _latest_actions() -> LatestActionsMemento:
    latest = LatestActions.start(_WORLD)
    latest.note(ActionAttemptForTests(actor_id=_ALICE, action_kind=ActionKind.SEARCH), WorldTick(4))
    latest.note(
        ObjectInteractionAttempt(_BOB, thing("lever", "landing"), InteractionForTests(_PULL_LEVER), {}, Openly()),
        WorldTick(6),
    )
    return latest.memento()


def _notice(template: str, people: dict[str, PersonRef | Unidentified], at: int) -> MissedNotice:
    return MissedNotice(TextWithAssignedPeople(template=template, people=people), WorldTick(at))


def _missed_notices() -> MissedNoticesMemento:
    notices = MissedNotices.start(_ALICE)
    notices.keep(
        _notice(
            "{target}の荷を{actor}が{witness}の前で取った。",
            {"target": _SEEN_ALICE, "actor": _SEEN_STRANGER, "witness": Unidentified()},
            9,
        )
    )
    notices.keep(_notice("扉が軋んだ。", {}, 3))
    return notices.memento()


def _happening(name: str) -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId(name),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        effect=NoEffect(),
        once=False,
        notice=NoNotice(),
    )


def _reaction(name: str) -> ReactionDeclaration:
    return ReactionDeclaration(
        reaction_id=ReactionId(name),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        when_becomes_true=NoEffect(),
        when_becomes_false=NoEffect(),
    )


def _scenario_progress() -> ScenarioProgressMemento:
    progress = ScenarioProgress.start(_WORLD)
    progress.note_happening_fired(_happening("tide_turns"), WorldTick(5))
    progress.note_happening_fired(_happening("ship_arrives"), WorldTick(8))
    progress.note_reaction_truth(_reaction("door_closed"), True)
    progress.note_reaction_truth(_reaction("lamp_lit"), False)
    return progress.memento()


_MEMENTOS = {
    "weather": _weather(),
    "world_ending": _ending(),
    "world_stage": _stage(),
    "latest_actions": _latest_actions(),
    "missed_notices": _missed_notices(),
    "scenario_progress": _scenario_progress(),
}


def _round_trip(memento: object) -> object:
    return GAME_WORLD_CODECS.memento(GAME_WORLD_CODECS.stored(memento), type(memento))


def _with_state(stored: StoredMemento, change: dict[str, object]) -> StoredMemento:
    state = json.loads(stored.state)
    state.update(change)
    return replace(stored, state=json.dumps(state))


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
    ("weather", ("current",), "type"),
    ("latest_actions", ("last_done", 0), "action"),
    ("missed_notices", ("notices", 0), "text"),
    ("missed_notices", ("notices", 0, "text"), "people"),
    ("missed_notices", ("notices", 0, "text", "people", "target", "person_ref"), "visible_name"),
    ("scenario_progress", ("last_fired", 0), "at"),
    ("scenario_progress", ("reaction_truths", 0), "truth"),
]
_NESTED_IDS = [f"{kind}:{key}" for kind, _, key in _NESTED_OBJECTS]


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
        "done",
        [
            ActionLastDoneAt(_ALICE, ActionKind.SEARCH, WorldTick(4)),
            ActionLastDoneAt(Anyone(), ActionKind.SEARCH, WorldTick(4)),
            ActionLastDoneAt(_BOB, _PULL_LEVER, WorldTick(6)),
            ActionLastDoneAt(Anyone(), _PULL_LEVER, WorldTick(6)),
        ],
        ids=["person_did_action_kind", "anyone_did_action_kind", "person_did_interaction", "anyone_did_interaction"],
    )
    def test_every_doer_and_action_survives_a_round_trip(self, done: ActionLastDoneAt) -> None:
        """行った人 (ある人・誰でも) と行為 (行為の種類・やりとり) の、どの組み合わせも読み戻すと同じになる。"""
        memento = LatestActionsMemento(_WORLD, frozenset({done}))

        assert _round_trip(memento) == memento

    def test_values_are_written_under_their_tags(self) -> None:
        """どちらかの型の値は印で包んで書く。誰でもは anyone、やりとりは interaction_id、名の見えない人は no_visible_name の印になる。"""
        latest = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["latest_actions"]).state)
        notices = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["missed_notices"]).state)

        assert {"who": {"anyone": {}}, "action": {"interaction_id": "pull_lever"}, "at": 6} in latest["last_done"]
        assert notices["notices"][0]["text"]["people"] == {
            "actor": {"person_ref": {"handle": 2, "appearance": "背の高い人", "visible_name": {"no_visible_name": {}}}},
            "target": {
                "person_ref": {"handle": 1, "appearance": "赤い外套の人", "visible_name": {"display_name": "アリス"}}
            },
            "witness": {"unidentified": {}},
        }

    def test_missed_notices_keep_their_order(self) -> None:
        """取り逃した知らせの列は、知らせを受けた順 (tick 9 のあとに tick 3) のまま書いて読む。"""
        restored = _round_trip(_MEMENTOS["missed_notices"])

        assert [notice.happened_at for notice in restored.notices] == [WorldTick(9), WorldTick(3)]  # type: ignore[attr-defined]

    def test_people_in_a_notice_are_written_in_placeholder_order(self) -> None:
        """文の印と人の対応は、memento に入れた順 (target, actor, witness) に依らず、印の名前の昇順で行の文字列に書く。"""
        state = GAME_WORLD_CODECS.stored(_MEMENTOS["missed_notices"]).state

        positions = [state.index(f'"{placeholder}": {{') for placeholder in ("actor", "target", "witness")]

        assert positions == sorted(positions)

    @pytest.mark.parametrize(
        ("memento", "listed", "sort_key"),
        [
            (
                LatestActionsMemento(
                    _WORLD,
                    frozenset(
                        ActionLastDoneAt(who, action, WorldTick(1))
                        for who in (PersonId("p0"), PersonId("p1"), PersonId("p2"), Anyone())
                        for action in (ActionKind.SEARCH, _PULL_LEVER)
                    ),
                ),
                "last_done",
                lambda item: json.dumps([item["who"], item["action"]], sort_keys=True),
            ),
            (
                ScenarioProgressMemento(
                    _WORLD,
                    last_fired=frozenset(
                        HappeningLastFiredAt(HappeningId(f"happening_{n}"), WorldTick(n)) for n in range(8)
                    ),
                    reaction_truths=frozenset(),
                ),
                "last_fired",
                lambda item: item["happening"],
            ),
            (
                ScenarioProgressMemento(
                    _WORLD,
                    last_fired=frozenset(),
                    reaction_truths=frozenset(
                        ReactionLastTruth(ReactionId(f"reaction_{n}"), n % 2 == 0) for n in range(8)
                    ),
                ),
                "reaction_truths",
                lambda item: item["reaction"],
            ),
        ],
        ids=["latest_actions", "scenario_progress_last_fired", "scenario_progress_reaction_truths"],
    )
    def test_sets_are_written_in_key_order(self, memento: object, listed: str, sort_key: Callable[[Any], Any]) -> None:
        """8 件の集合は、集合の走査順に依らず、持ち主のキーの昇順に並べて書く。同じ memento がいつも同じ JSON の文字列になる。"""
        state = json.loads(GAME_WORLD_CODECS.stored(memento).state)

        keys = [sort_key(item) for item in state[listed]]

        assert len(keys) == 8
        assert keys == sorted(keys)


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
        """入れ子のオブジェクト (天気・行為の記録・知らせ・文・見えた人・出来事・反応) に知らないキーがあると、そのキーの名前を添えて止まる。"""
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

    @pytest.mark.parametrize(
        ("kind", "listed", "repeated", "reason"),
        [
            (
                "latest_actions",
                "last_done",
                [
                    {"who": {"person_id": "alice"}, "action": {"action_kind": "SEARCH"}, "at": 4},
                    {"who": {"person_id": "alice"}, "action": {"action_kind": "SEARCH"}, "at": 7},
                ],
                "two ticks",
            ),
            (
                "scenario_progress",
                "last_fired",
                [{"happening": "tide_turns", "at": 5}, {"happening": "tide_turns", "at": 9}],
                "two ticks",
            ),
            (
                "scenario_progress",
                "reaction_truths",
                [{"reaction": "lamp_lit", "truth": True}, {"reaction": "lamp_lit", "truth": False}],
                "two truths",
            ),
        ],
        ids=["latest_actions", "scenario_progress_last_fired", "scenario_progress_reaction_truths"],
    )
    def test_same_key_with_two_values_is_refused(
        self, kind: str, listed: str, repeated: list[object], reason: str
    ) -> None:
        """同じキー (人と行為、出来事、反応) に違う値を持つ項目を 2 件書いた行は、後の値で上書きせずに memento の決まりで止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_MEMENTOS[kind]), {listed: repeated})

        with pytest.raises(StoredMementoUnreadableException, match=reason):
            GAME_WORLD_CODECS.memento(stored, type(_MEMENTOS[kind]))

    def test_unknown_weather_type_is_refused(self) -> None:
        """WeatherType のメンバーの名前でない天気は、その値を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_MEMENTOS["weather"]), {"current": {"type": "HAIL"}})

        with pytest.raises(StoredMementoUnreadableException, match="HAIL"):
            GAME_WORLD_CODECS.memento(stored, WeatherMemento)

    def test_placeholder_written_twice_is_refused(self) -> None:
        """文の同じ印を 2 回書いた行は、後の値で上書きせずに止まる。"""
        stored = GAME_WORLD_CODECS.stored(_MEMENTOS["missed_notices"])
        written = stored.state.replace(
            '"witness": {"unidentified": {}}', '"witness": {"unidentified": {}}, "witness": {"unidentified": {}}'
        )

        with pytest.raises(StoredMementoUnreadableException, match="more than once"):
            GAME_WORLD_CODECS.memento(replace(stored, state=written), MissedNoticesMemento)

    def test_people_not_matching_the_placeholders_are_refused(self) -> None:
        """文の印と人の対応が合わない行は、ドメインが断った理由で止まる。"""
        stored = _with_nested(
            GAME_WORLD_CODECS.stored(_MEMENTOS["missed_notices"]),
            ("notices", 0, "text", "people"),
            lambda people: people.pop("witness"),
        )

        with pytest.raises(StoredMementoUnreadableException, match="differ"):
            GAME_WORLD_CODECS.memento(stored, MissedNoticesMemento)
