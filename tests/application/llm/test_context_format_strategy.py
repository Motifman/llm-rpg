"""SectionBasedContextFormatStrategy のテスト。

Issue #227 chore β で section format を ``## ...`` から ``【...】`` に変更し、
objective_text / inventory_text を新規 section として追加。
"""

import pytest

from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)


class TestSectionBasedContextFormatStrategy:
    """``【...】`` 見出し形式での組み立て (escape_game format)。"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy()

    def test_format_renders_minimum_required_sections(self, strategy):
        """current_state と recent_events は常に出力される (空でも placeholder)。"""
        text = strategy.format(
            current_state_text="現在地: 広場",
            recent_events_text="- イベント1",
        )
        assert "【現在地と周囲】" in text
        assert "【直近の出来事】" in text
        assert "現在地: 広場" in text
        assert "- イベント1" in text

    def test_format_omits_optional_sections_when_empty(self, strategy):
        """memo / 記憶 / 目的 / 物証 は空なら section ごと省略される。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            relevant_memories_text="",
            active_memos_text="",
            objective_text="",
            inventory_text="",
        )
        assert "【進行中のメモ】" not in text
        assert "【関連する記憶】" not in text
        assert "【現在の目的】" not in text
        assert "【所持・判明した物証】" not in text

    def test_format_includes_objective_when_provided(self, strategy):
        """objective_text を渡すと【現在の目的】section が先頭に来る。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="脱出すること",
        )
        assert "【現在の目的】" in text
        assert "脱出すること" in text
        # 目的が先頭、その後に現在地
        idx_obj = text.index("【現在の目的】")
        idx_state = text.index("【現在地と周囲】")
        assert idx_obj < idx_state

    def test_format_includes_inventory_when_provided(self, strategy):
        """inventory_text を渡すと【所持・判明した物証】section が末尾に出る。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            inventory_text="- 鍵",
        )
        assert "【所持・判明した物証】" in text
        assert "- 鍵" in text

    def test_format_includes_relevant_memories_when_provided(self, strategy):
        """relevant_memories_text 非空時のみ【関連する記憶】section が出る。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            relevant_memories_text="過去に似た状況...",
        )
        assert "【関連する記憶】" in text
        assert "過去に似た状況..." in text

    def test_format_includes_active_memos_when_provided(self, strategy):
        """active_memos_text 非空時のみ【進行中のメモ】section が現在地直後に出る。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            active_memos_text="- [m1] テスト",
        )
        assert "【進行中のメモ】" in text
        idx_state = text.index("【現在地と周囲】")
        idx_memo = text.index("【進行中のメモ】")
        idx_events = text.index("【直近の出来事】")
        assert idx_state < idx_memo < idx_events

    def test_format_empty_current_state_uses_placeholder(self, strategy):
        """current_state_text が空なら「（情報なし）」が出る。"""
        text = strategy.format(
            current_state_text="",
            recent_events_text="x",
        )
        assert "（情報なし）" in text

    def test_format_empty_recent_events_uses_nashi(self, strategy):
        """recent_events_text が空なら「（なし）」が出る。"""
        text = strategy.format(
            current_state_text="a",
            recent_events_text="",
        )
        assert "（なし）" in text

    def test_current_state_text_not_str_raises_type_error(self, strategy):
        """current_state_text が str でないとき TypeError を投げる。"""
        with pytest.raises(TypeError, match="current_state_text must be str"):
            strategy.format(
                current_state_text=123,  # type: ignore[arg-type]
                recent_events_text="",
            )

    def test_recent_events_text_not_str_raises_type_error(self, strategy):
        """recent_events_text が str でないとき TypeError を投げる。"""
        with pytest.raises(TypeError, match="recent_events_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text=None,  # type: ignore[arg-type]
            )

    def test_relevant_memories_text_not_str_raises_type_error(self, strategy):
        """relevant_memories_text が str でないとき TypeError を投げる。"""
        with pytest.raises(TypeError, match="relevant_memories_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                relevant_memories_text=[],  # type: ignore[arg-type]
            )

    def test_objective_text_not_str_raises_type_error(self, strategy):
        """objective_text が str でないとき TypeError を投げる。"""
        with pytest.raises(TypeError, match="objective_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                objective_text=123,  # type: ignore[arg-type]
            )

    def test_inventory_text_not_str_raises_type_error(self, strategy):
        """inventory_text が str でないとき TypeError を投げる。"""
        with pytest.raises(TypeError, match="inventory_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                inventory_text=None,  # type: ignore[arg-type]
            )
