"""SectionBasedContextFormatStrategy のテスト。

Issue #356 後続 Phase 0: section 並び順を ``stable_to_volatile`` (default) と
``legacy`` の 2 モードに切替可能化。

- ``stable_to_volatile`` (default): objective → memos → inventory → memories
  → recent_events → current_state。prefix cache 安定領域を最大化し、
  「今ここ」を末尾に置いて Lost-in-the-middle 緩和を狙う
- ``legacy``: Issue #227 chore β 時代の旧順序。A/B 検証用に保持
"""

import logging

import pytest

from ai_rpg_world.application.llm.services.context_format_strategy import (
    ENV_PROMPT_SECTION_ORDER,
    SECTION_ORDER_LEGACY,
    SECTION_ORDER_STABLE_TO_VOLATILE,
    SectionBasedContextFormatStrategy,
    build_section_format_strategy_from_env,
    resolve_section_order_from_env,
)


class TestSectionBasedContextFormatStrategyDefault:
    """default = stable_to_volatile order での挙動。"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy()

    def test_default_section_order_stable_volatile(self, strategy):
        """constructor 引数なしなら ``stable_to_volatile`` モード。"""
        assert strategy._section_order == SECTION_ORDER_STABLE_TO_VOLATILE

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
        for other in ["【現在の目的】", "【進行中のメモ】", "【所持・判明した物証】",
                       "【関連する記憶】", "【直近の出来事】"]:
            assert text.index(other) < idx_current_state, (
                f"{other} は【現在地と周囲】より前に出るべき"
            )

    def test_stable_volatile_order(self, strategy):
        """objective → recent_events → inventory → memos → memories → current_state。

        Y_after_pr612 実測で memos (23-43%) も inventory (11-19%) も volatile
        と判明。recent_events は head 安定 (= append-only) なので、静的群の
        直後に置いて head 安定 prefix を最大化し、inventory / memos は
        その下に集約する。
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
            "inv":      text.index("【所持・判明した物証】"),
            "memos":    text.index("【進行中のメモ】"),
            "mem":      text.index("【関連する記憶】"),
            "current":  text.index("【現在地と周囲】"),
        }
        assert idx["obj"] < idx["events"] < idx["inv"] < idx["memos"] < idx["mem"] < idx["current"]

    def test_prediction_feedback_recent_events_memories_rendered(self, strategy):
        """【前回の予測と実際】は直近出来事の直後、関連する記憶の直前に置く (prefix cache 順)。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            relevant_memories_text="記憶",
            prediction_feedback_text="- 予測: 扉が開く\n- 実際: 開かなかった",
        )
        assert "【前回の予測と実際】" in text
        idx_events = text.index("【直近の出来事】")
        idx_feedback = text.index("【前回の予測と実際】")
        idx_mem = text.index("【関連する記憶】")
        assert idx_events < idx_feedback < idx_mem

    def test_pending_predictions_prediction_feedback_neighbor_rendered(self, strategy):
        """U10a (予測誤差統一設計 部品6): 【保留中の予測】は【前回の予測と実際】

        の隣 (直後) に置く (計画書の配置指定)。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            relevant_memories_text="記憶",
            prediction_feedback_text="- 予測: 扉が開く\n- 実際: 開かなかった",
            pending_predictions_text="・夕方に木の下でカイトと会う",
        )
        assert "【保留中の予測】" in text
        idx_feedback = text.index("【前回の予測と実際】")
        idx_pending = text.index("【保留中の予測】")
        idx_mem = text.index("【関連する記憶】")
        assert idx_feedback < idx_pending < idx_mem

    def test_returns_empty_when_pending_predictions_section(self, strategy):
        """再浮上する pending prediction が無ければ (空文字)、【保留中の予測】

        section 自体が出ない (= 導入前と byte 一致)。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            prediction_feedback_text="- 予測: 扉が開く\n- 実際: 開かなかった",
        )
        assert "【保留中の予測】" not in text

    def test_inventory_order(self, strategy):
        """inventory は memories の前。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            inventory_text="- 鍵",
            relevant_memories_text="思い出",
        )
        assert text.index("【所持・判明した物証】") < text.index("【関連する記憶】")

    def test_empty_current_state_placeholder(self, strategy):
        """current_state_text が空なら「（情報なし）」が出る。"""
        text = strategy.format(current_state_text="", recent_events_text="x")
        assert "（情報なし）" in text

    def test_empty_recent_events_nashi(self, strategy):
        """recent_events_text が空なら「（なし）」が出る。"""
        text = strategy.format(current_state_text="a", recent_events_text="")
        assert "（なし）" in text

    def test_learned_text_objective_after_rendered(self, strategy):
        """Phase 1c: 【関連する学び】section が objective より後、memos より前。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            learned_text="- タカシは信頼できる",
            active_memos_text="メモ",
        )
        assert "【関連する学び】" in text
        assert "- タカシは信頼できる" in text
        idx_obj = text.index("【現在の目的】")
        idx_learned = text.index("【関連する学び】")
        idx_memos = text.index("【進行中のメモ】")
        assert idx_obj < idx_learned < idx_memos

    def test_returns_empty_when_learned_text_section(self, strategy):
        """空文字なら section ヘッダも出ない。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            learned_text="",
        )
        assert "【関連する学び】" not in text

    def test_mid_summary_text_learned_after_memos_before_rendered(self, strategy):
        """Phase 2: 【最近の流れ】section が learned 直後 / memos より前。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            learned_text="- 学び",
            mid_summary_text="[最新] 動き",
            active_memos_text="メモ",
        )
        assert "【最近の流れ】" in text
        assert "[最新] 動き" in text
        idx_learned = text.index("【関連する学び】")
        idx_mid = text.index("【最近の流れ】")
        idx_memos = text.index("【進行中のメモ】")
        assert idx_learned < idx_mid < idx_memos

    def test_returns_empty_when_mid_summary_text_section(self, strategy):
        """midsummarytext が空なら section ごと省略。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            mid_summary_text="",
        )
        assert "【最近の流れ】" not in text

    def test_long_summary_text_objective_after_learned_before_rendered(self, strategy):
        """Phase 3: 【自己像と世界観】section が objective 直後 / learned より前。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            long_summary_text="私について: 寡黙な漁師",
            learned_text="- タカシは信頼できる",
            mid_summary_text="[最新] 動き",
        )
        assert "【自己像と世界観】" in text
        assert "私について: 寡黙な漁師" in text
        idx_obj = text.index("【現在の目的】")
        idx_long = text.index("【自己像と世界観】")
        idx_learned = text.index("【関連する学び】")
        idx_mid = text.index("【最近の流れ】")
        assert idx_obj < idx_long < idx_learned < idx_mid

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


class TestSectionBasedContextFormatStrategyLegacyMode:
    """legacy order (Issue #227 chore β 時代の旧順序) の挙動。A/B 検証用。"""

    @pytest.fixture
    def strategy(self):
        return SectionBasedContextFormatStrategy(section_order=SECTION_ORDER_LEGACY)

    def test_legacy_order(self, strategy):
        """legacy モードでは旧来の section 並び順を保つ。"""
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

    def test_legacy_empty_section(self, strategy):
        """空 section の挙動は default と同じ。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
        )
        assert "【現在の目的】" not in text
        assert "【進行中のメモ】" not in text
        assert "【関連する記憶】" not in text
        assert "【所持・判明した物証】" not in text
        assert "【関連する学び】" not in text

    def test_legacy_learned_text_objective_after_rendered(self, strategy):
        """legacy 順序でも§【関連する学び】は objective 直後、current_state より前。"""
        text = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            objective_text="目的",
            learned_text="- タカシは信頼できる",
        )
        idx_obj = text.index("【現在の目的】")
        idx_learned = text.index("【関連する学び】")
        idx_state = text.index("【現在地と周囲】")
        assert idx_obj < idx_learned < idx_state

    def test_legacy_prediction_feedback_recent_events_before(self, strategy):
        """legacy 順序でも予測 feedback は【直近の出来事】の直前。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            active_memos_text="メモ",
            prediction_feedback_text="- 予測: 音がする\n- 実際: 静かだった",
        )
        idx_memos = text.index("【進行中のメモ】")
        idx_feedback = text.index("【前回の予測と実際】")
        idx_events = text.index("【直近の出来事】")
        assert idx_memos < idx_feedback < idx_events

    def test_legacy_pending_predictions_prediction_feedback_neighbor(self, strategy):
        """legacy 順序でも【保留中の予測】は【前回の予測と実際】の隣

        (直後・直近の出来事の直前) に置く。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            prediction_feedback_text="- 予測: 音がする\n- 実際: 静かだった",
            pending_predictions_text="・夕方に木の下でカイトと会う",
        )
        idx_feedback = text.index("【前回の予測と実際】")
        idx_pending = text.index("【保留中の予測】")
        idx_events = text.index("【直近の出来事】")
        assert idx_feedback < idx_pending < idx_events

    def test_returns_empty_when_legacy_pending_predictions(self, strategy):
        """legacy でも pending predictions が空なら省略される。"""
        text = strategy.format(
            current_state_text="現在地",
            recent_events_text="出来事",
            prediction_feedback_text="- 予測: 音がする\n- 実際: 静かだった",
        )
        assert "【保留中の予測】" not in text


class TestSectionBasedContextFormatStrategyValidation:
    """constructor / format の入力検証。"""

    def test_unknown_section_order_value_error(self):
        """section_order に未定義の文字列を渡すと ValueError。"""
        with pytest.raises(ValueError, match="section_order must be one of"):
            SectionBasedContextFormatStrategy(section_order="random")

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

    def test_non_string_learned_text_raises_type_error(self):
        """learned_text が str でないとき TypeError を投げる (Phase 1c)。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="learned_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                learned_text=[],  # type: ignore[arg-type]
            )

    def test_non_string_prediction_feedback_text_raises_type_error(self):
        """prediction_feedback_text が str でないとき TypeError を投げる。"""
        strategy = SectionBasedContextFormatStrategy()
        with pytest.raises(TypeError, match="prediction_feedback_text must be str"):
            strategy.format(
                current_state_text="",
                recent_events_text="",
                prediction_feedback_text=[],  # type: ignore[arg-type]
            )


class TestResolveSectionOrderFromEnv:
    """``PROMPT_SECTION_ORDER`` env var 解決。実験スクリプトの A/B 用。"""

    def test_env_unset_default(self):
        """env を渡さなければ default (stable_to_volatile)。"""
        assert resolve_section_order_from_env(env={}) == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_env_empty_string_default(self):
        """値があっても空文字なら default 扱い。"""
        assert resolve_section_order_from_env(env={ENV_PROMPT_SECTION_ORDER: ""}) == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_env_around_blank_default(self):
        """空白のみも default 扱い (strip)。"""
        assert resolve_section_order_from_env(env={ENV_PROMPT_SECTION_ORDER: "   "}) == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_env_stable_volatile(self):
        """有効値 ``stable_to_volatile`` がそのまま返る。"""
        v = resolve_section_order_from_env(env={ENV_PROMPT_SECTION_ORDER: "stable_to_volatile"})
        assert v == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_env_legacy(self):
        """有効値 ``legacy`` がそのまま返る。"""
        assert resolve_section_order_from_env(env={ENV_PROMPT_SECTION_ORDER: "legacy"}) == SECTION_ORDER_LEGACY

    def test_unknown_raises_value_error(self):
        """typo (``stable_to_volatil`` 等) で silent fallback せず即落とす (PR #434)。

        PR #433 経緯: ``rolling`` のような短縮形が silent fallback で sliding_window
        になり、実験前提を壊した事例があった。同じ silent failure を未然に防ぐ。
        """
        with pytest.raises(ValueError) as exc_info:
            resolve_section_order_from_env(env={ENV_PROMPT_SECTION_ORDER: "stable_to_volatil"})
        msg = str(exc_info.value)
        assert "PROMPT_SECTION_ORDER" in msg
        assert "stable_to_volatil" in msg  # bad value
        # 正しい値リストがメッセージに含まれる
        assert "stable_to_volatile" in msg
        assert "legacy" in msg


class TestBuildSectionFormatStrategyFromEnv:
    """env 由来で strategy を構築するファクトリ。wiring から呼ばれる。"""

    def test_env_unset_default_strategy_rendered(self):
        """env 未設定なら default の strategy が出る。"""
        strategy = build_section_format_strategy_from_env(env={})
        assert isinstance(strategy, SectionBasedContextFormatStrategy)
        assert strategy.section_order == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_env_legacy_config_legacy_strategy_rendered(self):
        """envlegacy を設定すると legacystrategy が出る。"""
        strategy = build_section_format_strategy_from_env(
            env={ENV_PROMPT_SECTION_ORDER: "legacy"}
        )
        assert strategy.section_order == SECTION_ORDER_LEGACY
