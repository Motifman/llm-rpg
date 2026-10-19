"""存在しない tool 名から、意図した tool を意味で選んで提案する (#1413)。

## 文字の類似度では、ほとんど候補が出ない

過去 89 run の ``UNSUPPORTED_TOOL`` 24 件は、typo より発明された名前に寄っていた。
``say`` は ``speak`` の ``channel`` で、``gather`` は ``interact`` に操作名を渡すこと
だった。先頭の単語が共通しないので、文字の類似度では救えない。

## 提案にとどめる

別の tool として実行はしない。引数の写し替えが要り、足りない引数の扱いが難しい。
失敗は失敗のまま返し、「もしかして 'X' ですか?」の中身だけを変える。

## 「該当なし」を必ず入れる

24 件中 10 件は ``inner_thought`` を tool 名として送った崩れで、どの tool にも
当たらないのが正解。入れないと、必ずどれかに寄る。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    offered_tools_from_payload,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_name_rescue import (
    NO_MATCH_OPTION,
    QUESTION_NAME,
    ToolNameRescue,
)

_OFFERED: dict[str, str | None] = {
    "speak": "同じ場所の相手に話しかける。",
    "interact": "対象の物に操作を行う。",
    "wait": None,
}


class _RecordingPort(ITypedJudgmentPort):
    def __init__(
        self,
        *,
        chosen: str = "speak",
        probability: float = 0.93,
        confidence: float | None = 0.9,
        raises: bool = False,
    ) -> None:
        self._chosen = chosen
        self._probability = probability
        self._confidence = confidence
        self._raises = raises
        self.calls: list[tuple[Any, Mapping[str, Question]]] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append((state, questions))
        if self._raises:
            raise TypedJudgmentUnavailableException(
                "timed out", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED"
            )
        return {
            QUESTION_NAME: JudgmentResult(
                value=self._chosen,
                probabilities={self._chosen: self._probability, "wait": 0.01},
                confidence=self._confidence,
                source=JudgmentSource.JEV,
                latency_ms=120.0,
            )
        }

    @property
    def question(self) -> ChoiceQuestion:
        question = self.calls[-1][1][QUESTION_NAME]
        assert isinstance(question, ChoiceQuestion)
        return question

    @property
    def state(self) -> Mapping[str, Any]:
        return self.calls[-1][0]


def _suggest(
    port: ITypedJudgmentPort,
    requested: str = "say",
    *,
    arguments: Mapping[str, Any] | None = None,
    offered: Mapping[str, str | None] = _OFFERED,
):
    rescue = ToolNameRescue(port=port)
    return rescue.suggest(requested, offered=offered, arguments=arguments or {})


_OFFERED_WITH_PICKUP: dict[str, str | None] = {
    "pickup_item": "足元の品を拾う。",
    "speak": "話しかける。",
}


class TestTheJudgmentPicksTheIntendedTool:
    """判断が「該当なし」以外を選べば、確率や確信によらず失敗文の提案を差し替えることを保証する。"""

    def test_say_is_suggested_as_speak(self) -> None:
        """say を呼び、判断が speak を選ぶと、提案は speak で出所は判断になる。"""
        port = _RecordingPort(chosen="speak", probability=0.93, confidence=0.9)

        suggestion = _suggest(port, "say", arguments={"content": "おはよう"})

        assert suggestion.tool == "speak"
        assert suggestion.source == "judgment"
        assert suggestion.judgment is not None
        assert suggestion.judgment.accepted is True

    def test_a_low_probability_choice_replaces_the_similarity_suggestion(self) -> None:
        """類似度なら pickup_item になる pickup でも、判断が確率 0.53・確信 0.3 で speak を選べば提案は speak。"""
        port = _RecordingPort(chosen="speak", probability=0.53, confidence=0.3)

        suggestion = _suggest(port, "pickup", offered=_OFFERED_WITH_PICKUP)

        assert suggestion.tool == "speak"
        assert suggestion.source == "judgment"
        assert suggestion.judgment is not None
        assert suggestion.judgment.accepted is True
        assert suggestion.judgment.fallback_reason is None


class TestTheQuestionOffersOnlyWhatWasSent:
    """選択肢が、送った tool の名前と意味、「該当なし」だけで作られることを保証する。"""

    def test_options_are_the_offered_tools_with_their_meaning_and_no_match(self) -> None:
        """選択肢は送った tool (名前 → 説明の 1 行目) と「該当なし」だけ。"""
        port = _RecordingPort()

        _suggest(port)

        options = dict(port.question.options)
        assert set(options) == {"speak", "interact", "wait", NO_MATCH_OPTION}
        assert options["speak"] == "同じ場所の相手に話しかける。"

    def test_a_tool_without_description_uses_its_name_as_meaning(self) -> None:
        """説明の無い tool は、名前を意味に使う。空の意味は選択肢にしない。"""
        port = _RecordingPort()

        _suggest(port)

        assert port.question.options["wait"] == "wait"


class TestTheStateCarriesWhatTheCallSaid:
    """判断の材料に、呼び出しが示していた意図が入ることを保証する。"""

    def test_state_has_the_name_arguments_and_thought(self) -> None:
        """呼ばれた名前、送られた引数、inner_thought が state に入る。inner_thought は引数から外す。"""
        port = _RecordingPort()

        _suggest(
            port,
            "say",
            arguments={
                "channel": "say",
                "content": "灯りを探そう",
                "inner_thought": "暗い所は一人で入りたくない",
            },
        )

        state = port.state
        assert state["called_tool_name"] == "say"
        assert state["arguments"] == {"channel": "say", "content": "灯りを探そう"}
        assert state["inner_thought"] == "暗い所は一人で入りたくない"

    def test_integer_arguments_are_left_out_of_the_state(self) -> None:
        """整数の引数 (item_id など) は state に入れない。名前の引数は残す (設計原則 1)。"""
        port = _RecordingPort()

        _suggest(
            port,
            "give",
            arguments={"item_id": 42, "target_label": "アオイ", "urgent": True},
        )

        assert port.state["arguments"] == {"target_label": "アオイ", "urgent": True}


class TestItFallsBackToTheSimilaritySuggestion:
    """判断を採らないとき、文字の類似度による今の提案に戻ることを保証する。

    どの場合も、類似度で候補が出る名前 (``pickup`` → ``pickup_item``) を使い、
    戻ったことを提案の中身で確かめる。
    """

    def test_no_match_falls_back_to_similarity(self) -> None:
        """「該当なし」なら類似度の提案に戻し、縮退の理由を no_match と残す。"""
        port = _RecordingPort(chosen=NO_MATCH_OPTION, probability=0.95)

        suggestion = _suggest(port, "pickup", offered=_OFFERED_WITH_PICKUP)

        assert suggestion.tool == "pickup_item"
        assert suggestion.source == "similarity"
        assert suggestion.judgment is not None
        assert suggestion.judgment.chosen is None
        assert suggestion.judgment.fallback_reason == "no_match"

    def test_no_match_without_a_similar_name_suggests_nothing(self) -> None:
        """「該当なし」で類似度の候補も無ければ、提案しない (inner_thought を送った崩れ)。"""
        port = _RecordingPort(chosen=NO_MATCH_OPTION, probability=0.95)

        suggestion = _suggest(port, "inner_thought")

        assert suggestion.tool is None
        assert suggestion.source is None

    def test_an_unavailable_judgment_falls_back_and_says_why(self) -> None:
        """判断ポートが例外を投げたら類似度の提案に戻し、unavailable_reason を残す。"""
        port = _RecordingPort(raises=True)

        suggestion = _suggest(port, "pickup", offered=_OFFERED_WITH_PICKUP)

        assert suggestion.tool == "pickup_item"
        assert suggestion.judgment is not None
        assert suggestion.judgment.unavailable_reason == "TYPED_JUDGMENT_TRANSPORT_FAILED"
        assert suggestion.judgment.fallback_reason == "unavailable"


class TestTheTracePayload:
    """trace に残す値が、判断の読み直しと次のターンとの突き合わせに足りることを保証する。"""

    def test_payload_has_what_the_issue_asks_for(self) -> None:
        """呼ばれた名前、選択肢ごとの確率、確信、提案とその出所、採否、縮退理由を持ち、閾値は持たない。"""
        port = _RecordingPort(chosen="speak", probability=0.93, confidence=0.9)

        payload = _suggest(port, "say").trace_payload()

        assert payload is not None
        assert payload["requested"] == "say"
        assert payload["probabilities"] == {"speak": 0.93, "wait": 0.01}
        assert payload["suggested"] == "speak"
        assert payload["suggestion_source"] == "judgment"
        assert payload["confidence"] == 0.9
        assert "min_confidence" not in payload
        assert payload["accepted"] is True
        assert payload["fallback_reason"] is None
        assert payload["options"] == ["interact", "speak", "wait"]


class _BrokenPort(ITypedJudgmentPort):
    def judge(self, state, questions):  # type: ignore[no-untyped-def,override]
        raise ValueError("probability is not a number")


class TestAnUnexpectedErrorFallsBack:
    """判断ポートの想定外の例外も、判断不能として類似度の提案に戻すことを保証する。"""

    def test_an_unexpected_error_falls_back_and_says_why(self) -> None:
        """判断ポートが ValueError を投げても例外を外へ出さず、UNEXPECTED_ERROR で類似度の提案に戻す。"""
        suggestion = _suggest(
            _BrokenPort(), "pickup",
            offered=_OFFERED_WITH_PICKUP,
        )

        assert suggestion.tool == "pickup_item"
        assert suggestion.judgment is not None
        assert suggestion.judgment.fallback_reason == "unavailable"
        assert suggestion.judgment.unavailable_reason == "UNEXPECTED_ERROR"


class TestTheMeaningIsTheFirstDescriptionLine:
    """送った tool 定義から、選択肢の意味として説明の 1 行目を取り出すことを保証する。"""

    @staticmethod
    def _offered(description: object) -> dict[str, str | None]:
        return offered_tools_from_payload(
            [{"type": "function", "function": {"name": "speak", "description": description}}]
        )

    def test_a_multi_line_description_gives_its_first_line(self) -> None:
        """複数行の説明は 1 行目だけになる。"""
        assert self._offered("話しかける。\nchannel=say は同じ場所に届く") == {"speak": "話しかける。"}

    def test_leading_blank_lines_and_spaces_are_skipped(self) -> None:
        """先頭の空行と前後の空白を除いた最初の行を取る。"""
        assert self._offered("\n\n  話しかける。  \n2 行目") == {"speak": "話しかける。"}

    @pytest.mark.parametrize("description", ["", "   \n  ", None, 3])
    def test_a_missing_description_gives_none(self, description: object) -> None:
        """説明が空・空白だけ・無い・文字列でないときは None (名前で代用する側に任せる)。"""
        assert self._offered(description) == {"speak": None}
