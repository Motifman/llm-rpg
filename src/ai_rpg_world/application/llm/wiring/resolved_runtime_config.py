"""``ResolvedLlmRuntimeConfig``: 実験設定から解決した LLM runtime 全設定を 1 か所に集約する frozen DTO。

# 何のため

PR #443 で連続発覚した silent failure (PR #439 / #441 / #444 / #446) の構造的
共通原因は「**env を読む経路が複数あり、各経路が独立に解釈する**」ことだった
(architect レビュー PR #444 後)。

- ``run_scenario_experiment.py`` が env を読んで run_start trace に書く
- ``wiring/_build_short_term_memory`` が env を読んで kind を解決する
- ``demos/world_runtime/world_runtime.py`` が **別経路で** env を読んで
  ``DefaultSlidingWindowMemory`` を直接作る (PR #439 で fix した silent failure
  の原因)
- ``demos/world_runtime/world_runtime.py`` が **また別経路で** env を読み
  忘れて ``SectionBasedContextFormatStrategy()`` を ClassVar で作る (PR #446
  で fix した silent failure)
- ``LiteLLMClient`` が env を読んで model / api_base / timeout を解決
- ``LiteLLMClient`` が **また別経路で** OpenRouter routing を解決

これらは各箇所で fail-fast 化 (PR #434) されているが、**「全部の経路で解決
結果が同じ」を構造で保証する仕組みがない**。trace に書かれた値と実体が
ズレうる。

本 DTO は profile/config の値を解決する単一窓口として定義し、entrypoint
(``run_scenario_experiment.py`` 等) で ``ResolvedLlmRuntimeConfig.from_mapping()``
を呼び、wiring 関数の引数として渡し回す形に統一する (PR 3/6 で実施)。

# 設計指針

1. **immutable** (``frozen=True``): 構築後に値が変わらない / hash 可能
2. **fail-fast**: 設定値の typo / 不正値は ``from_mapping`` で即 ``ValueError``
   (PR #434 ポリシー継承)
3. **外側 shell を読まない**: ``from_mapping`` は引数 mapping だけを読む
4. **trace 表現**: ``to_trace_dict()`` で run_start payload に書ける dict を返す
5. **既存 resolver の活用**: 内部で既存 ``resolve_short_term_memory_kind`` 等を
   呼ぶ薄いラッパー (= 段階移行可能 / behavior 等価)

# 将来計画

- PR 2/6 (本 PR): DTO 定義 + ``from_mapping`` 実装 + tests
- PR 3/6: 既存 entrypoint / wiring を DTO ベースに移行
  (``_build_short_term_memory_from_mapping`` 等の env 直読 helper を廃止)
- PR 4/6: ``NullTraceRecorder`` と組み合わせて全 wiring に同一 instance を渡す
- PR 6/6: Builder pattern で staged construction を強制 → setter 後注入を廃止
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


SUPPORTED_RUNTIME_CONFIG_KEYS = frozenset({
    "BELIEF_ATTRIBUTION_ENABLED",
    "BELIEF_CONSOLIDATION_ENABLED",
    "BELIEF_EVIDENCE_ENABLED",
    "EPISODIC_EXPLORE_RELATED_ENABLED",
    "EPISODIC_PROMOTION_EXPANSION_HOPS",
    "EPISODIC_PROMOTION_FORCE_FULL_SCAN",
    "EPISODIC_RECALL_ENABLED",
    "ERROR_DRIVEN_REINTERPRETATION_ENABLED",
    "ERROR_GATED_ENCODING_ENABLED",
    "ESCAPE_LLM_SSOT",
    "GOAL_REFLECT_ENABLED",
    "GOAL_REVISION_ENABLED",
    "GOAL_STAGNATION_EVIDENCE_ENABLED",
    "GOAL_STORE_ENABLED",
    "HEARSAY_ENABLED",
    "LLM_AFTERGLOW_CAPACITY",
    "LLM_AFTERGLOW_ENABLED",
    "LLM_AFTERGLOW_MAX_RESIDENCE",
    "LLM_CLIENT",
    "LLM_EPISODIC_ENABLED",
    "LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS",
    "LLM_EPISODIC_RECALL_HABITUATION_ENABLED",
    "LLM_EPISODIC_RECALL_SLOT_CAPACITY",
    "LLM_EPISODIC_RECALL_SLOT_COOLDOWN",
    "LLM_EPISODIC_RECALL_SLOT_ENABLED",
    "LLM_EPISODIC_RECALL_SLOT_INSERT_PER_TICK",
    "LLM_EPISODIC_RECALL_SLOT_INSERT_SCORE_THRESHOLD",
    "LLM_EPISODIC_RECALL_SLOT_MAX_RESIDENCE",
    "LLM_EPISODIC_REINTERPRETATION_ENABLED",
    "LLM_EPISODIC_SUBJECTIVE_ENABLED",
    "LLM_EXPECTED_RESULT_POLICY",
    "LLM_IDLE_TIMEOUT_TICKS",
    "LLM_MODEL",
    "LLM_RATE_LIMIT_RETRY_ATTEMPTS",
    "LLM_RATE_LIMIT_RETRY_BASE_SLEEP",
    "LLM_REASONING_EFFORT",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "LLM_TOOL_MODE",
    "LLM_TURN_PARALLEL_WORKERS",
    "LLM_WALL_TIME_CAP_SECONDS",
    "MEMO_DISTILL_ENABLED",
    "OPENAI_API_BASE",
    "OPENROUTER_PROVIDER",
    "OPENROUTER_QUANTIZATION",
    "OPENROUTER_REQUIRE_PARAMS",
    "PENDING_PREDICTION_ENABLED",
    "PREDICTION_CONTEXT_ID_ENABLED",
    "PROMPT_SECTION_ORDER",
    "RECALL_HIT_BOOST_ENABLED",
    "SALIENCE_STRUCTURED_FAILURE_ENABLED",
    "SCENARIO_RANDOM_SEED",
    "SEMANTIC_LLM_GIST_ENABLED",
    "SEMANTIC_PASSIVE_TOP_K",
    "SEMANTIC_SEARCH_ENABLED",
    "SHORT_TERM_MEMORY_KIND",
    "SHORT_TERM_MEMORY_SCHEDULER_MODE",
    "STAGNATION_PRESSURE_ENABLED",
    "STAGNATION_REASONING_ENABLED",
    "STATE_COLLAPSE_EVIDENCE_ENABLED",
    "SUBJECTIVE_EPISODE_DB_PATH",
    "UNCONSCIOUS_CONTEXT_ENABLED",
})

_SECRET_ENV_ONLY_KEYS = frozenset({"OPENAI_API_KEY"})


@dataclass(frozen=True)
class ResolvedLlmRuntimeConfig:
    """env から resolve した LLM runtime 設定の単一 source of truth (PR #446 後続)。

    各フィールドは「**resolve 済み**」の最終値を持つ。env を直読する経路を本
    DTO の ``from_mapping`` だけに集約することで、PR #439 / #446 のような「同 env を
    2 箇所で別解釈する silent failure」を構造で防ぐ。

    Attributes:
        # === Short-term memory (Phase 2) ===
        short_term_memory_kind: ``"sliding_window"`` | ``"rolling_summary"``
        short_term_memory_scheduler_mode: ``"inline"`` | ``"thread_pool"``

        # === Prompt section ordering (Phase 0) ===
        prompt_section_order: ``"stable_to_volatile"`` | ``"legacy"``

        # === LLM client / model ===
        llm_client_kind: ``"stub"`` | ``"litellm"``
        llm_model: model 名 (例: ``"openrouter/google/gemma-4-31b-it"``)。
            未設定なら None (= LiteLLMClient default)
        llm_api_key: ``OPENAI_API_KEY`` の値。実 LLM を呼ぶときに必要
        llm_api_base: ``OPENAI_API_BASE`` の値 (vLLM / OpenRouter で必要)
        llm_request_timeout_seconds: litellm の request timeout (PR #444 で
            導入された long-tail hang 対策)

        # === OpenRouter provider routing (PR #426) ===
        openrouter_provider: provider 名 (例: ``"Parasail"``)。未設定なら None
        openrouter_quantization: quant 指定 (例: ``"fp8"``)。未設定なら None
        openrouter_require_params: True なら必須 param 全対応 provider のみ

        # === Episodic memory (Phase 1a / Phase B) ===
        episodic_enabled: ``LLM_EPISODIC_ENABLED=1`` で ON
        episodic_explore_related_enabled: ``EPISODIC_EXPLORE_RELATED_ENABLED=1``
            で memory_explore_related tool を露出

        # === Semantic memory (Phase 1b-1d) ===
        semantic_llm_gist_enabled: ``SEMANTIC_LLM_GIST_ENABLED=1`` で episodic →
            semantic 昇格時に LLM 要約を生成
        semantic_passive_top_k: ``SEMANTIC_PASSIVE_TOP_K`` 整数。>0 で prompt
            に §learned section が出る
        semantic_search_enabled: ``SEMANTIC_SEARCH_ENABLED=1`` で能動 semantic
            検索 tool を露出
    """

    # Short-term memory
    short_term_memory_kind: str
    short_term_memory_scheduler_mode: str

    # Prompt
    prompt_section_order: str

    # LLM client
    llm_client_kind: str
    llm_model: Optional[str]
    llm_api_key: Optional[str]
    llm_api_base: Optional[str]
    llm_request_timeout_seconds: float
    llm_reasoning_effort: str
    llm_wall_time_cap_seconds: Optional[float]
    llm_rate_limit_retry_attempts: int
    llm_rate_limit_retry_base_sleep: float
    llm_turn_parallel_workers: int
    llm_idle_timeout_ticks: int

    # OpenRouter routing
    openrouter_provider: Optional[str]
    openrouter_quantization: Optional[str]
    openrouter_require_params: bool

    # Episodic memory
    episodic_enabled: bool
    episodic_subjective_enabled: bool
    episodic_explore_related_enabled: bool
    episodic_promotion_force_full_scan: bool
    episodic_promotion_expansion_hops: int

    # Semantic memory
    semantic_llm_gist_enabled: bool
    semantic_passive_top_k: int
    semantic_search_enabled: bool

    # Prediction (#526): 行動前の予測 expected_result を core action tool の
    # schema に露出するか。``"off"`` (露出せず挙動不変) | ``"optional"`` (schema
    # に出すが required にしない) | ``"required"`` (毎ターン必須)。
    expected_result_policy: str

    # Prediction (#526 / U3): 段1=LLM 駆動のエピソード再解釈 (credit assignment) を
    # 有効化するか。``LLM_EPISODIC_REINTERPRETATION_ENABLED=1`` で ON。default OFF で
    # 従来の episodic-only 動作 (再解釈を組まない)。
    episodic_reinterpretation_enabled: bool

    # #526 段階 2: 慣化ペナルティ (recall された episode のスコアを decay_window
    # tick の間だけ下げる)。``LLM_EPISODIC_RECALL_HABITUATION_ENABLED=1`` で ON。
    # default OFF で既存挙動と完全同一。decay_window は
    # ``LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS`` で 0 以上の整数で上書き可。
    recall_habituation_enabled: bool = False
    recall_habituation_decay_window_ticks: int = 5

    # #526 段階 3: 想起スロット (working memory)。
    # ``LLM_EPISODIC_RECALL_SLOT_ENABLED=1`` で ON、各パラメータは env で
    # 上書き可:
    #   ``LLM_EPISODIC_RECALL_SLOT_CAPACITY``           (N)
    #   ``LLM_EPISODIC_RECALL_SLOT_INSERT_PER_TICK``    (K_insert)
    #   ``LLM_EPISODIC_RECALL_SLOT_MAX_RESIDENCE``      (L)
    #   ``LLM_EPISODIC_RECALL_SLOT_COOLDOWN``           (C)
    #   ``LLM_EPISODIC_RECALL_SLOT_INSERT_SCORE_THRESHOLD`` (score 閾値)
    #
    # PR-A: slot を「希少資源」化する default に更新。
    # N=4 / K_insert=1 / L=8 / C=5 / threshold=2。
    # K=1 で 1 tick で 1 件しか入れ替えないため recall section の前半が
    # 安定し、prefix cache が育つ。閾値 2 で「2 軸以上の cue で当たった
    # 強い signal だけ」が slot に入る (弱い候補は後段の Afterglow 行き)。
    recall_slot_enabled: bool = False
    recall_slot_capacity: int = 4
    recall_slot_insert_per_tick: int = 1
    recall_slot_max_residence: int = 8
    recall_slot_cooldown_ticks: int = 5
    recall_slot_insert_score_threshold: int = 2

    # #526 段階 3 PR-C: afterglow index (= ぼんやり覚えてる 1 行見出し)。
    # ``LLM_AFTERGLOW_ENABLED=1`` で ON (要 slot enable)。容量 M と滞在期間
    # M_L は env で上書き可:
    #   ``LLM_AFTERGLOW_CAPACITY``       (default 10)
    #   ``LLM_AFTERGLOW_MAX_RESIDENCE``  (default 10 tick)
    afterglow_enabled: bool = False
    afterglow_capacity: int = 10
    afterglow_max_residence: int = 10

    # Active episodic recall tool (Issue #526 後続)。
    episodic_recall_enabled: bool = False

    # Prediction / belief / semantic journal 系。いずれも実験条件を変える
    # flag なので、run_start / manifest に残すため本 DTO に集約する。
    prediction_context_id_enabled: bool = False
    belief_evidence_enabled: bool = False
    belief_consolidation_enabled: bool = False
    belief_attribution_enabled: bool = False
    salience_structured_failure_enabled: bool = False
    memo_distill_enabled: bool = False
    unconscious_context_enabled: bool = False
    error_driven_reinterpretation_enabled: bool = False
    recall_hit_boost_enabled: bool = False
    error_gated_encoding_enabled: bool = False
    pending_prediction_enabled: bool = False
    hearsay_enabled: bool = False
    state_collapse_evidence_enabled: bool = False

    # Goal / stagnation 系。
    goal_store_enabled: bool = False
    goal_revision_enabled: bool = False
    goal_reflect_enabled: bool = False
    goal_stagnation_evidence_enabled: bool = False
    stagnation_pressure_enabled: bool = False
    stagnation_reasoning_enabled: bool = False

    # Prompt / tool 表面。``tool_mode`` は TODO 系 tool の露出を切り替えるため、
    # 実験条件として trace に残す。``escape_llm_ssot_enabled`` は system prompt
    # 文字列を変えるため同じく実験条件。
    tool_mode: str = "default"
    escape_llm_ssot_enabled: bool = False
    scenario_random_seed: Optional[int] = None

    # Episode store の永続化先 (``SUBJECTIVE_EPISODE_DB_PATH``)。None なら in-memory。
    # 実 path 指定時は SQLite 永続化。従来 ``_default_episodic_episode_store`` が
    # os.environ を直読みしており profile/manifest の外で決まっていた
    # (PR #736 の単一窓口化で取り残されていた env)。config に載せ替えて
    # 解決経路を from_mapping の 1 本に固定し、run_start / manifest に残す。
    subjective_episode_db_path: Optional[str] = None

    # ──────────────────────────────────────────────────────────────
    # Invariants
    # ──────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """frozen DTO の不変条件を全構築経路で検証する (silent failure の構造的対処)。

        ``from_mapping`` は env typo を resolver 段で fail-fast 化しているが、
        ``for_tests`` / ``cls(...)`` 直接構築はそこを通らない。policy のような
        enum 的フィールドは、どの構築経路でも未知値が silent に通らないよう
        本メソッドで一括検証する (codex PR #557 レビュー反映)。
        """
        if self.expected_result_policy not in _VALID_EXPECTED_RESULT_POLICIES:
            raise ValueError(
                f"expected_result_policy={self.expected_result_policy!r} is not recognized. "
                f"valid: {sorted(_VALID_EXPECTED_RESULT_POLICIES)}"
            )
        if self.tool_mode not in _VALID_TOOL_MODES:
            raise ValueError(
                f"tool_mode={self.tool_mode!r} is not recognized. "
                f"valid: {sorted(_VALID_TOOL_MODES)}"
            )
        if self.llm_reasoning_effort not in _VALID_REASONING_EFFORTS:
            raise ValueError(
                f"llm_reasoning_effort={self.llm_reasoning_effort!r} is not recognized. "
                f"valid: {sorted(_VALID_REASONING_EFFORTS)}"
            )
        if self.stagnation_reasoning_enabled and not self.stagnation_pressure_enabled:
            raise ValueError(
                "STAGNATION_REASONING_ENABLED=1 requires "
                "STAGNATION_PRESSURE_ENABLED=1"
            )
        if self.stagnation_reasoning_enabled and not self.goal_reflect_enabled:
            raise ValueError(
                "STAGNATION_REASONING_ENABLED=1 requires GOAL_REFLECT_ENABLED=1"
            )
        if (
            self.goal_stagnation_evidence_enabled or self.stagnation_pressure_enabled
        ) and not self.belief_consolidation_enabled:
            raise ValueError(
                "GOAL_STAGNATION_EVIDENCE_ENABLED=1 / "
                "STAGNATION_PRESSURE_ENABLED=1 require "
                "BELIEF_CONSOLIDATION_ENABLED=1"
            )
        if (
            self.goal_stagnation_evidence_enabled
            or self.stagnation_pressure_enabled
            or self.stagnation_reasoning_enabled
        ) and not self.episodic_enabled:
            raise ValueError(
                "GOAL_STAGNATION_EVIDENCE_ENABLED=1 / "
                "STAGNATION_PRESSURE_ENABLED=1 / "
                "STAGNATION_REASONING_ENABLED=1 require LLM_EPISODIC_ENABLED=1"
            )
        # SUBJECTIVE_EPISODE_DB_PATH は episode store が組まれる経路でしか意味を
        # 持たない。episodic OFF では store 自体を作らず、subjective 経路は
        # (scheduler と共有する都合で) 常に in-memory を使うため、どちらの場合も
        # path 指定は静かに無視される。従来 env 直読み時代からの silent failure
        # なので、無視になる組み合わせは fail-fast で落とす。
        if self.subjective_episode_db_path:
            if not self.episodic_enabled:
                raise ValueError(
                    "SUBJECTIVE_EPISODE_DB_PATH requires LLM_EPISODIC_ENABLED=1 "
                    "(episodic OFF では episode store を組まないため path が無視される)"
                )
            if self.episodic_subjective_enabled:
                raise ValueError(
                    "SUBJECTIVE_EPISODE_DB_PATH is not supported with "
                    "LLM_EPISODIC_SUBJECTIVE_ENABLED=1 "
                    "(subjective 経路は in-memory episode store 固定なので path が"
                    "無視される)。永続化が要るなら subjective を OFF にするか "
                    "snapshot を使う"
                )

    # ──────────────────────────────────────────────────────────────
    # Construction
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def from_mapping(
        cls,
        values: Optional[Mapping[str, str]] = None,
    ) -> "ResolvedLlmRuntimeConfig":
        """設定値から全フィールドを resolve する (PR 2/6 の核心)。

        - ``values`` 省略時は空設定として扱う。環境変数は読まない
        - 各フィールドは既存 resolver (``feature_flags.resolve_*`` /
          ``context_format_strategy.resolve_section_order_from_env`` /
          ``_llm_client_factory`` の値) を呼ぶ薄いラッパー
        - 不正値は各 resolver が ``ValueError`` を投げる (PR #434 fail-fast 継承)

        Raises:
            ValueError: values のいずれかが不正値のとき
        """
        # 既存 resolver の import は関数内で行い、循環参照を避ける
        from ai_rpg_world.application.llm.services.context_format_strategy import (
            resolve_section_order_from_env,
        )
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_episodic_explore_related_enabled,
            resolve_episodic_recall_enabled,
            resolve_belief_attribution_enabled,
            resolve_belief_consolidation_enabled,
            resolve_belief_evidence_enabled,
            resolve_error_driven_reinterpretation_enabled,
            resolve_error_gated_encoding_enabled,
            resolve_goal_reflect_enabled,
            resolve_goal_revision_enabled,
            resolve_goal_stagnation_evidence_enabled,
            resolve_goal_store_enabled,
            resolve_hearsay_enabled,
            resolve_memo_distill_enabled,
            resolve_pending_prediction_enabled,
            resolve_prediction_context_id_enabled,
            resolve_recall_hit_boost_enabled,
            resolve_salience_structured_failure_enabled,
            resolve_semantic_llm_gist_enabled,
            resolve_semantic_passive_top_k,
            resolve_semantic_search_enabled,
            resolve_short_term_memory_kind,
            resolve_short_term_memory_scheduler_mode,
            resolve_stagnation_pressure_enabled,
            resolve_stagnation_reasoning_enabled,
            resolve_state_collapse_evidence_enabled,
            resolve_unconscious_context_enabled,
        )

        source: Mapping[str, str] = values if values is not None else {}
        _validate_runtime_config_keys(source)

        # 既存 resolver は env=None だと os.environ を読むものがあるため、
        # ここでは必ず明示 mapping を渡す。実験設定の入力経路を
        # profile/config → 本 DTO の 1 本に固定するため。
        short_term_memory_kind = resolve_short_term_memory_kind(env=source)
        short_term_memory_scheduler_mode = resolve_short_term_memory_scheduler_mode(
            env=source
        )
        prompt_section_order = resolve_section_order_from_env(env=source)
        episodic_explore_related_enabled = resolve_episodic_explore_related_enabled(
            env=source
        )
        semantic_llm_gist_enabled = resolve_semantic_llm_gist_enabled(env=source)
        semantic_passive_top_k = resolve_semantic_passive_top_k(env=source)
        semantic_search_enabled = resolve_semantic_search_enabled(env=source)
        episodic_recall_enabled = resolve_episodic_recall_enabled(env=source)

        # LLM client kind (factory と同じロジックで解決)
        llm_client_kind = _resolve_llm_client_kind(source)
        llm_model = _strip_or_none(source.get("LLM_MODEL"))
        llm_api_key = None
        llm_api_base = _strip_or_none(source.get("OPENAI_API_BASE"))
        llm_request_timeout_seconds = _resolve_timeout_seconds(source)
        llm_reasoning_effort = _resolve_reasoning_effort(source)
        llm_wall_time_cap_seconds = _resolve_optional_positive_float(
            source, "LLM_WALL_TIME_CAP_SECONDS"
        )
        llm_rate_limit_retry_attempts = _resolve_non_negative_int(
            source, "LLM_RATE_LIMIT_RETRY_ATTEMPTS", default=3
        )
        llm_rate_limit_retry_base_sleep = _resolve_non_negative_float(
            source, "LLM_RATE_LIMIT_RETRY_BASE_SLEEP", default=2.0
        )
        llm_turn_parallel_workers = _resolve_non_negative_int(
            source, "LLM_TURN_PARALLEL_WORKERS", default=0
        )
        llm_idle_timeout_ticks = _resolve_positive_int(
            source, "LLM_IDLE_TIMEOUT_TICKS", default=6
        )

        # OpenRouter routing
        openrouter_provider = _strip_or_none(source.get("OPENROUTER_PROVIDER"))
        openrouter_quantization = _strip_or_none(source.get("OPENROUTER_QUANTIZATION"))
        openrouter_require_params = _parse_truthy(
            source.get("OPENROUTER_REQUIRE_PARAMS"), default=False
        )

        # Episodic on/off (旧来は episodic_stack.is_episodic_enabled が同等の
        # ロジック。bool 解釈は _parse_truthy で統一)
        episodic_enabled = _parse_truthy(source.get("LLM_EPISODIC_ENABLED"), default=False)
        episodic_subjective_enabled = _parse_truthy(
            source.get("LLM_EPISODIC_SUBJECTIVE_ENABLED"), default=True
        )
        episodic_promotion_force_full_scan = _parse_truthy(
            source.get("EPISODIC_PROMOTION_FORCE_FULL_SCAN"), default=False
        )
        episodic_promotion_expansion_hops = _resolve_non_negative_int(
            source, "EPISODIC_PROMOTION_EXPANSION_HOPS", default=4
        )

        # Prediction (#526): expected_result 露出 policy
        expected_result_policy = _resolve_expected_result_policy(source)

        # Prediction (#526 / U3): エピソード再解釈 on/off
        episodic_reinterpretation_enabled = _parse_truthy(
            source.get("LLM_EPISODIC_REINTERPRETATION_ENABLED"), default=False
        )

        # #526 段階 2: 慣化ペナルティ (default off / decay 5 tick)
        recall_habituation_enabled = _parse_truthy(
            source.get("LLM_EPISODIC_RECALL_HABITUATION_ENABLED"), default=False
        )
        recall_habituation_decay_window_ticks = _resolve_recall_habituation_decay(
            source
        )

        # #526 段階 3 + PR-A: 想起スロット (default off / N=4 K=1 L=8 C=5 / 閾値=2)
        recall_slot_enabled = _parse_truthy(
            source.get("LLM_EPISODIC_RECALL_SLOT_ENABLED"), default=False
        )
        recall_slot_capacity = _resolve_non_negative_int(
            source, "LLM_EPISODIC_RECALL_SLOT_CAPACITY", default=4
        )
        recall_slot_insert_per_tick = _resolve_non_negative_int(
            source, "LLM_EPISODIC_RECALL_SLOT_INSERT_PER_TICK", default=1
        )
        recall_slot_max_residence = _resolve_non_negative_int(
            source, "LLM_EPISODIC_RECALL_SLOT_MAX_RESIDENCE", default=8
        )
        recall_slot_cooldown_ticks = _resolve_non_negative_int(
            source, "LLM_EPISODIC_RECALL_SLOT_COOLDOWN", default=5
        )
        recall_slot_insert_score_threshold = _resolve_non_negative_int(
            source, "LLM_EPISODIC_RECALL_SLOT_INSERT_SCORE_THRESHOLD", default=2
        )

        # #526 段階 3 PR-C: afterglow index (default off / M=10, M_L=10)
        afterglow_enabled = _parse_truthy(
            source.get("LLM_AFTERGLOW_ENABLED"), default=False
        )
        afterglow_capacity = _resolve_non_negative_int(
            source, "LLM_AFTERGLOW_CAPACITY", default=10
        )
        afterglow_max_residence = _resolve_non_negative_int(
            source, "LLM_AFTERGLOW_MAX_RESIDENCE", default=10
        )

        prediction_context_id_enabled = resolve_prediction_context_id_enabled(env=source)
        belief_evidence_enabled = resolve_belief_evidence_enabled(env=source)
        belief_consolidation_enabled = resolve_belief_consolidation_enabled(env=source)
        belief_attribution_enabled = resolve_belief_attribution_enabled(env=source)
        salience_structured_failure_enabled = (
            resolve_salience_structured_failure_enabled(env=source)
        )
        memo_distill_enabled = resolve_memo_distill_enabled(env=source)
        unconscious_context_enabled = resolve_unconscious_context_enabled(env=source)
        error_driven_reinterpretation_enabled = (
            resolve_error_driven_reinterpretation_enabled(env=source)
        )
        recall_hit_boost_enabled = resolve_recall_hit_boost_enabled(env=source)
        error_gated_encoding_enabled = resolve_error_gated_encoding_enabled(env=source)
        pending_prediction_enabled = resolve_pending_prediction_enabled(env=source)
        hearsay_enabled = resolve_hearsay_enabled(env=source)
        state_collapse_evidence_enabled = resolve_state_collapse_evidence_enabled(
            env=source
        )
        goal_store_enabled = resolve_goal_store_enabled(env=source)
        goal_revision_enabled = resolve_goal_revision_enabled(env=source)
        goal_reflect_enabled = resolve_goal_reflect_enabled(env=source)
        goal_stagnation_evidence_enabled = resolve_goal_stagnation_evidence_enabled(
            env=source
        )
        stagnation_pressure_enabled = resolve_stagnation_pressure_enabled(env=source)
        stagnation_reasoning_enabled = resolve_stagnation_reasoning_enabled(env=source)
        tool_mode = _resolve_tool_mode(source)
        escape_llm_ssot_enabled = _parse_truthy(
            source.get("ESCAPE_LLM_SSOT"), default=False
        )
        scenario_random_seed = _resolve_optional_int(source, "SCENARIO_RANDOM_SEED")
        subjective_episode_db_path = _strip_or_none(
            source.get("SUBJECTIVE_EPISODE_DB_PATH")
        )

        return cls(
            short_term_memory_kind=short_term_memory_kind,
            short_term_memory_scheduler_mode=short_term_memory_scheduler_mode,
            prompt_section_order=prompt_section_order,
            llm_client_kind=llm_client_kind,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_api_base=llm_api_base,
            llm_request_timeout_seconds=llm_request_timeout_seconds,
            llm_reasoning_effort=llm_reasoning_effort,
            llm_wall_time_cap_seconds=llm_wall_time_cap_seconds,
            llm_rate_limit_retry_attempts=llm_rate_limit_retry_attempts,
            llm_rate_limit_retry_base_sleep=llm_rate_limit_retry_base_sleep,
            llm_turn_parallel_workers=llm_turn_parallel_workers,
            llm_idle_timeout_ticks=llm_idle_timeout_ticks,
            openrouter_provider=openrouter_provider,
            openrouter_quantization=openrouter_quantization,
            openrouter_require_params=openrouter_require_params,
            episodic_enabled=episodic_enabled,
            episodic_subjective_enabled=episodic_subjective_enabled,
            episodic_explore_related_enabled=episodic_explore_related_enabled,
            episodic_promotion_force_full_scan=episodic_promotion_force_full_scan,
            episodic_promotion_expansion_hops=episodic_promotion_expansion_hops,
            semantic_llm_gist_enabled=semantic_llm_gist_enabled,
            semantic_passive_top_k=semantic_passive_top_k,
            semantic_search_enabled=semantic_search_enabled,
            expected_result_policy=expected_result_policy,
            episodic_reinterpretation_enabled=episodic_reinterpretation_enabled,
            recall_habituation_enabled=recall_habituation_enabled,
            recall_habituation_decay_window_ticks=recall_habituation_decay_window_ticks,
            recall_slot_enabled=recall_slot_enabled,
            recall_slot_capacity=recall_slot_capacity,
            recall_slot_insert_per_tick=recall_slot_insert_per_tick,
            recall_slot_insert_score_threshold=recall_slot_insert_score_threshold,
            recall_slot_max_residence=recall_slot_max_residence,
            recall_slot_cooldown_ticks=recall_slot_cooldown_ticks,
            afterglow_enabled=afterglow_enabled,
            afterglow_capacity=afterglow_capacity,
            afterglow_max_residence=afterglow_max_residence,
            episodic_recall_enabled=episodic_recall_enabled,
            prediction_context_id_enabled=prediction_context_id_enabled,
            belief_evidence_enabled=belief_evidence_enabled,
            belief_consolidation_enabled=belief_consolidation_enabled,
            belief_attribution_enabled=belief_attribution_enabled,
            salience_structured_failure_enabled=salience_structured_failure_enabled,
            memo_distill_enabled=memo_distill_enabled,
            unconscious_context_enabled=unconscious_context_enabled,
            error_driven_reinterpretation_enabled=error_driven_reinterpretation_enabled,
            recall_hit_boost_enabled=recall_hit_boost_enabled,
            error_gated_encoding_enabled=error_gated_encoding_enabled,
            pending_prediction_enabled=pending_prediction_enabled,
            hearsay_enabled=hearsay_enabled,
            state_collapse_evidence_enabled=state_collapse_evidence_enabled,
            goal_store_enabled=goal_store_enabled,
            goal_revision_enabled=goal_revision_enabled,
            goal_reflect_enabled=goal_reflect_enabled,
            goal_stagnation_evidence_enabled=goal_stagnation_evidence_enabled,
            stagnation_pressure_enabled=stagnation_pressure_enabled,
            stagnation_reasoning_enabled=stagnation_reasoning_enabled,
            tool_mode=tool_mode,
            escape_llm_ssot_enabled=escape_llm_ssot_enabled,
            scenario_random_seed=scenario_random_seed,
            subjective_episode_db_path=subjective_episode_db_path,
        )

    @classmethod
    def for_tests(cls, **overrides: Any) -> "ResolvedLlmRuntimeConfig":
        """test 用の safe default factory (PR #446 architect 提案)。

        全フィールドを「最も無害な default」で埋め、上書きしたい項目だけ
        keyword で渡す。test fixture の肥大化を防ぐ。

        - LLM 系は全部 ``stub`` / None で「実 LLM を呼ばない」
        - feature flag は全部 OFF
        - prompt_section_order は ``stable_to_volatile`` (= default)

        Usage:
            cfg = ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_kind="rolling_summary",
            )
        """
        defaults: dict[str, Any] = dict(
            short_term_memory_kind="sliding_window",
            # PR #467: K run #466 で thread_pool を本番 default に。テスト
            # factory も from_mapping と整合させる。テストで inline を要求するなら
            # 明示 override する。
            short_term_memory_scheduler_mode="thread_pool",
            prompt_section_order="stable_to_volatile",
            llm_client_kind="stub",
            llm_model=None,
            llm_api_key=None,
            llm_api_base=None,
            llm_request_timeout_seconds=90.0,
            llm_reasoning_effort="none",
            llm_wall_time_cap_seconds=None,
            llm_rate_limit_retry_attempts=3,
            llm_rate_limit_retry_base_sleep=2.0,
            llm_turn_parallel_workers=0,
            llm_idle_timeout_ticks=6,
            openrouter_provider=None,
            openrouter_quantization=None,
            openrouter_require_params=False,
            episodic_enabled=False,
            episodic_subjective_enabled=True,
            episodic_explore_related_enabled=False,
            episodic_promotion_force_full_scan=False,
            episodic_promotion_expansion_hops=4,
            semantic_llm_gist_enabled=False,
            semantic_passive_top_k=0,
            semantic_search_enabled=False,
            expected_result_policy="off",
            episodic_reinterpretation_enabled=False,
            recall_habituation_enabled=False,
            recall_habituation_decay_window_ticks=5,
            recall_slot_enabled=False,
            recall_slot_capacity=4,
            recall_slot_insert_per_tick=1,
            recall_slot_max_residence=8,
            recall_slot_cooldown_ticks=5,
            recall_slot_insert_score_threshold=2,
            afterglow_enabled=False,
            afterglow_capacity=10,
            afterglow_max_residence=10,
            episodic_recall_enabled=False,
            prediction_context_id_enabled=False,
            belief_evidence_enabled=False,
            belief_consolidation_enabled=False,
            belief_attribution_enabled=False,
            salience_structured_failure_enabled=False,
            memo_distill_enabled=False,
            unconscious_context_enabled=False,
            error_driven_reinterpretation_enabled=False,
            recall_hit_boost_enabled=False,
            error_gated_encoding_enabled=False,
            pending_prediction_enabled=False,
            hearsay_enabled=False,
            state_collapse_evidence_enabled=False,
            goal_store_enabled=False,
            goal_revision_enabled=False,
            goal_reflect_enabled=False,
            goal_stagnation_evidence_enabled=False,
            stagnation_pressure_enabled=False,
            stagnation_reasoning_enabled=False,
            tool_mode="default",
            escape_llm_ssot_enabled=False,
            scenario_random_seed=None,
            subjective_episode_db_path=None,
        )
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise TypeError(
                f"Unknown override keys: {sorted(unknown)}. "
                f"valid: {sorted(defaults)}"
            )
        defaults.update(overrides)
        return cls(**defaults)

    # ──────────────────────────────────────────────────────────────
    # Observability
    # ──────────────────────────────────────────────────────────────

    def to_trace_dict(self) -> dict[str, Any]:
        """run_start trace payload 用の dict 表現 (PR 3/6 で entrypoint が利用)。

        ``llm_api_key`` は **必ずマスク** する (実値を trace に書かない安全弁)。
        その他は dataclass の全フィールドをそのまま出力。
        """
        d = asdict(self)
        # API key は trace に書かない (= 漏洩防止)
        if d.get("llm_api_key"):
            d["llm_api_key"] = "***"
        return d


# ──────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _validate_runtime_config_keys(source: Mapping[str, str]) -> None:
    """profile/runtime_config の typo と秘密値混入を入口で止める。"""
    env_only = sorted(set(source) & _SECRET_ENV_ONLY_KEYS)
    if env_only:
        raise ValueError(
            "secret key(s) are not allowed in runtime_config: "
            f"{env_only}. Set them via process environment instead."
        )
    unknown = sorted(set(source) - SUPPORTED_RUNTIME_CONFIG_KEYS)
    if unknown:
        raise ValueError(
            f"unknown runtime_config key(s): {unknown}. "
            f"valid: {sorted(SUPPORTED_RUNTIME_CONFIG_KEYS)}"
        )


def _strip_or_none(value: Optional[str]) -> Optional[str]:
    """空文字 / None / 空白のみ → None、それ以外は strip した値。"""
    if value is None:
        return None
    s = value.strip()
    return s or None


def _parse_truthy(value: Optional[str], *, default: bool) -> bool:
    """bool 解釈。``_parse_bool_env`` と同じロジック (PR #434 ポリシー)。

    未設定 / 空文字 → ``default``
    truthy / falsy リテラル → True / False
    その他 → ValueError (fail-fast)
    """
    if value is None or not value.strip():
        return default
    raw = value.strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    raise ValueError(
        f"{value!r} is not a recognized boolean. "
        f"truthy: {sorted(_TRUTHY)}, falsy: {sorted(_FALSY)}"
    )


_VALID_EXPECTED_RESULT_POLICIES = frozenset({"off", "optional", "required"})
_VALID_TOOL_MODES = frozenset({"default", "pure_spot_graph"})
_VALID_REASONING_EFFORTS = frozenset({
    "",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
})


def _resolve_expected_result_policy(source: Mapping[str, str]) -> str:
    """``LLM_EXPECTED_RESULT_POLICY`` を解決 (#526 / PR #434 fail-fast 継承)。

    未設定 / 空文字 → ``"off"`` (露出せず挙動不変)。off / optional / required の
    いずれでもなければ ``ValueError``。
    """
    raw = (source.get("LLM_EXPECTED_RESULT_POLICY") or "off").strip().lower()
    if raw not in _VALID_EXPECTED_RESULT_POLICIES:
        raise ValueError(
            f"LLM_EXPECTED_RESULT_POLICY={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_EXPECTED_RESULT_POLICIES)}"
        )
    return raw


def _resolve_tool_mode(source: Mapping[str, str]) -> str:
    """``LLM_TOOL_MODE`` を解決する。

    旧 world_runtime 経路は未知値を warning + default fallback にしていたが、
    実験条件では typo を黙って受ける価値が低いため fail-fast に揃える。
    """
    raw = (source.get("LLM_TOOL_MODE") or "").strip().lower()
    if not raw:
        return "default"
    if raw not in _VALID_TOOL_MODES:
        raise ValueError(
            f"LLM_TOOL_MODE={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_TOOL_MODES)}"
        )
    return raw


def _resolve_reasoning_effort(source: Mapping[str, str]) -> str:
    """``LLM_REASONING_EFFORT`` を解決する。

    reasoning model でコストが膨らむ事故を防ぐため、既定は ``"none"``。
    空文字は「reasoning 関連フィールドを一切注入しない」を表す明示値として許す。
    """
    raw = source.get("LLM_REASONING_EFFORT")
    value = "none" if raw is None else raw.strip().lower()
    if value not in _VALID_REASONING_EFFORTS:
        raise ValueError(
            f"LLM_REASONING_EFFORT={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_REASONING_EFFORTS)}"
        )
    return value


def _resolve_optional_int(
    source: Mapping[str, str],
    env_name: str,
) -> Optional[int]:
    raw = (source.get(env_name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{env_name}={raw!r} must be an integer")


def _resolve_non_negative_int(
    source: Mapping[str, str], key: str, *, default: int
) -> int:
    """``key`` を 0 以上の整数として解決。未設定 / 空文字 → ``default``。

    負値・非数値は ``ValueError`` で fail-fast。``_resolve_recall_habituation_decay``
    と同じ方針を共有 helper として一般化したもの。
    """
    raw = (source.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as e:
        raise ValueError(f"{key}={raw!r} is not an integer") from e
    if value < 0:
        raise ValueError(f"{key}={value} must be 0 or greater")
    return value


def _resolve_positive_int(
    source: Mapping[str, str], key: str, *, default: int
) -> int:
    raw = (source.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as e:
        raise ValueError(f"{key}={raw!r} is not an integer") from e
    if value < 1:
        raise ValueError(f"{key}={value} must be 1 or greater")
    return value


def _resolve_non_negative_float(
    source: Mapping[str, str], key: str, *, default: float
) -> float:
    raw = (source.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as e:
        raise ValueError(f"{key}={raw!r} is not a number") from e
    if value < 0:
        raise ValueError(f"{key}={value} must be 0 or greater")
    return value


def _resolve_optional_positive_float(
    source: Mapping[str, str], key: str
) -> Optional[float]:
    raw = (source.get(key) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as e:
        raise ValueError(f"{key}={raw!r} is not a number") from e
    if value <= 0:
        raise ValueError(f"{key}={value} must be greater than 0")
    return value


def _resolve_recall_habituation_decay(source: Mapping[str, str]) -> int:
    """``LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS`` を解決 (#526 段階 2)。

    未設定 / 空文字 → default 5。負値・非数値は fail-fast で ``ValueError``。
    """
    raw = (source.get("LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS") or "").strip()
    if not raw:
        return 5
    try:
        value = int(raw)
    except ValueError as e:
        raise ValueError(
            f"LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS={raw!r} is not an integer"
        ) from e
    if value < 0:
        raise ValueError(
            f"LLM_EPISODIC_RECALL_HABITUATION_DECAY_TICKS={value} must be 0 or greater"
        )
    return value


_VALID_LLM_CLIENT_KINDS = frozenset({"stub", "litellm"})


def _resolve_llm_client_kind(source: Mapping[str, str]) -> str:
    """``LLM_CLIENT`` を解決 (factory と同じロジック / PR #434 fail-fast 継承)。"""
    raw = (source.get("LLM_CLIENT") or "stub").strip().lower()
    if raw not in _VALID_LLM_CLIENT_KINDS:
        raise ValueError(
            f"LLM_CLIENT={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_LLM_CLIENT_KINDS)}"
        )
    return raw


_DEFAULT_TIMEOUT_SECONDS = 90.0


def _resolve_timeout_seconds(source: Mapping[str, str]) -> float:
    """``LLM_REQUEST_TIMEOUT_SECONDS`` を解決 (LiteLLMClient と同じ default / fail-fast)。"""
    raw = (source.get("LLM_REQUEST_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"LLM_REQUEST_TIMEOUT_SECONDS={raw!r} must be a number (seconds)"
        )


__all__ = ["ResolvedLlmRuntimeConfig", "SUPPORTED_RUNTIME_CONFIG_KEYS"]
