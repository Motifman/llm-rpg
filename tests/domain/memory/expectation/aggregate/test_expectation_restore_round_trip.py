"""判定を受けて移った状態を restore がすべて受け入れ、別の終わり方とは取り違えないことを、短い判定の列の総当たりで保証する。

照合ごとの規則 (record / judge_shape / expire_if_overdue) と復元の検証は別の入口なので、
片方だけ規則を変えるとずれる。ずれたら、この総当たりのどれかが落ちる。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationDismissed,
    ExpectationEvent,
    ExpectationExpired,
    ExpectationSettled,
    ExpectationVoided,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_snapshot import (
    ExpectationSnapshot,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)

FORMED_AT = 10
EXPIRES_AT = 13
FORMATION = {
    "expectation_id": ExpectationId("exp-1"),
    "holder": BeingId("being-rio"),
    "content": "箱を開けても空だろう",
    "origin": ExpectationOrigin.WITH_ACTION,
    "likelihood": Likelihood.PROBABLY,
    "formed_at_turn": FORMED_AT,
    "expires_at_turn": EXPIRES_AT,
}
_STATUS_BY_EVENT: dict[type[object], ExpectationStatus] = {
    ExpectationSettled: ExpectationStatus.SETTLED,
    ExpectationVoided: ExpectationStatus.VOIDED,
    ExpectationDismissed: ExpectationStatus.DISMISSED,
    ExpectationExpired: ExpectationStatus.EXPIRED,
}


@dataclass(frozen=True)
class _Reached:
    """判定を受けて移った先。保存するときに集約から取り出すはずの値。"""

    label: str
    shape: ShapeVerdict | None
    checks: tuple[Check, ...]
    status: ExpectationStatus
    closed_at_turn: int | None


def _drive(
    shape: ShapeVerdict | None,
    verdicts: tuple[CheckVerdict, ...],
    overdue: bool,
) -> _Reached | None:
    expectation = Expectation(**FORMATION)  # type: ignore[arg-type]
    closing: ExpectationEvent | None = None
    if shape is not None:
        closing = expectation.judge_shape(shape, turn=FORMED_AT)
    accepted: list[Check] = []
    for offset, verdict in enumerate(verdicts, start=1):
        if closing is not None and type(closing) in _STATUS_BY_EVENT:
            return None
        check = Check(turn=FORMED_AT + offset, verdict=verdict)
        accepted.append(check)
        event = expectation.record(check)
        if event is not None and type(event) in _STATUS_BY_EVENT:
            closing = event
    if overdue:
        if closing is not None and type(closing) in _STATUS_BY_EVENT:
            return None
        closing = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

    label = "-".join(
        [shape.value if shape else "noshape"]
        + [v.value for v in verdicts]
        + (["overdue"] if overdue else [])
    )
    if closing is None or type(closing) not in _STATUS_BY_EVENT:
        return _Reached(label, shape, tuple(accepted), ExpectationStatus.OPEN, None)
    return _Reached(
        label,
        shape,
        tuple(accepted),
        _STATUS_BY_EVENT[type(closing)],
        closing.turn,
    )


def _reachable_states() -> list[_Reached]:
    reached: list[_Reached] = []
    for shape in (None, *ShapeVerdict):
        for length in range(0, 4):
            for verdicts in itertools.product(CheckVerdict, repeat=length):
                for overdue in (False, True):
                    state = _drive(shape, verdicts, overdue)
                    if state is not None:
                        reached.append(state)
    return reached


_REACHABLE = _reachable_states()


def _snapshot_of(state: _Reached, status: ExpectationStatus) -> ExpectationSnapshot:
    return ExpectationSnapshot(
        **FORMATION,  # type: ignore[arg-type]
        shape=state.shape,
        checks=state.checks,
        status=status,
        closed_at_turn=state.closed_at_turn,
    )


def _restore(state: _Reached, status: ExpectationStatus) -> Expectation:
    return Expectation.restore(_snapshot_of(state, status))


def _driven(state: _Reached) -> Expectation:
    """``_drive`` と同じ判定の列を、もう一度集約に渡して終えたもの。"""
    expectation = Expectation(**FORMATION)  # type: ignore[arg-type]
    if state.shape is not None:
        expectation.judge_shape(state.shape, turn=FORMED_AT)
    for check in state.checks:
        expectation.record(check)
    if state.label.endswith("overdue"):
        expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)
    return expectation


def test_reachable_states_cover_every_status() -> None:
    """総当たりで辿り着く状態は、清算待ちと 4 通りの終わり方をすべて含む。"""
    assert {state.status for state in _REACHABLE} == set(ExpectationStatus)


@pytest.mark.parametrize("state", _REACHABLE, ids=lambda s: s.label)
def test_restore_accepts_every_reachable_state(state: _Reached) -> None:
    """判定を受けて移った状態は、そのまま restore に渡すと作り直せる。"""
    expectation = _restore(state, state.status)

    assert expectation.content == FORMATION["content"]


@pytest.mark.parametrize("state", _REACHABLE, ids=lambda s: s.label)
def test_restore_rejects_reachable_state_with_other_status(state: _Reached) -> None:
    """判定を受けて移った状態のまま終わり方だけを別のものにすると、どれも ExpectationValidationException で拒む。"""
    others = [status for status in ExpectationStatus if status is not state.status]

    for other in others:
        with pytest.raises(ExpectationValidationException):
            _restore(state, other)


@pytest.mark.parametrize("state", _REACHABLE, ids=lambda s: s.label)
def test_snapshot_of_driven_expectation_carries_reached_state(state: _Reached) -> None:
    """判定を受けて移った予期の保存用の値は、移った先の状態と、終わりを告げた出来事のターンを持つ。"""
    snapshot = _driven(state).snapshot()

    assert snapshot == _snapshot_of(state, state.status)


@pytest.mark.parametrize("state", _REACHABLE, ids=lambda s: s.label)
def test_restore_of_snapshot_reads_back_same_snapshot(state: _Reached) -> None:
    """判定を受けて移った予期の保存用の値を restore に渡すと、作り直した予期から同じ値を読み出せる。"""
    snapshot = _driven(state).snapshot()

    assert Expectation.restore(snapshot).snapshot() == snapshot


def test_dismissed_snapshot_keeps_judged_turn_after_formed_turn() -> None:
    """作ったターンより後に形の判定で外した予期は、判定したターンを終わったターンとして保存し、往復しても保つ。"""
    expectation = Expectation(**FORMATION)  # type: ignore[arg-type]
    expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=FORMED_AT + 2)

    snapshot = Expectation.restore(expectation.snapshot()).snapshot()

    assert snapshot.status is ExpectationStatus.DISMISSED
    assert snapshot.closed_at_turn == FORMED_AT + 2
