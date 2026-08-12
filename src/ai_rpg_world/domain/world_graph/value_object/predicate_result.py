"""用途を跨いで述語評価の理由を失わず運ぶ値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Generic, Optional, TypeVar

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PredicateResultValidationException,
)


PredicateT = TypeVar("PredicateT")


class PredicateReasonCode(str, Enum):
    """述語が成立しなかった理由の機械可読な区分。"""

    NOT_SATISFIED = "not_satisfied"
    MISSING_CONTEXT = "missing_context"
    UNSUPPORTED_PREDICATE = "unsupported_predicate"


@dataclass(frozen=True)
class PredicateResult(Generic[PredicateT]):
    """成立可否に加え、失敗した述語・経路・不足入力を保持する。"""

    is_satisfied: bool
    reason_code: Optional[PredicateReasonCode] = None
    failure_message: Optional[str] = None
    failed_predicate: Optional[PredicateT] = None
    failed_path: Optional[tuple[int, ...]] = None
    missing_context: FrozenSet[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.is_satisfied, bool):
            raise PredicateResultValidationException(
                "is_satisfied must be bool"
            )
        if self.reason_code is not None and not isinstance(
            self.reason_code, PredicateReasonCode
        ):
            raise PredicateResultValidationException(
                "reason_code must be PredicateReasonCode or None"
            )
        if self.failure_message is not None and (
            not isinstance(self.failure_message, str) or not self.failure_message
        ):
            raise PredicateResultValidationException(
                "failure_message must be non-empty str or None"
            )
        self._validate_path()
        self._validate_context_names()

        if self.is_satisfied:
            if (
                self.reason_code is not None
                or self.failure_message is not None
                or self.failed_predicate is not None
                or self.failed_path is not None
                or self.missing_context
            ):
                raise PredicateResultValidationException(
                    "satisfied result must not contain failure details"
                )
            return

        if self.reason_code is None:
            raise PredicateResultValidationException(
                "failed result requires reason_code"
            )
        if self.failed_predicate is None or self.failed_path is None:
            raise PredicateResultValidationException(
                "failed result requires failed_predicate and failed_path"
            )
        if self.reason_code is PredicateReasonCode.MISSING_CONTEXT:
            if not self.missing_context:
                raise PredicateResultValidationException(
                    "missing-context result requires context names"
                )
        elif self.missing_context:
            raise PredicateResultValidationException(
                "only missing-context result may contain context names"
            )

    def _validate_path(self) -> None:
        if self.failed_path is None:
            return
        if not isinstance(self.failed_path, tuple) or any(
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            for index in self.failed_path
        ):
            raise PredicateResultValidationException(
                "failed_path must be a tuple of non-negative int"
            )

    def _validate_context_names(self) -> None:
        if not isinstance(self.missing_context, frozenset) or any(
            not isinstance(name, str) or not name
            for name in self.missing_context
        ):
            raise PredicateResultValidationException(
                "missing_context must be a frozenset of non-empty str"
            )

    @classmethod
    def satisfied(cls) -> "PredicateResult[PredicateT]":
        """成立結果を返す。"""
        return cls(is_satisfied=True)

    @classmethod
    def not_satisfied(
        cls,
        *,
        failed_predicate: PredicateT,
        failed_path: tuple[int, ...],
        failure_message: Optional[str] = None,
    ) -> "PredicateResult[PredicateT]":
        """世界状態と述語が正常に不一致だった結果を返す。"""
        return cls(
            is_satisfied=False,
            reason_code=PredicateReasonCode.NOT_SATISFIED,
            failure_message=failure_message,
            failed_predicate=failed_predicate,
            failed_path=failed_path,
        )

    @classmethod
    def context_missing(
        cls,
        *,
        failed_predicate: PredicateT,
        failed_path: tuple[int, ...],
        required_context: set[str] | frozenset[str],
        failure_message: Optional[str] = None,
    ) -> "PredicateResult[PredicateT]":
        """評価に必要な入力が渡っていない結果を返す。"""
        if not isinstance(required_context, (set, frozenset)):
            raise PredicateResultValidationException(
                "required_context must be a set or frozenset of context names"
            )
        return cls(
            is_satisfied=False,
            reason_code=PredicateReasonCode.MISSING_CONTEXT,
            failure_message=failure_message,
            failed_predicate=failed_predicate,
            failed_path=failed_path,
            missing_context=frozenset(required_context),
        )

    @classmethod
    def unsupported(
        cls,
        *,
        failed_predicate: PredicateT,
        failed_path: tuple[int, ...],
        failure_message: Optional[str] = None,
    ) -> "PredicateResult[PredicateT]":
        """評価器が述語の種類を実装していない結果を返す。"""
        return cls(
            is_satisfied=False,
            reason_code=PredicateReasonCode.UNSUPPORTED_PREDICATE,
            failure_message=failure_message,
            failed_predicate=failed_predicate,
            failed_path=failed_path,
        )


__all__ = ["PredicateReasonCode", "PredicateResult"]
