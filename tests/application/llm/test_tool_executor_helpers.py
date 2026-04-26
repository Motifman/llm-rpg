"""tool_executor_helpers のテスト。"""

from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    append_inner_thought_to_message,
)


def test_append_inner_thought_appends_when_present() -> None:
    out = append_inner_thought_to_message("操作した。", {"inner_thought": " 胸騒ぎがした。  "})
    assert "操作した。" in out
    assert "【心の声】" in out
    assert "胸騒ぎがした。" in out


def test_append_inner_thought_unchanged_when_empty() -> None:
    assert append_inner_thought_to_message("同上", {}) == "同上"
    assert append_inner_thought_to_message("同上", {"inner_thought": "   "}) == "同上"
