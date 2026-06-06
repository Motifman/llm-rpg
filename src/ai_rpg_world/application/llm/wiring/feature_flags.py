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
