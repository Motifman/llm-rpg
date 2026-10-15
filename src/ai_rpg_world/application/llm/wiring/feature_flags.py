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


