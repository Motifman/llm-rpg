"""SectionBasedContextFormatStrategy のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)


class TestSectionBasedContextFormatStrategy:
    """SectionBasedContextFormatStrategy（案A）の正常・例外ケース"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy()

    def test_format_includes_all_sections(self, strategy):
        """現在の状況・直近の出来事・関連する記憶の3セクションが含まれる"""
        text = strategy.format(
            current_state_text="現在地: 広場",
            recent_events_text="- イベント1",
            relevant_memories_text="記憶なし",
        )
        assert "## 現在の状況" in text
        assert "## 直近の出来事（新しい順）" in text
        assert "## 関連する記憶" in text
        assert "現在地: 広場" in text
        assert "- イベント1" in text
        assert "記憶なし" in text

    def test_format_empty_current_state_uses_placeholder(self, strategy):
        """現在状態が空のとき（情報なし）と表示"""
        text = strategy.format(
            current_state_text="",
            recent_events_text="x",
            relevant_memories_text="",
        )
        assert "（情報なし）" in text

    def test_format_empty_recent_events_uses_nashi(self, strategy):
        """直近の出来事が空のとき（なし）と表示"""
        text = strategy.format(
            current_state_text="a",
            recent_events_text="",
            relevant_memories_text="",
        )
        assert "（なし）" in text

    def test_current_state_text_not_str_raises_type_error(self, strategy):
        """current_state_text が str でないとき TypeError"""
        with pytest.raises(TypeError, match="current_state_text must be str"):
            strategy.format(
                current_state_text=123,  # type: ignore[arg-type]
                recent_events_text="",
                relevant_memories_text="",
            )

    def test_recent_events_text_not_str_raises_type_error(self, strategy):
        """recent_events_text が str でないとき TypeError"""
        with pytest.raises(TypeError, match="recent_events_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text=None,  # type: ignore[arg-type]
                relevant_memories_text="",
            )

    def test_relevant_memories_text_not_str_raises_type_error(self, strategy):
        """relevant_memories_text が str でないとき TypeError"""
        with pytest.raises(TypeError, match="relevant_memories_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                relevant_memories_text=[],  # type: ignore[arg-type]
            )
