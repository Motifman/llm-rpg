"""L5 長期帯 (long summary) の Value Object。

DDD 再編 (Issue #470 Phase 1): 元 ``application/llm/contracts/short_term_memory.py``
から domain に昇格した純粋 Value Object。

L5 は **1 player につき 1 件のみ** 保持され、L4 evict 時に最古 L4 と
previous_l5 を統合して新世代が生成される。persona drift 防止のため
self_image の核は不変、装飾段だけが体験で更新される設計 (prompt 側で強制)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class L5LongSummary:
    """長期帯 (L5) 1 件分の自己像と世界観 (Phase 3)。

    L4 が ``keep_gen + 1`` 世代目に達したとき、最古 L4 + 現在の L5 を LLM で
    統合して新世代 L5 が生成される。L5 は **1 player につき 1 件のみ** 保持。

    schema 設計指針 (docs §4.2):
    - **narrative voice のみ**: 学び / 関係性 / 世界ルールは semantic 経路の責務
    - **時系列の細部は捨てる**: L5 は時を超えた「いまの自分」「いまの世界観」
    - **persona drift 防止**: 性格 (persona) は previous_l5 のものを保ち、
      事実認識のみ更新される。プロンプト側で強制
    """

    summary_id: str
    player_id: int
    generation_index: int  # 何回目の L5 か (drift 検出用)
    generated_at: datetime
    self_image: str
    world_view: str
    is_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.summary_id, str) or not self.summary_id.strip():
            raise ValueError("summary_id must be non-empty str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.generation_index, int) or self.generation_index < 0:
            raise ValueError("generation_index must be non-negative int")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be datetime")
        if not isinstance(self.self_image, str):
            raise TypeError("self_image must be str")
        if not isinstance(self.world_view, str):
            raise TypeError("world_view must be str")
        if not isinstance(self.is_fallback, bool):
            raise TypeError("is_fallback must be bool")


__all__ = ["L5LongSummary"]
