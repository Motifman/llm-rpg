"""発明された行動名を、対象の操作一覧から意味で選び直す。

## 文字の重なりでは寄せられなかった

``_pick_action_name`` は表示の写し崩れ (quote つき、表示行の丸ごとコピー) だけを
救い、``gather`` のような発明された名前は「その操作はありません」で失敗させて
いた。65 run で 111 件の主因である。``gather`` を ``reap_wheat`` に文字の
類似度で寄せる安全な方法が無いので、意図的に諦めていた。

意味で選べるなら寄せられる。確信が低いときは従来どおり失敗させる。

## 問わない場面がある

候補集合が空になるのは、行為者に操作をすべて伏せた物体のとき
(design_decisions #46)。ここで問うと、伏せた操作の存在を確率として漏らし
かねない。**当たらなかった**ときだけ問う。

## 黙って置き換えない

置換したことを当人に見せる。黙って通すと ``gather`` が通る名前だと学び、
同じ名前を書き続ける。履歴と trace の両方に元の値を残す
(design_decisions #47)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Union

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.action_name_rescue import (
    NO_MATCH_OPTION,
    ActionNameRescue,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    ActionNameSource,
    pick_action_name,
)


class _RecordingPort(ITypedJudgmentPort):
    """問われた内容を記録し、決めた答えを返す。"""

    def __init__(
        self,
        *,
        chosen: str = "reap_wheat",
        probability: float = 0.97,
        confidence: float | None = 0.96,
        raises: bool = False,
    ) -> None:
        self.states: list[Any] = []
        self.questions: list[Mapping[str, Question]] = []
        self._chosen = chosen
        self._probability = probability
        self._confidence = confidence
        self._raises = raises

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.states.append(state)
        self.questions.append(questions)
        if self._raises:
            raise TypedJudgmentUnavailableException("nope")
        name = next(iter(questions))
        return {
            name: JudgmentResult(
                value=self._chosen,
                probabilities={self._chosen: self._probability},
                confidence=self._confidence,
                source=JudgmentSource.JEV,
                latency_ms=120.0,
            )
        }


def _wheat_field() -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(
        label="OBJ1",
        kind="spot_graph_object",
        display_name="麦畑",
        world_object_id=10,
        available_interactions=("reap_wheat", "water_field"),
        interaction_labels=(
            ("reap_wheat", "麦を刈り取る"),
            ("water_field", "水をやる"),
        ),
    )


def _hidden_object() -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(
        label="OBJ2",
        kind="spot_graph_object",
        display_name="納屋の鍵箱",
        world_object_id=11,
    )


def _rescued(
    written: str,
    target: ToolRuntimeTargetDto,
    port: _RecordingPort,
    *,
    min_confidence: float = 0.7,
    inner_thought: str = "小麦を集めたい",
) -> tuple[Any, _RecordingPort]:
    rescue = ActionNameRescue(port=port, min_confidence=min_confidence)
    resolution = rescue.rescue(
        pick_action_name(written, target),
        target=target,
        inner_thought=inner_thought,
    )
    return resolution, port


class TestTheRescueOnlyRunsWhenTheNameDidNotMatch:
    """問う場面と問わない場面が分かれていることを保証する。"""

    def test_a_name_already_offered_is_not_asked_about(self) -> None:
        """一覧にある名前は、ポートを呼ばずにそのまま通る。"""
        resolution, port = _rescued("reap_wheat", _wheat_field(), _RecordingPort())

        assert port.questions == []
        assert resolution.source is ActionNameSource.VERBATIM

    def test_a_copied_display_form_is_not_asked_about(self) -> None:
        """写し崩れは従来の正規化で直るので、ポートを呼ばない。"""
        resolution, port = _rescued('"reap_wheat"', _wheat_field(), _RecordingPort())

        assert port.questions == []
        assert resolution.source is ActionNameSource.NORMALIZED

    def test_an_object_with_no_offered_action_is_not_asked_about(self) -> None:
        """候補集合が空の物体は問わない。伏せた操作の存在を確率で漏らさない。"""
        resolution, port = _rescued("gather", _hidden_object(), _RecordingPort())

        assert port.questions == []
        assert resolution.source is ActionNameSource.NOT_OFFERED


class TestAnInventedNameIsAskedAboutAndCanBeReplaced:
    """発明された名前が、確信があるときだけ置き換わることを保証する。"""

    def test_a_confident_choice_replaces_the_written_name(self) -> None:
        """確率と confidence が閾値以上なら、一覧の名前へ置き換わる。"""
        resolution, _ = _rescued("gather", _wheat_field(), _RecordingPort())

        assert resolution.value == "reap_wheat"
        assert resolution.original == "gather"
        assert resolution.source is ActionNameSource.JUDGMENT
        assert resolution.was_replaced is True

    def test_the_question_offers_every_action_with_its_meaning(self) -> None:
        """選択肢は一覧の操作すべてで、それぞれの意味ラベルが説明に付く。"""
        _, port = _rescued("gather", _wheat_field(), _RecordingPort())

        question = next(iter(port.questions[0].values()))
        assert isinstance(question, ChoiceQuestion)
        assert question.options["reap_wheat"] == "麦を刈り取る"
        assert question.options["water_field"] == "水をやる"

    def test_the_question_always_offers_a_way_out(self) -> None:
        """「該当なし」が必ず選択肢に入る。無いと必ずどれかに寄る。"""
        _, port = _rescued("gather", _wheat_field(), _RecordingPort())

        question = next(iter(port.questions[0].values()))
        assert NO_MATCH_OPTION in question.options

    def test_the_state_carries_the_written_name_and_the_inner_thought(self) -> None:
        """書かれた名前と直前の思考が state に入る。"""
        _, port = _rescued("gather", _wheat_field(), _RecordingPort())

        state = port.states[0]
        assert state["written_action_name"] == "gather"
        assert state["inner_thought"] == "小麦を集めたい"
        assert state["target"] == "麦畑"

    def test_the_state_carries_no_internal_ids(self) -> None:
        """state に整数 ID を入れない (設計原則 1)。名前だけを渡す。"""
        _, port = _rescued("gather", _wheat_field(), _RecordingPort())

        flat = repr(port.states[0])
        assert "world_object_id" not in flat
        assert "OBJ1" not in flat


class TestAnUncertainChoiceLeavesTheNameAlone:
    """確信が足りないとき、従来の失敗経路に残ることを保証する。"""

    def test_a_no_match_answer_does_not_replace_anything(self) -> None:
        """「該当なし」が選ばれたら置き換えない。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(chosen=NO_MATCH_OPTION)
        )

        assert resolution.value == "gather"
        assert resolution.source is ActionNameSource.UNRESOLVED

    def test_a_low_probability_does_not_replace_anything(self) -> None:
        """選んだ選択肢の確率が閾値未満なら置き換えない。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(probability=0.4)
        )

        assert resolution.value == "gather"
        assert resolution.source is ActionNameSource.UNRESOLVED

    def test_a_low_confidence_does_not_replace_anything(self) -> None:
        """confidence が閾値未満なら置き換えない。確率だけを見ない。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(confidence=0.3)
        )

        assert resolution.value == "gather"
        assert resolution.source is ActionNameSource.UNRESOLVED

    def test_the_judgment_is_recorded_even_when_it_is_not_taken(self) -> None:
        """採らなかった判断も、確率と閾値と採否が残る。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(probability=0.4)
        )

        assert resolution.judgment is not None
        assert resolution.judgment.chosen == "reap_wheat"
        assert resolution.judgment.probability == 0.4
        assert resolution.judgment.min_confidence == 0.7
        assert resolution.judgment.accepted is False


class TestAnUnavailablePortFallsBackLoudly:
    """判断を得られなかったことが、判断の結果に化けないことを保証する。"""

    def test_a_failing_port_leaves_the_written_name(self) -> None:
        """ポートが失敗したら置き換えず、従来の失敗経路へ落ちる。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(raises=True)
        )

        assert resolution.value == "gather"
        assert resolution.source is ActionNameSource.UNRESOLVED

    def test_a_failing_port_is_distinguishable_from_a_low_score(self) -> None:
        """失敗は「確信が足りなかった」と別の記録になる。

        同じに潰すと、OFF の run と全件 fallback の run が trace で見分けられない。
        """
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(raises=True)
        )

        assert resolution.judgment is not None
        assert resolution.judgment.unavailable_reason is not None
        assert resolution.judgment.chosen is None


class TestSemanticResolverCompatibility:
    """ライブラリへの移行後も採用基準と動的候補を維持し、契約違反を記録する。"""

    def test_an_outside_answer_is_an_explicit_backend_failure(self) -> None:
        """候補にない回答は該当なしと混同せず、判断器の契約違反として残す。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(chosen="fly")
        )
        assert resolution.value == "gather"
        assert resolution.judgment.unavailable_reason == "invalid_response"

    @pytest.mark.parametrize("confidence", [None, 0.7])
    def test_probability_at_threshold_is_accepted(
        self, confidence: float | None
    ) -> None:
        """確率が閾値ちょうどなら、確信度が省略または閾値以上の回答を採用する。"""
        resolution, _ = _rescued(
            "gather",
            _wheat_field(),
            _RecordingPort(probability=0.7, confidence=confidence),
        )
        assert resolution.value == "reap_wheat"
        assert resolution.judgment.accepted is True
        assert resolution.judgment.confidence == confidence

    def test_missing_answer_is_recorded(self) -> None:
        """質問の回答が欠けた場合は ANSWER_MISSING を残し、置き換えない。"""
        class MissingPort(_RecordingPort):
            def judge(self, state, questions):
                return {}

        resolution, _ = _rescued("gather", _wheat_field(), MissingPort())
        assert resolution.value == "gather"
        assert resolution.judgment.unavailable_reason == "ANSWER_MISSING"

    def test_candidates_follow_the_current_target(self) -> None:
        """同じ救済器を再利用しても、前の対象の操作を次の対象へ持ち越さない。"""
        port = _RecordingPort(chosen=NO_MATCH_OPTION)
        rescue = ActionNameRescue(port=port, min_confidence=0.7)
        shore = ToolRuntimeTargetDto(
            label="OBJ3", kind="spot_graph_object", display_name="浜辺",
            available_interactions=("collect_shellfish",),
            interaction_labels=(("collect_shellfish", "貝を集める"),),
        )
        for target in (_wheat_field(), shore):
            rescue.rescue(
                pick_action_name("gather", target), target=target, inner_thought=None
            )
        assert set(next(iter(port.questions[0].values())).options) == {
            "reap_wheat", "water_field", NO_MATCH_OPTION,
        }
        assert set(next(iter(port.questions[1].values())).options) == {
            "collect_shellfish", NO_MATCH_OPTION,
        }

    def test_no_match_keeps_its_evidence(self) -> None:
        """該当なしでも確率・確信度・所要時間・出所を記録する。"""
        resolution, _ = _rescued(
            "gather", _wheat_field(), _RecordingPort(chosen=NO_MATCH_OPTION)
        )
        assert resolution.judgment.chosen is None
        assert resolution.judgment.probability == 0.97
        assert resolution.judgment.confidence == 0.96
        assert resolution.judgment.latency_ms == 120.0
        assert resolution.judgment.source == "jev"

    def test_empty_input_does_not_ask_the_backend(self) -> None:
        """空の行動名は判断材料がないので、例外を投げずに元の失敗経路へ戻す。"""
        resolution, port = _rescued("   ", _wheat_field(), _RecordingPort())
        assert resolution.source is ActionNameSource.UNRESOLVED
        assert resolution.judgment is None
        assert port.questions == []

    def test_an_unlabelled_action_can_still_be_selected(self) -> None:
        """表示ラベルがない候補も操作名を説明として渡し、選択できる。"""
        resolution, port = _rescued(
            "gather", replace(_wheat_field(), interaction_labels=()), _RecordingPort()
        )
        assert resolution.value == "reap_wheat"
        question = next(iter(port.questions[0].values()))
        assert question.options["reap_wheat"] == "reap_wheat"

    def test_a_reserved_option_collision_is_recorded(self) -> None:
        """操作名が該当なしの予約値と衝突したら、通信せず契約違反を記録する。"""
        resolution, port = _rescued(
            "gather",
            replace(
                _wheat_field(),
                available_interactions=(NO_MATCH_OPTION,),
                interaction_labels=(),
            ),
            _RecordingPort(),
        )
        assert resolution.judgment.unavailable_reason == "invalid_response"
        assert port.questions == []

    def test_missing_probability_is_rejected(self) -> None:
        """選択した候補の確率が欠けていれば、確信度が高くても採用しない。"""
        class MissingProbabilityPort(_RecordingPort):
            def judge(self, state, questions):
                return {
                    name: replace(answer, probabilities={})
                    for name, answer in super().judge(state, questions).items()
                }

        resolution, _ = _rescued("gather", _wheat_field(), MissingProbabilityPort())
        assert resolution.value == "gather"
        assert resolution.judgment.chosen == "reap_wheat"
        assert resolution.judgment.accepted is False
        assert resolution.judgment.probability is None
