from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, PassageStateDeclaration
from ai_rpg_world.game_world.domain.exception.spot_declaration_exception import (
    DuplicatePassageStateNameException,
    InitialPassageStateNotDeclaredException,
    NoPassageStatesException,
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
        hidden_until_revealed=False,
    )


class TestPassageDeclarationWithoutStates:
    """PassageDeclaration が状態を既定で埋めず、1 つも無い宣言を断ることを保証する。"""

    def test_empty_states_raise(self) -> None:
        """states に空の tuple を渡すと、状態を補わずに NoPassageStatesException を投げる。"""
        with pytest.raises(NoPassageStatesException):
            PassageDeclaration(
                passage_id=PassageId("path"),
                ends=(SpotId("field"), SpotId("forest")),
                two_way=True,
                travel_ticks=Ticks(2),
                states=(),
                initial_state=OPEN,
                hidden_until_revealed=False,
            )


class TestPassageDeclarationInitialState:
    """PassageDeclaration の初めの状態が、宣言した状態のどれかでなければならないことを保証する。"""

    def test_initial_state_not_in_states_raises(self) -> None:
        """initial_state に states に無い名前を渡すと InitialPassageStateNotDeclaredException を投げる。"""
        with pytest.raises(InitialPassageStateNotDeclaredException):
            _door(initial_state=LOCKED)


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
                hidden_until_revealed=False,
            )

    def test_passage_whose_two_ends_are_the_same_spot_raises(self) -> None:
        """ends の 2 つが同じ場所だと PassageEndsAtSameSpotException を投げる。"""
        with pytest.raises(PassageEndsAtSameSpotException):
            PassageDeclaration(
                passage_id=PassageId("loop"),
                ends=(SpotId("hall"), SpotId("hall")),
                two_way=True,
                travel_ticks=Ticks(1),
                states=_door_states(),
                initial_state=CLOSED,
                hidden_until_revealed=False,
            )


class TestPassageDeclarationHiddenUntilRevealed:
    """PassageDeclaration が、初めは無い道 (RevealPassageEffect で現れる) を宣言できることを保証する。"""

    def test_passage_keeps_hidden_until_revealed_when_declared(self) -> None:
        """hidden_until_revealed=True を渡すと、その値を持つ。"""
        passage = PassageDeclaration(
            passage_id=PassageId("secret_tunnel"),
            ends=(SpotId("cellar"), SpotId("well")),
            two_way=True,
            travel_ticks=Ticks(3),
            states=_door_states(),
            initial_state=OPEN,
            hidden_until_revealed=True,
        )

        assert passage.hidden_until_revealed is True
