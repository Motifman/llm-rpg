"""``Expectation`` 集約: 予期と、その清算の規則。

判定 (照合・形) は外から 1 件ずつ受け取るが、状態をどう移すかはこの集約だけが
決める (#1335 の原則「LLM は判断候補を返し、状態遷移の可否はドメインが決める」)。
状態を直接書き換える口は持たない。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationDismissed,
    ExpectationEvent,
    ExpectationExpired,
    ExpectationSettled,
    ExpectationVoided,
    ProvisionallyMissed,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationAlreadyClosedException,
    ExpectationCheckRuleException,
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
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
from ai_rpg_world.domain.memory.expectation.value_object.turn import require_turn


def _require_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExpectationValidationException(f"{name} must be a non-empty str")
    return value.strip()


def _require_optional_text(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, name=name)


def _require_ids(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ExpectationValidationException(f"{name} must be tuple[str, ...]")
    return tuple(
        _require_text(item, name=f"{name}[{index}]") for index, item in enumerate(value)
    )


class Expectation:
    """本人が「これから起きる」と思ったこと。

    照合は 1 ターンに 1 回まで受け取る。直前の照合と同じ当否が続いたら確定する。
    1 回の判断のぶれを信念まで届かせないため (#1436 試作 2)。暫定の判定は最後の
    照合の当否で、別の項目としては持たない。

    判定の状態は公開しない。状態をどう移すかはこの集約が決め、外へは返す出来事
    で伝える。外で状態を読んで判断すると、規則が集約の外へ漏れる。
    """

    def __init__(
        self,
        *,
        expectation_id: ExpectationId,
        holder: BeingId,
        content: str,
        origin: ExpectationOrigin,
        likelihood: Likelihood,
        formed_at_turn: int,
        expires_at_turn: int,
        formed_with: str | None = None,
        due: str | None = None,
        beliefs_in_mind: tuple[str, ...] = (),
        episodes_in_mind: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(expectation_id, ExpectationId):
            raise ExpectationValidationException(
                "expectation_id must be ExpectationId"
            )
        if not isinstance(holder, BeingId):
            raise ExpectationValidationException("holder must be BeingId")
        if not isinstance(origin, ExpectationOrigin):
            raise ExpectationValidationException("origin must be ExpectationOrigin")
        if not isinstance(likelihood, Likelihood):
            raise ExpectationValidationException("likelihood must be Likelihood")
        formed = require_turn(formed_at_turn, name="formed_at_turn")
        expires = require_turn(expires_at_turn, name="expires_at_turn")
        if expires < formed:
            raise ExpectationValidationException(
                f"expires_at_turn ({expires}) must be >= formed_at_turn ({formed})"
            )

        self._expectation_id = expectation_id
        self._holder = holder
        self._content = _require_text(content, name="content")
        self._origin = origin
        self._likelihood = likelihood
        self._formed_at_turn = formed
        self._expires_at_turn = expires
        self._formed_with = _require_optional_text(formed_with, name="formed_with")
        self._due = _require_optional_text(due, name="due")
        self._beliefs_in_mind = _require_ids(beliefs_in_mind, name="beliefs_in_mind")
        self._episodes_in_mind = _require_ids(
            episodes_in_mind, name="episodes_in_mind"
        )

        self._shape: ShapeVerdict | None = None
        self._checks: list[Check] = []
        self._status = ExpectationStatus.OPEN

    @property
    def expectation_id(self) -> ExpectationId:
        return self._expectation_id

    @property
    def holder(self) -> BeingId:
        return self._holder

    @property
    def content(self) -> str:
        return self._content

    @property
    def origin(self) -> ExpectationOrigin:
        return self._origin

    @property
    def likelihood(self) -> Likelihood:
        return self._likelihood

    @property
    def formed_at_turn(self) -> int:
        return self._formed_at_turn

    @property
    def expires_at_turn(self) -> int:
        return self._expires_at_turn

    @property
    def formed_with(self) -> str | None:
        return self._formed_with

    @property
    def due(self) -> str | None:
        return self._due

    @property
    def beliefs_in_mind(self) -> tuple[str, ...]:
        return self._beliefs_in_mind

    @property
    def episodes_in_mind(self) -> tuple[str, ...]:
        return self._episodes_in_mind

    def judge_shape(
        self, shape: ShapeVerdict, *, turn: int
    ) -> ExpectationDismissed | None:
        self._require_open()
        if not isinstance(shape, ShapeVerdict):
            raise ExpectationValidationException("shape must be ShapeVerdict")
        self._require_within_term(require_turn(turn, name="turn"))
        if self._shape is not None:
            raise ExpectationCheckRuleException(
                f"shape has already been judged as {self._shape.value}"
            )
        if self._checks:
            raise ExpectationCheckRuleException(
                "shape must be judged before the first check"
            )

        self._shape = shape
        if shape.is_settleable:
            return None
        self._status = ExpectationStatus.DISMISSED
        return ExpectationDismissed(
            expectation_id=self._expectation_id,
            holder=self._holder,
            turn=turn,
            shape=shape,
        )

    def record(self, check: Check) -> ExpectationEvent | None:
        self._require_open()
        if not isinstance(check, Check):
            raise ExpectationValidationException("check must be Check")
        self._require_within_term(check.turn)
        previous = self._checks[-1] if self._checks else None
        if previous is not None and check.turn <= previous.turn:
            raise ExpectationCheckRuleException(
                f"check turn ({check.turn}) must be after previous check "
                f"turn ({previous.turn})"
            )

        self._checks.append(check)
        if check.verdict is CheckVerdict.NOT_AN_EXPECTATION:
            self._status = ExpectationStatus.VOIDED
            return ExpectationVoided(
                expectation_id=self._expectation_id,
                holder=self._holder,
                turn=check.turn,
            )
        outcome = check.verdict.outcome
        if outcome is None:
            return None
        if previous is not None and previous.verdict.outcome is outcome:
            return self._settle(outcome, turn=check.turn)
        if outcome is Outcome.MISS:
            return ProvisionallyMissed(
                expectation_id=self._expectation_id,
                holder=self._holder,
                turn=check.turn,
                likelihood=self._likelihood,
            )
        return None

    def expire_if_overdue(
        self, *, now_turn: int
    ) -> ExpectationSettled | ExpectationExpired | None:
        """期限のターンを過ぎていれば、最後の暫定の判定で確定させる。暫定の判定が無ければ期限切れにする。"""
        self._require_open()
        now = require_turn(now_turn, name="now_turn")
        if now <= self._expires_at_turn:
            return None
        provisional = self._checks[-1].verdict.outcome if self._checks else None
        if provisional is not None:
            return self._settle(provisional, turn=now)
        self._status = ExpectationStatus.EXPIRED
        return ExpectationExpired(
            expectation_id=self._expectation_id,
            holder=self._holder,
            turn=now,
        )

    def _settle(self, outcome: Outcome, *, turn: int) -> ExpectationSettled:
        self._status = ExpectationStatus.SETTLED
        return ExpectationSettled(
            expectation_id=self._expectation_id,
            holder=self._holder,
            turn=turn,
            outcome=outcome,
            likelihood=self._likelihood,
            beliefs_in_mind=self._beliefs_in_mind,
            episodes_in_mind=self._episodes_in_mind,
        )

    def _require_open(self) -> None:
        if not self._status.is_open:
            raise ExpectationAlreadyClosedException(
                f"expectation {self._expectation_id} is already {self._status.value}"
            )

    def _require_within_term(self, turn: int) -> None:
        if turn < self._formed_at_turn:
            raise ExpectationCheckRuleException(
                f"turn ({turn}) must not be before formed_at_turn "
                f"({self._formed_at_turn})"
            )
        if turn > self._expires_at_turn:
            raise ExpectationCheckRuleException(
                f"turn ({turn}) is past expires_at_turn "
                f"({self._expires_at_turn}); expire_if_overdue first"
            )


__all__ = ["Expectation"]
