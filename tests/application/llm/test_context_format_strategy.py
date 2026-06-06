"""SectionBasedContextFormatStrategy のテスト。

Issue #356 後続 Phase 0: section 並び順を ``stable_to_volatile`` (default) と
``legacy`` の 2 モードに切替可能化。

- ``stable_to_volatile`` (default): objective → memos → inventory → memories
  → recent_events → current_state。prefix cache 安定領域を最大化し、
  「今ここ」を末尾に置いて Lost-in-the-middle 緩和を狙う
- ``legacy``: Issue #227 chore β 時代の旧順序。A/B 検証用に保持
"""

import pytest

from ai_rpg_world.application.llm.services.context_format_strategy import (
    SECTION_ORDER_LEGACY,
    SECTION_ORDER_STABLE_TO_VOLATILE,
    SectionBasedContextFormatStrategy,
)


class TestSectionBasedContextFormatStrategyDefault:
    """default = stable_to_volatile order での挙動。"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy()

    def test_default_section_order_は_stable_to_volatile(self, strategy):
        """constructor 引数なしなら ``stable_to_volatile`` モード。"""
        assert strategy._section_order == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_必須セクションが常に出力される(self, strategy):
        """current_state と recent_events は空でも placeholder で必ず出る。"""
        text = strategy.format(
            current_state_text="現在地: 広場",
            recent_events_text="- イベント1",
        )
        assert "【現在地と周囲】" in text
        assert "【直近の出来事】" in text
        assert "現在地: 広場" in text
        assert "- イベント1" in text

    def test_空のオプション_section_は省略される(self, strategy):
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

    def test_objective_は最も先頭で出る(self, strategy):
        """【現在の目的】は全 section の中で最先頭。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="脱出すること",
        )
        assert "【現在の目的】" in text
        assert text.index("【現在の目的】") < text.index("【現在地と周囲】")

    def test_current_state_は最末尾で出る(self, strategy):
        """【現在地と周囲】は全 section の中で最末尾 (Phase 0 の核)。

        prefix cache 安定領域を最大化し、Lost-in-the-middle 緩和も狙う。
        """
        text = strategy.format(
            current_state_text="現在地: x",
            recent_events_text="- 出来事",
            relevant_memories_text="記憶a",
            active_memos_text="メモb",
            objective_text="目的c",
            inventory_text="物証d",
        )
        idx_current_state = text.index("【現在地と周囲】")
        for other in ["【現在の目的】", "【進行中のメモ】", "【所持・判明した物証】",
                       "【関連する記憶】", "【直近の出来事】"]:
            assert text.index(other) < idx_current_state, (
                f"{other} は【現在地と周囲】より前に出るべき"
            )

    def test_stable_to_volatile_順序が正しい(self, strategy):
        """objective → memos → inventory → memories → recent_events → current_state。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            relevant_memories_text="記憶",
            active_memos_text="メモ",
            objective_text="目的",
            inventory_text="物証",
        )
        idx = {
            "obj":      text.index("【現在の目的】"),
            "memos":    text.index("【進行中のメモ】"),
            "inv":      text.index("【所持・判明した物証】"),
            "mem":      text.index("【関連する記憶】"),
            "events":   text.index("【直近の出来事】"),
            "current":  text.index("【現在地と周囲】"),
        }
        assert idx["obj"] < idx["memos"] < idx["inv"] < idx["mem"] < idx["events"] < idx["current"]

    def test_inventory_セクションが出ても順序が崩れない(self, strategy):
        """inventory は memories の前。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            inventory_text="- 鍵",
            relevant_memories_text="思い出",
        )
        assert text.index("【所持・判明した物証】") < text.index("【関連する記憶】")

    def test_空_current_state_は_placeholder(self, strategy):
        """current_state_text が空なら「（情報なし）」が出る。"""
        text = strategy.format(current_state_text="", recent_events_text="x")
        assert "（情報なし）" in text

    def test_空_recent_events_は_nashi(self, strategy):
        """recent_events_text が空なら「（なし）」が出る。"""
        text = strategy.format(current_state_text="a", recent_events_text="")
        assert "（なし）" in text


class TestSectionBasedContextFormatStrategyLegacyMode:
    """legacy order (Issue #227 chore β 時代の旧順序) の挙動。A/B 検証用。"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy(section_order=SECTION_ORDER_LEGACY)

    def test_legacy_順序が正しい(self, strategy):
        """objective → current_state → memos → recent_events → memories → inventory。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            relevant_memories_text="記憶",
            active_memos_text="メモ",
            objective_text="目的",
            inventory_text="物証",
        )
        idx = {
            "obj":      text.index("【現在の目的】"),
            "current":  text.index("【現在地と周囲】"),
            "memos":    text.index("【進行中のメモ】"),
            "events":   text.index("【直近の出来事】"),
            "mem":      text.index("【関連する記憶】"),
            "inv":      text.index("【所持・判明した物証】"),
        }
        assert idx["obj"] < idx["current"] < idx["memos"] < idx["events"] < idx["mem"] < idx["inv"]

    def test_legacy_でも空セクションは省略される(self, strategy):
        """空 section の挙動は default と同じ。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
        )
        assert "【現在の目的】" not in text
        assert "【進行中のメモ】" not in text
        assert "【関連する記憶】" not in text
        assert "【所持・判明した物証】" not in text


class TestSectionBasedContextFormatStrategyValidation:
    """constructor / format の入力検証。"""

    def test_未知の_section_order_は_value_error(self):
        """section_order に未定義の文字列を渡すと ValueError。"""
        with pytest.raises(ValueError, match="section_order must be one of"):
            SectionBasedContextFormatStrategy(section_order="random")

    def test_current_state_text_が_str_でなければ_type_error(self):
        """current_state_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="current_state_text must be str"):
            strategy.format(
                current_state_text=123,  # type: ignore[arg-type]
                recent_events_text="",
            )

    def test_recent_events_text_が_str_でなければ_type_error(self):
        """recent_events_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="recent_events_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text=None,  # type: ignore[arg-type]
            )

    def test_relevant_memories_text_が_str_でなければ_type_error(self):
        """relevant_memories_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="relevant_memories_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                relevant_memories_text=[],  # type: ignore[arg-type]
            )

    def test_objective_text_が_str_でなければ_type_error(self):
        """objective_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="objective_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                objective_text=123,  # type: ignore[arg-type]
            )

    def test_inventory_text_が_str_でなければ_type_error(self):
        """inventory_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="inventory_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                inventory_text=None,  # type: ignore[arg-type]
            )
