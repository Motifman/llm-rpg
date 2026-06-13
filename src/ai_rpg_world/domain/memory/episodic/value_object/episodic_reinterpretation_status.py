"""EpisodicReinterpretationStatus — 再解釈ジャーナル entry の有効状態 Enum。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py`` から domain に昇格。
"""

from __future__ import annotations

from enum import Enum


class EpisodicReinterpretationStatus(str, Enum):
    """再解釈ジャーナル entry の有効状態。"""

    ACTIVE = "active"
    SUPERSEDED = "superseded"


__all__ = ["EpisodicReinterpretationStatus"]
