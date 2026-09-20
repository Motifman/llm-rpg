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

from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

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
        confidence: Optional[float] = 0.96,
        raises: bool = False,
    ) -> None:
        self.states: List[Any] = []
        self.questions: List[Mapping[str, Question]] = []
        self._chosen = chosen
        self._probability = probability
        self._confidence = confidence
        self._raises = raises

    def judge(
        self,
        state: Union[str, Mapping[str, Any], Sequence[Any]],
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
) -> Tuple[Any, _RecordingPort]:
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
