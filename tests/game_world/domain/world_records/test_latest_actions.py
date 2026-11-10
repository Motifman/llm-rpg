from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.common_rule_refusal import TooTired
from ai_rpg_world.game_world.domain.action.interaction_attempts import ObjectInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.subject import Anyone
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_records import (
    ActionAttemptFailedEvent,
    ActionLastDoneAt,
    LatestActions,
    LatestActionsMemento,
    NeverDone,
    PersonActedEvent,
)
from tests.game_world.domain.whereabouts._builders import thing
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import InteractionForTests

_WORLD = WorldId("mine")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_PULL_LEVER = InteractionId("pull_lever")
_ALICE_SEARCHES = ActionAttemptForTests(actor_id=_ALICE, action_kind=ActionKind.SEARCH)
_BOB_SEARCHES = ActionAttemptForTests(actor_id=_BOB, action_kind=ActionKind.SEARCH)
_ALICE_PULLS_LEVER = ObjectInteractionAttempt(
    _ALICE, thing("lever", "lift_landing"), InteractionForTests(_PULL_LEVER), {}, Openly()
)
from tests.game_world.support.memento_for_tests import rebuilt_from_memento


class TestLatestActionsNote:
    """LatestActions.note が、行った人ごとと誰でもの両方で、行為の鍵ごとに最後に行った tick を記録することを保証する。"""

    def test_nothing_has_been_done_at_first(self) -> None:
        """作った直後は自分の世界の ID を持ち、誰の、誰でもの、どの行為の last_done_at も NeverDone。"""
        latest = LatestActions(_WORLD)

        assert latest.world_id == _WORLD
        assert latest.last_done_at(_ALICE, ActionKind.SEARCH) == NeverDone()
        assert latest.last_done_at(Anyone(), _PULL_LEVER) == NeverDone()

    def test_note_records_the_tick_for_the_actor_and_for_anyone(self) -> None:
        """alice が tick 4 に探したら、alice の SEARCH も誰でもの SEARCH も tick 4、bob の SEARCH は NeverDone。"""
        latest = LatestActions(_WORLD)

        latest.note(_ALICE_SEARCHES, WorldTick(4))

        assert latest.last_done_at(_ALICE, ActionKind.SEARCH) == WorldTick(4)
        assert latest.last_done_at(Anyone(), ActionKind.SEARCH) == WorldTick(4)
        assert latest.last_done_at(_BOB, ActionKind.SEARCH) == NeverDone()

    def test_anyone_answers_the_latest_among_everyone(self) -> None:
        """alice が tick 4、bob が tick 6 に探したら、誰でもの SEARCH は tick 6、alice の SEARCH は tick 4 のまま。"""
        latest = LatestActions(_WORLD)

        latest.note(_ALICE_SEARCHES, WorldTick(4))
        latest.note(_BOB_SEARCHES, WorldTick(6))

        assert latest.last_done_at(Anyone(), ActionKind.SEARCH) == WorldTick(6)
        assert latest.last_done_at(_ALICE, ActionKind.SEARCH) == WorldTick(4)

    def test_interaction_is_recorded_by_its_kind_and_its_interaction(self) -> None:
        """alice が tick 3 にレバーを引いたら、INTERACT_WITH_OBJECT でも pull_lever でも tick 3 を答える。"""
        latest = LatestActions(_WORLD)

        latest.note(_ALICE_PULLS_LEVER, WorldTick(3))

        assert latest.last_done_at(_ALICE, ActionKind.INTERACT_WITH_OBJECT) == WorldTick(3)
        assert latest.last_done_at(Anyone(), _PULL_LEVER) == WorldTick(3)
        assert latest.last_done_at(_ALICE, ActionKind.SEARCH) == NeverDone()

    def test_note_records_person_acted_event(self) -> None:
        """note は、世界・行った行為・tick を持つ PersonActedEvent をためる。"""
        latest = LatestActions(_WORLD)

        latest.note(_ALICE_SEARCHES, WorldTick(4))

        [event] = latest.get_events()
        assert isinstance(event, PersonActedEvent)
        assert (event.world_id, event.attempt, event.at) == (_WORLD, _ALICE_SEARCHES, WorldTick(4))


class TestLatestActionsFailedAttempt:
    """LatestActions.note_failed_attempt が、断られた試みをイベントにするだけで、最後に行った行為を変えないことを保証する。"""

    def test_failed_attempt_is_not_done(self) -> None:
        """alice の探す試みが tick 5 に断られても、alice の SEARCH の last_done_at は NeverDone のまま。"""
        latest = LatestActions(_WORLD)

        latest.note_failed_attempt(_refusal_of(_ALICE_SEARCHES), WorldTick(5))

        assert latest.last_done_at(_ALICE, ActionKind.SEARCH) == NeverDone()

    def test_failed_attempt_records_event_with_refusal(self) -> None:
        """note_failed_attempt は、世界・断った理由 (ActionRefusal)・tick を持つ ActionAttemptFailedEvent をためる。"""
        latest = LatestActions(_WORLD)
        refusal = _refusal_of(_ALICE_SEARCHES)

        latest.note_failed_attempt(refusal, WorldTick(5))

        [event] = latest.get_events()
        assert isinstance(event, ActionAttemptFailedEvent)
        assert (event.world_id, event.refusal, event.at) == (_WORLD, refusal, WorldTick(5))


def _refusal_of(attempt: ActionAttemptForTests) -> ActionRefusal:
    return ActionRefusal(
        attempt=attempt,
        reason=TooTired(),
        text=TextWithUnassignedPeople("{actor}は疲れて動けない").about({"actor": _ALICE}),
    )


class TestNeverDone:
    """NeverDone が、まだ行っていない行為の起点として、渡した基準の時刻を答えることを保証する。"""

    def test_later_of_answers_the_baseline(self) -> None:
        """NeverDone の later_of は、渡した tick 7 をそのまま返す。"""
        assert NeverDone().later_of(WorldTick(7)) == WorldTick(7)


class TestLatestActionsMemento:
    """LatestActions を memento から作り直すと、人ごとと誰でもの最後に行った tick が元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_latest_actions_answer_the_same_ticks(self) -> None:
        """alice が tick 4 に探し tick 5 にレバーを引き、bob が tick 6 に探したあと作り直すと、どの last_done_at も元と同じ。"""
        latest = LatestActions(_WORLD)
        latest.note(_ALICE_SEARCHES, WorldTick(4))
        latest.note(_ALICE_PULLS_LEVER, WorldTick(5))
        latest.note(_BOB_SEARCHES, WorldTick(6))

        rebuilt = rebuilt_from_memento(latest)

        assert rebuilt.memento() == latest.memento()
        assert rebuilt.last_done_at(_ALICE, ActionKind.SEARCH) == WorldTick(4)
        assert rebuilt.last_done_at(_ALICE, _PULL_LEVER) == WorldTick(5)
        assert rebuilt.last_done_at(Anyone(), ActionKind.SEARCH) == WorldTick(6)
        assert rebuilt.last_done_at(_BOB, _PULL_LEVER) == NeverDone()
        assert rebuilt.world_id == _WORLD

    def test_memento_does_not_depend_on_the_order_of_noting(self) -> None:
        """tick 4 に alice と bob が探したとき、alice から記録しても bob から記録しても、memento は等しい。"""
        alice_first = LatestActions(_WORLD)
        alice_first.note(_ALICE_SEARCHES, WorldTick(4))
        alice_first.note(_BOB_SEARCHES, WorldTick(4))
        bob_first = LatestActions(_WORLD)
        bob_first.note(_BOB_SEARCHES, WorldTick(4))
        bob_first.note(_ALICE_SEARCHES, WorldTick(4))

        assert alice_first.memento() == bob_first.memento()

    def test_rebuilding_records_no_event(self) -> None:
        """行為を記録したあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        latest = LatestActions(_WORLD)
        latest.note(_ALICE_SEARCHES, WorldTick(4))

        assert rebuilt_from_memento(latest).get_events() == []


class TestLatestActionsMementoRefusesRepeatedKey:
    """LatestActionsMemento が、同じ人の同じ行為に 2 つの tick を持つ memento を作ることを断ることを保証する。"""

    def test_same_actor_and_action_at_two_ticks_is_refused(self) -> None:
        """alice の SEARCH が tick 4 と tick 6 の 2 つある memento を作ると、RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            LatestActionsMemento(
                world_id=_WORLD,
                last_done=frozenset(
                    {
                        ActionLastDoneAt(_ALICE, ActionKind.SEARCH, WorldTick(4)),
                        ActionLastDoneAt(_ALICE, ActionKind.SEARCH, WorldTick(6)),
                    }
                ),
            )
