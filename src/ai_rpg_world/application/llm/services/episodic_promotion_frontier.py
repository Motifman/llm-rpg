"""セマンティック昇格が部分グラフを展開する際のシードとなるエピソード ID のバッファ。"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Sequence


class EpisodicPromotionFrontier:
    """
    同一プレイヤーについて、プロンプト構築〜ツール実行 1 運用単位でたまる episode_id を蓄え、
    on_after_tool_turn 先頭で drain して昇格処理が読み取る。
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._ids: dict[int, set[str]] = defaultdict(set)

    def add(self, player_id: int, episode_id: str) -> None:
        eid = episode_id.strip()
        if not eid:
            return
        with self._lock:
            self._ids[player_id].add(eid)

    def add_many(self, player_id: int, episode_ids: Sequence[str] | tuple[str, ...]) -> None:
        for e in episode_ids:
            self.add(player_id, e)

    def drain(self, player_id: int) -> set[str]:
        with self._lock:
            return self._ids.pop(player_id, set())
