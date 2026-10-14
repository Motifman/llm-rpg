"""LLM 配線まわりの env-driven feature flag。

実験スクリプトから A/B 検証する用途で、scenario 内容と直交する knob を
ここに集約する。既存の他の env var (``EPISODIC_PROMOTION_FORCE_FULL_SCAN``,
``SUBJECTIVE_EPISODE_DB_PATH``, ``LLM_MODEL`` 等) と
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
from collections.abc import Mapping

_logger = logging.getLogger(__name__)


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _parse_bool_env(
    var_name: str,
    env: Mapping[str, str] | None = None,
    *,
    default: bool = False,
) -> bool:
    """設定値を bool として解釈する。値が未設定なら ``default``。

    - truthy: ``"1" / "true" / "yes" / "on"`` (case-insensitive) → True
    - falsy:  ``"0" / "false" / "no" / "off"`` (case-insensitive) → False
    - 上記以外の文字列 → ``ValueError`` (silent fallback 防止: 過去に
      ``MEMORY_KIND=rolling`` のような typo が黙って default に縮退して
      実験前提を壊した事例があった / PR #433 で発覚)

    Args:
        var_name: 設定名 (エラーメッセージに含める)
        env: 設定 mapping。None は許可しない
        default: 未設定時の戻り値

    Raises:
        ValueError: 値が truthy / falsy のいずれにも該当しないとき
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )
    source = env
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
    env: Mapping[str, str] | None = None,
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
    env: Mapping[str, str] | None = None,
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
    env: Mapping[str, str] | None = None,
) -> int:
    """``SEMANTIC_PASSIVE_TOP_K`` env var を非負整数に解釈する。

    - 未設定 / 空文字 → default (0)
    - 非整数 / 負数 → ``ValueError`` (silent fallback 防止 / PR #433 経緯)
    - 値が ``>0`` なら prompt に §learned section が出る (Phase 1c)

    Raises:
        ValueError: 非整数または負数のとき
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )
    source = env
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
    env: Mapping[str, str] | None = None,
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
    env: Mapping[str, str] | None = None,
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
ENV_SHORT_TERM_MEMORY_TURN_CAP = "SHORT_TERM_MEMORY_TURN_CAP"
ENV_SHORT_TERM_MEMORY_TURN_COMPACT_COUNT = "SHORT_TERM_MEMORY_TURN_COMPACT_COUNT"
SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW = "sliding_window"
SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY = "rolling_summary"
_VALID_SHORT_TERM_MEMORY_KINDS = frozenset({
    SHORT_TERM_MEMORY_KIND_SLIDING_WINDOW,
    SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
})


def resolve_short_term_memory_kind(
    env: Mapping[str, str] | None = None,
) -> str:
    """``SHORT_TERM_MEMORY_KIND`` env を解決する。

    - default は ``rolling_summary``。新しい記憶の書き起こし (#1626) は畳む
      ときに呼ばれ、``sliding_window`` には畳む瞬間が無い (#1631)
    - 未知文字列は ``ValueError`` (silent fallback 防止 / PR #433 経緯:
      短縮形 ``rolling`` を渡したのに silent fallback で sliding_window が
      使われ、実験 24h 分が無駄になりかけた)

    詳細は docs/memory_system/short_term_memory_design.md §6.1。

    Raises:
        ValueError: 未知の文字列 (短縮形 typo 等) のとき
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )
    source = env
    raw = (source.get(ENV_SHORT_TERM_MEMORY_KIND) or "").strip().lower()
    if not raw:
        return SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY
    if raw not in _VALID_SHORT_TERM_MEMORY_KINDS:
        raise ValueError(
            f"{ENV_SHORT_TERM_MEMORY_KIND}={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_SHORT_TERM_MEMORY_KINDS)}"
        )
    return raw


def log_short_term_memory_kind_state(kind: str) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info("%s resolved to %s", ENV_SHORT_TERM_MEMORY_KIND, kind)


def resolve_short_term_memory_turn_window(
    env: Mapping[str, str] | None = None,
) -> tuple[int, int]:
    """自分のターン単位の窓上限と、一度に畳むターン数を解決する。

    ``compact_count`` は ``cap`` より小さくなければならない。等しい値を
    許すと、畳んだ直後に直近出来事が空になり、自己の連続性が切れる。
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )

    def _positive_int(name: str, default: int) -> int:
        raw = (env.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer: {raw!r}") from exc
        if value <= 0:
            raise ValueError(f"{name} must be greater than 0: {value}")
        return value

    cap = _positive_int(ENV_SHORT_TERM_MEMORY_TURN_CAP, 20)
    compact_count = _positive_int(
        ENV_SHORT_TERM_MEMORY_TURN_COMPACT_COUNT, 10
    )
    if compact_count >= cap:
        raise ValueError(
            f"{ENV_SHORT_TERM_MEMORY_TURN_COMPACT_COUNT} must be smaller than "
            f"{ENV_SHORT_TERM_MEMORY_TURN_CAP}: {compact_count} >= {cap}"
        )
    return cap, compact_count


# ──────────────────────────────────────────────────────────────────
# Semantic memory: belief evidence buffer 転記 (U2, 証拠台帳統一設計)
# ──────────────────────────────────────────────────────────────────


ENV_BELIEF_EVIDENCE_ENABLED = "BELIEF_EVIDENCE_ENABLED"


def resolve_belief_evidence_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    """``BeliefEvidence`` の evidence buffer を作るか。

    ``BELIEF_EVIDENCE_ENABLED=1`` で ON、未設定 / その他は OFF。

    この flag 自身が足していた書き手 (chunk の外れ、約束の清算) は #1631 で消した。
    いまは buffer を作るだけで、積むのは固着パス (``BELIEF_CONSOLIDATION_ENABLED``)
    のクラスタ昇格だけになる。buffer そのものは信念の部品を消す段で扱う。

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
    env: Mapping[str, str] | None = None,
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
# Memo tool exposure
# ──────────────────────────────────────────────────────────────────


ENV_MEMO_TOOLS_ENABLED = "MEMO_TOOLS_ENABLED"


def resolve_memo_tools_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    """memo_add / memo_list / memo_done を LLM に露出するか。

    未設定なら ON。``MEMO_TOOLS_ENABLED=0`` で明示的に OFF。

    memo は既存 run で長く使われてきた手帳 tool なので、既定は互換性を優先
    して ON にする。OFF は memo 廃止 A/B 実験の腕として使い、memo section
    と memo 完了 hint も同時に止める。
    """
    return _parse_bool_env(ENV_MEMO_TOOLS_ENABLED, env=env, default=True)


def log_memo_tools_enabled_state(enabled: bool) -> None:
    """wiring 構築時に解決結果を 1 度ログる。"""
    _logger.info(
        "%s resolved to %s",
        ENV_MEMO_TOOLS_ENABLED,
        "ENABLED" if enabled else "DISABLED",
    )


# ──────────────────────────────────────────────────────────────────
# Semantic memory: attribution + CONFIRMATION (U4)
# ──────────────────────────────────────────────────────────────────


ENV_BELIEF_ATTRIBUTION_ENABLED = "BELIEF_ATTRIBUTION_ENABLED"


def resolve_belief_attribution_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    """「信じて行動した」の attribution (S3) + CONFIRMATION (的中の支持) を
    動かすか。

    ``BELIEF_ATTRIBUTION_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - PREDICTION_ERROR evidence に in-context belief が添付されない
    - CONFIRMATION evidence が生成されない
    - 固着パスの shortlist に in-context belief を強制搭載する経路が働かない
      (``BeliefEvidence.in_context_belief_ids`` が常に空のため)

    prompt build 時に in-context だった belief_id を行動に記録する仕組み
    (``PREDICTION_CONTEXT_ID_ENABLED``) は #1631 で消したので、ON にしても
    ``BeliefEvidence.in_context_belief_ids`` は常に空のまま縮退する。

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
# 想起の信用割り当て・ranking boost (U9b)
# ──────────────────────────────────────────────────────────────────


ENV_RECALL_HIT_BOOST_ENABLED = "RECALL_HIT_BOOST_ENABLED"


def resolve_recall_hit_boost_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    """「この記憶を思い出したから予測が当たった」を recall ranking の boost に
    還流するか (予測誤差統一設計 部品5 の的中側 = U9b。外れ側の U9a は #1631 で消した)。

    ``RECALL_HIT_BOOST_ENABLED=1`` で ON、未設定 / その他は OFF。

    OFF (既定) のとき:
    - chunk 主観補完の完了点 (同期 chunk_coordinator / 非同期 scheduler の
      いずれも) で的中側 sidecar (``IEpisodicRecallSuccessStore``) への
      record_hit が一切行われない
    - ``EpisodicPassiveRecallRetrievalService`` の ranking (``multi_cue_score``)
      への boost 加算は常に 0 (= 導入前と byte 一致)

    的中を数えていた書き手は #1631 で消したので、ON にしても record_hit は
    行われず、安全に縮退する。

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

