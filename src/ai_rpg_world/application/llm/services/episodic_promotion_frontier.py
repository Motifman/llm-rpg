"""セマンティック昇格が部分グラフを展開する際のシードとなるエピソード ID のバッファ。"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Sequence

from ai_rpg_world.domain.being.value_object.being_id import BeingId


class EpisodicPromotionFrontier:
    """同一 Being について、プロンプト〜ツール実行 1 単位でたまる episode_id を蓄え、
    on_after_tool_turn で drain して昇格が読む。
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._ids: dict[BeingId, set[str]] = defaultdict(set)

    def add(self, being_id: BeingId, episode_id: str) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        eid = episode_id.strip()
        if not eid:
            return
        with self._lock:
            self._ids[being_id].add(eid)

    def add_many(
        self,
        being_id: BeingId,
        episode_ids: Sequence[str] | tuple[str, ...],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        for e in episode_ids:
            self.add(being_id, e)

    def drain(self, being_id: BeingId) -> set[str]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            return self._ids.pop(being_id, set())
