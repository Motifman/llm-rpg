"""PredicateResult が述語評価の成立・未成立・文脈不足を区別する契約。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PredicateResultValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateReasonCode,
    PredicateResult,
)


class TestPredicateResultFactories:
    """用途を跨ぐ4種類の評価結果を、曖昧な組合せなしで生成する。"""

    def test_satisfied_result_has_no_failure_information(self) -> None:
        """成立結果には理由・失敗述語・経路・不足文脈を持たせない。"""
        result = PredicateResult.satisfied()

        assert result.is_satisfied is True
        assert result.reason_code is None
        assert result.failure_message is None
        assert result.failed_predicate is None
        assert result.failed_path is None
        assert result.missing_context == frozenset()

    def test_not_satisfied_result_identifies_predicate_and_path(self) -> None:
        """通常の未成立は、落ちた述語と根からの子番号を保持する。"""
        predicate = object()

        result = PredicateResult.not_satisfied(
            failed_predicate=predicate,
            failed_path=(1, 2),
            failure_message="条件を満たしていない。",
        )

        assert result.is_satisfied is False
        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is predicate
        assert result.failed_path == (1, 2)
        assert result.failure_message == "条件を満たしていない。"
        assert result.missing_context == frozenset()

    def test_missing_context_result_names_required_inputs(self) -> None:
        """文脈不足は通常の未成立と別の理由コードと入力名を持つ。"""
        predicate = object()

        result = PredicateResult.context_missing(
            failed_predicate=predicate,
            failed_path=(),
            required_context={"current_weather"},
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"current_weather"})

    def test_unsupported_result_is_distinct_from_world_state_mismatch(self) -> None:
        """未対応の述語は、世界状態が合わない通常未成立と区別する。"""
        predicate = object()

        result = PredicateResult.unsupported(
            failed_predicate=predicate,
            failed_path=(),
        )

        assert result.reason_code is PredicateReasonCode.UNSUPPORTED_PREDICATE


class TestPredicateResultInvariants:
    """直接構築でも成功と失敗の情報が矛盾する状態を拒否する。"""

    def test_satisfied_result_rejects_failure_details(self) -> None:
        """成立なのに失敗理由を持つ矛盾した結果は生成できない。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult(
                is_satisfied=True,
                reason_code=PredicateReasonCode.NOT_SATISFIED,
                failed_predicate=object(),
                failed_path=(),
            )

    def test_satisfied_result_rejects_even_an_empty_failure_path(self) -> None:
        """空tupleも根を指す経路なので、成立結果へ混入できない。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult(is_satisfied=True, failed_path=())

    def test_failed_result_requires_predicate_and_path(self) -> None:
        """未成立結果は、どこで落ちたかを必ず機械的に特定できる。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult(
                is_satisfied=False,
                reason_code=PredicateReasonCode.NOT_SATISFIED,
            )

    def test_missing_context_requires_at_least_one_input_name(self) -> None:
        """文脈不足を名乗りながら不足項目が空の結果は拒否する。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult(
                is_satisfied=False,
                reason_code=PredicateReasonCode.MISSING_CONTEXT,
                failed_predicate=object(),
                failed_path=(),
            )

    def test_non_missing_reason_rejects_missing_context_names(self) -> None:
        """通常未成立へ不足文脈を混ぜ、理由を二重化する状態を拒否する。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult(
                is_satisfied=False,
                reason_code=PredicateReasonCode.NOT_SATISFIED,
                failed_predicate=object(),
                failed_path=(),
                missing_context=frozenset({"current_weather"}),
            )

    @pytest.mark.parametrize("failed_path", [[0], (True,), (-1,)])
    def test_failed_path_rejects_non_tuple_bool_and_negative_index(
        self,
        failed_path: object,
    ) -> None:
        """失敗経路は非負整数の tuple だけを受理する。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult.not_satisfied(
                failed_predicate=object(),
                failed_path=failed_path,  # type: ignore[arg-type]
            )

    def test_context_missing_rejects_bare_string_before_conversion(self) -> None:
        """文脈名の文字列を一文字ずつの集合へ静かに変換しない。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult.context_missing(
                failed_predicate=object(),
                failed_path=(),
                required_context="weather",  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize(
        "missing_context",
        [{"weather"}, frozenset({""}), frozenset({1})],
    )
    def test_direct_construction_rejects_invalid_context_name_collection(
        self,
        missing_context: object,
    ) -> None:
        """不足文脈は空でない文字列だけを持つ frozenset に限定する。"""
        with pytest.raises(PredicateResultValidationException):
            PredicateResult(
                is_satisfied=False,
                reason_code=PredicateReasonCode.MISSING_CONTEXT,
                failed_predicate=object(),
                failed_path=(),
                missing_context=missing_context,  # type: ignore[arg-type]
            )
