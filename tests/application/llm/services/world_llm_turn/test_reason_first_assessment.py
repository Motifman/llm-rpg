"""reason-first の状況評価 (assess_situation) を読み、行動段階の文面に足す挙動の試験。"""

from ai_rpg_world.application.llm.services.world_llm_turn.phase_a import (
    append_reason_first_assessment,
    parse_assessment_tool_call,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_ASSESS_SITUATION


class TestParseAssessmentToolCall:
    """assess_situation の呼び出しから、評価として使う欄だけを取り出すことを保証する。"""

    def test_reads_only_inner_thought_even_if_expected_result_is_passed(self) -> None:
        """#1631 で消した expected_result を LLM が渡しても、評価は inner_thought だけになる。"""
        tool_call = {
            "name": TOOL_NAME_ASSESS_SITUATION,
            "arguments": {"inner_thought": " 周囲を見直す。 ", "expected_result": "出口が見つかる"},
        }

        assessment, reason = parse_assessment_tool_call(tool_call)

        assert assessment == {"inner_thought": "周囲を見直す。"}
        assert reason == ""

    def test_missing_inner_thought_is_rejected(self) -> None:
        """inner_thought が空なら評価は無く、理由 missing_inner_thought を返す。"""
        tool_call = {"name": TOOL_NAME_ASSESS_SITUATION, "arguments": {"inner_thought": "  "}}

        assert parse_assessment_tool_call(tool_call) == (None, "missing_inner_thought")


class TestAppendReasonFirstAssessment:
    """行動段階の user 文面に足す【行動前の状況評価】の中身を保証する。"""

    def test_appends_thought_and_instruction_without_expected_line(self) -> None:
        """評価に expected_result が混ざっていても、考えと行動の指示だけを足し、「期待する結果」の行は出さない。"""
        messages = [{"role": "user", "content": "状況"}]

        out = append_reason_first_assessment(
            messages, {"inner_thought": "周囲を見直す。", "expected_result": "出口が見つかる"}
        )

        content = out[-1]["content"]
        assert "【行動前の状況評価】\n- 考え: 周囲を見直す。" in content
        assert "期待する結果" not in content
        assert messages == [{"role": "user", "content": "状況"}]
