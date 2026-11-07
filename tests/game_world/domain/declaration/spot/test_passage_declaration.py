from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, PassageStateDeclaration
from ai_rpg_world.game_world.domain.exception.spot_declaration_exception import (
    DuplicatePassageStateNameException,
    InitialPassageStateNotDeclaredException,
    PassageEndsAtSameSpotException,
    UndeclaredPassageStateException,
)
from ai_rpg_world.game_world.domain.sound import SoundLoss
from ai_rpg_world.game_world.domain.value_object import DisplayName, PassageId, PassageStateName, SpotId, Ticks

OPEN = PassageStateName("open")
CLOSED = PassageStateName("closed")
LOCKED = PassageStateName("locked")


def _door_states() -> tuple[PassageStateDeclaration, ...]:
    return (
        PassageStateDeclaration(
            name=OPEN, display_name=DisplayName("開いている"), traversable=True, sound_loss=SoundLoss(0)
        ),
        PassageStateDeclaration(
            name=CLOSED, display_name=DisplayName("閉じている"), traversable=False, sound_loss=SoundLoss(20)
        ),
    )


def _door(initial_state: PassageStateName = CLOSED) -> PassageDeclaration:
    return PassageDeclaration(
        passage_id=PassageId("cellar_door"),
        ends=(SpotId("hall"), SpotId("cellar")),
        two_way=True,
        travel_ticks=Ticks(1),
        states=_door_states(),
        initial_state=initial_state,
    )


class TestPassageDeclarationWithoutStates:
    """states を書かない PassageDeclaration が、通れる・減衰 0 の状態を 1 つだけ持つことを保証する。"""

    def test_omitted_states_become_a_single_open_traversable_state_without_sound_loss(self) -> None:
        """states と initial_state を書かないと、名前 open・呼び名「開いている」・通れる・減衰 0 の状態 1 つを持ち、それが初めの状態になる。"""
        passage = PassageDeclaration(
            passage_id=PassageId("path"),
            ends=(SpotId("field"), SpotId("forest")),
            two_way=True,
            travel_ticks=Ticks(2),
        )

        assert passage.states == (
            PassageStateDeclaration(
                name=OPEN, display_name=DisplayName("開いている"), traversable=True, sound_loss=SoundLoss(0)
            ),
        )
        assert passage.initial_state == OPEN

    def test_empty_states_tuple_is_treated_the_same_as_omitted_states(self) -> None:
        """states に空の tuple を渡しても、書かなかったときと同じ 1 つの状態を持つ。"""
        passage = PassageDeclaration(
            passage_id=PassageId("path"),
            ends=(SpotId("field"), SpotId("forest")),
            two_way=True,
            travel_ticks=Ticks(2),
            states=(),
        )

        assert passage.states == (
            PassageStateDeclaration(
                name=OPEN, display_name=DisplayName("開いている"), traversable=True, sound_loss=SoundLoss(0)
            ),
        )


class TestPassageDeclarationInitialState:
    """PassageDeclaration の初めの状態が、宣言した状態のどれかでなければならないことを保証する。"""

    def test_initial_state_not_in_states_raises(self) -> None:
        """initial_state に states に無い名前を渡すと InitialPassageStateNotDeclaredException を投げる。"""
        with pytest.raises(InitialPassageStateNotDeclaredException):
            _door(initial_state=LOCKED)

    def test_written_states_without_initial_state_raises_unless_open_is_declared(self) -> None:
        """states を書いて initial_state を省くと、初めの状態は open になり、states に open が無ければ InitialPassageStateNotDeclaredException を投げる。"""
        states = (
            PassageStateDeclaration(
                name=CLOSED, display_name=DisplayName("閉じている"), traversable=False, sound_loss=SoundLoss(20)
            ),
        )

        with pytest.raises(InitialPassageStateNotDeclaredException):
            PassageDeclaration(
                passage_id=PassageId("gate"),
                ends=(SpotId("yard"), SpotId("road")),
                two_way=True,
                travel_ticks=Ticks(1),
                states=states,
            )


class TestPassageDeclarationAllows:
    """PassageDeclaration.allows が、指定した状態の traversable を答えることを保証する。"""

    def test_allows_is_true_for_a_traversable_state(self) -> None:
        """通れる状態 open を渡すと True を返す。"""
        assert _door().allows(OPEN) is True

    def test_allows_is_false_for_a_blocking_state(self) -> None:
        """通れない状態 closed を渡すと False を返す。"""
        assert _door().allows(CLOSED) is False

    def test_allows_for_an_undeclared_state_raises(self) -> None:
        """宣言に無い状態の名前を渡すと UndeclaredPassageStateException を投げる。"""
        with pytest.raises(UndeclaredPassageStateException):
            _door().allows(LOCKED)


class TestPassageDeclarationState:
    """PassageDeclaration.state が、名前に合う状態の宣言を返すことを保証する。"""

    def test_state_returns_the_declaration_with_that_name(self) -> None:
        """closed を渡すと、closed の状態の宣言 (呼び名・通れるか・減衰) を返す。"""
        assert _door().state(CLOSED) == PassageStateDeclaration(
            name=CLOSED, display_name=DisplayName("閉じている"), traversable=False, sound_loss=SoundLoss(20)
        )

    def test_state_for_an_undeclared_name_raises(self) -> None:
        """宣言に無い状態の名前を渡すと UndeclaredPassageStateException を投げる。"""
        with pytest.raises(UndeclaredPassageStateException):
            _door().state(LOCKED)


class TestPassageDeclarationRejectsAmbiguousDeclarations:
    """PassageDeclaration が、状態の答えが決まらない宣言と、同じ場所へ戻る通路を作らないことを保証する。"""

    def test_two_states_with_the_same_name_raise(self) -> None:
        """同じ名前の状態を 2 つ書くと DuplicatePassageStateNameException を投げる。"""
        states = (
            PassageStateDeclaration(
                name=CLOSED, display_name=DisplayName("閉じている"), traversable=False, sound_loss=SoundLoss(20)
            ),
            PassageStateDeclaration(
                name=CLOSED, display_name=DisplayName("閉じている"), traversable=True, sound_loss=SoundLoss(0)
            ),
        )

        with pytest.raises(DuplicatePassageStateNameException):
            PassageDeclaration(
                passage_id=PassageId("cellar_door"),
                ends=(SpotId("hall"), SpotId("cellar")),
                two_way=True,
                travel_ticks=Ticks(1),
                states=states,
                initial_state=CLOSED,
            )

    def test_passage_whose_two_ends_are_the_same_spot_raises(self) -> None:
        """ends の 2 つが同じ場所だと PassageEndsAtSameSpotException を投げる。"""
        with pytest.raises(PassageEndsAtSameSpotException):
            PassageDeclaration(
                passage_id=PassageId("loop"),
                ends=(SpotId("hall"), SpotId("hall")),
                two_way=True,
                travel_ticks=Ticks(1),
            )


class TestPassageDeclarationHiddenUntilRevealed:
    """PassageDeclaration が、初めは無い道 (RevealPassageEffect で現れる) を宣言できることを保証する。"""

    def test_passage_is_present_from_the_start_when_hidden_until_revealed_is_omitted(self) -> None:
        """hidden_until_revealed を書かないと、初めからある道 (False) になる。"""
        passage = PassageDeclaration(
            passage_id=PassageId("path"),
            ends=(SpotId("field"), SpotId("forest")),
            two_way=True,
            travel_ticks=Ticks(2),
        )

        assert passage.hidden_until_revealed is False

    def test_passage_keeps_hidden_until_revealed_when_declared(self) -> None:
        """hidden_until_revealed=True を渡すと、その値を持つ。"""
        passage = PassageDeclaration(
            passage_id=PassageId("secret_tunnel"),
            ends=(SpotId("cellar"), SpotId("well")),
            two_way=True,
            travel_ticks=Ticks(3),
            hidden_until_revealed=True,
        )

        assert passage.hidden_until_revealed is True
