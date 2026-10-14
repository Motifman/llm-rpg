"""``wiring/feature_flags.py`` の env-driven knob 解決テスト。"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.llm.wiring.feature_flags import (
    DEFAULT_SEMANTIC_PASSIVE_TOP_K,
    ENV_BELIEF_ATTRIBUTION_ENABLED,
    ENV_BELIEF_EVIDENCE_ENABLED,
    ENV_MEMO_TOOLS_ENABLED,
    ENV_RECALL_HIT_BOOST_ENABLED,
    ENV_SEMANTIC_PASSIVE_TOP_K,
    ENV_SHORT_TERM_MEMORY_KIND,
    SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
    SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW,
    log_belief_attribution_enabled_state,
    log_belief_evidence_enabled_state,
    log_memo_tools_enabled_state,
    log_recall_hit_boost_enabled_state,
    log_semantic_passive_top_k_state,
    log_short_term_memory_kind_state,
    resolve_belief_attribution_enabled,
    resolve_belief_evidence_enabled,
    resolve_memo_tools_enabled,
    resolve_recall_hit_boost_enabled,
    resolve_semantic_passive_top_k,
    resolve_short_term_memory_kind,
)


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


class TestResolveShortTermMemoryKind:
    """``SHORT_TERM_MEMORY_KIND`` env 解決 (Phase 2)。"""

    def test_default_short_term_memory(self) -> None:
        """設定に書かなければ rolling_summary になる。新しい記憶の書き起こしは畳むときに呼ばれる (#1631)。"""
        assert resolve_short_term_memory_kind(env={}) == SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY

    def test_env_empty_string_default_2(self) -> None:
        """空文字を渡しても、書かなかったときと同じ rolling_summary になる。"""
        assert resolve_short_term_memory_kind(
            env={ENV_SHORT_TERM_MEMORY_KIND: ""}
        ) == SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY

    def test_short_term_memory(self) -> None:
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


class TestResolveMemoToolsEnabled:
    """``MEMO_TOOLS_ENABLED`` の env パース。"""

    def test_env_unset_default_on(self) -> None:
        """env 未設定なら既存 run 互換で memo tool を露出する。"""
        assert resolve_memo_tools_enabled(env={}) is True

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_on(self, raw: str) -> None:
        """truthy な値は memo tool 露出 ON。"""
        assert resolve_memo_tools_enabled(env={ENV_MEMO_TOOLS_ENABLED: raw}) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off(self, raw: str) -> None:
        """falsy な値は memo tool 露出 OFF。"""
        assert resolve_memo_tools_enabled(env={ENV_MEMO_TOOLS_ENABLED: raw}) is False

    def test_unknown_raises_value_error(self) -> None:
        """未知の値は ValueError で落とし、実験 profile の typo を黙って受けない。"""
        with pytest.raises(ValueError):
            resolve_memo_tools_enabled(env={ENV_MEMO_TOOLS_ENABLED: "maybe"})

    def test_log_state_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_memo_tools_enabled_state(True)
            log_memo_tools_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("MEMO_TOOLS_ENABLED" in m for m in messages)


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
