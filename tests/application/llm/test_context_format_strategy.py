"""SectionBasedContextFormatStrategy のテスト。

Issue #356 後続 Phase 0: section の並びは objective → L5 → L4 → recent_events →
learned → memories → memos → current_state。更新頻度の高い想起群を出来事の
後ろへ置き、「今ここ」を末尾に置く。
"""

import logging

import pytest

from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)


class TestSectionBasedContextFormatStrategyDefault:
    """section の並びと、空の section の扱い。"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy()

    def test_documented_behavior(self, strategy):
        """current_state と recent_events は空でも placeholder で必ず出る。"""
        text = strategy.format(
            current_state_text="現在地: 広場",
            recent_events_text="- イベント1",
        )
        assert "【現在地と周囲】" in text
        assert "【直近の出来事】" in text
        assert "現在地: 広場" in text
        assert "- イベント1" in text

    def test_empty_section(self, strategy):
        """memo / 記憶 / 目的 / 物証 は空なら section ごと省略される。

        Issue #526 後続: 「受動想起では何も浮かばなかった」の sentinel text 注入は
        prompt_builder._run_passive_recall 側の責務。formatter は受け取った
        relevant_memories_text を信じて、空なら従来通り section を省略する。"""
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

    def test_objective_first_rendered(self, strategy):
        """【現在の目的】は全 section の中で最先頭。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="脱出すること",
        )
        assert "【現在の目的】" in text
        assert text.index("【現在の目的】") < text.index("【現在地と周囲】")

    def test_current_state_last_rendered(self, strategy):
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
        for other in ["【現在の目的】", "【進行中のメモ】",
                       "【関連する記憶】", "【直近の出来事】"]:
            assert text.index(other) < idx_current_state, (
                f"{other} は【現在地と周囲】より前に出るべき"
            )

    def test_stable_volatile_order(self, strategy):
        """objective → recent_events → memories → memos → current_state。

        recent_events は head 安定 (= append-only) なので静的群の直後に置く。
        所持品は current_state に一本化され、この独立sectionには出さない。
        """
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
            "events":   text.index("【直近の出来事】"),
            "memos":    text.index("【進行中のメモ】"),
            "mem":      text.index("【関連する記憶】"),
            "current":  text.index("【現在地と周囲】"),
        }
        assert "【所持・判明した物証】" not in text
        assert idx["obj"] < idx["events"] < idx["mem"] < idx["memos"] < idx["current"]

    def test_duplicate_inventory_section_is_omitted(self, strategy):
        """旧 inventory section は省略し、現在地と周囲にある所持品だけを残す。"""
        text = strategy.format(
            current_state_text='所持アイテム:\n  - "鍵" x2 (道具)',
            recent_events_text="y",
            inventory_text="- 鍵\n- 鍵",
            relevant_memories_text="思い出",
        )
        assert "【所持・判明した物証】" not in text
        assert '  - "鍵" x2 (道具)' in text
        assert "- 鍵\n- 鍵" not in text

    def test_empty_current_state_placeholder(self, strategy):
        """current_state_text が空なら「（情報なし）」が出る。"""
        text = strategy.format(current_state_text="", recent_events_text="x")
        assert "（情報なし）" in text

    def test_empty_recent_events_nashi(self, strategy):
        """recent_events_text が空なら「（なし）」が出る。"""
        text = strategy.format(current_state_text="a", recent_events_text="")
        assert "（なし）" in text

    def test_mid_summary_precedes_recent_events(self, strategy):
        """【最近の流れ】は直近の出来事より前に置かれる。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            mid_summary_text="[最新] 動き",
            active_memos_text="メモ",
        )
        assert "【最近の流れ】" in text
        assert "[最新] 動き" in text
        idx_mid = text.index("【最近の流れ】")
        idx_events = text.index("【直近の出来事】")
        assert idx_mid < idx_events

    def test_returns_empty_when_mid_summary_text_section(self, strategy):
        """midsummarytext が空なら section ごと省略。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            mid_summary_text="",
        )
        assert "【最近の流れ】" not in text

    def test_long_summary_text_precedes_mid_summary(self, strategy):
        """【自己像と世界観】は目的の後、最近の流れより前に置かれる。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            long_summary_text="私について: 寡黙な漁師",
            mid_summary_text="[最新] 動き",
        )
        assert "【自己像と世界観】" in text
        assert "私について: 寡黙な漁師" in text
        idx_obj = text.index("【現在の目的】")
        idx_long = text.index("【自己像と世界観】")
        idx_mid = text.index("【最近の流れ】")
        idx_events = text.index("【直近の出来事】")
        assert idx_obj < idx_long < idx_mid < idx_events

    def test_known_people_follow_objective_and_precede_self_image(self, strategy):
        """【知っている人】は【現在の目的】の直後、【自己像と世界観】より前に置く。新しい人を知ったときだけ、この節から後ろが変わる。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            known_people_text="- ノア（あなたと同じ側）\n- カイ",
            long_summary_text="私について",
        )
        assert "【知っている人】\n- ノア（あなたと同じ側）\n- カイ\n" in text
        assert text.index("【現在の目的】") < text.index("【知っている人】") < text.index("【自己像と世界観】")

    def test_known_people_section_is_omitted_when_empty(self, strategy):
        """known_people_text が空なら【知っている人】の節ごと省略する。"""
        text = strategy.format(current_state_text="x", recent_events_text="y", known_people_text="")
        assert "【知っている人】" not in text

    def test_returns_empty_when_long_summary_text_section(self, strategy):
        """longsummarytext が空なら section ごと省略。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            long_summary_text="",
        )
        assert "【自己像と世界観】" not in text

    def test_non_string_long_summary_text_raises_type_error(self, strategy):
        """long summary text が str でなければ type error。"""
        with pytest.raises(TypeError, match="long_summary_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                long_summary_text=[],  # type: ignore[arg-type]
            )

    def test_non_string_mid_summary_text_raises_type_error(self, strategy):
        """mid summary text が str でなければ type error。"""
        with pytest.raises(TypeError, match="mid_summary_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                mid_summary_text=[],  # type: ignore[arg-type]
            )


class TestSectionBasedContextFormatStrategyValidation:
    """constructor / format の入力検証。"""

    def test_non_string_current_state_text_raises_type_error(self):
        """current_state_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="current_state_text must be str"):
            strategy.format(
                current_state_text=123,  # type: ignore[arg-type]
                recent_events_text="",
            )

    def test_non_string_recent_events_text_raises_type_error(self):
        """recent_events_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="recent_events_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text=None,  # type: ignore[arg-type]
            )

    def test_non_string_relevant_memories_text_raises_type_error(self):
        """relevant_memories_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="relevant_memories_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                relevant_memories_text=[],  # type: ignore[arg-type]
            )

    def test_non_string_objective_text_raises_type_error(self):
        """objective_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="objective_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                objective_text=123,  # type: ignore[arg-type]
            )

    def test_non_string_inventory_text_raises_type_error(self):
        """inventory_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="inventory_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                inventory_text=None,  # type: ignore[arg-type]
            )
