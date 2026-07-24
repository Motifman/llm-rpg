"""``ResolvedLlmRuntimeConfig`` の単一窓口性 / fail-fast / trace 表現を検証する。

PR #439 / #446 で発覚した「同 env を 2 経路で別解釈する silent failure」を
構造で防ぐための DTO。本テスト群は以下を保証する:

1. 設定値から全フィールドを 1 度で解決できる (= from_mapping が単一窓口)
2. 設定値の typo / 不正値で `ValueError` を投げる (= fail-fast / PR #434 継承)
3. trace 用の dict 表現で API key が必ずマスクされる (= 漏洩防止)
4. test 用 safe default factory (`for_tests`) で test fixture を簡潔化できる
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


# ──────────────────────────────────────────────────────────────────
# from_mapping: 単一窓口 + fail-fast
# ──────────────────────────────────────────────────────────────────


class TestFromEnvDefaults:
    """設定値が空なら全フィールドが「最も無害な default」になる。"""

    def test_empty_config_default_resolve(self) -> None:
        """空設定で default に resolve。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.short_term_memory_kind == "sliding_window"
        # PR #467: scheduler default は thread_pool に変更 (K run #466 で検証済)
        assert cfg.short_term_memory_scheduler_mode == "thread_pool"
        assert cfg.prompt_section_order == "stable_to_volatile"
        assert cfg.llm_client_kind == "stub"
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base is None
        assert cfg.llm_request_timeout_seconds == 90.0
        assert cfg.llm_reasoning_effort == "none"
        assert cfg.llm_wall_time_cap_seconds is None
        assert cfg.llm_rate_limit_retry_attempts == 3
        assert cfg.llm_rate_limit_retry_base_sleep == 2.0
        assert cfg.openrouter_provider is None
        assert cfg.openrouter_quantization is None
        assert cfg.openrouter_require_params is False
        assert cfg.episodic_enabled is False
        assert cfg.episodic_subjective_enabled is True
        assert cfg.episodic_explore_related_enabled is False
        assert cfg.episodic_promotion_force_full_scan is False
        assert cfg.episodic_promotion_expansion_hops == 4
        assert cfg.semantic_llm_gist_enabled is False
        assert cfg.semantic_passive_top_k == 0
        assert cfg.semantic_search_enabled is False
        assert cfg.episodic_reinterpretation_enabled is False
        assert cfg.belief_evidence_enabled is False
        assert cfg.goal_reflect_enabled is False
        assert cfg.stagnation_reasoning_enabled is False
        assert cfg.tool_mode == "default"
        assert cfg.scenario_random_seed is None
        assert cfg.prompt_dataset_capture_enabled is False
        assert cfg.prompt_dataset_capture_failure_policy == "fail"
        assert cfg.reason_first_two_step_enabled is False


class TestPromptDatasetCaptureConfig:
    """prompt dataset capture は Being ID を保存できる設定でだけ有効化できる。"""

    def test_enabled_requires_episodic_enabled(self) -> None:
        """capture 有効・episodic 無効なら being_id が取れないため fail-fast する。"""
        with pytest.raises(ValueError, match="LLM_EPISODIC_ENABLED"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"PROMPT_DATASET_CAPTURE_ENABLED": "1"}
            )

    def test_enabled_with_episodic_resolves_failure_policy(self) -> None:
        """episodic 有効なら capture を有効化でき、保存失敗時方針も解決される。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_EPISODIC_ENABLED": "1",
                "PROMPT_DATASET_CAPTURE_ENABLED": "1",
                "PROMPT_DATASET_CAPTURE_FAILURE_POLICY": "warn",
            }
        )
        assert cfg.prompt_dataset_capture_enabled is True
        assert cfg.prompt_dataset_capture_failure_policy == "warn"


class TestReasonFirstTwoStepConfig:
    """reason-first 2段階ターンの有効化 flag を単一窓口で解決する。"""

    def test_unset_false(self) -> None:
        """REASON_FIRST_TWO_STEP_ENABLED 未設定なら既存 1段階 turn のまま。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.reason_first_two_step_enabled is False

    def test_truthy_true(self) -> None:
        """REASON_FIRST_TWO_STEP_ENABLED=1 で gated reason-first を有効化する。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"REASON_FIRST_TWO_STEP_ENABLED": "1"}
        )
        assert cfg.reason_first_two_step_enabled is True

    def test_invalid_value_fail_fast(self) -> None:
        """typo は silent に OFF へ落とさず ValueError で止める。"""
        with pytest.raises(ValueError, match="REASON_FIRST_TWO_STEP_ENABLED"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"REASON_FIRST_TWO_STEP_ENABLED": "maybe"}
            )

    def test_trace_dict_includes_flag(self) -> None:
        """run_start / manifest から reason-first 有効化条件を後で確認できる。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            reason_first_two_step_enabled=True
        )
        assert cfg.to_trace_dict()["reason_first_two_step_enabled"] is True


class TestEpisodicReinterpretationEnabled:
    """段1 (エピソード再解釈) の on/off 解決。"""

    def test_unset_false_2(self) -> None:
        """LLM_EPISODIC_REINTERPRETATION_ENABLED 未設定なら False (= 従来 episodic-only)。"""
        assert ResolvedLlmRuntimeConfig.from_mapping(values={}).episodic_reinterpretation_enabled is False

    def test_truthy_true_2(self) -> None:
        """1/true 等で True。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_EPISODIC_REINTERPRETATION_ENABLED": "1"}
        )
        assert cfg.episodic_reinterpretation_enabled is True

    def test_for_tests_default_False(self) -> None:
        """for_tests の default は False、override 可。"""
        assert ResolvedLlmRuntimeConfig.for_tests().episodic_reinterpretation_enabled is False
        assert (
            ResolvedLlmRuntimeConfig.for_tests(
                episodic_reinterpretation_enabled=True
            ).episodic_reinterpretation_enabled
            is True
        )


class TestRecallHabituationEnabled:
    """段階 2 (慣化ペナルティ) の on/off + decay_window の解決。"""

    def test_unset_false(self) -> None:
        """``LLM_EPISODIC_RECALL_HABITUATION_ENABLED`` 未設定なら False。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.recall_habituation_enabled is False
        assert cfg.recall_habituation_decay_window_ticks == 5  # default

    def test_truthy_true(self) -> None:
        """truthy で True。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_EPISODIC_RECALL_HABITUATION_ENABLED": "1"}
        )
        assert cfg.recall_habituation_enabled is True

    def test_decay_window_can_be_set_explicitly(self) -> None:
        """``LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS`` で window を上書き。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_EPISODIC_RECALL_HABITUATION_ENABLED": "1",
                "LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS": "8",
            }
        )
        assert cfg.recall_habituation_decay_window_ticks == 8

    def test_decay_window_negative_raises_value_error(self) -> None:
        """負値は fail-fast。"""
        with pytest.raises(ValueError, match="HABITUATION_DECAY_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS": "-1"}
            )

    def test_decay_window_raises_value_error(self) -> None:
        """decay window 非数値は ValueError。"""
        with pytest.raises(ValueError, match="HABITUATION_DECAY_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS": "abc"}
            )

    def test_for_tests_default(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.for_tests()
        assert cfg.recall_habituation_enabled is False
        assert cfg.recall_habituation_decay_window_ticks == 5

    def test_for_tests_override(self) -> None:
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            recall_habituation_enabled=True,
            recall_habituation_decay_window_ticks=10,
        )
        assert cfg.recall_habituation_enabled is True
        assert cfg.recall_habituation_decay_window_ticks == 10

    def test_trace_dict_included_2(self) -> None:
        """totracedict に含まれる。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            recall_habituation_enabled=True,
            recall_habituation_decay_window_ticks=7,
        )
        d = cfg.to_trace_dict()
        assert d["recall_habituation_enabled"] is True
        assert d["recall_habituation_decay_window_ticks"] == 7


class TestExpectedResultPolicy:
    """予測 (expected_result) 露出 policy の解決 (off/optional/required)。"""

    def test_unset_off(self) -> None:
        """LLM_EXPECTED_RESULT_POLICY 未設定なら off (= schema に出さず挙動不変)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.expected_result_policy == "off"

    def test_optional_resolve(self) -> None:
        """optional を解決する (大文字・空白も吸収)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_EXPECTED_RESULT_POLICY": " Optional "})
        assert cfg.expected_result_policy == "optional"

    def test_required_resolve(self) -> None:
        """required を解決する。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_EXPECTED_RESULT_POLICY": "required"})
        assert cfg.expected_result_policy == "required"

    def test_invalid_raises_value_error(self) -> None:
        """未知の policy は fail-fast で ValueError。"""
        with pytest.raises(ValueError, match="LLM_EXPECTED_RESULT_POLICY"):
            ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_EXPECTED_RESULT_POLICY": "maybe"})

    def test_for_tests_default_off(self) -> None:
        """for_tests の default は off。"""
        assert ResolvedLlmRuntimeConfig.for_tests().expected_result_policy == "off"

    def test_for_tests_override_2(self) -> None:
        """for_tests で override できる。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(expected_result_policy="required")
        assert cfg.expected_result_policy == "required"

    def test_trace_dict_included(self) -> None:
        """trace payload に policy が出る (run の設定を post-hoc で追える)。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(expected_result_policy="optional")
        assert cfg.to_trace_dict()["expected_result_policy"] == "optional"

    def test_tests_invalid_value_fail_fast(self) -> None:
        """for_tests 経由の typo も __post_init__ で ValueError (from_mapping 以外も fail-fast)。"""
        with pytest.raises(ValueError, match="expected_result_policy"):
            ResolvedLlmRuntimeConfig.for_tests(expected_result_policy="optionnal")

    def test_invalid_value_fail_fast(self) -> None:
        """cls(...) 直接構築の typo も __post_init__ で ValueError。"""
        base = ResolvedLlmRuntimeConfig.for_tests()
        from dataclasses import replace

        with pytest.raises(ValueError, match="expected_result_policy"):
            replace(base, expected_result_policy="maybe")


class TestFromEnvExplicit:
    """設定値明示で全フィールドが正しく resolve される。"""

    def test_all_config_resolve(self) -> None:
        """全フィールド明示設定で resolve。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "SHORT_TERM_MEMORY_KIND": "rolling_summary",
                "SHORT_TERM_MEMORY_SCHEDULER_MODE": "thread_pool",
                "PROMPT_SECTION_ORDER": "legacy",
                "LLM_CLIENT": "litellm",
                "LLM_MODEL": "openrouter/google/gemma-4-31b-it",
                "OPENAI_API_BASE": "https://openrouter.ai/api/v1",
                "LLM_REQUEST_TIMEOUT_SECONDS": "60",
                "LLM_REASONING_EFFORT": "minimal",
                "LLM_WALL_TIME_CAP_SECONDS": "65",
                "LLM_RATE_LIMIT_RETRY_ATTEMPTS": "2",
                "LLM_RATE_LIMIT_RETRY_BASE_SLEEP": "1.5",
                "OPENROUTER_PROVIDER": "Parasail",
                "OPENROUTER_QUANTIZATION": "fp8",
                "OPENROUTER_REQUIRE_PARAMS": "true",
                "LLM_EPISODIC_ENABLED": "1",
                "LLM_EPISODIC_SUBJECTIVE_ENABLED": "0",
                "EPISODIC_EXPLORE_RELATED_ENABLED": "1",
                "EPISODIC_PROMOTION_FORCE_FULL_SCAN": "1",
                "EPISODIC_PROMOTION_EXPANSION_HOPS": "6",
                "SEMANTIC_LLM_GIST_ENABLED": "1",
                "SEMANTIC_PASSIVE_TOP_K": "3",
                "SEMANTIC_SEARCH_ENABLED": "yes",
                "EPISODIC_RECALL_ENABLED": "1",
                "PREDICTION_CONTEXT_ID_ENABLED": "1",
                "BELIEF_EVIDENCE_ENABLED": "1",
                "BELIEF_CONSOLIDATION_ENABLED": "1",
                "BELIEF_ATTRIBUTION_ENABLED": "1",
                "SALIENCE_STRUCTURED_FAILURE_ENABLED": "1",
                "MEMO_DISTILL_ENABLED": "1",
                "UNCONSCIOUS_CONTEXT_ENABLED": "1",
                "ERROR_DRIVEN_REINTERPRETATION_ENABLED": "1",
                "RECALL_HIT_BOOST_ENABLED": "1",
                "ERROR_GATED_ENCODING_ENABLED": "1",
                "PENDING_PREDICTION_ENABLED": "1",
                "HEARSAY_ENABLED": "1",
                "STATE_COLLAPSE_EVIDENCE_ENABLED": "1",
                "GOAL_STORE_ENABLED": "1",
                "GOAL_REVISION_ENABLED": "1",
                "GOAL_REFLECT_ENABLED": "1",
                "GOAL_STAGNATION_EVIDENCE_ENABLED": "1",
                "STAGNATION_PRESSURE_ENABLED": "1",
                "STAGNATION_REASONING_ENABLED": "1",
                "LLM_TOOL_MODE": "pure_spot_graph",
                "ESCAPE_LLM_SSOT": "1",
                "SCENARIO_RANDOM_SEED": "42",
            }
        )
        assert cfg.short_term_memory_kind == "rolling_summary"
        assert cfg.short_term_memory_scheduler_mode == "thread_pool"
        assert cfg.prompt_section_order == "legacy"
        assert cfg.llm_client_kind == "litellm"
        assert cfg.llm_model == "openrouter/google/gemma-4-31b-it"
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base == "https://openrouter.ai/api/v1"
        assert cfg.llm_request_timeout_seconds == 60.0
        assert cfg.llm_reasoning_effort == "minimal"
        assert cfg.llm_wall_time_cap_seconds == 65.0
        assert cfg.llm_rate_limit_retry_attempts == 2
        assert cfg.llm_rate_limit_retry_base_sleep == 1.5
        assert cfg.openrouter_provider == "Parasail"
        assert cfg.openrouter_quantization == "fp8"
        assert cfg.openrouter_require_params is True
        assert cfg.episodic_enabled is True
        assert cfg.episodic_subjective_enabled is False
        assert cfg.episodic_explore_related_enabled is True
        assert cfg.episodic_promotion_force_full_scan is True
        assert cfg.episodic_promotion_expansion_hops == 6
        assert cfg.semantic_llm_gist_enabled is True
        assert cfg.semantic_passive_top_k == 3
        assert cfg.semantic_search_enabled is True
        assert cfg.episodic_recall_enabled is True
        assert cfg.prediction_context_id_enabled is True
        assert cfg.belief_evidence_enabled is True
        assert cfg.belief_consolidation_enabled is True
        assert cfg.belief_attribution_enabled is True
        assert cfg.salience_structured_failure_enabled is True
        assert cfg.memo_distill_enabled is True
        assert cfg.unconscious_context_enabled is True
        assert cfg.error_driven_reinterpretation_enabled is True
        assert cfg.recall_hit_boost_enabled is True
        assert cfg.error_gated_encoding_enabled is True
        assert cfg.pending_prediction_enabled is True
        assert cfg.hearsay_enabled is True
        assert cfg.state_collapse_evidence_enabled is True
        assert cfg.goal_store_enabled is True
        assert cfg.goal_revision_enabled is True
        assert cfg.goal_reflect_enabled is True
        assert cfg.goal_stagnation_evidence_enabled is True
        assert cfg.stagnation_pressure_enabled is True
        assert cfg.stagnation_reasoning_enabled is True
        assert cfg.tool_mode == "pure_spot_graph"
        assert cfg.escape_llm_ssot_enabled is True
        assert cfg.scenario_random_seed == 42

    def test_empty_string_env_default(self) -> None:
        """空文字は「未設定」と等価 (PR #434 ポリシー)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_MODEL": "",
                "OPENROUTER_PROVIDER": "",
            }
        )
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.openrouter_provider is None


class TestFromEnvFailFast:
    """typo / 不正値 → ValueError (= PR #434 ポリシー継承)。"""

    def test_runtime_config_unknown_raises_value_error(self) -> None:
        """profile の typo は既定値への縮退ではなく起動時に止まる。"""
        with pytest.raises(ValueError, match="unknown runtime_config key"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_EPOSODIC_ENABLED": "1"}
            )

    def test_runtime_config_api_key_raises_value_error(self) -> None:
        """秘密情報は profile ではなく process environment だけに置く。"""
        with pytest.raises(ValueError, match="secret key"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"OPENAI_API_KEY": "sk-secret"}
            )

    def test_short_term_memory_kind_raises_value_error(self) -> None:
        """shorttermmemorykind 短縮形は ValueError。"""
        with pytest.raises(ValueError, match="SHORT_TERM_MEMORY_KIND"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"SHORT_TERM_MEMORY_KIND": "rolling"}  # 正しくは rolling_summary
            )

    def test_scheduler_mode_unknown_raises_value_error(self) -> None:
        """scheduler mode 未知の値は ValueError。"""
        with pytest.raises(ValueError, match="SHORT_TERM_MEMORY_SCHEDULER_MODE"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"SHORT_TERM_MEMORY_SCHEDULER_MODE": "async_io"}
            )

    def test_section_order_typo_raises_value_error(self) -> None:
        """section order typo は ValueError。"""
        with pytest.raises(ValueError, match="PROMPT_SECTION_ORDER"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"PROMPT_SECTION_ORDER": "stable_to_volatil"}  # typo
            )

    def test_llm_client_unknown_raises_value_error(self) -> None:
        """llm client 未知の値は ValueError。"""
        with pytest.raises(ValueError, match="LLM_CLIENT"):
            ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_CLIENT": "ollama"})

    def test_timeout_raises_value_error(self) -> None:
        """timeout 非数値は ValueError。"""
        with pytest.raises(ValueError, match="LLM_REQUEST_TIMEOUT_SECONDS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_REQUEST_TIMEOUT_SECONDS": "ten"}
            )

    def test_episodic_enabled_typo_raises_value_error(self) -> None:
        """episodic enabled typo は ValueError。"""
        with pytest.raises(ValueError, match="boolean"):
            ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_EPISODIC_ENABLED": "yeah"})

    def test_openrouter_require_params_typo_raises_value_error(self) -> None:
        """openrouter require params typo は ValueError。"""
        with pytest.raises(ValueError, match="boolean"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"OPENROUTER_REQUIRE_PARAMS": "tru"}  # typo
            )

    def test_semantic_passive_top_k_raises_value_error_2(self) -> None:
        """semantic passive top k 非数値は ValueError。"""
        with pytest.raises(ValueError, match="SEMANTIC_PASSIVE_TOP_K"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"SEMANTIC_PASSIVE_TOP_K": "abc"}
            )

    def test_semantic_passive_top_k_raises_value_error(self) -> None:
        """semantic passive top k 負数は ValueError。"""
        with pytest.raises(ValueError, match="SEMANTIC_PASSIVE_TOP_K"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"SEMANTIC_PASSIVE_TOP_K": "-1"}
            )

    def test_llm_tool_mode_unknown_raises_value_error(self) -> None:
        """実験条件を変える tool mode の typo は fail-fast。"""
        with pytest.raises(ValueError, match="LLM_TOOL_MODE"):
            ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_TOOL_MODE": "pure"})

    def test_stagnation_reasoning_missing_raises_value_error(self) -> None:
        """熟考だけ ON で pressure / reflect が無い組み合わせは静かな失敗なので落とす。"""
        with pytest.raises(ValueError, match="STAGNATION_PRESSURE_ENABLED"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={
                    "LLM_EPISODIC_ENABLED": "1",
                    "BELIEF_CONSOLIDATION_ENABLED": "1",
                    "GOAL_REFLECT_ENABLED": "1",
                    "STAGNATION_REASONING_ENABLED": "1",
                }
            )


class TestSubjectiveEpisodeDbPath:
    """SUBJECTIVE_EPISODE_DB_PATH を単一窓口 (config) に載せる (二重入口撤去)。

    従来は ``_default_episodic_episode_store`` が os.environ を直読みしており、
    profile/config の外で episode store の永続化先が決まってしまっていた
    (manifest にも残らない silent failure)。config フィールド化して解決経路を
    from_mapping の 1 本に固定する。
    """

    def test_unset_is_none(self) -> None:
        """未設定なら None (= in-memory episode store)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.subjective_episode_db_path is None

    def test_set_resolves_to_path_when_subjective_off(self) -> None:
        """subjective OFF + episodic ON なら SUBJECTIVE_EPISODE_DB_PATH をそのまま解決する。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_EPISODIC_ENABLED": "1",
                "LLM_EPISODIC_SUBJECTIVE_ENABLED": "0",
                "SUBJECTIVE_EPISODE_DB_PATH": "  var/episodes.db  ",
            }
        )
        assert cfg.subjective_episode_db_path == "var/episodes.db"

    def test_recorded_in_trace_dict(self) -> None:
        """解決した path は run_start trace / manifest に残る (再現性)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_EPISODIC_ENABLED": "1",
                "LLM_EPISODIC_SUBJECTIVE_ENABLED": "0",
                "SUBJECTIVE_EPISODE_DB_PATH": "var/episodes.db",
            }
        )
        assert cfg.to_trace_dict()["subjective_episode_db_path"] == "var/episodes.db"

    def test_for_tests_default_none_and_override(self) -> None:
        """for_tests の default は None、override 可。"""
        assert ResolvedLlmRuntimeConfig.for_tests().subjective_episode_db_path is None
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True,
            episodic_subjective_enabled=False,
            subjective_episode_db_path="var/x.db",
        )
        assert cfg.subjective_episode_db_path == "var/x.db"

    def test_with_subjective_enabled_raises_value_error(self) -> None:
        """subjective 経路は常に in-memory なので db_path 併用は静かな無視。fail-fast で落とす。"""
        with pytest.raises(ValueError, match="SUBJECTIVE_EPISODE_DB_PATH"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={
                    "LLM_EPISODIC_ENABLED": "1",
                    "LLM_EPISODIC_SUBJECTIVE_ENABLED": "1",
                    "SUBJECTIVE_EPISODE_DB_PATH": "var/episodes.db",
                }
            )

    def test_without_episodic_raises_value_error(self) -> None:
        """episodic OFF では episode store 自体を組まないので db_path は無視される。fail-fast で落とす。"""
        with pytest.raises(ValueError, match="SUBJECTIVE_EPISODE_DB_PATH"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={
                    "LLM_EPISODIC_ENABLED": "0",
                    "LLM_EPISODIC_SUBJECTIVE_ENABLED": "0",
                    "SUBJECTIVE_EPISODE_DB_PATH": "var/episodes.db",
                }
            )


class TestFromMappingIgnoresOsEnviron:
    """引数省略時も環境変数を読まず、空設定の既定値になる。"""

    def test_values_os_environ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """values 省略時も os environ を読まない。"""
        monkeypatch.setenv("SHORT_TERM_MEMORY_KIND", "rolling_summary")
        monkeypatch.setenv("PROMPT_SECTION_ORDER", "legacy")
        cfg = ResolvedLlmRuntimeConfig.from_mapping()
        assert cfg.short_term_memory_kind == "sliding_window"
        assert cfg.prompt_section_order == "stable_to_volatile"

    def test_subjective_episode_db_path_os_environ_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SUBJECTIVE_EPISODE_DB_PATH が env にあっても config は読まない (二重入口撤去)。"""
        monkeypatch.setenv("SUBJECTIVE_EPISODE_DB_PATH", "/tmp/leaked.db")
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.subjective_episode_db_path is None


# ──────────────────────────────────────────────────────────────────
# Immutability
# ──────────────────────────────────────────────────────────────────


class TestImmutability:
    """frozen dataclass: 構築後の改変を防ぐ (= hash 可能 / 共有 safe)。"""

    def test_field_set_frozen_instance_error(self) -> None:
        """field の set は FrozenInstanceError。"""
        from dataclasses import FrozenInstanceError

        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        with pytest.raises(FrozenInstanceError):
            cfg.short_term_memory_kind = "rolling_summary"  # type: ignore[misc]

    def test_hash(self) -> None:
        """frozen=True なので hash できる (= set / dict key に使える)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        # raise しないことを assert
        _ = hash(cfg)


# ──────────────────────────────────────────────────────────────────
# Test fixture factory
# ──────────────────────────────────────────────────────────────────


class TestForTestsFactory:
    """test fixture の肥大化を防ぐ safe default factory。"""

    def test_overrides_default_same(self) -> None:
        """overrides 無しで default と同じ。"""
        cfg_from_factory = ResolvedLlmRuntimeConfig.for_tests()
        cfg_from_mapping = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg_from_factory == cfg_from_mapping

    def test_override_keyword(self) -> None:
        """override だけ keyword で指定できる。"""
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

    def test_unknown_override_key_raises_type_error(self) -> None:
        """typo を発見する fail-fast。"""
        with pytest.raises(TypeError, match="Unknown override keys"):
            ResolvedLlmRuntimeConfig.for_tests(short_term_memory="rolling_summary")  # type: ignore[call-arg]


# ──────────────────────────────────────────────────────────────────
# Trace observability
# ──────────────────────────────────────────────────────────────────


class TestToTraceDict:
    """run_start trace 用の dict 表現。API key 必ずマスク。"""

    def test_all_dict_rendered(self) -> None:
        """全フィールドが dict に出る。"""
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
        assert "belief_evidence_enabled" in d
        assert "stagnation_reasoning_enabled" in d
        assert "tool_mode" in d

    def test_api_key(self) -> None:
        """API key の生値は絶対に trace に出さない (漏洩防止)。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key="sk-or-secret-12345")
        d = cfg.to_trace_dict()
        assert d["llm_api_key"] == "***"
        # 生値が trace dict 内のどこにも存在しない
        assert "sk-or-secret-12345" not in str(d)

    def test_api_key_none(self) -> None:
        """api key None の場合 None のまま。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key=None)
        d = cfg.to_trace_dict()
        assert d["llm_api_key"] is None


# ──────────────────────────────────────────────────────────────────
# 既存 resolver との一貫性 (= behavior equivalence)
# ──────────────────────────────────────────────────────────────────


class TestExistingResolverParity:
    """``from_mapping`` が既存 resolver と同じ値を返すことを担保する (= 移行時の
    behavior 等価)。PR 3/6 で既存 wiring を本 DTO に置き換えるときに、両経路で
    結果が一致することを構造的に保証する。"""

    def test_short_term_memory_kind_existing_resolver_matches(self) -> None:
        """shorttermmemorykind は既存 resolver と一致。"""
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_short_term_memory_kind,
        )

        values = {"SHORT_TERM_MEMORY_KIND": "rolling_summary"}
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values=values)
        assert cfg.short_term_memory_kind == resolve_short_term_memory_kind(env=values)

    def test_section_order_existing_resolver_matches(self) -> None:
        """sectionorder は既存 resolver と一致。"""
        from ai_rpg_world.application.llm.services.context_format_strategy import (
            resolve_section_order_from_env,
        )

        values = {"PROMPT_SECTION_ORDER": "legacy"}
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values=values)
        assert cfg.prompt_section_order == resolve_section_order_from_env(env=values)

    def test_semantic_passive_top_k_existing_resolver_matches(self) -> None:
        """semanticpassivetopk は既存 resolver と一致。"""
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_semantic_passive_top_k,
        )

        values = {"SEMANTIC_PASSIVE_TOP_K": "5"}
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values=values)
        assert cfg.semantic_passive_top_k == resolve_semantic_passive_top_k(env=values)
