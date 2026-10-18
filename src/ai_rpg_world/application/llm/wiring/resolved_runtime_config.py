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
5. **既存 resolver の活用**: 内部で既存 ``resolve_short_term_memory_turn_window`` 等を
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

from ai_rpg_world.application.llm.services.world_llm_turn.llm_failure_streak_monitor import (
    DEFAULT_FAILURE_STREAK_ABORT,
)
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailurePolicy,
)

_DEFAULT_BEING_EPISODE_INDEX_LIMIT = 10
_DEFAULT_BEING_EPISODE_RECALL_MAX_HANDLES = 3

SUPPORTED_RUNTIME_CONFIG_KEYS = frozenset({
    "BEING_EPISODE_INDEX_LIMIT",
    "BEING_EPISODE_RECALL_MAX_HANDLES",
    "LLM_CLIENT",
    "LLM_FAILURE_STREAK_ABORT",
    "LLM_IDLE_TIMEOUT_TICKS",
    "LLM_MAX_OUTPUT_TOKENS",
    "LLM_MODEL",
    "LLM_RATE_LIMIT_RETRY_ATTEMPTS",
    "LLM_RATE_LIMIT_RETRY_BASE_SLEEP",
    "LLM_REASONING_EFFORT",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "LLM_SESSION_ID_ENABLED",
    "LLM_TOOL_CHOICE",
    "LLM_TURN_PARALLEL_WORKERS",
    "LLM_WALL_TIME_CAP_SECONDS",
    "OPENAI_API_BASE",
    "OPENROUTER_PROVIDER",
    "OPENROUTER_QUANTIZATION",
    "PROMPT_DATASET_CAPTURE_FAILURE_POLICY",
    "SCENARIO_RANDOM_SEED",
    "SHORT_TERM_MEMORY_TURN_CAP",
    "SHORT_TERM_MEMORY_TURN_COMPACT_COUNT",
    "TYPED_JUDGMENT_ACTION_NAME_MIN_CONFIDENCE",
    "TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE",
    "TYPED_JUDGMENT_API_KEY_ENV",
    "TYPED_JUDGMENT_MEMO_MIN_PROBABILITY",
    "TYPED_JUDGMENT_ENDPOINT",
    "TYPED_JUDGMENT_MODEL",
    "TYPED_JUDGMENT_PROVIDER",
    "TYPED_JUDGMENT_SEMANTIC_REPEAT_ENABLED",
    "TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY",
    "TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW",
    "TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED",
    "TYPED_JUDGMENT_TIMEOUT_SECONDS",
    "WORLD_TICK_FAILURE_POLICY",
})

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
        typed_judgment_loop_diagnosis_enabled: ループ警告の発火時に、繰り返しの
            理由を問うて文面を選ぶ (#1411)。**既定は off**。provider が off なら
            有効にしても入らない
        typed_judgment_semantic_repeat_enabled: 直近の行動の窓を材料に、言い直しや
            往復のような意味上の繰り返しを問う (#1412)。**既定は off**
        typed_judgment_semantic_repeat_min_probability: 繰り返しと見なす確率の閾値。
            警告が待機へ押すのを避けるため高めに置く
        typed_judgment_semantic_repeat_window: 判断に渡す直近の行動の件数
    """

    # LLM client
    llm_client_kind: str
    llm_model: str | None
    llm_api_key: str | None
    llm_api_base: str | None
    llm_request_timeout_seconds: float
    llm_reasoning_effort: str
    llm_max_output_tokens: int | None
    llm_wall_time_cap_seconds: float | None
    llm_rate_limit_retry_attempts: int
    llm_rate_limit_retry_base_sleep: float
    llm_turn_parallel_workers: int
    llm_idle_timeout_ticks: int
    llm_failure_streak_abort: int
    llm_tool_choice: str
    llm_session_id_enabled: bool

    # OpenRouter routing
    openrouter_provider: str | None
    openrouter_quantization: str | None

    # 型付き判断 (#1319)
    typed_judgment_provider: str
    typed_judgment_endpoint: str
    typed_judgment_model: str
    typed_judgment_timeout_seconds: float
    typed_judgment_api_key_env: str
    typed_judgment_action_name_min_confidence: float
    typed_judgment_target_label_min_confidence: float
    typed_judgment_memo_min_probability: float
    typed_judgment_loop_diagnosis_enabled: bool
    typed_judgment_semantic_repeat_enabled: bool
    typed_judgment_semantic_repeat_min_probability: float
    typed_judgment_semantic_repeat_window: int


    short_term_memory_turn_cap: int = 20
    short_term_memory_turn_compact_count: int = 10



    # Active episodic recall tool (Issue #526 後続)。

    # #1623: 目次に載せる件数 N と、1 回に呼び出せる件数 M。
    being_episode_index_limit: int = _DEFAULT_BEING_EPISODE_INDEX_LIMIT
    being_episode_recall_max_handles: int = _DEFAULT_BEING_EPISODE_RECALL_MAX_HANDLES

    # Goal / stagnation 系。

    # Prompt / tool 表面。
    scenario_random_seed: int | None = None
    prompt_dataset_capture_failure_policy: str = "fail"
    # reason-first 2段階ターン。True でも常時発火ではなく、Phase A 入口で
    # 既存の loop_guard / action_result / stagnation state を読んだ gated 発火にする。
    # 設定のキーは無く、llm_tool_choice から決める (_reason_first_two_step_enabled_for)。
    reason_first_two_step_enabled: bool = True

    # 世界の tick の 1 体ぶんの例外を、取りやめて続けるか止めるか (design_decisions D1558)。
    # 既定が isolate なのは、その場で書いた実験設定がキーを書き忘れても run を捨てないため。
    world_tick_failure_policy: str = WorldTickFailurePolicy.ISOLATE.value

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
        WorldTickFailurePolicy.parse(self.world_tick_failure_policy)
        if self.prompt_dataset_capture_failure_policy not in {"fail", "warn"}:
            raise ValueError(
                "prompt_dataset_capture_failure_policy="
                f"{self.prompt_dataset_capture_failure_policy!r} is not recognized. "
                "valid: ['fail', 'warn']"
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
          ``_llm_client_factory`` の値) を呼ぶ薄いラッパー
        - 不正値は各 resolver が ``ValueError`` を投げる (PR #434 fail-fast 継承)

        Raises:
            ValueError: values のいずれかが不正値のとき
        """
        # 既存 resolver の import は関数内で行い、循環参照を避ける
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            resolve_short_term_memory_turn_window,
        )

        source: Mapping[str, str] = values if values is not None else {}
        _validate_runtime_config_keys(source)

        # 既存 resolver は env=None だと os.environ を読むものがあるため、
        # ここでは必ず明示 mapping を渡す。実験設定の入力経路を
        # profile/config → 本 DTO の 1 本に固定するため。
        (
            short_term_memory_turn_cap,
            short_term_memory_turn_compact_count,
        ) = resolve_short_term_memory_turn_window(env=source)

        # LLM client kind (factory と同じロジックで解決)
        llm_client_kind = _resolve_llm_client_kind(source)
        llm_model = _strip_or_none(source.get("LLM_MODEL"))
        llm_api_key = None
        llm_api_base = _strip_or_none(source.get("OPENAI_API_BASE"))
        llm_request_timeout_seconds = _resolve_timeout_seconds(source)
        llm_reasoning_effort = _resolve_reasoning_effort(source)
        llm_max_output_tokens = _resolve_optional_positive_int(
            source, "LLM_MAX_OUTPUT_TOKENS"
        )
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
        if typed_judgment_semantic_repeat_window < 2:
            raise ValueError(
                "TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW must be 2 or greater"
            )
        # OpenRouter routing
        openrouter_provider = _strip_or_none(source.get("OPENROUTER_PROVIDER"))
        openrouter_quantization = _strip_or_none(source.get("OPENROUTER_QUANTIZATION"))

        # Prediction (#526 / U3): エピソード再解釈 on/off



        being_episode_index_limit = _resolve_positive_int(
            source, "BEING_EPISODE_INDEX_LIMIT", default=_DEFAULT_BEING_EPISODE_INDEX_LIMIT
        )
        being_episode_recall_max_handles = _resolve_positive_int(
            source,
            "BEING_EPISODE_RECALL_MAX_HANDLES",
            default=_DEFAULT_BEING_EPISODE_RECALL_MAX_HANDLES,
        )
        scenario_random_seed = _resolve_optional_int(source, "SCENARIO_RANDOM_SEED")
        prompt_dataset_capture_failure_policy = (
            source.get("PROMPT_DATASET_CAPTURE_FAILURE_POLICY") or "fail"
        ).strip().lower()
        reason_first_two_step_enabled = _reason_first_two_step_enabled_for(
            llm_tool_choice
        )
        try:
            world_tick_failure_policy = WorldTickFailurePolicy.parse(
                source.get("WORLD_TICK_FAILURE_POLICY") or WorldTickFailurePolicy.ISOLATE.value
            ).value
        except ValueError as exc:
            raise ValueError(f"WORLD_TICK_FAILURE_POLICY: {exc}") from exc

        return cls(
            short_term_memory_turn_cap=short_term_memory_turn_cap,
            short_term_memory_turn_compact_count=short_term_memory_turn_compact_count,
            llm_client_kind=llm_client_kind,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_api_base=llm_api_base,
            llm_request_timeout_seconds=llm_request_timeout_seconds,
            llm_reasoning_effort=llm_reasoning_effort,
            llm_max_output_tokens=llm_max_output_tokens,
            llm_wall_time_cap_seconds=llm_wall_time_cap_seconds,
            llm_rate_limit_retry_attempts=llm_rate_limit_retry_attempts,
            llm_rate_limit_retry_base_sleep=llm_rate_limit_retry_base_sleep,
            llm_turn_parallel_workers=llm_turn_parallel_workers,
            llm_idle_timeout_ticks=llm_idle_timeout_ticks,
            llm_failure_streak_abort=llm_failure_streak_abort,
            llm_tool_choice=llm_tool_choice,
            llm_session_id_enabled=llm_session_id_enabled,
            openrouter_provider=openrouter_provider,
            openrouter_quantization=openrouter_quantization,
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
            typed_judgment_loop_diagnosis_enabled=typed_judgment_loop_diagnosis_enabled,
            typed_judgment_semantic_repeat_enabled=typed_judgment_semantic_repeat_enabled,
            typed_judgment_semantic_repeat_min_probability=(
                typed_judgment_semantic_repeat_min_probability
            ),
            typed_judgment_semantic_repeat_window=typed_judgment_semantic_repeat_window,
            being_episode_index_limit=being_episode_index_limit,
            being_episode_recall_max_handles=being_episode_recall_max_handles,
            scenario_random_seed=scenario_random_seed,
            prompt_dataset_capture_failure_policy=prompt_dataset_capture_failure_policy,
            reason_first_two_step_enabled=reason_first_two_step_enabled,
            world_tick_failure_policy=world_tick_failure_policy,
        )

    @classmethod
    def for_tests(cls, **overrides: Any) -> ResolvedLlmRuntimeConfig:
        """test 用の safe default factory (PR #446 architect 提案)。

        全フィールドを「最も無害な default」で埋め、上書きしたい項目だけ
        keyword で渡す。test fixture の肥大化を防ぐ。

        - LLM 系は全部 ``stub`` / None で「実 LLM を呼ばない」
        - feature flag は全部 OFF。reason-first 2段階ターンだけは設定で切れないので、
          本番と同じく llm_tool_choice から決める

        Usage:
            cfg = ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="jev",
            )
        """
        defaults: dict[str, Any] = dict(
            short_term_memory_turn_cap=20,
            short_term_memory_turn_compact_count=10,
            llm_client_kind="stub",
            llm_model=None,
            llm_api_key=None,
            llm_api_base=None,
            llm_request_timeout_seconds=90.0,
            llm_reasoning_effort="minimal",
            llm_max_output_tokens=None,
            llm_wall_time_cap_seconds=None,
            llm_rate_limit_retry_attempts=3,
            llm_rate_limit_retry_base_sleep=2.0,
            llm_turn_parallel_workers=0,
            llm_idle_timeout_ticks=6,
            llm_failure_streak_abort=DEFAULT_FAILURE_STREAK_ABORT,
            llm_tool_choice="required",
            llm_session_id_enabled=True,
            openrouter_provider=None,
            openrouter_quantization=None,
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
            typed_judgment_loop_diagnosis_enabled=False,
            typed_judgment_semantic_repeat_enabled=False,
            typed_judgment_semantic_repeat_min_probability=(
                _DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY
            ),
            typed_judgment_semantic_repeat_window=(
                _DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW
            ),
            being_episode_index_limit=_DEFAULT_BEING_EPISODE_INDEX_LIMIT,
            being_episode_recall_max_handles=_DEFAULT_BEING_EPISODE_RECALL_MAX_HANDLES,
            scenario_random_seed=None,
            prompt_dataset_capture_failure_policy="fail",
            reason_first_two_step_enabled=True,
            world_tick_failure_policy=WorldTickFailurePolicy.ISOLATE.value,
        )
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise TypeError(
                f"Unknown override keys: {sorted(unknown)}. "
                f"valid: {sorted(defaults)}"
            )
        defaults.update(overrides)
        if "reason_first_two_step_enabled" not in overrides:
            defaults["reason_first_two_step_enabled"] = (
                _reason_first_two_step_enabled_for(defaults["llm_tool_choice"])
            )
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


def _reason_first_two_step_enabled_for(llm_tool_choice: str) -> bool:
    """reason-first 2段階ターンを使うかを tool_choice から決める。

    第1段は named tool_choice を使う。DeepSeek で thinking + named の対応を
    実 API なしに保証できないため、auto 比較腕では 2段階経路を実効 OFF にし、
    解決済み設定にも false として残す。
    """
    return llm_tool_choice != "auto"


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

#: 過去 run の窓 20 件で測った (scripts/jev_semantic_repeat_demo.py)。繰り返しで
#: ない窓の最大は 0.51 で、完全一致で拾えなかった繰り返し 10 件のうち 6 件が
#: 0.86 以上だった。警告が待機へ押すのを避けるため、非繰り返しの最大から離して置く。
_DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY = 0.8
_DEFAULT_TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW = 4



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
    """bool 解釈 (PR #434 ポリシー)。

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

    既定は ``"minimal"``。本命の profile をはじめ、実 LLM の run の多くが
    minimal で動いており、書き忘れた run だけが熟考なしで走るのを避ける (#1631)。
    ``"none"`` を使う profile は値を明示している。
    空文字は「reasoning 関連フィールドを一切注入しない」を表す明示値として許す。
    """
    raw = source.get("LLM_REASONING_EFFORT")
    value = "minimal" if raw is None else raw.strip().lower()
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

    負値・非数値は ``ValueError`` で fail-fast。
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


def _resolve_optional_positive_int(
    source: Mapping[str, str], key: str
) -> int | None:
    raw = (source.get(key) or "").strip()
    if not raw:
        return None
    return _resolve_positive_int(source, key, default=0)


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
