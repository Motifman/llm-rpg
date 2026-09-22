"""候補に当たらなかった対象の名前を、いま選べる候補から意味で選び直す。

行動名の救済 (#1321) と同じ形。当たらなかったときだけ問い、「該当なし」を必ず
選択肢に入れ、確信が足りなければ従来どおり失敗させる。判断は採否にかかわらず
trace に残し、置き換えたときは結果文で当人に見せる。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    TARGET_LABEL_JUDGMENTS_KEY,
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_label_rescue import (
    NO_MATCH_OPTION,
    QUESTION_NAME,
    TargetLabelRescue,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)


class _FixedPort(ITypedJudgmentPort):
    """常に同じ選択肢を返す。渡された state と質問を記録する。"""

    def __init__(self, choice: str, probability: float = 0.95, confidence: float | None = 0.9) -> None:
        self.choice, self.probability, self.confidence = choice, probability, confidence
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    def judge(self, state, questions):
        self.calls.append((state, dict(questions)))
        return {
            name: JudgmentResult(
                value=self.choice,
                probabilities={self.choice: self.probability},
                confidence=self.confidence,
                source=JudgmentSource.JEV,
                latency_ms=9.0,
            )
            for name in questions
        }


class _FailingPort(ITypedJudgmentPort):
    def judge(self, state, questions):
        raise TypedJudgmentUnavailableException("down", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED")


def _target(label: str, name: str, *, kind: str = "spot_graph_object", **extra: Any) -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(label=label, kind=kind, display_name=name, **extra)


def _context() -> ToolRuntimeContextDto:
    east = _target("O1", "東の祭壇", world_object_id=11, available_interactions=("offer",), interaction_labels=(("offer", "供物を捧げる"),))
    west = _target("O2", "西の祭壇", world_object_id=12, available_interactions=("offer",), interaction_labels=(("offer", "供物を捧げる"),))
    return ToolRuntimeContextDto(targets={"O1": east, "O2": west})


def _resolve(port: ITypedJudgmentPort | None, written: str, *, min_confidence: float = 0.85) -> dict[str, Any]:
    rescue = TargetLabelRescue(port=port, min_confidence=min_confidence) if port else None
    resolver = SpotGraphArgumentResolver(target_label_rescue=rescue)
    return resolver.resolve_args(
        "interact",
        {"target_label": written, "action_name": "offer", "inner_thought": "祭壇に捧げる"},
        _context(),
    )


class TestTheRescueOnlyRunsWhenTheNameDidNotMatch:
    def test_a_name_already_offered_is_not_asked_about(self) -> None:
        """候補に当たった名前は Jev に問わず、そのまま解決する。"""
        port = _FixedPort("東の祭壇")

        resolved = _resolve(port, "東の祭壇")

        assert resolved["object_id"] == 11
        assert port.calls == []
        assert TARGET_LABEL_JUDGMENTS_KEY not in resolved

    def test_without_a_rescue_the_failure_is_unchanged(self) -> None:
        """救済を配線していなければ、従来どおり INVALID_TARGET_LABEL で失敗する (**正の対照**)。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolve(None, "East Shrine")

        assert caught.value.error_code == "INVALID_TARGET_LABEL"
        assert caught.value.judgment is None


class TestAnUnmatchedNameIsAskedAboutAndCanBeReplaced:
    def test_a_confident_choice_replaces_the_written_name(self) -> None:
        """確信のある選択は書かれた名前を置き換え、判断が結果に載る。"""
        port = _FixedPort("東の祭壇")

        resolved = _resolve(port, "East Shrine")

        assert resolved["object_id"] == 11
        (judgment,) = resolved[TARGET_LABEL_JUDGMENTS_KEY]
        assert judgment["original"] == "East Shrine"
        assert judgment["replaced_with"] == "東の祭壇"
        assert judgment["accepted"] is True
        assert judgment["probability"] == 0.95 and judgment["confidence"] == 0.9
        assert judgment["min_confidence"] == 0.85 and judgment["source"] == "jev"

    def test_the_question_offers_every_candidate_and_a_way_out(self) -> None:
        """質問は候補の全部と「該当なし」を選択肢に持つ。"""
        port = _FixedPort("東の祭壇")

        _resolve(port, "East Shrine")

        _, questions = port.calls[0]
        options = questions[QUESTION_NAME].options
        assert set(options) == {"東の祭壇", "西の祭壇", NO_MATCH_OPTION}

    def test_the_state_carries_the_written_name_hints_and_no_ids(self) -> None:
        """state に書かれた名前・ツール・候補の説明 (種別とできること)・心の声が入り、整数 ID は入らない。"""
        port = _FixedPort("東の祭壇")

        _resolve(port, "East Shrine")

        state, _ = port.calls[0]
        assert state["written_target_name"] == "East Shrine"
        assert state["tool"] == "interact"
        assert state["candidates"]["東の祭壇"] == "この場所の物。できること: 供物を捧げる"
        assert state["inner_thought"] == "祭壇に捧げる"
        assert "11" not in repr(state) and "O1" not in repr(state)


class TestAnUncertainChoiceLeavesTheFailure:
    def test_a_no_match_answer_keeps_the_failure_and_records_the_judgment(self) -> None:
        """「該当なし」なら従来どおり失敗し、問うた判断は例外に載って trace へ運ばれる。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolve(_FixedPort(NO_MATCH_OPTION), "大型カニ")

        assert caught.value.error_code == "INVALID_TARGET_LABEL"
        judgment = caught.value.judgment
        assert judgment is not None
        assert judgment["accepted"] is False and judgment["chosen"] is None
        assert judgment["replaced_with"] is None

    def test_a_low_probability_does_not_replace_anything(self) -> None:
        """確率が閾値未満なら、確信が高くても置き換えない。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolve(_FixedPort("東の祭壇", probability=0.3, confidence=0.95), "East Shrine")

        assert caught.value.judgment["accepted"] is False
        assert caught.value.judgment["probability"] == 0.3

    def test_a_low_confidence_does_not_replace_anything(self) -> None:
        """確信が閾値未満なら置き換えず、失敗のまま。判断は残る。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolve(_FixedPort("東の祭壇", probability=0.9, confidence=0.6), "East Shrine")

        assert caught.value.judgment["accepted"] is False
        assert caught.value.judgment["chosen"] == "東の祭壇"

    def test_a_failing_port_keeps_the_failure_and_the_reason(self) -> None:
        """ポートが落ちても従来どおり失敗し、unavailable_reason が残る。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolve(_FailingPort(), "East Shrine")

        assert caught.value.judgment["unavailable_reason"] == "TYPED_JUDGMENT_TRANSPORT_FAILED"

    def test_kind_mismatch_is_not_asked_about(self) -> None:
        """種別違いの失敗 (INVALID_TARGET_KIND) は名前の問題ではないので問わない。"""
        port = _FixedPort("東の祭壇")
        ctx = ToolRuntimeContextDto(targets={"S1": _target("S1", "祭壇前", kind="spot_graph_sub_location", sub_location_id=1)})
        resolver = SpotGraphArgumentResolver(target_label_rescue=TargetLabelRescue(port=port, min_confidence=0.85))

        with pytest.raises(ToolArgumentResolutionException) as caught:
            resolver.resolve_args("interact", {"target_label": "S1", "action_name": "offer", "inner_thought": "x"}, ctx)

        assert caught.value.error_code == "INVALID_TARGET_KIND"
        assert port.calls == []


class TestConstruction:
    def test_a_threshold_outside_the_unit_interval_is_rejected(self) -> None:
        """min_confidence が (0, 1] の外なら ValueError になる。"""
        with pytest.raises(ValueError):
            TargetLabelRescue(port=_FixedPort("x"), min_confidence=0.0)
