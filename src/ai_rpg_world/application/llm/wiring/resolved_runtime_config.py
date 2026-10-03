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

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CHAR_BIGRAM_BM25,
    SUPPORTED_TEXT_CANDIDATE_NARROWERS,
)
from ai_rpg_world.application.llm.services.world_llm_turn.llm_failure_streak_monitor import (
    DEFAULT_FAILURE_STREAK_ABORT,
)

SUPPORTED_RUNTIME_CONFIG_KEYS = frozenset({
    "BELIEF_ATTRIBUTION_ENABLED",
    "BELIEF_CANDIDATE_NARROWER",
    "BELIEF_CANDIDATE_TOP_K",
    "BELIEF_CONSOLIDATION_ENABLED",
    "BELIEF_CREATE_GATE_ENABLED",
    "BELIEF_CREATE_GATE_MIN_CONFIDENCE",
    "BELIEF_EVIDENCE_ENABLED",
    "DISTANT_VIEW_TRACE_ENABLED",
    "EPISODIC_EXPLORE_RELATED_ENABLED",
    "EXPECTATION_ARGUMENT_ENABLED",
    "EXPECTATION_DATED_TERM_TURNS",
    "EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS",
    "EXPECTATION_GROUNDS_MAX_QUESTIONS",
    "EXPECTATION_GROUNDS_MIN_PROBABILITY",
    "EXPECTATION_SETTLEMENT_ENABLED",
    "EXPECTATION_SETTLEMENT_MAX_OPEN",
    "EXPECTATION_SETTLEMENT_TIMELINE_TURNS",
    "EXPECTATION_UNDATED_TERM_TURNS",
    "EPISODIC_PROMOTION_EXPANSION_HOPS",
    "EPISODIC_PROMOTION_FORCE_FULL_SCAN",
    "EPISODIC_RECALL_ENABLED",
    "ERROR_DRIVEN_REINTERPRETATION_ENABLED",
    "ERROR_GATED_ENCODING_ENABLED",
    "END_ON_ALL_DOWN",
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
    "LLM_FAILURE_STREAK_ABORT",
    "LLM_IDLE_TIMEOUT_TICKS",
    "LLM_MEETING_SERIAL_TURNS",
    "LLM_MODEL",
    "LLM_RATE_LIMIT_RETRY_ATTEMPTS",
    "LLM_RATE_LIMIT_RETRY_BASE_SLEEP",
    "LLM_REASONING_EFFORT",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "LLM_SESSION_ID_ENABLED",
    "LLM_TOOL_MODE",
    "LLM_TOOL_CHOICE",
    "LLM_TURN_PARALLEL_WORKERS",
    "LLM_WALL_TIME_CAP_SECONDS",
    "MEMO_DISTILL_ENABLED",
    "MEMO_TOOLS_ENABLED",
    "OPENAI_API_BASE",
    "OPENROUTER_PROVIDER",
    "OPENROUTER_QUANTIZATION",
    "OPENROUTER_REQUIRE_PARAMS",
    "PENDING_PREDICTION_ENABLED",
    "PREDICTION_CONTEXT_ID_ENABLED",
    "PROMPT_DATASET_CAPTURE_ENABLED",
    "PROMPT_DATASET_CAPTURE_FAILURE_POLICY",
    "PROMPT_SECTION_ORDER",
    "RECALL_HIT_BOOST_ENABLED",
    "REASON_FIRST_TWO_STEP_ENABLED",
    "SALIENCE_STRUCTURED_FAILURE_ENABLED",
    "SCENARIO_RANDOM_SEED",
    "SEMANTIC_LLM_GIST_ENABLED",
    "SEMANTIC_PASSIVE_TOP_K",
    "SEMANTIC_SEARCH_ENABLED",
    "SHORT_TERM_MEMORY_KIND",
    "SHORT_TERM_MEMORY_SCHEDULER_MODE",
    "SHORT_TERM_MEMORY_TURN_CAP",
    "SHORT_TERM_MEMORY_TURN_COMPACT_COUNT",
    "STAGNATION_PRESSURE_ENABLED",
    "STAGNATION_REASONING_ENABLED",
    "STATE_COLLAPSE_EVIDENCE_ENABLED",
    "SUBJECTIVE_EPISODE_DB_PATH",
    "TYPED_JUDGMENT_ACTION_NAME_MIN_CONFIDENCE",
    "TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE",
    "TYPED_JUDGMENT_API_KEY_ENV",
    "TYPED_JUDGMENT_MEMO_MIN_PROBABILITY",
    "TYPED_JUDGMENT_ENDPOINT",
    "TYPED_JUDGMENT_GOAL_HINT_ENABLED",
    "TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY",
    "TYPED_JUDGMENT_MODEL",
    "TYPED_JUDGMENT_PROVIDER",
    "TYPED_JUDGMENT_SEMANTIC_REPEAT_ENABLED",
    "TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY",
    "TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW",
    "TYPED_JUDGMENT_TURN_GATE_ENABLED",
    "TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW",
    "TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED",
    "TYPED_JUDGMENT_TIMEOUT_SECONDS",
    "UNCONSCIOUS_CONTEXT_ENABLED",
})

#: 同じ意味を問う候補の件数。過去の snapshot の似た組 96 組で、相方が文字の
#: 2 字組の BM25 の上位に入った割合は K=3 で 96%、K=5 で 100%。30 組を K=3 / 5 / 10
#: で Jev に問い、K を増やしても選び間違いは増えなかった
#: (scripts/jev_belief_create_gate_measure.py)。
_DEFAULT_BELIEF_CANDIDATE_TOP_K = 5

#: 形と同じ意味の答えを採る確信度の閾値。同じ 96 組 (K=5) で、強めに置き換えた
#: 先が違う主張だった例は確信度によらず 0 件で、閾値 0.4 で同じ主張の組の 90%、
#: 0.6 で 61% を強めに置き換えた。0.4 で「いまの状況」と判定された文は、採り
#: 尽くした・持っている・提案した、の類だった。run の trace で決め直す。
_DEFAULT_BELIEF_CREATE_GATE_MIN_CONFIDENCE = 0.4

#: profile / runtime_config に書かせない秘密。値そのものは env からだけ読む。
#: profile は run の記録として ``experiment.config.source.json`` に残るため、
#: ここに書かれたキーは記録へ焼き付く。
_SECRET_ENV_ONLY_KEYS = frozenset({"OPENAI_API_KEY", "OPENROUTER_API_KEY"})


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

        # === 型付き判断 (#1319) ===
        typed_judgment_provider: ``"off"`` | ``"jev"`` | ``"stub"``。
            ``off`` の run は現行と同じ振る舞いになる
        typed_judgment_endpoint: Decisions endpoint の URL
        typed_judgment_model: 版を固定したモデル ID
        typed_judgment_timeout_seconds: 1 回の呼び出しを打ち切る秒数
        typed_judgment_api_key_env: キーが入っている env の名前。**値は入れない**
        typed_judgment_action_name_min_confidence: 行動名を置き換える閾値
        typed_judgment_target_label_min_confidence: 対象の名前を置き換える閾値。
            行動名より高い (既定 0.85)
        typed_judgment_memo_min_probability: memo を達成扱いにする閾値
        typed_judgment_turn_gate_enabled: tick の終わりに pending の全員へ「いま
            動く必要があるか」を問う起動判定を挟む。**既定は off**。provider を jev に
            しても起動判定は入らない (#222)。観察するときだけ明示的に true にする
        typed_judgment_turn_gate_skip_below: 動く必要がある確率がこれ未満なら
            回さない。取りこぼしを避けるため小さく置く
        typed_judgment_loop_diagnosis_enabled: ループ警告の発火時に、繰り返しの
            理由を問うて文面を選ぶ (#1411)。**既定は off**。provider が off なら
            有効にしても入らない
        typed_judgment_semantic_repeat_enabled: 直近の行動の窓を材料に、言い直しや
            往復のような意味上の繰り返しを問う (#1412)。**既定は off**
        typed_judgment_semantic_repeat_min_probability: 繰り返しと見なす確率の閾値。
            警告が待機へ押すのを避けるため高めに置く
        typed_judgment_semantic_repeat_window: 判断に渡す直近の行動の件数
        typed_judgment_goal_hint_enabled: 行動の結果のあと、未達成の目的が達成
            されたかを問い、可能性が高ければ hint を添える (#1448)。**既定は off**。
            目的の改訂 (goal_outcome) が無い run では入らない
        typed_judgment_goal_hint_min_probability: 目的の hint を出す確率の閾値
        expectation_settlement_enabled: ターンの終わりに、予期の形と当否を Jev に
            問うて清算する (#1440)。**既定は off**。判断の provider が要る
        expectation_settlement_max_open: 清算の問いに載せる清算待ちの予期の上限。
            超えたら期日の無い古い予期から期限を繰り上げて閉じる
        expectation_settlement_timeline_turns: 清算の問いに見せる出来事の時系列の
            ターン数
        expectation_event_max_delivery_attempts: 予期の出来事を配り直す回数の上限。
            清算の有効化によらず、予期の出来事を配るときに使う
        expectation_grounds_max_questions: 予期を書いたターンの清算の呼び出しに
            並べる、根拠の問い (頭にあった信念とエピソードごとの問い) の上限 (#1484)
        expectation_grounds_min_probability: 根拠として採る確率の閾値。これを
            超えたものだけを根拠にする
        expectation_argument_enabled: 環境の tool に予期の引数 ``expectations`` を
            付け、書かれた予期を積む (#1441)。**既定は off**。清算と、プロンプトに
            載った信念を記録する台帳が要り、``expected_result`` とは併用できない
        expectation_undated_term_turns: 期日の無い予期を、書いてから何ターンで
            期限切れにするか
        expectation_dated_term_turns: 期日のある予期の期限。期日は環境の時間で
            書かれ、届いた出来事の時刻で清算されるので、ターン数では長めに切る

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
    llm_model: str | None
    llm_api_key: str | None
    llm_api_base: str | None
    llm_request_timeout_seconds: float
    llm_reasoning_effort: str
    llm_wall_time_cap_seconds: float | None
    llm_rate_limit_retry_attempts: int
    llm_rate_limit_retry_base_sleep: float
    llm_turn_parallel_workers: int
    llm_meeting_serial_turns: bool
    llm_idle_timeout_ticks: int
    llm_failure_streak_abort: int
    llm_tool_choice: str
    llm_session_id_enabled: bool

    # OpenRouter routing
    openrouter_provider: str | None
    openrouter_quantization: str | None
    openrouter_require_params: bool

    # 型付き判断 (#1319)
    typed_judgment_provider: str
    typed_judgment_endpoint: str
    typed_judgment_model: str
    typed_judgment_timeout_seconds: float
    typed_judgment_api_key_env: str
    typed_judgment_action_name_min_confidence: float
    typed_judgment_target_label_min_confidence: float
    typed_judgment_memo_min_probability: float
    typed_judgment_turn_gate_enabled: bool
    typed_judgment_turn_gate_skip_below: float
    typed_judgment_loop_diagnosis_enabled: bool
    typed_judgment_semantic_repeat_enabled: bool
    typed_judgment_semantic_repeat_min_probability: float
    typed_judgment_semantic_repeat_window: int
    typed_judgment_goal_hint_enabled: bool
    typed_judgment_goal_hint_min_probability: float
    expectation_settlement_enabled: bool
    expectation_settlement_max_open: int
    expectation_settlement_timeline_turns: int
    expectation_event_max_delivery_attempts: int
    expectation_grounds_max_questions: int
    expectation_grounds_min_probability: float
    expectation_argument_enabled: bool
    expectation_undated_term_turns: int
    expectation_dated_term_turns: int

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
    short_term_memory_turn_cap: int = 20
    short_term_memory_turn_compact_count: int = 10

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
    belief_create_gate_enabled: bool = False
    belief_candidate_narrower: str = CHAR_BIGRAM_BM25
    belief_candidate_top_k: int = _DEFAULT_BELIEF_CANDIDATE_TOP_K
    belief_create_gate_min_confidence: float = _DEFAULT_BELIEF_CREATE_GATE_MIN_CONFIDENCE
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
    memo_tools_enabled: bool = True
    escape_llm_ssot_enabled: bool = False
    scenario_random_seed: int | None = None
    prompt_dataset_capture_enabled: bool = False
    prompt_dataset_capture_failure_policy: str = "fail"
    distant_view_trace_enabled: bool = False
    # reason-first 2段階ターン。True でも常時発火ではなく、Phase A 入口で
    # 既存の loop_guard / action_result / stagnation state を読んだ gated 発火にする。
    reason_first_two_step_enabled: bool = False
    # 全員が down または outcome 確定済みなら、DEAD 猶予を待たず outcome モードを
    # 終了する。既定 OFF で、蘇生手段を実験したい profile は従来どおり猶予を残す。
    end_on_all_down: bool = False

    # Episode store の永続化先 (``SUBJECTIVE_EPISODE_DB_PATH``)。None なら in-memory。
    # 実 path 指定時は SQLite 永続化。従来 ``_default_episodic_episode_store`` が
    # os.environ を直読みしており profile/manifest の外で決まっていた
    # (PR #736 の単一窓口化で取り残されていた env)。config に載せ替えて
    # 解決経路を from_mapping の 1 本に固定し、run_start / manifest に残す。
    subjective_episode_db_path: str | None = None

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
        if (
            self.short_term_memory_turn_cap <= 0
            or self.short_term_memory_turn_compact_count <= 0
            or self.short_term_memory_turn_compact_count
            >= self.short_term_memory_turn_cap
        ):
            raise ValueError(
                "short-term memory turn window requires "
                "0 < compact_count < cap"
            )
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
        if self.llm_tool_choice not in _VALID_TOOL_CHOICES:
            raise ValueError(
                f"llm_tool_choice={self.llm_tool_choice!r} is not recognized. "
                f"valid: {sorted(_VALID_TOOL_CHOICES)}"
            )
        if self.prompt_dataset_capture_failure_policy not in {"fail", "warn"}:
            raise ValueError(
                "prompt_dataset_capture_failure_policy="
                f"{self.prompt_dataset_capture_failure_policy!r} is not recognized. "
                "valid: ['fail', 'warn']"
            )
        self._validate_belief_create_gate()
        self._validate_expectation_settlement()
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
        values: Mapping[str, str] | None = None,
    ) -> ResolvedLlmRuntimeConfig:
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
            resolve_belief_attribution_enabled,
            resolve_belief_consolidation_enabled,
            resolve_belief_evidence_enabled,
            resolve_episodic_explore_related_enabled,
            resolve_episodic_recall_enabled,
            resolve_error_driven_reinterpretation_enabled,
            resolve_error_gated_encoding_enabled,
            resolve_goal_reflect_enabled,
            resolve_goal_revision_enabled,
            resolve_goal_stagnation_evidence_enabled,
            resolve_goal_store_enabled,
            resolve_hearsay_enabled,
            resolve_memo_distill_enabled,
            resolve_memo_tools_enabled,
            resolve_pending_prediction_enabled,
            resolve_prediction_context_id_enabled,
            resolve_recall_hit_boost_enabled,
            resolve_salience_structured_failure_enabled,
            resolve_semantic_llm_gist_enabled,
            resolve_semantic_passive_top_k,
            resolve_semantic_search_enabled,
            resolve_short_term_memory_kind,
            resolve_short_term_memory_scheduler_mode,
            resolve_short_term_memory_turn_window,
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
        (
            short_term_memory_turn_cap,
            short_term_memory_turn_compact_count,
        ) = resolve_short_term_memory_turn_window(env=source)
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
        llm_meeting_serial_turns = _parse_truthy(
            source.get("LLM_MEETING_SERIAL_TURNS"), default=False
        )
        llm_idle_timeout_ticks = _resolve_positive_int(
            source, "LLM_IDLE_TIMEOUT_TICKS", default=6
        )
        # 連続失敗で run を止める閾値。0 で無効。既定 8 の根拠は
        # LlmFailureStreakMonitor の試験に書いた (履歴 68 run の校正)。
        llm_failure_streak_abort = _resolve_non_negative_int(
            source,
            "LLM_FAILURE_STREAK_ABORT",
            default=DEFAULT_FAILURE_STREAK_ABORT,
        )
        llm_tool_choice = _resolve_tool_choice(source)
        try:
            llm_session_id_enabled = _parse_truthy(
                source.get("LLM_SESSION_ID_ENABLED"), default=True
            )
        except ValueError as exc:
            raise ValueError(f"LLM_SESSION_ID_ENABLED: {exc}") from exc

        # 型付き判断 (#1319)
        typed_judgment_provider = _resolve_typed_judgment_provider(source)
        typed_judgment_endpoint = (
            _strip_or_none(source.get("TYPED_JUDGMENT_ENDPOINT"))
            or _DEFAULT_TYPED_JUDGMENT_ENDPOINT
        )
        typed_judgment_model = (
            _strip_or_none(source.get("TYPED_JUDGMENT_MODEL"))
            or _DEFAULT_TYPED_JUDGMENT_MODEL
        )
        typed_judgment_timeout_seconds = _resolve_positive_float_with_default(
            source,
            "TYPED_JUDGMENT_TIMEOUT_SECONDS",
            default=_DEFAULT_TYPED_JUDGMENT_TIMEOUT_SECONDS,
        )
        typed_judgment_api_key_env = (
            _strip_or_none(source.get("TYPED_JUDGMENT_API_KEY_ENV"))
            or _DEFAULT_TYPED_JUDGMENT_API_KEY_ENV
        )
        typed_judgment_action_name_min_confidence = _resolve_ratio_with_default(
            source,
            "TYPED_JUDGMENT_ACTION_NAME_MIN_CONFIDENCE",
            default=_DEFAULT_TYPED_JUDGMENT_ACTION_NAME_MIN_CONFIDENCE,
        )
        typed_judgment_target_label_min_confidence = _resolve_ratio_with_default(
            source,
            "TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE",
            default=_DEFAULT_TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE,
        )
        typed_judgment_memo_min_probability = _resolve_ratio_with_default(
            source,
            "TYPED_JUDGMENT_MEMO_MIN_PROBABILITY",
            default=_DEFAULT_TYPED_JUDGMENT_MEMO_MIN_PROBABILITY,
        )
        try:
            typed_judgment_turn_gate_enabled = _parse_truthy(
                source.get("TYPED_JUDGMENT_TURN_GATE_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"TYPED_JUDGMENT_TURN_GATE_ENABLED: {exc}") from exc
        typed_judgment_turn_gate_skip_below = _resolve_ratio_with_default(
            source,
            "TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW",
            default=_DEFAULT_TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW,
        )
        try:
            typed_judgment_loop_diagnosis_enabled = _parse_truthy(
                source.get("TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED: {exc}") from exc
        try:
            typed_judgment_semantic_repeat_enabled = _parse_truthy(
                source.get("TYPED_JUDGMENT_SEMANTIC_REPEAT_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"TYPED_JUDGMENT_SEMANTIC_REPEAT_ENABLED: {exc}") from exc
        typed_judgment_semantic_repeat_min_probability = _resolve_ratio_with_default(
            source,
            "TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY",
            default=_DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY,
        )
        typed_judgment_semantic_repeat_window = _resolve_positive_int(
            source,
            "TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW",
            default=_DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW,
        )
        try:
            typed_judgment_goal_hint_enabled = _parse_truthy(
                source.get("TYPED_JUDGMENT_GOAL_HINT_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"TYPED_JUDGMENT_GOAL_HINT_ENABLED: {exc}") from exc
        typed_judgment_goal_hint_min_probability = _resolve_ratio_with_default(
            source,
            "TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY",
            default=_DEFAULT_TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY,
        )
        if typed_judgment_semantic_repeat_window < 2:
            raise ValueError(
                "TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW must be 2 or greater"
            )
        try:
            expectation_settlement_enabled = _parse_truthy(
                source.get("EXPECTATION_SETTLEMENT_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"EXPECTATION_SETTLEMENT_ENABLED: {exc}") from exc
        expectation_settlement_max_open = _resolve_positive_int(
            source,
            "EXPECTATION_SETTLEMENT_MAX_OPEN",
            default=_DEFAULT_EXPECTATION_SETTLEMENT_MAX_OPEN,
        )
        expectation_settlement_timeline_turns = _resolve_positive_int(
            source,
            "EXPECTATION_SETTLEMENT_TIMELINE_TURNS",
            default=_DEFAULT_EXPECTATION_SETTLEMENT_TIMELINE_TURNS,
        )
        expectation_event_max_delivery_attempts = _resolve_positive_int(
            source,
            "EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS",
            default=_DEFAULT_EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS,
        )
        expectation_grounds_max_questions = _resolve_positive_int(
            source,
            "EXPECTATION_GROUNDS_MAX_QUESTIONS",
            default=_DEFAULT_EXPECTATION_GROUNDS_MAX_QUESTIONS,
        )
        expectation_grounds_min_probability = _resolve_ratio_with_default(
            source,
            "EXPECTATION_GROUNDS_MIN_PROBABILITY",
            default=_DEFAULT_EXPECTATION_GROUNDS_MIN_PROBABILITY,
        )
        try:
            expectation_argument_enabled = _parse_truthy(
                source.get("EXPECTATION_ARGUMENT_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"EXPECTATION_ARGUMENT_ENABLED: {exc}") from exc
        expectation_undated_term_turns = _resolve_positive_int(
            source,
            "EXPECTATION_UNDATED_TERM_TURNS",
            default=_DEFAULT_EXPECTATION_UNDATED_TERM_TURNS,
        )
        expectation_dated_term_turns = _resolve_positive_int(
            source,
            "EXPECTATION_DATED_TERM_TURNS",
            default=_DEFAULT_EXPECTATION_DATED_TERM_TURNS,
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
        try:
            belief_create_gate_enabled = _parse_truthy(
                source.get("BELIEF_CREATE_GATE_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"BELIEF_CREATE_GATE_ENABLED: {exc}") from exc
        belief_candidate_narrower = (
            _strip_or_none(source.get("BELIEF_CANDIDATE_NARROWER")) or CHAR_BIGRAM_BM25
        )
        belief_candidate_top_k = _resolve_positive_int(
            source, "BELIEF_CANDIDATE_TOP_K", default=_DEFAULT_BELIEF_CANDIDATE_TOP_K
        )
        belief_create_gate_min_confidence = _resolve_ratio_with_default(
            source,
            "BELIEF_CREATE_GATE_MIN_CONFIDENCE",
            default=_DEFAULT_BELIEF_CREATE_GATE_MIN_CONFIDENCE,
        )
        salience_structured_failure_enabled = (
            resolve_salience_structured_failure_enabled(env=source)
        )
        memo_distill_enabled = resolve_memo_distill_enabled(env=source)
        memo_tools_enabled = resolve_memo_tools_enabled(env=source)
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
        prompt_dataset_capture_enabled = _parse_truthy(
            source.get("PROMPT_DATASET_CAPTURE_ENABLED"), default=False
        )
        prompt_dataset_capture_failure_policy = (
            source.get("PROMPT_DATASET_CAPTURE_FAILURE_POLICY") or "fail"
        ).strip().lower()
        distant_view_trace_enabled = _parse_truthy(
            source.get("DISTANT_VIEW_TRACE_ENABLED"), default=False
        )
        try:
            reason_first_two_step_enabled = _parse_truthy(
                source.get("REASON_FIRST_TWO_STEP_ENABLED"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"REASON_FIRST_TWO_STEP_ENABLED: {exc}") from exc
        # reason-first の第1段は named tool_choice を使う。DeepSeek で
        # thinking + named の対応を実 API なしに保証できないため、auto 比較腕では
        # 2段階経路を実効 OFF にし、解決済み設定にも false として残す。
        if llm_tool_choice == "auto":
            reason_first_two_step_enabled = False
        try:
            end_on_all_down = _parse_truthy(
                source.get("END_ON_ALL_DOWN"), default=False
            )
        except ValueError as exc:
            raise ValueError(f"END_ON_ALL_DOWN: {exc}") from exc
        subjective_episode_db_path = _strip_or_none(
            source.get("SUBJECTIVE_EPISODE_DB_PATH")
        )

        return cls(
            short_term_memory_kind=short_term_memory_kind,
            short_term_memory_scheduler_mode=short_term_memory_scheduler_mode,
            short_term_memory_turn_cap=short_term_memory_turn_cap,
            short_term_memory_turn_compact_count=short_term_memory_turn_compact_count,
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
            llm_meeting_serial_turns=llm_meeting_serial_turns,
            llm_idle_timeout_ticks=llm_idle_timeout_ticks,
            llm_failure_streak_abort=llm_failure_streak_abort,
            llm_tool_choice=llm_tool_choice,
            llm_session_id_enabled=llm_session_id_enabled,
            openrouter_provider=openrouter_provider,
            openrouter_quantization=openrouter_quantization,
            openrouter_require_params=openrouter_require_params,
            typed_judgment_provider=typed_judgment_provider,
            typed_judgment_endpoint=typed_judgment_endpoint,
            typed_judgment_model=typed_judgment_model,
            typed_judgment_timeout_seconds=typed_judgment_timeout_seconds,
            typed_judgment_api_key_env=typed_judgment_api_key_env,
            typed_judgment_action_name_min_confidence=(
                typed_judgment_action_name_min_confidence
            ),
            typed_judgment_target_label_min_confidence=(
                typed_judgment_target_label_min_confidence
            ),
            typed_judgment_memo_min_probability=typed_judgment_memo_min_probability,
            typed_judgment_turn_gate_enabled=typed_judgment_turn_gate_enabled,
            typed_judgment_turn_gate_skip_below=typed_judgment_turn_gate_skip_below,
            typed_judgment_loop_diagnosis_enabled=typed_judgment_loop_diagnosis_enabled,
            typed_judgment_semantic_repeat_enabled=typed_judgment_semantic_repeat_enabled,
            typed_judgment_semantic_repeat_min_probability=(
                typed_judgment_semantic_repeat_min_probability
            ),
            typed_judgment_semantic_repeat_window=typed_judgment_semantic_repeat_window,
            typed_judgment_goal_hint_enabled=typed_judgment_goal_hint_enabled,
            typed_judgment_goal_hint_min_probability=(
                typed_judgment_goal_hint_min_probability
            ),
            expectation_settlement_enabled=expectation_settlement_enabled,
            expectation_settlement_max_open=expectation_settlement_max_open,
            expectation_settlement_timeline_turns=expectation_settlement_timeline_turns,
            expectation_event_max_delivery_attempts=(
                expectation_event_max_delivery_attempts
            ),
            expectation_grounds_max_questions=expectation_grounds_max_questions,
            expectation_grounds_min_probability=expectation_grounds_min_probability,
            expectation_argument_enabled=expectation_argument_enabled,
            expectation_undated_term_turns=expectation_undated_term_turns,
            expectation_dated_term_turns=expectation_dated_term_turns,
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
            belief_create_gate_enabled=belief_create_gate_enabled,
            belief_candidate_narrower=belief_candidate_narrower,
            belief_candidate_top_k=belief_candidate_top_k,
            belief_create_gate_min_confidence=belief_create_gate_min_confidence,
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
            memo_tools_enabled=memo_tools_enabled,
            escape_llm_ssot_enabled=escape_llm_ssot_enabled,
            scenario_random_seed=scenario_random_seed,
            prompt_dataset_capture_enabled=prompt_dataset_capture_enabled,
            prompt_dataset_capture_failure_policy=prompt_dataset_capture_failure_policy,
            distant_view_trace_enabled=distant_view_trace_enabled,
            reason_first_two_step_enabled=reason_first_two_step_enabled,
            end_on_all_down=end_on_all_down,
            subjective_episode_db_path=subjective_episode_db_path,
        )

    @classmethod
    def for_tests(cls, **overrides: Any) -> ResolvedLlmRuntimeConfig:
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
            short_term_memory_turn_cap=20,
            short_term_memory_turn_compact_count=10,
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
            llm_meeting_serial_turns=False,
            llm_idle_timeout_ticks=6,
            llm_failure_streak_abort=DEFAULT_FAILURE_STREAK_ABORT,
            llm_tool_choice="required",
            llm_session_id_enabled=True,
            openrouter_provider=None,
            openrouter_quantization=None,
            openrouter_require_params=False,
            typed_judgment_provider="off",
            typed_judgment_endpoint=_DEFAULT_TYPED_JUDGMENT_ENDPOINT,
            typed_judgment_model=_DEFAULT_TYPED_JUDGMENT_MODEL,
            typed_judgment_timeout_seconds=_DEFAULT_TYPED_JUDGMENT_TIMEOUT_SECONDS,
            typed_judgment_api_key_env=_DEFAULT_TYPED_JUDGMENT_API_KEY_ENV,
            typed_judgment_action_name_min_confidence=(
                _DEFAULT_TYPED_JUDGMENT_ACTION_NAME_MIN_CONFIDENCE
            ),
            typed_judgment_target_label_min_confidence=(
                _DEFAULT_TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE
            ),
            typed_judgment_memo_min_probability=(
                _DEFAULT_TYPED_JUDGMENT_MEMO_MIN_PROBABILITY
            ),
            typed_judgment_turn_gate_enabled=False,
            typed_judgment_turn_gate_skip_below=(
                _DEFAULT_TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW
            ),
            typed_judgment_loop_diagnosis_enabled=False,
            typed_judgment_semantic_repeat_enabled=False,
            typed_judgment_semantic_repeat_min_probability=(
                _DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY
            ),
            typed_judgment_semantic_repeat_window=(
                _DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW
            ),
            typed_judgment_goal_hint_enabled=False,
            typed_judgment_goal_hint_min_probability=(
                _DEFAULT_TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY
            ),
            expectation_settlement_enabled=False,
            expectation_settlement_max_open=_DEFAULT_EXPECTATION_SETTLEMENT_MAX_OPEN,
            expectation_settlement_timeline_turns=(
                _DEFAULT_EXPECTATION_SETTLEMENT_TIMELINE_TURNS
            ),
            expectation_event_max_delivery_attempts=(
                _DEFAULT_EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS
            ),
            expectation_grounds_max_questions=_DEFAULT_EXPECTATION_GROUNDS_MAX_QUESTIONS,
            expectation_grounds_min_probability=(
                _DEFAULT_EXPECTATION_GROUNDS_MIN_PROBABILITY
            ),
            expectation_argument_enabled=False,
            expectation_undated_term_turns=_DEFAULT_EXPECTATION_UNDATED_TERM_TURNS,
            expectation_dated_term_turns=_DEFAULT_EXPECTATION_DATED_TERM_TURNS,
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
            belief_create_gate_enabled=False,
            belief_candidate_narrower=CHAR_BIGRAM_BM25,
            belief_candidate_top_k=_DEFAULT_BELIEF_CANDIDATE_TOP_K,
            belief_create_gate_min_confidence=_DEFAULT_BELIEF_CREATE_GATE_MIN_CONFIDENCE,
            salience_structured_failure_enabled=False,
            memo_distill_enabled=True,
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
            memo_tools_enabled=True,
            escape_llm_ssot_enabled=False,
            scenario_random_seed=None,
            prompt_dataset_capture_enabled=False,
            prompt_dataset_capture_failure_policy="fail",
            distant_view_trace_enabled=False,
            reason_first_two_step_enabled=False,
            end_on_all_down=False,
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

    def _validate_belief_create_gate(self) -> None:
        if self.belief_candidate_narrower not in SUPPORTED_TEXT_CANDIDATE_NARROWERS:
            raise ValueError(
                f"belief_candidate_narrower={self.belief_candidate_narrower!r} is not "
                f"recognized. valid: {sorted(SUPPORTED_TEXT_CANDIDATE_NARROWERS)}"
            )
        if self.belief_candidate_top_k < 1:
            raise ValueError("BELIEF_CANDIDATE_TOP_K must be 1 or greater")
        if not 0.0 < self.belief_create_gate_min_confidence <= 1.0:
            raise ValueError("BELIEF_CREATE_GATE_MIN_CONFIDENCE must be in (0, 1]")
        if not self.belief_create_gate_enabled:
            return
        if not (self.belief_consolidation_enabled and self.episodic_enabled):
            raise ValueError(
                "BELIEF_CREATE_GATE_ENABLED=1 requires BELIEF_CONSOLIDATION_ENABLED=1 "
                "and LLM_EPISODIC_ENABLED=1 (信念を固める処理が組まれないと gate が"
                "呼ばれない)"
            )
        if self.typed_judgment_provider == "off":
            raise ValueError(
                "BELIEF_CREATE_GATE_ENABLED=1 requires TYPED_JUDGMENT_PROVIDER "
                "other than off (問う先が無い)"
            )

    def _validate_expectation_settlement(self) -> None:
        for key, value in (
            ("EXPECTATION_SETTLEMENT_MAX_OPEN", self.expectation_settlement_max_open),
            (
                "EXPECTATION_SETTLEMENT_TIMELINE_TURNS",
                self.expectation_settlement_timeline_turns,
            ),
            (
                "EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS",
                self.expectation_event_max_delivery_attempts,
            ),
            ("EXPECTATION_UNDATED_TERM_TURNS", self.expectation_undated_term_turns),
            ("EXPECTATION_DATED_TERM_TURNS", self.expectation_dated_term_turns),
            (
                "EXPECTATION_GROUNDS_MAX_QUESTIONS",
                self.expectation_grounds_max_questions,
            ),
        ):
            if value < 1:
                raise ValueError(f"{key} must be 1 or greater")
        # 閾値を超えたものだけを根拠にするので、1 ではどの確率も根拠にならない。
        if not 0.0 < self.expectation_grounds_min_probability < 1.0:
            raise ValueError("EXPECTATION_GROUNDS_MIN_PROBABILITY must be in (0, 1)")
        if self.expectation_settlement_enabled and self.typed_judgment_provider == "off":
            raise ValueError(
                "EXPECTATION_SETTLEMENT_ENABLED=1 requires TYPED_JUDGMENT_PROVIDER "
                "other than off (問う先が無い)"
            )
        if not self.expectation_argument_enabled:
            return
        if not self.expectation_settlement_enabled:
            raise ValueError(
                "EXPECTATION_ARGUMENT_ENABLED=1 requires "
                "EXPECTATION_SETTLEMENT_ENABLED=1 (期限で閉じるのも清算なので、"
                "積んだ予期が閉じられずに増え続ける)"
            )
        if not self.prediction_context_id_enabled:
            raise ValueError(
                "EXPECTATION_ARGUMENT_ENABLED=1 requires "
                "PREDICTION_CONTEXT_ID_ENABLED=1 (頭にあった信念と想起を、"
                "そのターンのプロンプトから取る)"
            )
        if self.expected_result_policy != "off":
            raise ValueError(
                "EXPECTATION_ARGUMENT_ENABLED=1 requires "
                "LLM_EXPECTED_RESULT_POLICY=off (予測を書く欄が 2 つ並ぶ)"
            )

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


#: 型付き判断の provider。``llm`` は未実装なので受け取らない。受け取ると
#: 「指定したのに動かない」状態を profile から作れてしまう。
_VALID_TYPED_JUDGMENT_PROVIDERS = frozenset({"off", "jev", "stub"})

#: 接続先の既定。OpenRouter 経由。TypeSafe 直叩きも同じ body が通る。
_DEFAULT_TYPED_JUDGMENT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"

#: モデルは版を固定した ID を使う (design_decisions #39)。
_DEFAULT_TYPED_JUDGMENT_MODEL = "typesafe/jev-1.13"

#: 公表値は 70〜500ms。10 秒で打ち切れば、遅い 1 件が run を引き延ばさない。
_DEFAULT_TYPED_JUDGMENT_TIMEOUT_SECONDS = 10.0

#: キーの在り処の既定。値ではなく env の名前を profile に書く。
_DEFAULT_TYPED_JUDGMENT_API_KEY_ENV = "OPENROUTER_API_KEY"

#: memo を達成扱いにする確率の閾値の暫定値。
#:
#: 低くすると、語の重なりで誤検出していたのと同じ形で無関係な行動に hint を
#: 出す。人手ラベルで較正して決め直す (#1319)。
_DEFAULT_TYPED_JUDGMENT_MEMO_MIN_PROBABILITY = 0.7

#: 行動名を置き換える閾値の暫定値。
#:
#: **実測前の仮置きである。** 手元のプローブでは正しい救済が確率 0.97 /
#: confidence 0.96 だった。人手ラベル 50 件で較正して決め直す (#1319)。
#: 低くすると、意図していない操作に置き換えて別の失敗に化ける。
_DEFAULT_TYPED_JUDGMENT_ACTION_NAME_MIN_CONFIDENCE = 0.7

#: 対象の名前を置き換える閾値。過去 run で正しく置き換えた 5 件の最小は確率 0.93 /
#: 確信 0.89、誤った寄せは 0.8 台だった (scripts/jev_target_label_rescue_demo.py)。
_DEFAULT_TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE = 0.85

#: 動く必要がある確率がこれ未満のときだけ回さない。発言単位の起動判定 (#217) で
#: 0.05 → 0.15 に上げた値を引き継ぐ。tick 単位では未較正。
_DEFAULT_TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW = 0.15

#: 過去 run の窓 20 件で測った (scripts/jev_semantic_repeat_demo.py)。繰り返しで
#: ない窓の最大は 0.51 で、完全一致で拾えなかった繰り返し 10 件のうち 6 件が
#: 0.86 以上だった。警告が待機へ押すのを避けるため、非繰り返しの最大から離して置く。
_DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY = 0.8
_DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW = 4

#: 過去 run の行動と結果に本人の目的を当てた 23 件で測った
#: (scripts/jev_goal_completion_hint_demo.py)。達成していない 14 件の最大は 0.18 で、
#: 達成した 9 件は 0.9 / 0.9 / 0.82 / 0.68 と 0.35 以下に割れた。0.7 では明らかな
#: 達成 (渡す目的で 2 件とも渡せた、0.68) を落とすので、未達の最大から離して 0.5 に置く。
_DEFAULT_TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY = 0.5

#: 清算待ちの上限の暫定値。#1436 の試しで DeepSeek は 1 ターンに平均 2.9 件の予期を
#: 書き、形の判定で 15% ほどが外れた。数ターン分を抱えられる値に置き、予期を積む
#: 入口 (#1441) で実際の件数を見て決め直す。
_DEFAULT_EXPECTATION_SETTLEMENT_MAX_OPEN = 8
#: 見せる時系列のターン数の暫定値。#1436 の試作で、結果が 1 ターン後に届く予期は
#: 次のターンに当たったへ移った。数ターン遅れて届く結果まで拾える長さに置く。
_DEFAULT_EXPECTATION_SETTLEMENT_TIMELINE_TURNS = 4
_DEFAULT_EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS = 3
#: 根拠の問いの上限。頭に載る信念は最大 3 件で、1 ターンに書く予期は平均 3 件ほど
#: (#1436 の試し)。予期 1 件分の信念とエピソードは並べ切れ、1 ターンの問いが数十件に
#: 膨らまない値に置く。過去 run の 64 手を組み直した試し (#1484) では最大 7 件だった。
_DEFAULT_EXPECTATION_GROUNDS_MAX_QUESTIONS = 12
#: 同じ試しの清算できる予期で、0.5 では選んだ 19 件のうち根拠でないものは 1 件、0.4 では 33 件中 5 件。
#: 取りこぼしより、関係の無い信念に材料を積むほうが悪循環の入口になるので 0.5 に置く。
_DEFAULT_EXPECTATION_GROUNDS_MIN_PROBABILITY = 0.5
_DEFAULT_EXPECTATION_UNDATED_TERM_TURNS = 5
_DEFAULT_EXPECTATION_DATED_TERM_TURNS = 30


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


def _strip_or_none(value: str | None) -> str | None:
    """空文字 / None / 空白のみ → None、それ以外は strip した値。"""
    if value is None:
        return None
    s = value.strip()
    return s or None


def _parse_truthy(value: str | None, *, default: bool) -> bool:
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
_VALID_TOOL_CHOICES = frozenset({"required", "auto"})
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


def _resolve_ratio_with_default(
    source: Mapping[str, str], key: str, *, default: float
) -> float:
    """0 より大きく 1 以下の比率を解決する。範囲外は起動前に拒否する。

    確率と比べる閾値なので、1 を超える値や 0 以下は意味を持たない。黙って
    丸めると「設定したのに効かない」状態になる。
    """
    raw = (source.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key}={raw!r} is not a number") from exc
    if not 0.0 < value <= 1.0:
        raise ValueError(f"{key}={value} must be in (0, 1]")
    return value


def _resolve_typed_judgment_provider(source: Mapping[str, str]) -> str:
    """型付き判断の provider を解決し、未知値は起動前に拒否する。

    既定は ``off``。綴りを間違えたときに ``off`` へ黙って縮退すると、
    「有効にしたつもりの run」が現行の振る舞いで回り、比較実験の土台が崩れる。
    """
    raw = (source.get("TYPED_JUDGMENT_PROVIDER") or "off").strip().lower()
    if raw not in _VALID_TYPED_JUDGMENT_PROVIDERS:
        raise ValueError(
            f"TYPED_JUDGMENT_PROVIDER={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_TYPED_JUDGMENT_PROVIDERS)}"
        )
    return raw


def _resolve_positive_float_with_default(
    source: Mapping[str, str], key: str, *, default: float
) -> float:
    raw = (source.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key}={raw!r} is not a number") from exc
    if value <= 0:
        raise ValueError(f"{key}={value} must be greater than 0")
    return value


def _resolve_tool_choice(source: Mapping[str, str]) -> str:
    """1段階ターンの ``tool_choice`` を解決し、未知値は起動前に拒否する。"""

    raw = (source.get("LLM_TOOL_CHOICE") or "required").strip().lower()
    if raw not in _VALID_TOOL_CHOICES:
        raise ValueError(
            f"LLM_TOOL_CHOICE={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_TOOL_CHOICES)}"
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
) -> int | None:
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
) -> float | None:
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
