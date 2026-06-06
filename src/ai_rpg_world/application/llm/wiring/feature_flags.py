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


def _parse_bool_env(
    var_name: str,
    env: Optional[Mapping[str, str]] = None,
    *,
    default: bool = False,
) -> bool:
    """env var を bool として解釈する。値が未設定なら ``default``。

    truthy: ``"1" / "true" / "yes" / "on"`` (case-insensitive)
    それ以外 (``"0" / "false" / "" / 任意の文字列``) は False。
    """
    source = env if env is not None else os.environ
    raw = (source.get(var_name) or "").strip().lower()
    if not raw:
        return default
    return raw in _TRUTHY


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
    - 負数 / 非数値 → warning ログ + default
    - 値が `>0` なら prompt に §learned section が出る (Phase 1c)
    """
    source = env if env is not None else os.environ
    raw = (source.get(ENV_SEMANTIC_PASSIVE_TOP_K) or "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_PASSIVE_TOP_K
    try:
        v = int(raw)
    except ValueError:
        _logger.warning(
            "Unknown %s=%r (non-integer); falling back to %s",
            ENV_SEMANTIC_PASSIVE_TOP_K,
            raw,
            DEFAULT_SEMANTIC_PASSIVE_TOP_K,
        )
        return DEFAULT_SEMANTIC_PASSIVE_TOP_K
    if v < 0:
        _logger.warning(
            "%s=%d is negative; falling back to %d",
            ENV_SEMANTIC_PASSIVE_TOP_K,
            v,
            DEFAULT_SEMANTIC_PASSIVE_TOP_K,
        )
        return DEFAULT_SEMANTIC_PASSIVE_TOP_K
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
