"""``wiring/feature_flags.py`` の env-driven knob 解決テスト。

Phase 1a 配線: ``EPISODIC_EXPLORE_RELATED_ENABLED`` を env-driven にした。
default OFF とすることで、エピソード記憶 (生成 / passive recall) の検証中に
能動探索 tool を expose せず、検証変数の交絡を避ける。

詳細: ``docs/memory_system/semantic_memory_activation_plan.md`` §9。
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.llm.wiring.feature_flags import (
    DEFAULT_SEMANTIC_PASSIVE_TOP_K,
    ENV_BELIEF_ATTRIBUTION_ENABLED,
    ENV_BELIEF_EVIDENCE_ENABLED,
    ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED,
    ENV_EPISODIC_EXPLORE_RELATED_ENABLED,
    ENV_MEMO_DISTILL_ENABLED,
    ENV_PREDICTION_CONTEXT_ID_ENABLED,
    ENV_RECALL_HIT_BOOST_ENABLED,
    ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED,
    ENV_SEMANTIC_PASSIVE_TOP_K,
    ENV_SEMANTIC_SEARCH_ENABLED,
    ENV_SHORT_TERM_MEMORY_KIND,
    ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE,
    ENV_STATE_COLLAPSE_EVIDENCE_ENABLED,
    ENV_UNCONSCIOUS_CONTEXT_ENABLED,
    SCHEDULER_MODE_INLINE,
    SCHEDULER_MODE_THREAD_POOL,
    SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
    SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW,
    log_belief_attribution_enabled_state,
    log_belief_evidence_enabled_state,
    log_error_driven_reinterpretation_enabled_state,
    log_episodic_explore_related_state,
    log_memo_distill_enabled_state,
    log_prediction_context_id_state,
    log_semantic_passive_top_k_state,
    log_semantic_search_state,
    log_short_term_memory_kind_state,
    log_short_term_memory_scheduler_mode_state,
    log_recall_hit_boost_enabled_state,
    log_state_collapse_evidence_enabled_state,
    log_unconscious_context_enabled_state,
    resolve_belief_attribution_enabled,
    resolve_belief_evidence_enabled,
    resolve_error_driven_reinterpretation_enabled,
    resolve_episodic_explore_related_enabled,
    resolve_memo_distill_enabled,
    resolve_prediction_context_id_enabled,
    resolve_recall_hit_boost_enabled,
    resolve_salience_structured_failure_enabled,
    resolve_semantic_passive_top_k,
    resolve_semantic_search_enabled,
    resolve_short_term_memory_kind,
    resolve_short_term_memory_scheduler_mode,
    resolve_state_collapse_evidence_enabled,
    resolve_unconscious_context_enabled,
)


class TestResolveEpisodicExploreRelatedEnabled:
    """``EPISODIC_EXPLORE_RELATED_ENABLED`` の env パース。"""

    def test_env_unset_default_off_9(self) -> None:
        """env 未設定なら OFF (検証中の default 不活性方針)。"""
        assert resolve_episodic_explore_related_enabled(env={}) is False

    def test_env_empty_string_default_off_2(self) -> None:
        """空文字は未設定扱い → default OFF。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: ""}
        ) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "TRUE", "yes", "YES", "on", "On"])
    def test_truthy_value_9(self, raw: str) -> None:
        """truthy リテラル ("1", "true", "yes", "on") は case-insensitive で ON。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "FALSE", "Off"])
    def test_falsy_off(self, raw: str) -> None:
        """明示的に falsy ("0" / "false" / "no" / "off") を渡したら OFF。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
        ) is False

    @pytest.mark.parametrize("raw", ["random", "2", "yeah", "tru", "enable"])
    def test_unknown_raises_value_error_13(self, raw: str) -> None:
        """truthy / falsy のどちらでもない値で silent fallback せず fail-fast (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_episodic_explore_related_enabled(
                env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
            )
        msg = str(exc_info.value)
        assert ENV_EPISODIC_EXPLORE_RELATED_ENABLED in msg
        assert raw in msg

    def test_around_blank_strip(self) -> None:
        """env var の値に空白混入があっても解釈できる。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: "  1  "}
        ) is True


class TestLogEpisodicExploreRelatedState:
    """解決状態を INFO ログ 1 件で残す (run 再現性確保用)。"""

    def test_off_one_rendered(self, caplog: pytest.LogCaptureFixture) -> None:
        """ENABLED / DISABLED の 2 ケースで INFO log が出る。"""
        with caplog.at_level(logging.INFO, logger="ai_rpg_world.application.llm.wiring.feature_flags"):
            log_episodic_explore_related_state(True)
            log_episodic_explore_related_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveSemanticPassiveTopK:
    """``SEMANTIC_PASSIVE_TOP_K`` env パース (Phase 1c)。"""

    def test_default_zero(self) -> None:
        """default は 0 (= prompt §learned 非表示)。検証中の安定設定。"""
        assert DEFAULT_SEMANTIC_PASSIVE_TOP_K == 0
        assert resolve_semantic_passive_top_k(env={}) == 0

    def test_env_unset_default_zero(self) -> None:
        """env 未設定なら default 0。"""
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: ""}
        ) == 0

    def test_value(self) -> None:
        """有効な正整数なら その値。"""
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "3"}
        ) == 3
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "  5  "}
        ) == 5

    def test_returns_zero_0(self) -> None:
        """明示的に 0 を渡しても受理。"""
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "0"}
        ) == 0

    def test_case_raises_value_error_2(self) -> None:
        """typo / 非整数で silent fallback すると実験前提を壊すので fail-fast (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_semantic_passive_top_k(
                env={ENV_SEMANTIC_PASSIVE_TOP_K: "abc"}
            )
        assert "SEMANTIC_PASSIVE_TOP_K" in str(exc_info.value)
        assert "non-integer" in str(exc_info.value)

    def test_case_raises_value_error(self) -> None:
        """負の値を渡すのは意図がないと考え、fail-fast (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_semantic_passive_top_k(
                env={ENV_SEMANTIC_PASSIVE_TOP_K: "-3"}
            )
        assert "SEMANTIC_PASSIVE_TOP_K" in str(exc_info.value)
        assert ">= 0" in str(exc_info.value)


class TestLogSemanticPassiveTopKState:
    """解決結果を INFO ログ 1 件で残す。"""

    def test_top_k_value_log_rendered(self, caplog: pytest.LogCaptureFixture) -> None:
        """topk の値が log に出る。"""
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_semantic_passive_top_k_state(3)
            log_semantic_passive_top_k_state(0)
        assert any("3" in rec.message for rec in caplog.records)
        assert any("0" in rec.message for rec in caplog.records)


class TestResolveSemanticSearchEnabled:
    """``SEMANTIC_SEARCH_ENABLED`` env パース (Phase 1d)。"""

    def test_default_off_2(self) -> None:
        """default は OFF。"""
        assert resolve_semantic_search_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "ON", "True"])
    def test_truthy_2(self, raw: str) -> None:
        """truthy は ON。"""
        assert resolve_semantic_search_enabled(
            env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", ""])
    def test_falsy_empty_string_off_2(self, raw: str) -> None:
        """明示的 falsy / 空文字は OFF。空文字は「未設定」扱いで default を返す。"""
        assert resolve_semantic_search_enabled(
            env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
        ) is False

    @pytest.mark.parametrize("raw", ["random", "yeah", "tru", "2"])
    def test_unknown_raises_value_error_12(self, raw: str) -> None:
        """typo / 未知の値で silent fallback せず fail-fast (PR #434)。"""
        with pytest.raises(ValueError):
            resolve_semantic_search_enabled(
                env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
            )


class TestLogSemanticSearchState:
    """解決結果を INFO ログ 1 件で残す (Phase 1d)。"""

    def test_enabled_disabled_log_rendered_2(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ENABLED でも DISABLED でも log に出る。"""
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_semantic_search_state(True)
            log_semantic_search_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolvePredictionContextIdEnabled:
    """``PREDICTION_CONTEXT_ID_ENABLED`` env パース (予測誤差統一設計 U1)。"""

    def test_default_off(self) -> None:
        """default は OFF。"""
        assert resolve_prediction_context_id_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "ON", "True"])
    def test_truthy(self, raw: str) -> None:
        """truthy は ON。"""
        assert resolve_prediction_context_id_enabled(
            env={ENV_PREDICTION_CONTEXT_ID_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", ""])
    def test_falsy_empty_string_off(self, raw: str) -> None:
        """falsy リテラルまたは空文字は OFF。"""
        assert resolve_prediction_context_id_enabled(
            env={ENV_PREDICTION_CONTEXT_ID_ENABLED: raw}
        ) is False

    @pytest.mark.parametrize("raw", ["random", "yeah", "tru", "2"])
    def test_unknown_raises_value_error_11(self, raw: str) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_prediction_context_id_enabled(
                env={ENV_PREDICTION_CONTEXT_ID_ENABLED: raw}
            )


class TestLogPredictionContextIdState:
    """解決結果を INFO ログ 1 件で残す (予測誤差統一設計 U1)。"""

    def test_enabled_disabled_log_rendered(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ENABLED でも DISABLED でも log に出る。"""
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_prediction_context_id_state(True)
            log_prediction_context_id_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveShortTermMemoryKind:
    """``SHORT_TERM_MEMORY_KIND`` env 解決 (Phase 2)。"""

    def test_default_sliding_window(self) -> None:
        """default は sliding window。"""
        assert resolve_short_term_memory_kind(env={}) == SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW

    def test_env_empty_string_default_2(self) -> None:
        """env 空文字でも default。"""
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: ""}
        ) == SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW

    def test_sliding_window(self) -> None:
        """有効な sliding window。"""
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: "sliding_window"}
        ) == SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW

    def test_rolling_summary(self) -> None:
        """有効な rolling summary。"""
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: "rolling_summary"}
        ) == SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY

    def test_case_insensitive(self) -> None:
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: "ROLLING_SUMMARY"}
        ) == SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY

    def test_unknown_raises_value_error_10(self) -> None:
        """短縮形 (``rolling``) や typo を渡したら silent fallback せず即落とす。

        PR #433 経緯: ``rolling`` を渡したのに sliding_window で実験が走り、
        実験 24h 分が無駄になりかけた事例。
        """
        with pytest.raises(ValueError) as exc_info:
            resolve_short_term_memory_kind(
                env={ENV_SHORT_TERM_MEMORY_KIND: "rolling"}
            )
        msg = str(exc_info.value)
        assert "SHORT_TERM_MEMORY_KIND" in msg
        assert "rolling" in msg  # bad value
        # 有効値リストがメッセージに含まれる (ユーザーが正しい綴りを発見しやすい)
        assert "rolling_summary" in msg
        assert "sliding_window" in msg


class TestLogShortTermMemoryKindState:
    """解決結果を INFO ログ 1 件で残す (Phase 2)。"""

    def test_log_kind_value_rendered(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """log に kind の値が 出る。"""
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_short_term_memory_kind_state("sliding_window")
            log_short_term_memory_kind_state("rolling_summary")
        messages = [rec.message for rec in caplog.records]
        assert any("sliding_window" in m for m in messages)
        assert any("rolling_summary" in m for m in messages)


class TestResolveShortTermMemorySchedulerMode:
    """``SHORT_TERM_MEMORY_SCHEDULER_MODE`` env 解決 (Phase 2.1)。"""

    def test_default_thread_pool(self) -> None:
        """PR #467 以降の default は thread_pool (K run #466 で検証済)。

        旧 default = inline は Phase 2 互換用に env 明示で残る。
        """
        assert (
            resolve_short_term_memory_scheduler_mode(env={})
            == SCHEDULER_MODE_THREAD_POOL
        )

    def test_env_empty_string_default(self) -> None:
        """env 空文字でも default。"""
        assert (
            resolve_short_term_memory_scheduler_mode(
                env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: ""}
            )
            == SCHEDULER_MODE_THREAD_POOL
        )

    def test_inline(self) -> None:
        """有効な inline。"""
        assert resolve_short_term_memory_scheduler_mode(
            env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "inline"}
        ) == SCHEDULER_MODE_INLINE

    def test_thread_pool(self) -> None:
        """有効な thread pool。"""
        assert resolve_short_term_memory_scheduler_mode(
            env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "thread_pool"}
        ) == SCHEDULER_MODE_THREAD_POOL

    def test_case_insensitive_2(self) -> None:
        assert resolve_short_term_memory_scheduler_mode(
            env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "Thread_Pool"}
        ) == SCHEDULER_MODE_THREAD_POOL

    def test_unknown_raises_value_error_9(self) -> None:
        """typo / 未知のモードで silent fallback せず即落とす (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_short_term_memory_scheduler_mode(
                env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "async_io"}
            )
        msg = str(exc_info.value)
        assert "SHORT_TERM_MEMORY_SCHEDULER_MODE" in msg
        assert "async_io" in msg
        assert "inline" in msg
        assert "thread_pool" in msg


class TestLogShortTermMemorySchedulerModeState:
    """解決結果を INFO ログ 1 件で残す。"""

    def test_log_mode_value_rendered(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """log に mode の値が 出る。"""
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_short_term_memory_scheduler_mode_state("inline")
            log_short_term_memory_scheduler_mode_state("thread_pool")
        messages = [rec.message for rec in caplog.records]
        assert any("inline" in m for m in messages)
        assert any("thread_pool" in m for m in messages)


class TestResolveBeliefEvidenceEnabled:
    """U2 (証拠台帳統一設計): ``BELIEF_EVIDENCE_ENABLED`` の env パース。"""

    def test_env_unset_default_off_8(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_belief_evidence_enabled(env={}) is False

    def test_env_empty_string_default_off(self) -> None:
        """env 空文字なら default OFF。"""
        assert resolve_belief_evidence_enabled(
            env={ENV_BELIEF_EVIDENCE_ENABLED: ""}
        ) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_8(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_belief_evidence_enabled(
            env={ENV_BELIEF_EVIDENCE_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_8(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_belief_evidence_enabled(
            env={ENV_BELIEF_EVIDENCE_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_8(self) -> None:
        """typo による silent fallback を防ぐ (PR #433 経緯と同じ規約)。"""
        with pytest.raises(ValueError):
            resolve_belief_evidence_enabled(
                env={ENV_BELIEF_EVIDENCE_ENABLED: "yesplz"}
            )


class TestLogBeliefEvidenceEnabledState:
    def test_log_enabled_disabled_rendered(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """log に ENABLED DISABLED が出る。"""
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_belief_evidence_enabled_state(True)
            log_belief_evidence_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveSalienceStructuredFailureEnabled:
    """U6: ``SALIENCE_STRUCTURED_FAILURE_ENABLED`` の env パース。"""

    def test_env_unset_default_off_7(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_salience_structured_failure_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_7(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_salience_structured_failure_enabled(
            env={ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_7(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_salience_structured_failure_enabled(
            env={ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_7(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_salience_structured_failure_enabled(
                env={ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED: "yesplz"}
            )


class TestResolveMemoDistillEnabled:
    """U5: ``MEMO_DISTILL_ENABLED`` の env パース。"""

    def test_env_unset_default_off_6(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_memo_distill_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_6(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_memo_distill_enabled(
            env={ENV_MEMO_DISTILL_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_6(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_memo_distill_enabled(
            env={ENV_MEMO_DISTILL_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_6(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_memo_distill_enabled(
                env={ENV_MEMO_DISTILL_ENABLED: "yesplz"}
            )

    def test_log_state_log_6(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_memo_distill_enabled_state(True)
            log_memo_distill_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)


class TestResolveBeliefAttributionEnabled:
    """U4: ``BELIEF_ATTRIBUTION_ENABLED`` の env パース。"""

    def test_env_unset_default_off_5(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_belief_attribution_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_5(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_belief_attribution_enabled(
            env={ENV_BELIEF_ATTRIBUTION_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_5(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_belief_attribution_enabled(
            env={ENV_BELIEF_ATTRIBUTION_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_5(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_belief_attribution_enabled(
                env={ENV_BELIEF_ATTRIBUTION_ENABLED: "yesplz"}
            )

    def test_log_state_log_5(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_belief_attribution_enabled_state(True)
            log_belief_attribution_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveUnconsciousContextEnabled:
    """U7: ``UNCONSCIOUS_CONTEXT_ENABLED`` の env パース。"""

    def test_env_unset_default_off_4(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_unconscious_context_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_4(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_unconscious_context_enabled(
            env={ENV_UNCONSCIOUS_CONTEXT_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_4(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_unconscious_context_enabled(
            env={ENV_UNCONSCIOUS_CONTEXT_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_4(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_unconscious_context_enabled(
                env={ENV_UNCONSCIOUS_CONTEXT_ENABLED: "yesplz"}
            )

    def test_log_state_log_4(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_unconscious_context_enabled_state(True)
            log_unconscious_context_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveErrorDrivenReinterpretationEnabled:
    """U9a: ``ERROR_DRIVEN_REINTERPRETATION_ENABLED`` の env パース。"""

    def test_env_unset_default_off_3(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_error_driven_reinterpretation_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_3(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_error_driven_reinterpretation_enabled(
            env={ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_3(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_error_driven_reinterpretation_enabled(
            env={ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_3(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_error_driven_reinterpretation_enabled(
                env={ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED: "yesplz"}
            )

    def test_log_state_log_3(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_error_driven_reinterpretation_enabled_state(True)
            log_error_driven_reinterpretation_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveRecallHitBoostEnabled:
    """U9b: ``RECALL_HIT_BOOST_ENABLED`` の env パース。"""

    def test_env_unset_default_off_2(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_recall_hit_boost_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_2(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_recall_hit_boost_enabled(
            env={ENV_RECALL_HIT_BOOST_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off_2(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_recall_hit_boost_enabled(
            env={ENV_RECALL_HIT_BOOST_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error_2(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_recall_hit_boost_enabled(
                env={ENV_RECALL_HIT_BOOST_ENABLED: "yesplz"}
            )

    def test_log_state_log_2(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_recall_hit_boost_enabled_state(True)
            log_recall_hit_boost_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveStateCollapseEvidenceEnabled:
    """PR-D: ``STATE_COLLAPSE_EVIDENCE_ENABLED`` の env パース。"""

    def test_env_unset_default_off(self) -> None:
        """env 未設定なら default OFF。"""
        assert resolve_state_collapse_evidence_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value(self, raw: str) -> None:
        """truthy な値は ON。"""
        assert resolve_state_collapse_evidence_enabled(
            env={ENV_STATE_COLLAPSE_EVIDENCE_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off(self, raw: str) -> None:
        """falsy な値は OFF。"""
        assert resolve_state_collapse_evidence_enabled(
            env={ENV_STATE_COLLAPSE_EVIDENCE_ENABLED: raw}
        ) is False

    def test_unknown_raises_value_error(self) -> None:
        """未知の値は ValueError。"""
        with pytest.raises(ValueError):
            resolve_state_collapse_evidence_enabled(
                env={ENV_STATE_COLLAPSE_EVIDENCE_ENABLED: "yesplz"}
            )

    def test_log_state_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_state_collapse_evidence_enabled_state(True)
            log_state_collapse_evidence_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)
