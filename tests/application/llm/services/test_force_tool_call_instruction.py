"""案A: 熟考ターン (tool_choice=auto) 用の「必ずツールを呼べ」指示追加を固定する。

DeepSeek は thinking + tool_choice=required を 400 で拒否するため、熟考ターンは
auto にして代わりに末尾で強制指示する。追加は末尾のみ (prefix cache を保つ) で、
元の messages は変更しない (不変)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.force_tool_call_instruction import (
    FORCE_TOOL_CALL_INSTRUCTION,
    append_force_tool_call_instruction,
)


class TestAppendForceToolCallInstruction:
    def test_末尾メッセージの本文に指示を足した新リストを返す(self) -> None:
        """最後のメッセージ本文の末尾に指示が付き、元リスト・元 dict は変更されない。"""
        messages = [
            {"role": "system", "content": "あなたは冒険者だ。"},
            {"role": "user", "content": "目の前に貝がある。"},
        ]
        result = append_force_tool_call_instruction(messages)

        # 新リストが返る (別オブジェクト)
        assert result is not messages
        # 先頭 (system) は不変 = prefix cache を壊さない
        assert result[0] == {"role": "system", "content": "あなたは冒険者だ。"}
        # 末尾本文に指示が付く
        assert result[-1]["content"].startswith("目の前に貝がある。")
        assert FORCE_TOOL_CALL_INSTRUCTION in result[-1]["content"]
        # 元は不変
        assert messages[-1]["content"] == "目の前に貝がある。"

    def test_空リストなら指示メッセージ1件だけ返す(self) -> None:
        result = append_force_tool_call_instruction([])
        assert len(result) == 1
        assert result[0]["content"] == FORCE_TOOL_CALL_INSTRUCTION

    def test_本文がstrでないときは末尾に指示メッセージを足す(self) -> None:
        """content が str でない (structured 等) 稀なケースでは末尾に別メッセージを足す。"""
        messages = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
        result = append_force_tool_call_instruction(messages)
        assert len(result) == 2
        assert result[-1]["content"] == FORCE_TOOL_CALL_INSTRUCTION
        # 元メッセージは不変
        assert messages[0]["content"] == [{"type": "text", "text": "x"}]
