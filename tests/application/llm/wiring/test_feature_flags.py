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
    ENV_EPISODIC_EXPLORE_RELATED_ENABLED,
    ENV_MEMO_DISTILL_ENABLED,
    ENV_PREDICTION_CONTEXT_ID_ENABLED,
    ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED,
    ENV_SEMANTIC_PASSIVE_TOP_K,
    ENV_SEMANTIC_SEARCH_ENABLED,
    ENV_SHORT_TERM_MEMORY_KIND,
    ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE,
    SCHEDULER_MODE_INLINE,
    SCHEDULER_MODE_THREAD_POOL,
    SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
    SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW,
    log_belief_attribution_enabled_state,
    log_belief_evidence_enabled_state,
    log_episodic_explore_related_state,
    log_memo_distill_enabled_state,
    log_prediction_context_id_state,
    log_semantic_passive_top_k_state,
    log_semantic_search_state,
    log_short_term_memory_kind_state,
    log_short_term_memory_scheduler_mode_state,
    resolve_belief_attribution_enabled,
    resolve_belief_evidence_enabled,
    resolve_episodic_explore_related_enabled,
    resolve_memo_distill_enabled,
    resolve_prediction_context_id_enabled,
    resolve_salience_structured_failure_enabled,
    resolve_semantic_passive_top_k,
    resolve_semantic_search_enabled,
    resolve_short_term_memory_kind,
    resolve_short_term_memory_scheduler_mode,
)


class TestResolveEpisodicExploreRelatedEnabled:
    """``EPISODIC_EXPLORE_RELATED_ENABLED`` の env パース。"""

    def test_env_未設定なら_default_OFF(self) -> None:
        """env 未設定なら OFF (検証中の default 不活性方針)。"""
        assert resolve_episodic_explore_related_enabled(env={}) is False

    def test_env_空文字なら_default_OFF(self) -> None:
        """空文字は未設定扱い → default OFF。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: ""}
        ) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "TRUE", "yes", "YES", "on", "On"])
    def test_truthy_な値は_ON(self, raw: str) -> None:
        """truthy リテラル ("1", "true", "yes", "on") は case-insensitive で ON。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "FALSE", "Off"])
    def test_falsy_リテラルは_OFF(self, raw: str) -> None:
        """明示的に falsy ("0" / "false" / "no" / "off") を渡したら OFF。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
        ) is False

    @pytest.mark.parametrize("raw", ["random", "2", "yeah", "tru", "enable"])
    def test_未知の値は_ValueError(self, raw: str) -> None:
        """truthy / falsy のどちらでもない値で silent fallback せず fail-fast (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_episodic_explore_related_enabled(
                env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
            )
        msg = str(exc_info.value)
        assert ENV_EPISODIC_EXPLORE_RELATED_ENABLED in msg
        assert raw in msg

    def test_前後空白は_strip(self) -> None:
        """env var の値に空白混入があっても解釈できる。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: "  1  "}
        ) is True


class TestLogEpisodicExploreRelatedState:
    """解決状態を INFO ログ 1 件で残す (run 再現性確保用)。"""

    def test_ON_でも_OFF_でも_1件出る(self, caplog: pytest.LogCaptureFixture) -> None:
        """ENABLED / DISABLED の 2 ケースで INFO log が出る。"""
        with caplog.at_level(logging.INFO, logger="ai_rpg_world.application.llm.wiring.feature_flags"):
            log_episodic_explore_related_state(True)
            log_episodic_explore_related_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)


class TestResolveSemanticPassiveTopK:
    """``SEMANTIC_PASSIVE_TOP_K`` env パース (Phase 1c)。"""

    def test_default_は_0(self) -> None:
        """default は 0 (= prompt §learned 非表示)。検証中の安定設定。"""
        assert DEFAULT_SEMANTIC_PASSIVE_TOP_K == 0
        assert resolve_semantic_passive_top_k(env={}) == 0

    def test_env_未設定なら_default_0(self) -> None:
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: ""}
        ) == 0

    def test_有効な正整数なら_その値(self) -> None:
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "3"}
        ) == 3
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "  5  "}
        ) == 5

    def test_0_なら_0_を返す(self) -> None:
        """明示的に 0 を渡しても受理。"""
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "0"}
        ) == 0

    def test_非数値なら_ValueError(self) -> None:
        """typo / 非整数で silent fallback すると実験前提を壊すので fail-fast (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_semantic_passive_top_k(
                env={ENV_SEMANTIC_PASSIVE_TOP_K: "abc"}
            )
        assert "SEMANTIC_PASSIVE_TOP_K" in str(exc_info.value)
        assert "non-integer" in str(exc_info.value)

    def test_負数なら_ValueError(self) -> None:
        """負の値を渡すのは意図がないと考え、fail-fast (PR #434)。"""
        with pytest.raises(ValueError) as exc_info:
            resolve_semantic_passive_top_k(
                env={ENV_SEMANTIC_PASSIVE_TOP_K: "-3"}
            )
        assert "SEMANTIC_PASSIVE_TOP_K" in str(exc_info.value)
        assert ">= 0" in str(exc_info.value)


class TestLogSemanticPassiveTopKState:
    """解決結果を INFO ログ 1 件で残す。"""

    def test_top_k_の値が_log_に_出る(self, caplog: pytest.LogCaptureFixture) -> None:
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

    def test_default_は_OFF(self) -> None:
        assert resolve_semantic_search_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "ON", "True"])
    def test_truthy_は_ON(self, raw: str) -> None:
        assert resolve_semantic_search_enabled(
            env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", ""])
    def test_falsy_リテラルまたは空文字は_OFF(self, raw: str) -> None:
        """明示的 falsy / 空文字は OFF。空文字は「未設定」扱いで default を返す。"""
        assert resolve_semantic_search_enabled(
            env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
        ) is False

    @pytest.mark.parametrize("raw", ["random", "yeah", "tru", "2"])
    def test_未知の値は_ValueError(self, raw: str) -> None:
        """typo / 未知の値で silent fallback せず fail-fast (PR #434)。"""
        with pytest.raises(ValueError):
            resolve_semantic_search_enabled(
                env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
            )


class TestLogSemanticSearchState:
    """解決結果を INFO ログ 1 件で残す (Phase 1d)。"""

    def test_ENABLED_でも_DISABLED_でも_log_に_出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_default_は_OFF(self) -> None:
        assert resolve_prediction_context_id_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "ON", "True"])
    def test_truthy_は_ON(self, raw: str) -> None:
        assert resolve_prediction_context_id_enabled(
            env={ENV_PREDICTION_CONTEXT_ID_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", ""])
    def test_falsy_リテラルまたは空文字は_OFF(self, raw: str) -> None:
        assert resolve_prediction_context_id_enabled(
            env={ENV_PREDICTION_CONTEXT_ID_ENABLED: raw}
        ) is False

    @pytest.mark.parametrize("raw", ["random", "yeah", "tru", "2"])
    def test_未知の値は_ValueError(self, raw: str) -> None:
        with pytest.raises(ValueError):
            resolve_prediction_context_id_enabled(
                env={ENV_PREDICTION_CONTEXT_ID_ENABLED: raw}
            )


class TestLogPredictionContextIdState:
    """解決結果を INFO ログ 1 件で残す (予測誤差統一設計 U1)。"""

    def test_ENABLED_でも_DISABLED_でも_log_に_出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_default_は_sliding_window(self) -> None:
        assert resolve_short_term_memory_kind(env={}) == SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW

    def test_env_空文字でも_default(self) -> None:
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: ""}
        ) == SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW

    def test_有効な_sliding_window(self) -> None:
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: "sliding_window"}
        ) == SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW

    def test_有効な_rolling_summary(self) -> None:
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: "rolling_summary"}
        ) == SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY

    def test_case_insensitive(self) -> None:
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: "ROLLING_SUMMARY"}
        ) == SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY

    def test_未知の値は_ValueError(self) -> None:
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

    def test_log_に_kind_の値が_出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_default_は_thread_pool(self) -> None:
        """PR #467 以降の default は thread_pool (K run #466 で検証済)。

        旧 default = inline は Phase 2 互換用に env 明示で残る。
        """
        assert (
            resolve_short_term_memory_scheduler_mode(env={})
            == SCHEDULER_MODE_THREAD_POOL
        )

    def test_env_空文字でも_default(self) -> None:
        assert (
            resolve_short_term_memory_scheduler_mode(
                env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: ""}
            )
            == SCHEDULER_MODE_THREAD_POOL
        )

    def test_有効な_inline(self) -> None:
        assert resolve_short_term_memory_scheduler_mode(
            env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "inline"}
        ) == SCHEDULER_MODE_INLINE

    def test_有効な_thread_pool(self) -> None:
        assert resolve_short_term_memory_scheduler_mode(
            env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "thread_pool"}
        ) == SCHEDULER_MODE_THREAD_POOL

    def test_case_insensitive(self) -> None:
        assert resolve_short_term_memory_scheduler_mode(
            env={ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE: "Thread_Pool"}
        ) == SCHEDULER_MODE_THREAD_POOL

    def test_未知の値は_ValueError(self) -> None:
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

    def test_log_に_mode_の値が_出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_env_未設定なら_default_OFF(self) -> None:
        assert resolve_belief_evidence_enabled(env={}) is False

    def test_env_空文字なら_default_OFF(self) -> None:
        assert resolve_belief_evidence_enabled(
            env={ENV_BELIEF_EVIDENCE_ENABLED: ""}
        ) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_な値は_ON(self, raw: str) -> None:
        assert resolve_belief_evidence_enabled(
            env={ENV_BELIEF_EVIDENCE_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_な値は_OFF(self, raw: str) -> None:
        assert resolve_belief_evidence_enabled(
            env={ENV_BELIEF_EVIDENCE_ENABLED: raw}
        ) is False

    def test_未知の値は_ValueError(self) -> None:
        """typo による silent fallback を防ぐ (PR #433 経緯と同じ規約)。"""
        with pytest.raises(ValueError):
            resolve_belief_evidence_enabled(
                env={ENV_BELIEF_EVIDENCE_ENABLED: "yesplz"}
            )


class TestLogBeliefEvidenceEnabledState:
    def test_log_に_ENABLED_DISABLED_が出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_env_未設定なら_default_OFF(self) -> None:
        assert resolve_salience_structured_failure_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_な値は_ON(self, raw: str) -> None:
        assert resolve_salience_structured_failure_enabled(
            env={ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_な値は_OFF(self, raw: str) -> None:
        assert resolve_salience_structured_failure_enabled(
            env={ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED: raw}
        ) is False

    def test_未知の値は_ValueError(self) -> None:
        with pytest.raises(ValueError):
            resolve_salience_structured_failure_enabled(
                env={ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED: "yesplz"}
            )


class TestResolveMemoDistillEnabled:
    """U5: ``MEMO_DISTILL_ENABLED`` の env パース。"""

    def test_env_未設定なら_default_OFF(self) -> None:
        assert resolve_memo_distill_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_な値は_ON(self, raw: str) -> None:
        assert resolve_memo_distill_enabled(
            env={ENV_MEMO_DISTILL_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_な値は_OFF(self, raw: str) -> None:
        assert resolve_memo_distill_enabled(
            env={ENV_MEMO_DISTILL_ENABLED: raw}
        ) is False

    def test_未知の値は_ValueError(self) -> None:
        with pytest.raises(ValueError):
            resolve_memo_distill_enabled(
                env={ENV_MEMO_DISTILL_ENABLED: "yesplz"}
            )

    def test_log_state_はレベル情報でログを出す(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log_memo_distill_enabled_state(True)
            log_memo_distill_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)


class TestResolveBeliefAttributionEnabled:
    """U4: ``BELIEF_ATTRIBUTION_ENABLED`` の env パース。"""

    def test_env_未設定なら_default_OFF(self) -> None:
        assert resolve_belief_attribution_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_な値は_ON(self, raw: str) -> None:
        assert resolve_belief_attribution_enabled(
            env={ENV_BELIEF_ATTRIBUTION_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_な値は_OFF(self, raw: str) -> None:
        assert resolve_belief_attribution_enabled(
            env={ENV_BELIEF_ATTRIBUTION_ENABLED: raw}
        ) is False

    def test_未知の値は_ValueError(self) -> None:
        with pytest.raises(ValueError):
            resolve_belief_attribution_enabled(
                env={ENV_BELIEF_ATTRIBUTION_ENABLED: "yesplz"}
            )

    def test_log_state_はレベル情報でログを出す(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log_belief_attribution_enabled_state(True)
            log_belief_attribution_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)
