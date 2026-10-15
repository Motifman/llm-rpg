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

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig


class TestFromEnvDefaults:
    """設定値が空なら全フィールドが「最も無害な default」になる。"""

    def test_empty_config_default_resolve(self) -> None:
        """空設定で default に resolve。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.short_term_memory_kind == 'rolling_summary'
        assert cfg.llm_client_kind == 'stub'
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base is None
        assert cfg.llm_request_timeout_seconds == 90.0
        assert cfg.llm_reasoning_effort == 'none'
        assert cfg.llm_wall_time_cap_seconds is None
        assert cfg.llm_rate_limit_retry_attempts == 3
        assert cfg.llm_rate_limit_retry_base_sleep == 2.0
        assert cfg.openrouter_provider is None
        assert cfg.openrouter_quantization is None
        assert cfg.openrouter_require_params is False
        assert cfg.episodic_enabled is False
        assert cfg.episodic_subjective_enabled is True
        assert cfg.episodic_promotion_force_full_scan is False
        assert cfg.episodic_promotion_expansion_hops == 4
        assert cfg.semantic_llm_gist_enabled is False
        assert cfg.semantic_passive_top_k == 0
        assert cfg.belief_evidence_enabled is False
        assert cfg.memo_tools_enabled is True
        assert cfg.scenario_random_seed is None
        assert cfg.prompt_dataset_capture_enabled is False
        assert cfg.prompt_dataset_capture_failure_policy == 'fail'
        assert cfg.reason_first_two_step_enabled is False

class TestPromptDatasetCaptureConfig:
    """prompt dataset capture は episodic 記憶と独立して設定できる。"""

    def test_enabled_without_episodic_is_allowed(self) -> None:
        """capture は記録機能なので episodic 無効でも有効化できる。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'PROMPT_DATASET_CAPTURE_ENABLED': '1'})
        assert cfg.prompt_dataset_capture_enabled is True
        assert cfg.episodic_enabled is False

    def test_enabled_with_episodic_resolves_failure_policy(self) -> None:
        """episodic 有効なら capture を有効化でき、保存失敗時方針も解決される。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPISODIC_ENABLED': '1', 'PROMPT_DATASET_CAPTURE_ENABLED': '1', 'PROMPT_DATASET_CAPTURE_FAILURE_POLICY': 'warn'})
        assert cfg.prompt_dataset_capture_enabled is True
        assert cfg.prompt_dataset_capture_failure_policy == 'warn'

class TestWorldTickFailurePolicyConfig:
    """WORLD_TICK_FAILURE_POLICY が実 run では取りやめ、試験の既定では止める方針に解決されること。"""

    def test_from_mapping_defaults_to_isolate(self) -> None:
        """runtime_config に書かなければ isolate に解決され、キーを書き忘れた実験設定でも run が止まらない。"""
        assert ResolvedLlmRuntimeConfig.from_mapping().world_tick_failure_policy == 'isolate'

    def test_fail_fast_can_be_selected(self) -> None:
        """fail_fast と書けば、例外で止める方針に解決される。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'WORLD_TICK_FAILURE_POLICY': 'fail_fast'})
        assert cfg.world_tick_failure_policy == 'fail_fast'

    def test_unknown_value_fails_fast(self) -> None:
        """知らない値は既定へ倒さず、キー名を含む ValueError で止める。"""
        with pytest.raises(ValueError, match='WORLD_TICK_FAILURE_POLICY'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'WORLD_TICK_FAILURE_POLICY': 'skip'})

    def test_direct_construction_rejects_unknown_value(self) -> None:
        """from_mapping を通らない構築でも、知らない値は ValueError で止める。"""
        with pytest.raises(ValueError, match='fail_fast'):
            ResolvedLlmRuntimeConfig.for_tests(world_tick_failure_policy='skip')

class TestReasonFirstTwoStepConfig:
    """reason-first 2段階ターンの有効化 flag を単一窓口で解決する。"""

    def test_unset_false(self) -> None:
        """REASON_FIRST_TWO_STEP_ENABLED 未設定なら既存 1段階 turn のまま。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.reason_first_two_step_enabled is False

    def test_truthy_true(self) -> None:
        """REASON_FIRST_TWO_STEP_ENABLED=1 で gated reason-first を有効化する。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'REASON_FIRST_TWO_STEP_ENABLED': '1'})
        assert cfg.reason_first_two_step_enabled is True

    def test_invalid_value_fail_fast(self) -> None:
        """typo は silent に OFF へ落とさず ValueError で止める。"""
        with pytest.raises(ValueError, match='REASON_FIRST_TWO_STEP_ENABLED'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'REASON_FIRST_TWO_STEP_ENABLED': 'maybe'})

    def test_trace_dict_includes_flag(self) -> None:
        """run_start / manifest から reason-first 有効化条件を後で確認できる。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(reason_first_two_step_enabled=True)
        assert cfg.to_trace_dict()['reason_first_two_step_enabled'] is True

class TestShortTermMemoryTurnWindow:
    """自分のターン単位の窓設定を、全構築経路で同じ不変条件に保つ。"""

    def test_defaults_keep_twenty_turns_and_compact_ten(self) -> None:
        """未指定時は cap 20 / 畳む数 10 を使う。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.short_term_memory_turn_cap == 20
        assert cfg.short_term_memory_turn_compact_count == 10

    def test_mapping_rejects_compaction_that_would_empty_the_window(self) -> None:
        """畳む数が cap 以上なら、実験開始前に設定を拒否する。"""
        with pytest.raises(ValueError, match='must be smaller'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'SHORT_TERM_MEMORY_TURN_CAP': '4', 'SHORT_TERM_MEMORY_TURN_COMPACT_COUNT': '4'})

    def test_direct_construction_cannot_bypass_turn_window_invariant(self) -> None:
        """for_tests でも畳んだ直後に窓を空にする値は指定できない。"""
        with pytest.raises(ValueError, match='compact_count < cap'):
            ResolvedLlmRuntimeConfig.for_tests(short_term_memory_turn_cap=4, short_term_memory_turn_compact_count=4)

class TestFromEnvExplicit:
    """設定値明示で全フィールドが正しく resolve される。"""

    def test_all_config_resolve(self) -> None:
        """全フィールド明示設定で resolve。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'SHORT_TERM_MEMORY_KIND': 'rolling_summary', 'SHORT_TERM_MEMORY_TURN_CAP': '24', 'SHORT_TERM_MEMORY_TURN_COMPACT_COUNT': '8', 'LLM_CLIENT': 'litellm', 'LLM_MODEL': 'openrouter/google/gemma-4-31b-it', 'OPENAI_API_BASE': 'https://openrouter.ai/api/v1', 'LLM_REQUEST_TIMEOUT_SECONDS': '60', 'LLM_REASONING_EFFORT': 'minimal', 'LLM_WALL_TIME_CAP_SECONDS': '65', 'LLM_RATE_LIMIT_RETRY_ATTEMPTS': '2', 'LLM_RATE_LIMIT_RETRY_BASE_SLEEP': '1.5', 'OPENROUTER_PROVIDER': 'Parasail', 'OPENROUTER_QUANTIZATION': 'fp8', 'OPENROUTER_REQUIRE_PARAMS': 'true', 'LLM_EPISODIC_ENABLED': '1', 'LLM_EPISODIC_SUBJECTIVE_ENABLED': '0', 'EPISODIC_PROMOTION_FORCE_FULL_SCAN': '1', 'EPISODIC_PROMOTION_EXPANSION_HOPS': '6', 'SEMANTIC_LLM_GIST_ENABLED': '1', 'SEMANTIC_PASSIVE_TOP_K': '3', 'BELIEF_EVIDENCE_ENABLED': '1', 'BELIEF_CONSOLIDATION_ENABLED': '1', 'BELIEF_ATTRIBUTION_ENABLED': '1', 'MEMO_TOOLS_ENABLED': '0', 'SCENARIO_RANDOM_SEED': '42'})
        assert cfg.short_term_memory_kind == 'rolling_summary'
        assert cfg.short_term_memory_turn_cap == 24
        assert cfg.short_term_memory_turn_compact_count == 8
        assert cfg.llm_client_kind == 'litellm'
        assert cfg.llm_model == 'openrouter/google/gemma-4-31b-it'
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base == 'https://openrouter.ai/api/v1'
        assert cfg.llm_request_timeout_seconds == 60.0
        assert cfg.llm_reasoning_effort == 'minimal'
        assert cfg.llm_wall_time_cap_seconds == 65.0
        assert cfg.llm_rate_limit_retry_attempts == 2
        assert cfg.llm_rate_limit_retry_base_sleep == 1.5
        assert cfg.openrouter_provider == 'Parasail'
        assert cfg.openrouter_quantization == 'fp8'
        assert cfg.openrouter_require_params is True
        assert cfg.episodic_enabled is True
        assert cfg.episodic_subjective_enabled is False
        assert cfg.episodic_promotion_force_full_scan is True
        assert cfg.episodic_promotion_expansion_hops == 6
        assert cfg.semantic_llm_gist_enabled is True
        assert cfg.semantic_passive_top_k == 3
        assert cfg.belief_evidence_enabled is True
        assert cfg.belief_consolidation_enabled is True
        assert cfg.belief_attribution_enabled is True
        assert cfg.memo_tools_enabled is False
        assert cfg.scenario_random_seed == 42

    def test_end_on_all_down_flag_defaults_off_and_can_be_enabled(self) -> None:
        """END_ON_ALL_DOWN は既定 off で、profile/runtime_config から明示的に ON にできる。"""
        assert ResolvedLlmRuntimeConfig.from_mapping().end_on_all_down is False
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'END_ON_ALL_DOWN': 'true'})
        assert cfg.end_on_all_down is True

    def test_empty_string_env_default(self) -> None:
        """空文字は「未設定」と等価 (PR #434 ポリシー)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_MODEL': '', 'OPENROUTER_PROVIDER': ''})
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.openrouter_provider is None

class TestFromEnvFailFast:
    """typo / 不正値 → ValueError (= PR #434 ポリシー継承)。"""

    def test_runtime_config_unknown_raises_value_error(self) -> None:
        """profile の typo は既定値への縮退ではなく起動時に止まる。"""
        with pytest.raises(ValueError, match='unknown runtime_config key'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPOSODIC_ENABLED': '1'})

    def test_runtime_config_api_key_raises_value_error(self) -> None:
        """秘密情報は profile ではなく process environment だけに置く。"""
        with pytest.raises(ValueError, match='secret key'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'OPENAI_API_KEY': 'sk-secret'})

    def test_short_term_memory_kind_raises_value_error(self) -> None:
        """shorttermmemorykind 短縮形は ValueError。"""
        with pytest.raises(ValueError, match='SHORT_TERM_MEMORY_KIND'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'SHORT_TERM_MEMORY_KIND': 'rolling'})

    def test_llm_client_unknown_raises_value_error(self) -> None:
        """llm client 未知の値は ValueError。"""
        with pytest.raises(ValueError, match='LLM_CLIENT'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_CLIENT': 'ollama'})

    def test_timeout_raises_value_error(self) -> None:
        """timeout 非数値は ValueError。"""
        with pytest.raises(ValueError, match='LLM_REQUEST_TIMEOUT_SECONDS'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_REQUEST_TIMEOUT_SECONDS': 'ten'})

    def test_episodic_enabled_typo_raises_value_error(self) -> None:
        """episodic enabled typo は ValueError。"""
        with pytest.raises(ValueError, match='boolean'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPISODIC_ENABLED': 'yeah'})

    def test_openrouter_require_params_typo_raises_value_error(self) -> None:
        """openrouter require params typo は ValueError。"""
        with pytest.raises(ValueError, match='boolean'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'OPENROUTER_REQUIRE_PARAMS': 'tru'})

    def test_semantic_passive_top_k_raises_value_error_2(self) -> None:
        """semantic passive top k 非数値は ValueError。"""
        with pytest.raises(ValueError, match='SEMANTIC_PASSIVE_TOP_K'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'SEMANTIC_PASSIVE_TOP_K': 'abc'})

    def test_semantic_passive_top_k_raises_value_error(self) -> None:
        """semantic passive top k 負数は ValueError。"""
        with pytest.raises(ValueError, match='SEMANTIC_PASSIVE_TOP_K'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'SEMANTIC_PASSIVE_TOP_K': '-1'})


class TestTheRemovedMemoryPartKeysAreRejected:
    """消した記憶の部品 (#1631) のキーを profile に書くと、未知のキーとして起動前に落ちることを保証する。

    黙って無視すると、部品を有効にしたつもりの run が部品なしで走る。
    """

    @pytest.mark.parametrize(
        "key",
        [
            "STATE_COLLAPSE_EVIDENCE_ENABLED",
            "SALIENCE_STRUCTURED_FAILURE_ENABLED",
            "HEARSAY_ENABLED",
            "ERROR_GATED_ENCODING_ENABLED",
            "LLM_EXPECTED_RESULT_POLICY",
            "EXPECTATION_ARGUMENT_ENABLED",
            "EXPECTATION_UNDATED_TERM_TURNS",
            "EXPECTATION_DATED_TERM_TURNS",
            "EXPECTATION_SETTLEMENT_ENABLED",
            "EXPECTATION_SETTLEMENT_MAX_OPEN",
            "EXPECTATION_SETTLEMENT_TIMELINE_TURNS",
            "EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS",
            "EXPECTATION_GROUNDS_MAX_QUESTIONS",
            "EXPECTATION_GROUNDS_MIN_PROBABILITY",
            "MEMO_DISTILL_ENABLED",
            "SITUATION_BELIEF_RECALL_ENABLED",
            "SITUATION_BELIEF_RECALL_NARROWER",
            "TYPED_JUDGMENT_GOAL_HINT_ENABLED",
            "TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY",
            "STAGNATION_REASONING_ENABLED",
            "STAGNATION_PRESSURE_ENABLED",
            "GOAL_STAGNATION_EVIDENCE_ENABLED",
            "GOAL_REVISION_ENABLED",
            "GOAL_REFLECT_ENABLED",
            "GOAL_STORE_ENABLED",
            "PREDICTION_CONTEXT_ID_ENABLED",
            "UNCONSCIOUS_CONTEXT_ENABLED",
            "PENDING_PREDICTION_ENABLED",
            "ERROR_DRIVEN_REINTERPRETATION_ENABLED",
            "LLM_EPISODIC_REINTERPRETATION_ENABLED",
            "ESCAPE_LLM_SSOT",
            "PROMPT_SECTION_ORDER",
            "SHORT_TERM_MEMORY_SCHEDULER_MODE",
            "LLM_TOOL_MODE",
            "LLM_MEETING_SERIAL_TURNS",
            "EPISODIC_RECALL_ENABLED",
            "EPISODIC_EXPLORE_RELATED_ENABLED",
            "SEMANTIC_SEARCH_ENABLED",
            "LLM_AFTERGLOW_ENABLED",
            "LLM_AFTERGLOW_CAPACITY",
            "LLM_AFTERGLOW_MAX_RESIDENCE",
            "RECALL_HIT_BOOST_ENABLED",
            "LLM_EPISODIC_RECALL_HABITUATION_ENABLED",
            "LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS",
            "LLM_EPISODIC_RECALL_SLOT_ENABLED",
            "LLM_EPISODIC_RECALL_SLOT_CAPACITY",
            "LLM_EPISODIC_RECALL_SLOT_INSERT_PER_TICK",
            "LLM_EPISODIC_RECALL_SLOT_MAX_RESIDENCE",
            "LLM_EPISODIC_RECALL_SLOT_COOLDOWN",
            "LLM_EPISODIC_RECALL_SLOT_INSERT_SCORE_THRESHOLD",
        ],
    )
    def test_a_removed_memory_part_key_is_rejected_as_unknown(self, key: str) -> None:
        """消した部品のキーを true で書くと、unknown runtime_config key の ValueError になる。"""
        with pytest.raises(ValueError, match=f"unknown runtime_config key.*{key}"):
            ResolvedLlmRuntimeConfig.from_mapping(values={key: "true"})


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
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPISODIC_ENABLED': '1', 'LLM_EPISODIC_SUBJECTIVE_ENABLED': '0', 'SUBJECTIVE_EPISODE_DB_PATH': '  var/episodes.db  '})
        assert cfg.subjective_episode_db_path == 'var/episodes.db'

    def test_recorded_in_trace_dict(self) -> None:
        """解決した path は run_start trace / manifest に残る (再現性)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPISODIC_ENABLED': '1', 'LLM_EPISODIC_SUBJECTIVE_ENABLED': '0', 'SUBJECTIVE_EPISODE_DB_PATH': 'var/episodes.db'})
        assert cfg.to_trace_dict()['subjective_episode_db_path'] == 'var/episodes.db'

    def test_for_tests_default_none_and_override(self) -> None:
        """for_tests の default は None、override 可。"""
        assert ResolvedLlmRuntimeConfig.for_tests().subjective_episode_db_path is None
        cfg = ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True, episodic_subjective_enabled=False, subjective_episode_db_path='var/x.db')
        assert cfg.subjective_episode_db_path == 'var/x.db'

    def test_with_subjective_enabled_raises_value_error(self) -> None:
        """subjective 経路は常に in-memory なので db_path 併用は静かな無視。fail-fast で落とす。"""
        with pytest.raises(ValueError, match='SUBJECTIVE_EPISODE_DB_PATH'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPISODIC_ENABLED': '1', 'LLM_EPISODIC_SUBJECTIVE_ENABLED': '1', 'SUBJECTIVE_EPISODE_DB_PATH': 'var/episodes.db'})

    def test_without_episodic_raises_value_error(self) -> None:
        """episodic OFF では episode store 自体を組まないので db_path は無視される。fail-fast で落とす。"""
        with pytest.raises(ValueError, match='SUBJECTIVE_EPISODE_DB_PATH'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_EPISODIC_ENABLED': '0', 'LLM_EPISODIC_SUBJECTIVE_ENABLED': '0', 'SUBJECTIVE_EPISODE_DB_PATH': 'var/episodes.db'})

class TestFromMappingIgnoresOsEnviron:
    """引数省略時も環境変数を読まず、空設定の既定値になる。"""

    def test_values_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """values 省略時も os environ を読まない。"""
        monkeypatch.setenv('SHORT_TERM_MEMORY_KIND', 'sliding_window')
        cfg = ResolvedLlmRuntimeConfig.from_mapping()
        assert cfg.short_term_memory_kind == 'rolling_summary'

    def test_subjective_episode_db_path_os_environ_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SUBJECTIVE_EPISODE_DB_PATH が env にあっても config は読まない (二重入口撤去)。"""
        monkeypatch.setenv('SUBJECTIVE_EPISODE_DB_PATH', '/tmp/leaked.db')
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.subjective_episode_db_path is None

class TestImmutability:
    """frozen dataclass: 構築後の改変を防ぐ (= hash 可能 / 共有 safe)。"""

    def test_field_set_frozen_instance_error(self) -> None:
        """field の set は FrozenInstanceError。"""
        from dataclasses import FrozenInstanceError
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        with pytest.raises(FrozenInstanceError):
            cfg.short_term_memory_kind = 'rolling_summary'

    def test_hash(self) -> None:
        """frozen=True なので hash できる (= set / dict key に使える)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        _ = hash(cfg)

class TestForTestsFactory:
    """test fixture の肥大化を防ぐ safe default factory。"""

    def test_overrides_default_same(self) -> None:
        """overrides 無しで default と同じ。"""
        cfg_from_factory = ResolvedLlmRuntimeConfig.for_tests()
        cfg_from_mapping = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg_from_factory == cfg_from_mapping

    def test_override_keyword(self) -> None:
        """override だけ keyword で指定できる。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(short_term_memory_kind='rolling_summary', llm_client_kind='litellm')
        assert cfg.short_term_memory_kind == 'rolling_summary'
        assert cfg.llm_client_kind == 'litellm'
        assert cfg.semantic_passive_top_k == 0

    def test_unknown_override_key_raises_type_error(self) -> None:
        """typo を発見する fail-fast。"""
        with pytest.raises(TypeError, match='Unknown override keys'):
            ResolvedLlmRuntimeConfig.for_tests(short_term_memory='rolling_summary')

class TestToTraceDict:
    """run_start trace 用の dict 表現。API key 必ずマスク。"""

    def test_all_dict_rendered(self) -> None:
        """全フィールドが dict に出る。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(short_term_memory_kind='rolling_summary', llm_client_kind='litellm', llm_model='openrouter/google/gemma-4-31b-it')
        d = cfg.to_trace_dict()
        assert d['short_term_memory_kind'] == 'rolling_summary'
        assert d['llm_client_kind'] == 'litellm'
        assert d['llm_model'] == 'openrouter/google/gemma-4-31b-it'
        assert 'belief_evidence_enabled' in d

    def test_api_key(self) -> None:
        """API key の生値は絶対に trace に出さない (漏洩防止)。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key='sk-or-secret-12345')
        d = cfg.to_trace_dict()
        assert d['llm_api_key'] == '***'
        assert 'sk-or-secret-12345' not in str(d)

    def test_api_key_none(self) -> None:
        """api key None の場合 None のまま。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_api_key=None)
        d = cfg.to_trace_dict()
        assert d['llm_api_key'] is None

class TestExistingResolverParity:
    """``from_mapping`` が既存 resolver と同じ値を返すことを担保する (= 移行時の
    behavior 等価)。PR 3/6 で既存 wiring を本 DTO に置き換えるときに、両経路で
    結果が一致することを構造的に保証する。"""

    def test_short_term_memory_kind_existing_resolver_matches(self) -> None:
        """shorttermmemorykind は既存 resolver と一致。"""
        from ai_rpg_world.application.llm.wiring.feature_flags import resolve_short_term_memory_kind
        values = {'SHORT_TERM_MEMORY_KIND': 'rolling_summary'}
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values=values)
        assert cfg.short_term_memory_kind == resolve_short_term_memory_kind(env=values)

    def test_semantic_passive_top_k_existing_resolver_matches(self) -> None:
        """semanticpassivetopk は既存 resolver と一致。"""
        from ai_rpg_world.application.llm.wiring.feature_flags import resolve_semantic_passive_top_k
        values = {'SEMANTIC_PASSIVE_TOP_K': '5'}
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values=values)
        assert cfg.semantic_passive_top_k == resolve_semantic_passive_top_k(env=values)
