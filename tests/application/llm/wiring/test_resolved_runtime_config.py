"""``ResolvedLlmRuntimeConfig`` の単一窓口性 / fail-fast / trace 表現を検証する。

PR #439 / #446 で発覚した「同 env を 2 経路で別解釈する silent failure」を
構造で防ぐための DTO。本テスト群は以下を保証する:

1. env から全フィールドを 1 度で解決できる (= from_env が単一窓口)
2. env の typo / 不正値で `ValueError` を投げる (= fail-fast / PR #434 継承)
3. trace 用の dict 表現で API key が必ずマスクされる (= 漏洩防止)
4. test 用 safe default factory (`for_tests`) で test fixture を簡潔化できる
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


# ──────────────────────────────────────────────────────────────────
# from_env: 単一窓口 + fail-fast
# ──────────────────────────────────────────────────────────────────


class TestFromEnvDefaults:
    """env 全未設定なら全フィールドが「最も無害な default」になる。"""

    def test_全env_未設定で_default_に_resolve(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.from_env(env={})
        assert cfg.short_term_memory_kind == "sliding_window"
        # PR #467: scheduler default は thread_pool に変更 (K run #466 で検証済)
        assert cfg.short_term_memory_scheduler_mode == "thread_pool"
        assert cfg.prompt_section_order == "stable_to_volatile"
        assert cfg.llm_client_kind == "stub"
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base is None
        assert cfg.llm_request_timeout_seconds == 90.0
        assert cfg.openrouter_provider is None
        assert cfg.openrouter_quantization is None
        assert cfg.openrouter_require_params is False
        assert cfg.episodic_enabled is False
        assert cfg.episodic_explore_related_enabled is False
        assert cfg.semantic_llm_gist_enabled is False
        assert cfg.semantic_passive_top_k == 0
        assert cfg.semantic_search_enabled is False


class TestFromEnvExplicit:
    """env 明示で全フィールドが正しく resolve される。"""

    def test_全フィールド_明示_env_で_resolve(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.from_env(
            env={
                "SHORT_TERM_MEMORY_KIND": "rolling_summary",
                "SHORT_TERM_MEMORY_SCHEDULER_MODE": "thread_pool",
                "PROMPT_SECTION_ORDER": "legacy",
                "LLM_CLIENT": "litellm",
                "LLM_MODEL": "openrouter/google/gemma-4-31b-it",
                "OPENAI_API_KEY": "sk-test-x",
                "OPENAI_API_BASE": "https://openrouter.ai/api/v1",
                "LLM_REQUEST_TIMEOUT_SECONDS": "60",
                "OPENROUTER_PROVIDER": "Parasail",
                "OPENROUTER_QUANTIZATION": "fp8",
                "OPENROUTER_REQUIRE_PARAMS": "true",
                "LLM_EPISODIC_ENABLED": "1",
                "EPISODIC_EXPLORE_RELATED_ENABLED": "1",
                "SEMANTIC_LLM_GIST_ENABLED": "1",
                "SEMANTIC_PASSIVE_TOP_K": "3",
                "SEMANTIC_SEARCH_ENABLED": "yes",
            }
        )
        assert cfg.short_term_memory_kind == "rolling_summary"
        assert cfg.short_term_memory_scheduler_mode == "thread_pool"
        assert cfg.prompt_section_order == "legacy"
        assert cfg.llm_client_kind == "litellm"
        assert cfg.llm_model == "openrouter/google/gemma-4-31b-it"
        assert cfg.llm_api_key == "sk-test-x"
        assert cfg.llm_api_base == "https://openrouter.ai/api/v1"
        assert cfg.llm_request_timeout_seconds == 60.0
        assert cfg.openrouter_provider == "Parasail"
        assert cfg.openrouter_quantization == "fp8"
        assert cfg.openrouter_require_params is True
        assert cfg.episodic_enabled is True
        assert cfg.episodic_explore_related_enabled is True
        assert cfg.semantic_llm_gist_enabled is True
        assert cfg.semantic_passive_top_k == 3
        assert cfg.semantic_search_enabled is True

    def test_空文字_env_は_default_扱い(self) -> None:
        """空文字は「未設定」と等価 (PR #434 ポリシー)。"""
        cfg = ResolvedLlmRuntimeConfig.from_env(
            env={
                "LLM_MODEL": "",
                "OPENAI_API_KEY": "  ",  # whitespace only
                "OPENROUTER_PROVIDER": "",
            }
        )
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.openrouter_provider is None


class TestFromEnvFailFast:
    """typo / 不正値 → ValueError (= PR #434 ポリシー継承)。"""

    def test_short_term_memory_kind_短縮形_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="SHORT_TERM_MEMORY_KIND"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"SHORT_TERM_MEMORY_KIND": "rolling"}  # 正しくは rolling_summary
            )

    def test_scheduler_mode_未知の値は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="SHORT_TERM_MEMORY_SCHEDULER_MODE"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"SHORT_TERM_MEMORY_SCHEDULER_MODE": "async_io"}
            )

    def test_section_order_typo_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="PROMPT_SECTION_ORDER"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"PROMPT_SECTION_ORDER": "stable_to_volatil"}  # typo
            )

    def test_llm_client_未知の値は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="LLM_CLIENT"):
            ResolvedLlmRuntimeConfig.from_env(env={"LLM_CLIENT": "ollama"})

    def test_timeout_非数値は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="LLM_REQUEST_TIMEOUT_SECONDS"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"LLM_REQUEST_TIMEOUT_SECONDS": "ten"}
            )

    def test_episodic_enabled_typo_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="boolean"):
            ResolvedLlmRuntimeConfig.from_env(env={"LLM_EPISODIC_ENABLED": "yeah"})

    def test_openrouter_require_params_typo_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="boolean"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"OPENROUTER_REQUIRE_PARAMS": "tru"}  # typo
            )

    def test_semantic_passive_top_k_非数値は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="SEMANTIC_PASSIVE_TOP_K"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"SEMANTIC_PASSIVE_TOP_K": "abc"}
            )

    def test_semantic_passive_top_k_負数は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="SEMANTIC_PASSIVE_TOP_K"):
            ResolvedLlmRuntimeConfig.from_env(
                env={"SEMANTIC_PASSIVE_TOP_K": "-1"}
            )


class TestFromEnvUsesOsEnvironWhenEnvOmitted:
    """env 引数省略時は os.environ から読む。"""

    def test_env_None_で_os_environ_から_読む(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SHORT_TERM_MEMORY_KIND", "rolling_summary")
        monkeypatch.setenv("PROMPT_SECTION_ORDER", "legacy")
        cfg = ResolvedLlmRuntimeConfig.from_env()
        assert cfg.short_term_memory_kind == "rolling_summary"
        assert cfg.prompt_section_order == "legacy"


# ──────────────────────────────────────────────────────────────────
# Immutability
# ──────────────────────────────────────────────────────────────────


class TestImmutability:
    """frozen dataclass: 構築後の改変を防ぐ (= hash 可能 / 共有 safe)。"""

    def test_field_の_set_は_FrozenInstanceError(self) -> None:
        from dataclasses import FrozenInstanceError

        cfg = ResolvedLlmRuntimeConfig.from_env(env={})
        with pytest.raises(FrozenInstanceError):
            cfg.short_term_memory_kind = "rolling_summary"  # type: ignore[misc]

    def test_hash_可能(self) -> None:
        """frozen=True なので hash できる (= set / dict key に使える)。"""
        cfg = ResolvedLlmRuntimeConfig.from_env(env={})
        # raise しないことを assert
        _ = hash(cfg)


# ──────────────────────────────────────────────────────────────────
# Test fixture factory
# ──────────────────────────────────────────────────────────────────


class TestForTestsFactory:
    """test fixture の肥大化を防ぐ safe default factory。"""

    def test_overrides_無しで_default_と_同じ(self) -> None:
        cfg_from_factory = ResolvedLlmRuntimeConfig.for_tests()
        cfg_from_env = ResolvedLlmRuntimeConfig.from_env(env={})
        assert cfg_from_factory == cfg_from_env

    def test_override_だけ_keyword_で_指定できる(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            short_term_memory_kind="rolling_summary",
            llm_client_kind="litellm",
        )
        # 指定したものだけ変わる
        assert cfg.short_term_memory_kind == "rolling_summary"
        assert cfg.llm_client_kind == "litellm"
        # 他は default
        assert cfg.prompt_section_order == "stable_to_volatile"
        assert cfg.semantic_passive_top_k == 0

    def test_未知の_override_key_は_TypeError(self) -> None:
        """typo を発見する fail-fast。"""
        with pytest.raises(TypeError, match="Unknown override keys"):
            ResolvedLlmRuntimeConfig.for_tests(short_term_memory="rolling_summary")  # type: ignore[call-arg]


# ──────────────────────────────────────────────────────────────────
# Trace observability
# ──────────────────────────────────────────────────────────────────


class TestToTraceDict:
    """run_start trace 用の dict 表現。API key 必ずマスク。"""

    def test_全フィールド_が_dict_に_出る(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            short_term_memory_kind="rolling_summary",
            prompt_section_order="stable_to_volatile",
            llm_client_kind="litellm",
            llm_model="openrouter/google/gemma-4-31b-it",
        )
        d = cfg.to_trace_dict()
        assert d["short_term_memory_kind"] == "rolling_summary"
        assert d["prompt_section_order"] == "stable_to_volatile"
        assert d["llm_client_kind"] == "litellm"
        assert d["llm_model"] == "openrouter/google/gemma-4-31b-it"

    def test_api_key_は_マスク_される(self) -> None:
        """API key の生値は絶対に trace に出さない (漏洩防止)。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key="sk-or-secret-12345")
        d = cfg.to_trace_dict()
        assert d["llm_api_key"] == "***"
        # 生値が trace dict 内のどこにも存在しない
        assert "sk-or-secret-12345" not in str(d)

    def test_api_key_None_の場合_None_のまま(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key=None)
        d = cfg.to_trace_dict()
        assert d["llm_api_key"] is None


# ──────────────────────────────────────────────────────────────────
# 既存 resolver との一貫性 (= behavior equivalence)
# ──────────────────────────────────────────────────────────────────


class TestExistingResolverParity:
    """``from_env`` が既存 resolver と同じ値を返すことを担保する (= 移行時の
    behavior 等価)。PR 3/6 で既存 wiring を本 DTO に置き換えるときに、両経路で
    結果が一致することを構造的に保証する。"""

    def test_short_term_memory_kind_は_既存_resolver_と_一致(self) -> None:
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_short_term_memory_kind,
        )

        env = {"SHORT_TERM_MEMORY_KIND": "rolling_summary"}
        cfg = ResolvedLlmRuntimeConfig.from_env(env=env)
        assert cfg.short_term_memory_kind == resolve_short_term_memory_kind(env=env)

    def test_section_order_は_既存_resolver_と_一致(self) -> None:
        from ai_rpg_world.application.llm.services.context_format_strategy import (
            resolve_section_order_from_env,
        )

        env = {"PROMPT_SECTION_ORDER": "legacy"}
        cfg = ResolvedLlmRuntimeConfig.from_env(env=env)
        assert cfg.prompt_section_order == resolve_section_order_from_env(env=env)

    def test_semantic_passive_top_k_は_既存_resolver_と_一致(self) -> None:
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_semantic_passive_top_k,
        )

        env = {"SEMANTIC_PASSIVE_TOP_K": "5"}
        cfg = ResolvedLlmRuntimeConfig.from_env(env=env)
        assert cfg.semantic_passive_top_k == resolve_semantic_passive_top_k(env=env)
