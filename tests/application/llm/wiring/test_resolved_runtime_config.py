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
        assert cfg.llm_client_kind == 'stub'
        assert cfg.llm_model is None
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base is None
        assert cfg.llm_request_timeout_seconds == 90.0
        assert cfg.llm_reasoning_effort == 'minimal'
        assert cfg.llm_wall_time_cap_seconds is None
        assert cfg.llm_rate_limit_retry_attempts == 3
        assert cfg.llm_rate_limit_retry_base_sleep == 2.0
        assert cfg.openrouter_provider is None
        assert cfg.openrouter_quantization is None
        assert cfg.scenario_random_seed is None
        assert cfg.prompt_dataset_capture_failure_policy == 'fail'
        assert cfg.reason_first_two_step_enabled is True

class TestPromptDatasetCaptureConfig:
    """prompt dataset の保存に失敗したときの方針を解決する。"""

    def test_failure_policy_resolves_to_warn(self) -> None:
        """PROMPT_DATASET_CAPTURE_FAILURE_POLICY に warn を書くと、保存失敗時の方針が warn になる。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'PROMPT_DATASET_CAPTURE_FAILURE_POLICY': 'warn'})
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

class TestReasoningEffortDefault:
    """LLM_REASONING_EFFORT の既定は minimal で、明示した値はそのまま使う。"""

    def test_unset_resolves_to_minimal(self) -> None:
        """LLM_REASONING_EFFORT を書かないと minimal になる。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.llm_reasoning_effort == 'minimal'

    def test_explicit_none_stays_none(self) -> None:
        """LLM_REASONING_EFFORT に none と書けば、既定の minimal ではなく none のまま。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_REASONING_EFFORT': 'none'})
        assert cfg.llm_reasoning_effort == 'none'

class TestReasonFirstTwoStepConfig:
    """reason-first 2段階ターンを使うかを、設定のキーではなく tool_choice から決める。"""

    def test_required_enables_it(self) -> None:
        """何も書かない (tool_choice は既定の required) と、gated reason-first を使う。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.reason_first_two_step_enabled is True

    def test_for_tests_follows_the_tool_choice(self) -> None:
        """for_tests も本番と同じく、tool_choice が auto なら使わず、required なら使う。"""
        assert ResolvedLlmRuntimeConfig.for_tests().reason_first_two_step_enabled is True
        assert ResolvedLlmRuntimeConfig.for_tests(llm_tool_choice='auto').reason_first_two_step_enabled is False

    def test_trace_dict_includes_flag(self) -> None:
        """run_start / manifest から reason-first を使ったかを後で確認できる。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
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
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={'SHORT_TERM_MEMORY_TURN_CAP': '24', 'SHORT_TERM_MEMORY_TURN_COMPACT_COUNT': '8', 'LLM_CLIENT': 'litellm', 'LLM_MODEL': 'openrouter/google/gemma-4-31b-it', 'OPENAI_API_BASE': 'https://openrouter.ai/api/v1', 'LLM_REQUEST_TIMEOUT_SECONDS': '60', 'LLM_REASONING_EFFORT': 'low', 'LLM_WALL_TIME_CAP_SECONDS': '65', 'LLM_RATE_LIMIT_RETRY_ATTEMPTS': '2', 'LLM_RATE_LIMIT_RETRY_BASE_SLEEP': '1.5', 'OPENROUTER_PROVIDER': 'Parasail', 'OPENROUTER_QUANTIZATION': 'fp8', 'SCENARIO_RANDOM_SEED': '42'})
        assert cfg.short_term_memory_turn_cap == 24
        assert cfg.short_term_memory_turn_compact_count == 8
        assert cfg.llm_client_kind == 'litellm'
        assert cfg.llm_model == 'openrouter/google/gemma-4-31b-it'
        assert cfg.llm_api_key is None
        assert cfg.llm_api_base == 'https://openrouter.ai/api/v1'
        assert cfg.llm_request_timeout_seconds == 60.0
        assert cfg.llm_reasoning_effort == 'low'
        assert cfg.llm_wall_time_cap_seconds == 65.0
        assert cfg.llm_rate_limit_retry_attempts == 2
        assert cfg.llm_rate_limit_retry_base_sleep == 1.5
        assert cfg.openrouter_provider == 'Parasail'
        assert cfg.openrouter_quantization == 'fp8'
        assert cfg.scenario_random_seed == 42

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

    def test_llm_client_unknown_raises_value_error(self) -> None:
        """llm client 未知の値は ValueError。"""
        with pytest.raises(ValueError, match='LLM_CLIENT'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_CLIENT': 'ollama'})

    def test_timeout_raises_value_error(self) -> None:
        """timeout 非数値は ValueError。"""
        with pytest.raises(ValueError, match='LLM_REQUEST_TIMEOUT_SECONDS'):
            ResolvedLlmRuntimeConfig.from_mapping(values={'LLM_REQUEST_TIMEOUT_SECONDS': 'ten'})

class TestTheRemovedMemoryPartKeysAreRejected:
    """消した記憶の部品 (#1631) のキーを profile に書くと、未知のキーとして起動前に落ちることを保証する。

    黙って無視すると、部品を有効にしたつもりの run が部品なしで走る。
    """

    @pytest.mark.parametrize(
        "key",
        [
            "STATE_COLLAPSE_EVIDENCE_ENABLED",
            "BELIEF_EVIDENCE_ENABLED",
            "LLM_EPISODIC_ENABLED",
            "LLM_EPISODIC_SUBJECTIVE_ENABLED",
            "SUBJECTIVE_EPISODE_DB_PATH",
            "EPISODIC_PROMOTION_EXPANSION_HOPS",
            "EPISODIC_PROMOTION_FORCE_FULL_SCAN",
            "SEMANTIC_LLM_GIST_ENABLED",
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
            "SHORT_TERM_MEMORY_KIND",
            "OPENROUTER_REQUIRE_PARAMS",
            "DISTANT_VIEW_TRACE_ENABLED",
            "END_ON_ALL_DOWN",
            "PROMPT_DATASET_CAPTURE_ENABLED",
            "REASON_FIRST_TWO_STEP_ENABLED",
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
            "SEMANTIC_PASSIVE_TOP_K",
            "BELIEF_CREATE_GATE_ENABLED",
            "BELIEF_CREATE_GATE_MIN_CONFIDENCE",
            "BELIEF_CANDIDATE_NARROWER",
            "BELIEF_CANDIDATE_TOP_K",
            "BELIEF_CONSOLIDATION_ENABLED",
            "BELIEF_ATTRIBUTION_ENABLED",
            "MEMO_TOOLS_ENABLED",
        ],
    )
    def test_a_removed_memory_part_key_is_rejected_as_unknown(self, key: str) -> None:
        """消した部品のキーを true で書くと、unknown runtime_config key の ValueError になる。"""
        with pytest.raises(ValueError, match=f"unknown runtime_config key.*{key}"):
            ResolvedLlmRuntimeConfig.from_mapping(values={key: "true"})


class TestFromMappingIgnoresOsEnviron:
    """引数省略時も環境変数を読まず、空設定の既定値になる。"""

    def test_values_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """values 省略時も os environ を読まない。"""
        monkeypatch.setenv('SHORT_TERM_MEMORY_TURN_CAP', '99')
        cfg = ResolvedLlmRuntimeConfig.from_mapping()
        assert cfg.short_term_memory_turn_cap == 20

class TestImmutability:
    """frozen dataclass: 構築後の改変を防ぐ (= hash 可能 / 共有 safe)。"""

    def test_field_set_frozen_instance_error(self) -> None:
        """field の set は FrozenInstanceError。"""
        from dataclasses import FrozenInstanceError
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        with pytest.raises(FrozenInstanceError):
            cfg.llm_client_kind = 'litellm'

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
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_client_kind='litellm')
        assert cfg.llm_client_kind == 'litellm'

    def test_unknown_override_key_raises_type_error(self) -> None:
        """typo を発見する fail-fast。"""
        with pytest.raises(TypeError, match='Unknown override keys'):
            ResolvedLlmRuntimeConfig.for_tests(short_term_memory='rolling_summary')

class TestToTraceDict:
    """run_start trace 用の dict 表現。API key 必ずマスク。"""

    def test_all_dict_rendered(self) -> None:
        """全フィールドが dict に出る。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_client_kind='litellm', llm_model='openrouter/google/gemma-4-31b-it')
        d = cfg.to_trace_dict()
        assert d['short_term_memory_turn_cap'] == 20
        assert d['llm_client_kind'] == 'litellm'
        assert d['llm_model'] == 'openrouter/google/gemma-4-31b-it'
        assert 'being_memo_enabled' in d

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
