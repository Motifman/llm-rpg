"""EpisodicCueSource — cue がどの経路で付いたかを示す Enum。

DDD 再編 (Issue #470 Phase 1 PR2): 元 ``application/llm/contracts/episodic_memory.py``
から domain に昇格。
"""

from __future__ import annotations

from enum import Enum


class EpisodicCueSource(str, Enum):
    """cue がゲーム構造化入力から付いたことを示す（LLM 自由生成ではない）。"""

    RUNTIME_CONTEXT = "runtime_context"
    TOOL = "tool"
    OBSERVATION_STRUCTURED = "observation_structured"
    # Issue #283 後続: 観測 prose を WorldNounMatcher で走査し、含まれる固有名詞
    # から自動付与された cue (例: SNS で「書架A」と言及されると place_spot:3 が立つ)。
    # 構造化されていない自由文経由なので別 source として区別する。
    OBSERVATION_FREETEXT = "observation_freetext"


__all__ = ["EpisodicCueSource"]
