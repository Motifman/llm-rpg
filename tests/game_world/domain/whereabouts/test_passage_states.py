from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.spot_declaration_exception import UndeclaredPassageStateException
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    PassageAlreadyRemovedException,
    UnknownPassageException,
)
from ai_rpg_world.game_world.domain.value_object import PassageId, PassageStateName
from ai_rpg_world.game_world.domain.whereabouts import (
    PassageCondition,
    PassageInState,
    PassagePresence,
    PassageRemovedEvent,
    PassageRevealedEvent,
    PassageStateChangedEvent,
    PassageStates,
    PassageStatesMemento,
)
from tests.game_world.domain.whereabouts._builders import CLOSED, OPEN, WORLD, door, path, spot
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import compose_world, nouns

CELLAR_DOOR = door("cellar_door", "hall", "cellar")
STREET = path("street", "plaza", "hall")
SECRET = path("secret_tunnel", "cellar", "well", hidden_until_revealed=True)
SLIDE = path("slide", "hall", "beach", two_way=False)


def _states() -> PassageStates:
    return PassageStates(WORLD, (CELLAR_DOOR, STREET, SECRET, SLIDE))


_DESIGN = compose_world(
    nouns(
        spots=tuple(spot(name) for name in ("hall", "cellar", "plaza", "well", "beach")),
        passages=(CELLAR_DOOR, STREET, SECRET, SLIDE),
    )
)


def _conditions_of(states: PassageStates) -> set[PassageCondition]:
    return set(states.memento().passages)


class TestPassageStatesInitially:
    """PassageStates が、宣言の初めの状態と、初めは無い道から始まることを保証する。"""

    def test_world_id_is_the_given_world(self) -> None:
        """作るときに渡した WorldId を自分の ID として持つ。"""
        assert _states().world_id == WORLD

    def test_passage_starts_in_its_declared_initial_state(self) -> None:
        """初めの状態が閉じている扉は通れず、closed_passages に入る。開いている道は通れる。"""
        states = _states()

        assert states.is_traversable(CELLAR_DOOR) is False
        assert states.is_traversable(STREET) is True
        assert PassageId("cellar_door") in states.closed_passages()

    def test_passage_hidden_until_revealed_is_closed_until_it_is_revealed(self) -> None:
        """hidden_until_revealed の道は、状態が通れるものでも、現れるまでは通れず closed_passages に入る。"""
        states = _states()

        assert states.is_traversable(SECRET) is False
        assert PassageId("secret_tunnel") in states.closed_passages()

    def test_query_about_a_passage_not_given_at_creation_is_rejected(self) -> None:
        """作るときに渡していない通路について聞くと UnknownPassageException を投げる。"""
        with pytest.raises(UnknownPassageException):
            _states().is_traversable(path("elsewhere", "a", "b"))


class TestPassageStatesChangeState:
    """change_state が通路の状態を書き換え、変わる前と後の状態名をイベントに残すことを保証する。"""

    def test_change_state_opens_the_door_and_records_before_and_after(self) -> None:
        """閉じた扉を open にすると通れるようになり、before=closed・after=open の PassageStateChangedEvent を 1 件ためる。"""
        states = _states()

        states.change_state(CELLAR_DOOR, OPEN)

        assert states.is_traversable(CELLAR_DOOR) is True
        assert PassageId("cellar_door") not in states.closed_passages()
        [event] = states.get_events()
        assert isinstance(event, PassageStateChangedEvent)
        assert (event.world_id, event.passage, event.before, event.after) == (
            WORLD,
            PassageId("cellar_door"),
            CLOSED,
            OPEN,
        )

    def test_change_state_to_the_current_state_does_nothing(self) -> None:
        """今と同じ状態名を渡すと、例外もイベントも出さない。"""
        states = _states()

        states.change_state(CELLAR_DOOR, CLOSED)

        assert states.get_events() == []

    def test_change_state_to_an_undeclared_state_is_rejected_without_events(self) -> None:
        """宣言に無い状態名を渡すと UndeclaredPassageStateException を投げ、状態は変わらずイベントも出さない。"""
        states = _states()

        with pytest.raises(UndeclaredPassageStateException):
            states.change_state(CELLAR_DOOR, PassageStateName("ajar"))

        assert states.is_traversable(CELLAR_DOOR) is False
        assert states.get_events() == []


class TestPassageStatesRevealAndRemove:
    """reveal で道が現れ、remove で道が無くなることを保証する。"""

    def test_reveal_makes_a_hidden_passage_traversable(self) -> None:
        """隠れた道を reveal すると通れるようになり、PassageRevealedEvent を 1 件ためる。"""
        states = _states()

        states.reveal(SECRET)

        assert states.is_traversable(SECRET) is True
        [event] = states.get_events()
        assert isinstance(event, PassageRevealedEvent)
        assert (event.world_id, event.passage) == (WORLD, PassageId("secret_tunnel"))

    def test_reveal_of_a_passage_already_present_does_nothing(self) -> None:
        """初めからある道を reveal しても、例外もイベントも出さない。"""
        states = _states()

        states.reveal(STREET)

        assert states.get_events() == []

    def test_remove_closes_the_passage_for_good(self) -> None:
        """道を remove すると通れなくなり closed_passages に入り、PassageRemovedEvent を 1 件ためる。"""
        states = _states()

        states.remove(STREET)

        assert states.is_traversable(STREET) is False
        assert PassageId("street") in states.closed_passages()
        [event] = states.get_events()
        assert isinstance(event, PassageRemovedEvent)
        assert event.passage == PassageId("street")

    def test_remove_of_a_removed_passage_does_nothing(self) -> None:
        """無くなった道をもう一度 remove しても、例外も 2 件目のイベントも出さない。"""
        states = _states()
        states.remove(STREET)
        states.clear_events()

        states.remove(STREET)

        assert states.get_events() == []

    @pytest.mark.parametrize("act", ["reveal", "change_state"])
    def test_removed_passage_cannot_be_revealed_or_changed(self, act: str) -> None:
        """無くなった道を reveal・change_state すると PassageAlreadyRemovedException を投げ、イベントを出さない。"""
        states = _states()
        states.remove(CELLAR_DOOR)
        states.clear_events()

        with pytest.raises(PassageAlreadyRemovedException):
            if act == "reveal":
                states.reveal(CELLAR_DOOR)
            else:
                states.change_state(CELLAR_DOOR, OPEN)

        assert states.get_events() == []


class TestPassageStatesPassagesFrom:
    """passages_from が、その場所から出られる今ある道を、宣言の順に返すことを保証する。"""

    def test_passages_from_lists_present_passages_leaving_the_spot_including_closed_doors(self) -> None:
        """hall からは、閉じた扉・両方向の道・hall から出る片道を宣言の順に返す。"""
        states = _states()

        found = states.passages_from(spot("hall"), (CELLAR_DOOR, STREET, SECRET, SLIDE))

        assert found == (PassageId("cellar_door"), PassageId("street"), PassageId("slide"))

    def test_passages_from_skips_the_arriving_end_of_a_one_way_passage(self) -> None:
        """片道の着く側の場所 (beach) からは、その片道を返さない。"""
        assert _states().passages_from(spot("beach"), (CELLAR_DOOR, STREET, SECRET, SLIDE)) == ()

    def test_passages_from_skips_hidden_and_removed_passages(self) -> None:
        """現れる前の道と無くなった道は返さない。"""
        states = _states()
        states.remove(CELLAR_DOOR)

        assert states.passages_from(spot("cellar"), (CELLAR_DOOR, STREET, SECRET, SLIDE)) == ()


class TestPassageInState:
    """in_state が今の状態名を添えた PassageInState を返し、PassageInState が宣言に無い状態名を断ることを保証する。"""

    def test_in_state_pairs_the_passage_with_its_current_state(self) -> None:
        """扉を開けたあとの in_state は、扉の宣言と open を持つ PassageInState を返す。"""
        states = _states()
        states.change_state(CELLAR_DOOR, OPEN)

        assert states.in_state(CELLAR_DOOR) == PassageInState(passage=CELLAR_DOOR, state=OPEN)

    def test_passage_in_state_with_an_undeclared_state_is_rejected(self) -> None:
        """通路の宣言に無い状態名で PassageInState を作ると UndeclaredPassageStateException を投げる。"""
        with pytest.raises(UndeclaredPassageStateException):
            PassageInState(passage=CELLAR_DOOR, state=PassageStateName("ajar"))


class TestPassageStatesMemento:
    """PassageStates を memento から作り直すと、通路ごとの状態と、現れたか消えたかが元と同じになることを保証する。"""

    def test_rebuilt_states_answer_the_same(self) -> None:
        """扉を開け、隠し通路を現し、滑り台を消した状態を作り直すと、memento も通れるかの答えも元と同じになる。"""
        states = _states()
        states.change_state(CELLAR_DOOR, OPEN)
        states.reveal(SECRET)
        states.remove(SLIDE)

        rebuilt = rebuilt_from_memento(states, _DESIGN)

        assert rebuilt.memento() == states.memento()
        assert (rebuilt.is_traversable(CELLAR_DOOR), rebuilt.is_traversable(SECRET)) == (True, True)
        assert rebuilt.closed_passages() == frozenset({PassageId("slide")})
        with pytest.raises(PassageAlreadyRemovedException):
            rebuilt.reveal(SLIDE)

    def test_rebuilding_records_no_event(self) -> None:
        """状態を変えたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        states = _states()
        states.change_state(CELLAR_DOOR, OPEN)

        assert rebuilt_from_memento(states, _DESIGN).get_events() == []

    def test_memento_with_an_undeclared_passage_is_rejected(self) -> None:
        """宣言に無い通路 well_tunnel を持つ memento から作り直すと UndeclaredNounException を投げる。"""
        memento = PassageStatesMemento(
            world_id=WORLD,
            passages=frozenset(
                {*_conditions_of(_states()), PassageCondition(PassageId("well_tunnel"), OPEN, PassagePresence.PRESENT)}
            ),
        )

        with pytest.raises(UndeclaredNounException):
            PassageStates.from_memento(memento, _DESIGN)

    def test_memento_missing_a_declared_passage_is_rejected(self) -> None:
        """宣言にある滑り台が memento に無いと、初めの状態で埋めずに MementoDoesNotMatchDesignException を投げる。"""
        memento = PassageStatesMemento(
            world_id=WORLD,
            passages=frozenset(c for c in _conditions_of(_states()) if c.passage != PassageId("slide")),
        )

        with pytest.raises(MementoDoesNotMatchDesignException):
            PassageStates.from_memento(memento, _DESIGN)

    def test_memento_with_an_undeclared_state_is_rejected(self) -> None:
        """扉の宣言に無い状態 ajar を持つ memento から作り直すと UndeclaredPassageStateException を投げる。"""
        others = {c for c in _conditions_of(_states()) if c.passage != PassageId("cellar_door")}
        memento = PassageStatesMemento(
            world_id=WORLD,
            passages=frozenset(
                {*others, PassageCondition(PassageId("cellar_door"), PassageStateName("ajar"), PassagePresence.PRESENT)}
            ),
        )

        with pytest.raises(UndeclaredPassageStateException):
            PassageStates.from_memento(memento, _DESIGN)

    def test_memento_with_one_passage_twice_is_rejected(self) -> None:
        """扉が開いていると閉じているの 2 つで書かれた memento は、作るときに RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            PassageStatesMemento(
                world_id=WORLD,
                passages=frozenset(
                    {
                        PassageCondition(PassageId("cellar_door"), OPEN, PassagePresence.PRESENT),
                        PassageCondition(PassageId("cellar_door"), CLOSED, PassagePresence.PRESENT),
                    }
                ),
            )
