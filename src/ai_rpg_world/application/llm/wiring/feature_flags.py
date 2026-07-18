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


# ──────────────────────────────────────────────────────────────────
# 想起の信用割り当て・誤差駆動再解釈 (U9a)
# ──────────────────────────────────────────────────────────────────


ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED = "ERROR_DRIVEN_REINTERPRETATION_ENABLED"


def resolve_error_driven_reinterpretation_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """「この記憶を思い出したのに予測が外れた」を再解釈に還流させるか
    (予測誤差統一設計 部品5 の外れ側 = U9a。的中側の ranking boost は別 PR)。

    ``ERROR_DRIVEN_REINTERPRETATION_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - chunk 主観補完の完了点 (同期 chunk_coordinator / 非同期 scheduler の
      いずれも) で recall buffer への stamp が一切行われない
      (``EpisodicRecallObservation.prediction_outcome_error`` は常に None)
    - ``EpisodicReinterpretationCoordinator`` の system prompt / recall_context
      payload は導入前と byte 一致 (誤差駆動節が一切出ない)

    ON にするには実質的に ``PREDICTION_CONTEXT_ID_ENABLED`` (U1) と
    episodic reinterpretation (段1) の両方が ON である必要がある。どちらか
    が欠けていても本 flag だけ ON にして構わない: prediction_context_id が
    action に乗らない/recall buffer 自体が組まれないため、stamp 対象の
    recall observation が存在せず安全に縮退する (実害なし)。

    詳細は docs/memory_system/prediction_error_unified_memory_design.md
    「部品 5: 想起の信用割り当て」節、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U9 節。
    """
    return _parse_bool_env(
        ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED, env=env, default=False
    )


def log_error_driven_reinterpretation_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_ERROR_DRIVEN_REINTERPRETATION_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# 想起の信用割り当て・ranking boost (U9b)
# ──────────────────────────────────────────────────────────────────


ENV_RECALL_HIT_BOOST_ENABLED = "RECALL_HIT_BOOST_ENABLED"


def resolve_recall_hit_boost_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """「この記憶を思い出したから予測が当たった」を recall ranking の boost に
    還流するか (予測誤差統一設計 部品5 の的中側 = U9b。外れ側は U9a)。

    ``RECALL_HIT_BOOST_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - chunk 主観補完の完了点 (同期 chunk_coordinator / 非同期 scheduler の
      いずれも) で的中側 sidecar (``IEpisodicRecallSuccessStore``) への
      record_hit が一切行われない
    - ``EpisodicPassiveRecallRetrievalService`` の ranking (``multi_cue_score``)
      への boost 加算は常に 0 (= 導入前と byte 一致)

    ON にするには実質的に ``PREDICTION_CONTEXT_ID_ENABLED`` (U1) と
    episodic reinterpretation (段1、recall_buffer 構築のため) の両方が ON
    である必要がある。どちらかが欠けていても本 flag だけ ON にして構わない:
    prediction_context_id が action に乗らない / recall buffer 自体が組まれ
    ないため、record_hit 対象の recall observation が存在せず安全に縮退する
    (実害なし)。

    詳細は docs/memory_system/prediction_error_unified_memory_design.md
    「部品 5: 想起の信用割り当て」節、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U9 節。
    """
    return _parse_bool_env(ENV_RECALL_HIT_BOOST_ENABLED, env=env, default=False)


def log_recall_hit_boost_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_RECALL_HIT_BOOST_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# 誤差ゲート付き符号化: 境界 (2a) + 解像度 (2b) (U8)
# ──────────────────────────────────────────────────────────────────


ENV_ERROR_GATED_ENCODING_ENABLED = "ERROR_GATED_ENCODING_ENABLED"


def resolve_error_gated_encoding_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """密度を時間やイベント数ではなく予測誤差で決める 2 つの局所変更を動かすか
    (予測誤差統一設計 部品2、U8)。

    ``ERROR_GATED_ENCODING_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - ``decide_chunk_boundary`` に U8 で足した条項 (成功を予測していたのに
      失敗 / error_code 付き失敗があれば境界候補にする) は一切評価されず、
      境界挙動は U8 導入前と完全一致する
    - chunk 主観補完 LLM の system prompt の recall_text 長さ指示は U6 導入時
      の一律指示 (250〜450 字) のまま byte 一致 (salience_enabled の値に
      関わらず)

    ON にすると:
    - bucket 内に構造的な予測ミスがあれば (MIN_ACTIONS_FOR_CLOSE 到達後・
      scene 境界系の判定の後、観測件数閾値の前というルール順で) chunk 境界の
      候補になる (``ChunkBoundaryReason.PREDICTION_ERROR_SALIENT``)
    - ``SALIENCE_STRUCTURED_FAILURE_ENABLED`` (U6) も同時に ON のとき、
      recall_text の長さ指示が salience 連動になる (high: 250〜450字 /
      low: 80〜150字)。U6 flag が OFF のままだと salience 自体が存在しない
      ため、本 flag が ON でも長さ指示は変わらない (連動先が無いため安全に
      縮退)

    詳細は docs/memory_system/prediction_error_unified_memory_design.md
    「部品 2: 誤差ゲート付き符号化」節、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U8 節。
    """
    return _parse_bool_env(ENV_ERROR_GATED_ENCODING_ENABLED, env=env, default=False)


def log_error_gated_encoding_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_ERROR_GATED_ENCODING_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# pending prediction (約束・遅延予測) (U10a)
# ──────────────────────────────────────────────────────────────────


ENV_PENDING_PREDICTION_ENABLED = "PENDING_PREDICTION_ENABLED"


def resolve_pending_prediction_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """chunk 主観補完に pending_prediction (約束・見込み) の抽出・保持・

    再浮上を一括で足すか (予測誤差統一設計 部品6、U10a)。

    ``PENDING_PREDICTION_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - chunk 主観補完 LLM の system prompt に ``pending_prediction`` キーは
      一切出ない (byte 不変)
    - pending prediction store は構築されない (snapshot は空 in-memory
      fallback)
    - prompt の【保留中の予測】section は出ない (byte 不変)

    ON にすると:
    - chunk 主観補完が「将来の特定の時・場所・相手についての約束や見込み」を
      1 chunk につき最大 1 件抽出し、``PendingPrediction`` として per-Being
      store (容量上限 8 件) に積む
    - prompt build 時、解決 cue (spot / player) が現在の状況と一致し、かつ
      tick 範囲が到来しているものを最大 2 件、【保留中の予測】section に出す
    - 清算 (履行/破棄判定・期限失効) は本 flag のスコープ外 (U10b)

    詳細は docs/memory_system/prediction_error_unified_memory_design.md
    「部品 6: 保留中の予測」節、
    docs/memory_system/prediction_error_unified_implementation_plan.md の
    U10 節。
    """
    return _parse_bool_env(ENV_PENDING_PREDICTION_ENABLED, env=env, default=False)


def log_pending_prediction_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_PENDING_PREDICTION_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- P9 (伝聞 / HEARSAY) -----------------------------------------------------

ENV_HEARSAY_ENABLED = "HEARSAY_ENABLED"


def resolve_hearsay_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """chunk 主観補完に heard_claims (他者が語った世界・人についての主張) の

    抽出を足し、HEARSAY evidence に転記するか (belief_hearsay_design.md、P9)。

    ``HEARSAY_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - chunk 主観補完 LLM の system prompt に heard_claims キーは一切出ない
      (byte 不変)。episode.heard_claims は常に空 → 転記も起きない

    ON にすると:
    - chunk 主観補完が「他者が世界や人について語った主張」を抽出し、話者を
      ``source_speaker`` に、主張の対象を cue に分離した HEARSAY evidence を積む
      (自分の体験より弱い証拠。固着パスが discard に委ねる)
    """
    return _parse_bool_env(ENV_HEARSAY_ENABLED, env=env, default=False)


def log_hearsay_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_HEARSAY_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- P5 (goal store) ---------------------------------------------------------

ENV_GOAL_STORE_ENABLED = "GOAL_STORE_ENABLED"


def resolve_goal_store_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """【現在の目的】の描画を静的シナリオ文字列から goal store 駆動へ

    切り替えるか (目的層 goal_layer_design_active_inference.md G1、P5)。

    ``GOAL_STORE_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき: 従来どおり ``objective_text_provider`` は
    ``scenario.metadata.llm_objective_text`` の固定文字列を返す (goal store は
    構築されず snapshot は空 in-memory fallback)。

    ON にすると: run 開始時にシナリオ目的文を ``locked=True, origin="scenario"``
    で goal store に seed し、``objective_text_provider`` は store の active 目的を
    描画する。**locked 初期値なら描画結果は従来の静的テキストと同一** なので、
    既存シナリオの挙動は不変 (質感テストで固定)。目的の見直し・清算 (G2/G4) は
    本 flag のスコープ外。
    """
    return _parse_bool_env(ENV_GOAL_STORE_ENABLED, env=env, default=False)


def log_goal_store_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_GOAL_STORE_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- P6 (goal revision / 目的の見直し) ---------------------------------------

ENV_GOAL_REVISION_ENABLED = "GOAL_REVISION_ENABLED"


def resolve_goal_revision_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """目的の見直しターン (goal_layer_design_active_inference.md G2、P6) を

    有効化するか。``GOAL_REVISION_ENABLED=1`` で ON、未設定 / その他は OFF。

    goal store (GOAL_STORE_ENABLED) が前提。OFF (既定) のとき、見直し section も
    goal_update schema も一切出ない (プロンプト byte 不変)。ON のときだけ、
    トリガターン (active 目的が unlocked / 無し、かつ発火条件成立) に限り
    【目的の見直し】section と optional な ``goal_update`` フィールドを露出し、
    非 null なら goal store を supersede 更新する。**locked 目的 (シナリオ初期
    目的) ではトリガを発火させない** ため、勝利条件付きシナリオの run は
    プロンプト不変 (案A)。
    """
    return _parse_bool_env(ENV_GOAL_REVISION_ENABLED, env=env, default=False)


def log_goal_revision_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_GOAL_REVISION_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- P4 (goal reflect / 目的への前進評価) ------------------------------------

ENV_GOAL_REFLECT_ENABLED = "GOAL_REFLECT_ENABLED"


def resolve_goal_reflect_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """固着パスに reflect (目的への前進評価) を足すか (goal_layer G3 前身、P4)。

    ``GOAL_REFLECT_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき固着 system prompt に reflect 節は一切出ない (byte 不変)。
    ON のとき、固着 LLM が evidence 群と現在の目的を照らして停滞を判断でき、
    停滞宣言は内省観測として本人に注入される (belief journal には書かない)。
    監査対象の目的文と観測 sink は呼び出し側 (world_runtime) が渡す。
    """
    return _parse_bool_env(ENV_GOAL_REFLECT_ENABLED, env=env, default=False)


def log_goal_reflect_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_GOAL_REFLECT_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- P-U1 (目的停滞の evidence 化) ------------------------------------------

ENV_GOAL_STAGNATION_EVIDENCE_ENABLED = "GOAL_STAGNATION_EVIDENCE_ENABLED"


def resolve_goal_stagnation_evidence_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """reflect の stalled/misaligned verdict を ``goal:`` 軸の高 salience
    PREDICTION_ERROR evidence に変換するか (goal_utility_gradient_design.md P-U1)。

    ``GOAL_STAGNATION_EVIDENCE_ENABLED=1`` で ON、未設定 / その他は OFF。

    前提として ``GOAL_REFLECT_ENABLED`` が ON である必要がある (reflect が
    発火しなければ evidence 化の対象自体が生まれない。
    ``BeliefConsolidationCoordinator`` がこの組み合わせ不整合を起動時
    fail-fast で弾く)。

    OFF (既定) のとき、reflect は従来どおり内省観測を注入するだけで
    evidence は一切積まない (belief journal には書かない、という導入前の
    不変条件が維持される)。ON にすると、停滞 (stalled) / 乖離 (misaligned)
    と判定された回だけ (達成 achieved は対象外)、その期間の evidence の
    episode_ids を束ねた高 salience evidence を 1 件 buffer に積む。目的
    そのものの改訂は行わない (「停滞 ≠ 即改訂」の不変条件は変えない)。
    """
    return _parse_bool_env(
        ENV_GOAL_STAGNATION_EVIDENCE_ENABLED, env=env, default=False
    )


def log_goal_stagnation_evidence_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_GOAL_STAGNATION_EVIDENCE_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- P-U2 (停滞感 store) -----------------------------------------------------

ENV_STAGNATION_PRESSURE_ENABLED = "STAGNATION_PRESSURE_ENABLED"


def resolve_stagnation_pressure_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """reflect の verdict (stalled/misaligned/achieved) を「停滞感」カウンタに
    畳み込むか (goal_utility_gradient_design.md P-U2)。

    ``STAGNATION_PRESSURE_ENABLED=1`` で ON、未設定 / その他は OFF。

    前提として ``GOAL_REFLECT_ENABLED`` が ON である必要がある (reflect が
    発火しなければカウンタを動かす verdict 自体が生まれない。
    ``BeliefConsolidationCoordinator`` がこの組み合わせ不整合を起動時
    fail-fast で弾く)。

    OFF (既定) のとき、reflect は従来どおり内省観測を注入する / P-U1 の
    evidence 化を行うだけで、停滞感カウンタには一切触れない。ON にすると、
    stalled / misaligned の回にカウンタを +1、achieved の回に 0 リセットする。
    P-U1 (evidence 化) の乱発防止 cap とは独立に動く点に注意
    (cap は表示側の間引きであって、停滞の内部判定ではないため)。
    """
    return _parse_bool_env(ENV_STAGNATION_PRESSURE_ENABLED, env=env, default=False)


def log_stagnation_pressure_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_STAGNATION_PRESSURE_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ---- 案A (band-gated thinking) ----------------------------------------------

ENV_STAGNATION_REASONING_ENABLED = "STAGNATION_REASONING_ENABLED"


def resolve_stagnation_reasoning_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """停滞感 band が strong の局面で、停滞 reflect 注入直後の 1 行動に限り
    reasoning (熟考) を有効化するか (goal_utility_gradient_design.md 案A)。

    ``STAGNATION_REASONING_ENABLED=1`` で ON、未設定 / その他は OFF。

    前提として ``STAGNATION_PRESSURE_ENABLED`` (band の供給元) と
    ``GOAL_REFLECT_ENABLED`` (reflect 注入 = ラッチ武装のトリガ) の両方が ON で
    ある必要がある。この組み合わせ不整合は wiring 構築時に fail-fast で弾く。

    OFF (既定) のとき、行動経路は従来どおり ``reasoning_effort=None`` で invoke し
    (プロンプト byte 不変・プレフィックスキャッシュ不変)、ラッチも構築しない。
    ON にすると、詰まった局面の 1 行動だけ reasoning を焚き、tool 選択の前に
    熟考させる。inner_thought (tool_call 後の後付け) では埋められない「熟考 →
    行動選択」の解離を埋める狙い。
    """
    return _parse_bool_env(ENV_STAGNATION_REASONING_ENABLED, env=env, default=False)


def log_stagnation_reasoning_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_STAGNATION_REASONING_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: STATE_COLLAPSE evidence (PR-D)
# ──────────────────────────────────────────────────────────────────


ENV_STATE_COLLAPSE_EVIDENCE_ENABLED = "STATE_COLLAPSE_EVIDENCE_ENABLED"


def resolve_state_collapse_evidence_enabled(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """状態破綻 (戦闘不能への遷移 / 空腹 max 到達) の高 salience evidence
    転記を有効化するか。``STATE_COLLAPSE_EVIDENCE_ENABLED=1`` で ON、
    未設定 / その他は OFF。

    OFF (既定) のとき、``StateCollapseEvidenceTranscriber`` は配線されず
    (``world_runtime`` 側で None のまま)、戦闘不能/空腹 max 到達は従来通り
    prose 観測 1 行のみで belief 形成の素材にはならない (導入前と挙動不変)。

    ON にすると、is_down への遷移と hunger max 到達を
    ``BeliefEvidence(source_kind=STATE_COLLAPSE, salience=high)`` として
    evidence buffer に積む。判定基準はエンジン側の状態遷移そのもの
    (is_down フラグ / hunger.value >= hunger.max_value) であり、新規の
    LLM 判定は追加しない。「これが良い/悪い」という解釈は付けず事実の
    記述のみを text に残す (STRUCTURED_FAILURE と同じ転記のみ方針)。

    詳細は ``StateCollapseEvidenceTranscriber`` の docstring (PR-D) を参照。
    """
    return _parse_bool_env(
        ENV_STATE_COLLAPSE_EVIDENCE_ENABLED, env=env, default=False
    )


def log_state_collapse_evidence_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_STATE_COLLAPSE_EVIDENCE_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )
