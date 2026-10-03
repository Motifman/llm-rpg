"""``Expectation`` 集約: 予期と、その清算の規則。

判定 (照合・形) は外から 1 件ずつ受け取るが、状態をどう移すかはこの集約だけが
決める (#1335 の原則「LLM は判断候補を返し、状態遷移の可否はドメインが決める」)。
状態を直接書き換える口は持たない。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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

    照合は 1 ターンに 1 回まで受け取る。同じ当否が 2 回続いたら確定する。1 回の
    判断のぶれを信念まで届かせないため (#1436 試作 2)。暫定の判定は最後の当否
    つきの照合で、別の項目としては持たない。

    「まだ分からない」は新しい材料が無いという意味で、前の判定を打ち消さない。
    続いたかを数えるときも飛ばす。清算の問いは直近の数ターンしか見せないので、
    当たった証拠が見える範囲から外れただけでも「まだ分からない」が返りうる。

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
        self._closed_at_turn: int | None = None

    @classmethod
    def restore(cls, snapshot: ExpectationSnapshot) -> Expectation:
        """保存した状態から予期を作り直す。照合の記録を再生せず、状態をそのまま戻す。

        形の判定や期限の確認のターンは照合の記録に残らないので、再生では戻せない。
        状態が清算の規則と食い違うときは作り直さずに拒む。
        """
        if not isinstance(snapshot, ExpectationSnapshot):
            raise ExpectationValidationException(
                "snapshot must be ExpectationSnapshot"
            )
        expectation = cls(
            expectation_id=snapshot.expectation_id,
            holder=snapshot.holder,
            content=snapshot.content,
            origin=snapshot.origin,
            likelihood=snapshot.likelihood,
            formed_at_turn=snapshot.formed_at_turn,
            expires_at_turn=snapshot.expires_at_turn,
            formed_with=snapshot.formed_with,
            due=snapshot.due,
            beliefs_in_mind=snapshot.beliefs_in_mind,
            episodes_in_mind=snapshot.episodes_in_mind,
        )
        expectation._restore_state(
            shape=snapshot.shape,
            checks=snapshot.checks,
            status=snapshot.status,
            closed_at_turn=snapshot.closed_at_turn,
        )
        return expectation

    def snapshot(self) -> ExpectationSnapshot:
        """保存するための値を返す。状態を読んで判断する口ではなく、保存して ``restore`` に戻すためだけに使う。"""
        return ExpectationSnapshot(
            expectation_id=self._expectation_id,
            holder=self._holder,
            content=self._content,
            origin=self._origin,
            likelihood=self._likelihood,
            formed_at_turn=self._formed_at_turn,
            expires_at_turn=self._expires_at_turn,
            formed_with=self._formed_with,
            due=self._due,
            beliefs_in_mind=self._beliefs_in_mind,
            episodes_in_mind=self._episodes_in_mind,
            shape=self._shape,
            checks=tuple(self._checks),
            status=self._status,
            closed_at_turn=self._closed_at_turn,
        )

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

    @property
    def awaits_shape(self) -> bool:
        """清算待ちで、形の判定も照合もまだ受けていない。

        形の判定は最初の照合より前にしか受け取れない。予期を書いたターンに判定を
        得られなかった予期にも、次のターンに形を問えるよう外から分かるようにする。
        """
        return self._status.is_open and self._shape is None and not self._checks

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
        self._closed_at_turn = turn
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
        ending = _first_ending(self._checks)
        if ending is not None and ending.outcome is None:
            self._status = ExpectationStatus.VOIDED
            self._closed_at_turn = check.turn
            return ExpectationVoided(
                expectation_id=self._expectation_id,
                holder=self._holder,
                turn=check.turn,
            )
        if ending is not None and ending.outcome is not None:
            return self._settle(ending.outcome, turn=check.turn)
        if check.verdict is CheckVerdict.MISS:
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
        """期限のターンを過ぎていれば、暫定の判定で確定させる。当否つきの照合が無ければ期限切れにする。"""
        self._require_open()
        now = require_turn(now_turn, name="now_turn")
        if now <= self._expires_at_turn:
            return None
        provisional = _last_outcome(self._checks)
        if provisional is not None:
            return self._settle(provisional, turn=now)
        self._status = ExpectationStatus.EXPIRED
        self._closed_at_turn = now
        return ExpectationExpired(
            expectation_id=self._expectation_id,
            holder=self._holder,
            turn=now,
        )

    def expire_early(
        self, *, now_turn: int
    ) -> ExpectationSettled | ExpectationExpired:
        """清算待ちの件数の上限で外すとき、期限を前のターンに繰り上げて閉じる。

        閉じ方は期限を過ぎたときと同じ規則にする。上限で外す専用の閉じ方を持つと、
        保存して戻すときに、期限より前に閉じた理由を照合の記録から導けない。
        """
        self._require_open()
        now = require_turn(now_turn, name="now_turn")
        if now <= self._formed_at_turn:
            raise ExpectationCheckRuleException(
                f"now_turn ({now}) must be after formed_at_turn ({self._formed_at_turn})"
            )
        if self._checks and self._checks[-1].turn >= now:
            raise ExpectationCheckRuleException(
                f"now_turn ({now}) must be after the last check turn "
                f"({self._checks[-1].turn})"
            )
        self._expires_at_turn = min(self._expires_at_turn, now - 1)
        closed = self.expire_if_overdue(now_turn=now)
        assert closed is not None
        return closed

    def _settle(self, outcome: Outcome, *, turn: int) -> ExpectationSettled:
        self._status = ExpectationStatus.SETTLED
        self._closed_at_turn = turn
        return ExpectationSettled(
            expectation_id=self._expectation_id,
            holder=self._holder,
            turn=turn,
            outcome=outcome,
            likelihood=self._likelihood,
            beliefs_in_mind=self._beliefs_in_mind,
            episodes_in_mind=self._episodes_in_mind,
        )

    def _restore_state(
        self,
        *,
        shape: object,
        checks: object,
        status: object,
        closed_at_turn: object,
    ) -> None:
        if not isinstance(status, ExpectationStatus):
            raise ExpectationValidationException("status must be ExpectationStatus")
        if shape is not None and not isinstance(shape, ShapeVerdict):
            raise ExpectationValidationException("shape must be ShapeVerdict or None")
        if not isinstance(checks, tuple) or not all(
            isinstance(check, Check) for check in checks
        ):
            raise ExpectationValidationException("checks must be tuple[Check, ...]")
        for index, check in enumerate(checks):
            if not self._formed_at_turn <= check.turn <= self._expires_at_turn:
                raise ExpectationValidationException(
                    f"check turn ({check.turn}) is outside formed_at_turn "
                    f"({self._formed_at_turn}) .. expires_at_turn ({self._expires_at_turn})"
                )
            if index > 0 and check.turn <= checks[index - 1].turn:
                raise ExpectationValidationException(
                    "check turns must be strictly increasing"
                )
        closed = (
            None
            if closed_at_turn is None
            else require_turn(closed_at_turn, name="closed_at_turn")
        )
        if status.is_open != (closed is None):
            raise ExpectationValidationException(
                f"closed_at_turn must be set exactly when status is not open "
                f"(status={status.value}, closed_at_turn={closed})"
            )

        ended = _first_ending(checks)
        if ended is not None and ended.index != len(checks) - 1:
            raise ExpectationValidationException(
                "checks must not continue after the expectation ended"
            )
        implied = _implied_status(shape, checks, closed=closed)
        if status is not implied:
            raise ExpectationValidationException(
                f"status {status.value} contradicts shape and checks, "
                f"which imply {implied.value}"
            )
        if status is ExpectationStatus.DISMISSED and checks:
            raise ExpectationValidationException(
                "dismissed expectation must not have checks"
            )
        self._require_closed_turn_fits(status, closed, ended=ended, checks=checks)

        self._shape = shape
        self._checks = list(checks)
        self._status = status
        self._closed_at_turn = closed

    def _require_closed_turn_fits(
        self,
        status: ExpectationStatus,
        closed: int | None,
        *,
        ended: _Ending | None,
        checks: tuple[Check, ...],
    ) -> None:
        if closed is None:
            return
        if status is ExpectationStatus.DISMISSED:
            fits = self._formed_at_turn <= closed <= self._expires_at_turn
        elif ended is not None:
            fits = closed == checks[-1].turn
        else:
            fits = closed > self._expires_at_turn
        if not fits:
            raise ExpectationValidationException(
                f"{status.value} expectation cannot be closed at turn {closed} "
                f"(formed_at_turn={self._formed_at_turn}, "
                f"expires_at_turn={self._expires_at_turn}, "
                f"checks={[(c.turn, c.verdict.value) for c in checks]})"
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


@dataclass(frozen=True)
class _Ending:
    """照合の記録の中で予期が終わった位置。``outcome`` が None なら、予期になっていないとして外れた。"""

    index: int
    outcome: Outcome | None


def _first_ending(checks: Sequence[Check]) -> _Ending | None:
    """照合だけで予期が終わる最初の位置。同じ当否が、まだ分からないを飛ばして 2 回続くか、予期になっていないと判定されたところ。"""
    last_outcome: Outcome | None = None
    for index, check in enumerate(checks):
        if check.verdict is CheckVerdict.NOT_AN_EXPECTATION:
            return _Ending(index, outcome=None)
        outcome = check.verdict.outcome
        if outcome is None:
            continue
        if outcome is last_outcome:
            return _Ending(index, outcome=outcome)
        last_outcome = outcome
    return None


def _implied_status(
    shape: ShapeVerdict | None, checks: Sequence[Check], *, closed: int | None
) -> ExpectationStatus:
    """形の判定と照合の記録と、終わったかどうかから導ける状態。"""
    if shape is not None and not shape.is_settleable:
        return ExpectationStatus.DISMISSED
    ended = _first_ending(checks)
    if ended is not None:
        if ended.outcome is None:
            return ExpectationStatus.VOIDED
        return ExpectationStatus.SETTLED
    if closed is None:
        return ExpectationStatus.OPEN
    if _last_outcome(checks) is not None:
        return ExpectationStatus.SETTLED
    return ExpectationStatus.EXPIRED


def _last_outcome(checks: Sequence[Check]) -> Outcome | None:
    """暫定の判定。最後の当否つきの照合の当否。"""
    for check in reversed(checks):
        if check.verdict.outcome is not None:
            return check.verdict.outcome
    return None


__all__ = ["Expectation"]
