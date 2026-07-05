"""LLM 配線まわりの env-driven feature flag。

実験スクリプトから A/B 検証する用途で、scenario 内容と直交する knob を
ここに集約する。既存の他の env var (``EPISODIC_PROMOTION_FORCE_FULL_SCAN``,
``SUBJECTIVE_EPISODE_DB_PATH``, ``LLM_MODEL``, ``PROMPT_SECTION_ORDER`` 等) と
同じ慣例に揃える。

設計指針:

- **default は OFF** (新規機能を実験中の検証変数として導入するため、env で
  明示的に ON にしたときだけ動かす)。詳細は
  ``docs/memory_system/semantic_memory_activation_plan.md`` §9
- **「配線 (wire)」と「有効化 (enable)」を分離**: コードパスは常に通って
  いるが env 未設定なら不活性
- 値は ``"1" / "true" / "yes" / "on"`` (case-insensitive) を ON とみなす。
  ``EPISODIC_PROMOTION_FORCE_FULL_SCAN`` と同じパース規則
"""

from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

_logger = logging.getLogger(__name__)


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _parse_bool_env(
    var_name: str,
    env: Optional[Mapping[str, str]] = None,
    *,
    default: bool = False,
) -> bool:
    """env var を bool として解釈する。値が未設定なら ``default``。

    - truthy: ``"1" / "true" / "yes" / "on"`` (case-insensitive) → True
    - falsy:  ``"0" / "false" / "no" / "off"`` (case-insensitive) → False
    - 上記以外の文字列 → ``ValueError`` (silent fallback 防止: 過去に
      ``MEMORY_KIND=rolling`` のような typo が黙って default に縮退して
      実験前提を壊した事例があった / PR #433 で発覚)

    Args:
        var_name: 環境変数名 (エラーメッセージに含める)
        env: 上書き用 mapping (テストで使う)。None なら ``os.environ``
        default: 未設定時の戻り値

    Raises:
        ValueError: 値が truthy / falsy のいずれにも該当しないとき
    """
    source = env if env is not None else os.environ
    raw = (source.get(var_name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    raise ValueError(
        f"{var_name}={raw!r} is not a recognized boolean. "
        f"truthy: {sorted(_TRUTHY)}, falsy: {sorted(_FALSY)}"
    )


# ──────────────────────────────────────────────────────────────────
# Episodic memory active retrieval
# ──────────────────────────────────────────────────────────────────


ENV_EPISODIC_EXPLORE_RELATED_ENABLED = "EPISODIC_EXPLORE_RELATED_ENABLED"


def resolve_episodic_explore_related_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """``memory_explore_related`` tool を LLM に expose するか。

    `EPISODIC_EXPLORE_RELATED_ENABLED=1` で ON、未設定 / その他は OFF。

    実装 ([`episodic_memory_explore_tool_executor`](../services/executors/episodic_memory_explore_tool_executor.py))
    は既にある。LLM がリンクを能動的に辿るための tool だが、現在は episodic
    chunk 生成 / passive recall の検証中なので default OFF。検証フェーズで
    明示的に env で ON にして動作確認する。
    """
    return _parse_bool_env(ENV_EPISODIC_EXPLORE_RELATED_ENABLED, env=env, default=False)


def log_episodic_explore_related_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。run の再現性確保用。"""
    _logger.info(
        "%s resolved to %s",
        ENV_EPISODIC_EXPLORE_RELATED_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: LLM gist generation
# ──────────────────────────────────────────────────────────────────


ENV_SEMANTIC_LLM_GIST_ENABLED = "SEMANTIC_LLM_GIST_ENABLED"


def resolve_semantic_llm_gist_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """``SemanticGistService`` を ``EpisodicSemanticClusterPromotionService`` に
    注入するか。

    `SEMANTIC_LLM_GIST_ENABLED=1` で ON、未設定 / その他は OFF。

    OFF だと cluster 昇格時の gist は決定論的な concat のまま (検証中の
    挙動保持)。ON にすると LLM 抽象化を試み、失敗時は決定論 gist にフォール
    バックする (silent failure 防止のため warning ログを出す)。

    詳細は docs/memory_system/semantic_memory_activation_plan.md §9。
    """
    return _parse_bool_env(ENV_SEMANTIC_LLM_GIST_ENABLED, env=env, default=False)


def log_semantic_llm_gist_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_SEMANTIC_LLM_GIST_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: passive top-K recall into prompt
# ──────────────────────────────────────────────────────────────────


ENV_SEMANTIC_PASSIVE_TOP_K = "SEMANTIC_PASSIVE_TOP_K"
# default 0 = §learned section ごと非表示。検証で意図的に有効化するときは
# 3 程度から始める想定。実験 #25 後続で実測して調整。
DEFAULT_SEMANTIC_PASSIVE_TOP_K = 0


def resolve_semantic_passive_top_k(
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """``SEMANTIC_PASSIVE_TOP_K`` env var を非負整数に解釈する。

    - 未設定 / 空文字 → default (0)
    - 非整数 / 負数 → ``ValueError`` (silent fallback 防止 / PR #433 経緯)
    - 値が ``>0`` なら prompt に §learned section が出る (Phase 1c)

    Raises:
        ValueError: 非整数または負数のとき
    """
    source = env if env is not None else os.environ
    raw = (source.get(ENV_SEMANTIC_PASSIVE_TOP_K) or "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_PASSIVE_TOP_K
    try:
        v = int(raw)
    except ValueError:
        raise ValueError(
            f"{ENV_SEMANTIC_PASSIVE_TOP_K}={raw!r} must be a non-negative integer "
            f"(got non-integer value)"
        )
    if v < 0:
        raise ValueError(
            f"{ENV_SEMANTIC_PASSIVE_TOP_K}={v} must be >= 0 "
            f"(0 = §learned section disabled)"
        )
    return v


def log_semantic_passive_top_k_state(top_k: int) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %d (0 = §learned section disabled)",
        ENV_SEMANTIC_PASSIVE_TOP_K,
        top_k,
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: active search tool (Phase 1d)
# ──────────────────────────────────────────────────────────────────


ENV_SEMANTIC_SEARCH_ENABLED = "SEMANTIC_SEARCH_ENABLED"


def resolve_semantic_search_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """``memory_search_semantic`` tool を LLM に expose するか。

    `SEMANTIC_SEARCH_ENABLED=1` で ON、未設定 / その他は OFF。

    実装 (``SemanticMemorySearchToolExecutor``) は常に動くが、tool 自体を
    LLM に見せるかは env で制御する。検証フェーズで明示的に有効化する。

    詳細は docs/memory_system/semantic_memory_activation_plan.md §5.2, §9。
    """
    return _parse_bool_env(ENV_SEMANTIC_SEARCH_ENABLED, env=env, default=False)


def log_semantic_search_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_SEMANTIC_SEARCH_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Episodic memory: active recall tool (Issue #526 後続)
# ──────────────────────────────────────────────────────────────────


ENV_EPISODIC_RECALL_ENABLED = "EPISODIC_RECALL_ENABLED"


def resolve_episodic_recall_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """``memory_recall_episodes`` tool を LLM に expose するか。

    ``EPISODIC_RECALL_ENABLED=1`` で ON、未設定 / その他は OFF。

    Issue #526 の不在 2 (agent-driven 想起) に対する v0 実装。検証
    フェーズで明示的に有効化する。
    """
    return _parse_bool_env(ENV_EPISODIC_RECALL_ENABLED, env=env, default=False)


def log_episodic_recall_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_EPISODIC_RECALL_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Short-term memory: rolling summary (Phase 2)
# ──────────────────────────────────────────────────────────────────


ENV_SHORT_TERM_MEMORY_KIND = "SHORT_TERM_MEMORY_KIND"
SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW = "sliding_window"
SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY = "rolling_summary"
_VALID_SHORT_TERM_MEMORY_KINDS = frozenset({
    SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW,
    SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
})


def resolve_short_term_memory_kind(
    env: Optional[Mapping[str, str]] = None,
) -> str:
    """``SHORT_TERM_MEMORY_KIND`` env を解決する。

    - default は ``sliding_window`` (検証中の安定設定)
    - 未知文字列は ``ValueError`` (silent fallback 防止 / PR #433 経緯:
      短縮形 ``rolling`` を渡したのに silent fallback で sliding_window が
      使われ、実験 24h 分が無駄になりかけた)

    詳細は docs/memory_system/short_term_memory_design.md §6.1。

    Raises:
        ValueError: 未知の文字列 (短縮形 typo 等) のとき
    """
    source = env if env is not None else os.environ
    raw = (source.get(ENV_SHORT_TERM_MEMORY_KIND) or "").strip().lower()
    if not raw:
        return SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW
    if raw not in _VALID_SHORT_TERM_MEMORY_KINDS:
        raise ValueError(
            f"{ENV_SHORT_TERM_MEMORY_KIND}={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_SHORT_TERM_MEMORY_KINDS)}"
        )
    return raw


def log_short_term_memory_kind_state(kind: str) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info("%s resolved to %s", ENV_SHORT_TERM_MEMORY_KIND, kind)


# ──────────────────────────────────────────────────────────────────
# Short-term memory: L4 generation scheduler mode (Phase 2.1)
# ──────────────────────────────────────────────────────────────────


ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE = "SHORT_TERM_MEMORY_SCHEDULER_MODE"
SCHEDULER_MODE_INLINE = "inline"
SCHEDULER_MODE_THREAD_POOL = "thread_pool"
_VALID_SCHEDULER_MODES = frozenset({
    SCHEDULER_MODE_INLINE,
    SCHEDULER_MODE_THREAD_POOL,
})


def resolve_short_term_memory_scheduler_mode(
    env: Optional[Mapping[str, str]] = None,
) -> str:
    """``SHORT_TERM_MEMORY_SCHEDULER_MODE`` env を解決する。

    - **default は ``thread_pool``** (K run #466 で検証済、tick が L4 生成 LLM
      の 2-5s ブロックしない)
    - ``inline`` を明示指定すると Phase 2 互換 (tick がブロックする) に戻せる。
      テスト fixture や同期保証が必要なときに使う
    - ``max_workers=1`` (既定) で race は構造的に防止される
    - rolling_summary を選んでも scheduler は orthogonal な knob として独立
    - 未知文字列は ``ValueError`` (silent fallback 防止 / PR #433 経緯)

    詳細: docs/memory_system/short_term_memory_design.md §6 (Phase 2.1)。
    default 変更の経緯: docs/memory_system/k_run_thread_pool_deepseek_analysis.md。

    Raises:
        ValueError: 未知の文字列のとき
    """
    source = env if env is not None else os.environ
    raw = (source.get(ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE) or "").strip().lower()
    if not raw:
        return SCHEDULER_MODE_THREAD_POOL
    if raw not in _VALID_SCHEDULER_MODES:
        raise ValueError(
            f"{ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE}={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_SCHEDULER_MODES)}"
        )
    return raw


def log_short_term_memory_scheduler_mode_state(mode: str) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_SHORT_TERM_MEMORY_SCHEDULER_MODE,
        mode,
    )


# ──────────────────────────────────────────────────────────────────
# 予測誤差統一設計 U1: prediction_context_id / PredictionOutcome
# ──────────────────────────────────────────────────────────────────


ENV_PREDICTION_CONTEXT_ID_ENABLED = "PREDICTION_CONTEXT_ID_ENABLED"


def resolve_prediction_context_id_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """``PredictionContextLedger`` (id の発行・消費) を動かすか。

    ``PREDICTION_CONTEXT_ID_ENABLED=1`` で ON、未設定 / その他は OFF。

    id 自体は prompt 本文にも LLM 応答にも一切現れない (trace / snapshot
    のみに残るメタデータ) ため挙動への影響はほぼ無いが、新機構は default OFF
    で入れる本計画の共通規約 (docs/memory_system/
    prediction_error_unified_implementation_plan.md §0) に従う。OFF のときは
    ``DefaultPromptBuilder`` / ``ActionResultRecorder`` に ledger が渡らず、
    ``prediction_context_id`` は常に None (= 導入前と同じ挙動)。
    """
    return _parse_bool_env(ENV_PREDICTION_CONTEXT_ID_ENABLED, env=env, default=False)


def log_prediction_context_id_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_PREDICTION_CONTEXT_ID_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: belief evidence buffer 転記 (U2, 証拠台帳統一設計)
# ──────────────────────────────────────────────────────────────────


ENV_BELIEF_EVIDENCE_ENABLED = "BELIEF_EVIDENCE_ENABLED"


def resolve_belief_evidence_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """chunk 主観補完完了時に ``BeliefEvidence`` 転記を行うか。

    ``BELIEF_EVIDENCE_ENABLED=1`` で ON、未設定 / その他は OFF。

    ON でも semantic の想起挙動 (§learned section 等) は一切変わらない。
    prediction_error が非 None のときだけ evidence buffer に 1 件積む
    (= 学習の素材が観測可能になるだけ)。固着パス (belief journal への
    統合) は別 PR (U3) のスコープ。

    詳細は docs/memory_system/semantic_learning_consolidation_design.md。
    """
    return _parse_bool_env(ENV_BELIEF_EVIDENCE_ENABLED, env=env, default=False)


def log_belief_evidence_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_BELIEF_EVIDENCE_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: 固着パス BeliefConsolidationCoordinator (U3b)
# ──────────────────────────────────────────────────────────────────


ENV_BELIEF_CONSOLIDATION_ENABLED = "BELIEF_CONSOLIDATION_ENABLED"


def resolve_belief_consolidation_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """``BeliefConsolidationCoordinator`` を配線し belief journal への
    唯一の書き込み経路として動かすか。

    ``BELIEF_CONSOLIDATION_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のときは、``EpisodicSemanticClusterPromotionService`` が
    現行どおり semantic store に直接書き込む (recall_count>=3 ゲート込み)。
    ON にすると、その直書きが FAMILIARITY ``BeliefEvidence`` の emit
    (ゲート無し) に切り替わり、belief journal への書き込みは
    ``BeliefConsolidationCoordinator`` の固着パス経由に一本化される。

    詳細は docs/memory_system/semantic_learning_consolidation_design.md
    「固着パス: BeliefConsolidationCoordinator」節。
    """
    return _parse_bool_env(ENV_BELIEF_CONSOLIDATION_ENABLED, env=env, default=False)


def log_belief_consolidation_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_BELIEF_CONSOLIDATION_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: salience + STRUCTURED_FAILURE (U6)
# ──────────────────────────────────────────────────────────────────


ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED = "SALIENCE_STRUCTURED_FAILURE_ENABLED"


def resolve_salience_structured_failure_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """salience 判定 + STRUCTURED_FAILURE 転記 + high salience cap を動かすか。

    ``SALIENCE_STRUCTURED_FAILURE_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - chunk 主観補完 LLM の system prompt に salience 節は出ず、
      ``episode.salience`` は常に ``"low"`` (= 導入前と byte 同一の prompt)
    - loop_guard の cross_tick_failure 閾値到達は
      ``BeliefEvidence(source_kind=STRUCTURED_FAILURE)`` に転記されない
      (``record_and_check`` 自体は ``CrossTickFailureTrigger`` を返すが、
      呼び出し側で transcriber が None のため no-op になる)

    ON のとき、chunk 主観補完 LLM が salience を判定し、salience=high の
    evidence が件数閾値なしで次回固着パスに載る (S2 一撃学習)。加えて
    STRUCTURED_FAILURE evidence の転記も有効になる (S5 手続き学習)。

    詳細は docs/memory_system/semantic_learning_consolidation_design.md
    「salience (一撃学習の経路)」節、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U6 節。
    """
    return _parse_bool_env(
        ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED, env=env, default=False
    )


def log_salience_structured_failure_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_SALIENCE_STRUCTURED_FAILURE_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: MEMO_DISTILL 転記 (U5)
# ──────────────────────────────────────────────────────────────────


ENV_MEMO_DISTILL_ENABLED = "MEMO_DISTILL_ENABLED"


def resolve_memo_distill_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """memo_done 完了時に MEMO_DISTILL ``BeliefEvidence`` 転記を行うか。

    ``MEMO_DISTILL_ENABLED=1`` で ON、未設定 / その他は OFF。

    ON でも memo / memo_done の応答文言や既存挙動は一切変わらない。完了した
    memo 本文 + fulfillment_context を無条件で evidence buffer に積むだけ
    (ノイズかどうかの判定はしない)。固着パス (discard / create の意味判定)
    は U3b で実装済みの ``BeliefConsolidationCoordinator`` の仕事で、本 flag
    のスコープ外。

    詳細は docs/memory_system/semantic_learning_consolidation_design.md
    「証拠の入口」表の MEMO_DISTILL 行。
    """
    return _parse_bool_env(ENV_MEMO_DISTILL_ENABLED, env=env, default=False)


def log_memo_distill_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_MEMO_DISTILL_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: attribution + CONFIRMATION (U4)
# ──────────────────────────────────────────────────────────────────


ENV_BELIEF_ATTRIBUTION_ENABLED = "BELIEF_ATTRIBUTION_ENABLED"


def resolve_belief_attribution_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """「信じて行動した」の attribution (S3) + CONFIRMATION (的中の支持) を
    動かすか。

    ``BELIEF_ATTRIBUTION_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - ``ActionResultEntry.in_context_belief_ids`` は常に空 (= chunk_coordinator /
      scheduler が計算自体を行わない)
    - PREDICTION_ERROR evidence に in-context belief が添付されない
    - CONFIRMATION evidence が生成されない
    - 固着パスの shortlist に in-context belief を強制搭載する経路が働かない
      (``BeliefEvidence.in_context_belief_ids`` が常に空のため)

    ON にするには prompt build 時に belief_id が in-context として記録されて
    いる必要がある (= 実質的に ``PREDICTION_CONTEXT_ID_ENABLED`` (U1) が ON で
    ないと belief_ids が流れてこない)。U1 flag が OFF のまま本 flag だけ ON に
    しても、``PredictionContextLedger`` 自体が配線されず
    ``in_context_belief_ids`` は常に空になるため安全に縮退する (= 実害なし)。

    詳細は docs/memory_system/semantic_learning_consolidation_design.md
    「信用割り当て: attribution ledger」節、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U4 節。
    """
    return _parse_bool_env(ENV_BELIEF_ATTRIBUTION_ENABLED, env=env, default=False)


def log_belief_attribution_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_BELIEF_ATTRIBUTION_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# 無意識コンテキスト → chunk 主観補完 (U7)
# ──────────────────────────────────────────────────────────────────


ENV_UNCONSCIOUS_CONTEXT_ENABLED = "UNCONSCIOUS_CONTEXT_ENABLED"


def resolve_unconscious_context_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """chunk 主観補完 LLM に「無意識コンテキスト」(信念 top-K + L5 自己像/世界観) を
    渡すか。

    ``UNCONSCIOUS_CONTEXT_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - ``EpisodicChunkSubjectiveFieldsService`` の system prompt / user message は
      導入前と byte 一致 (無意識コンテキスト節が一切出ない)
    - belief top-K を取得する ``SemanticPassiveRecallService`` 追加インスタンスは
      構築されない (= 想起挙動・§learned section など既存の semantic 経路には
      一切影響しない)

    ON にすると、``prediction_error`` / ``salience`` の判定材料として cue 一致の
    active belief top-5 (確信度付き) + (RollingSummary 使用時のみ) L5
    self_image / world_view が system prompt の指示と共に user message に載る。
    これにより「誰にとっても同じ驚き」の判定から「このキャラにとっての驚き」の
    判定に変わる (確証バイアスは仕様。事実フィールドの改変禁止ガードは
    ``_assert_rule_fields_unchanged`` が既に担保している)。

    詳細は docs/memory_system/prediction_error_unified_memory_design.md §4、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U7 節。
    """
    return _parse_bool_env(ENV_UNCONSCIOUS_CONTEXT_ENABLED, env=env, default=False)


def log_unconscious_context_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_UNCONSCIOUS_CONTEXT_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )
