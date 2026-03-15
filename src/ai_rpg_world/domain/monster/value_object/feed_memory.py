"""
FeedMemory: 餌場の記憶を表す不変の値オブジェクト。

MonsterAggregate が持つ餌場記憶（object_id + coordinate）を LRU で保持する。
最大 MAX_FEED_MEMORIES 件を保持し、超えた分は古いものから追い出す。
既に同じ object_id がある場合は更新（末尾に移動）する。
"""

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


# 餌場記憶の最大件数（LRU で古いものを追い出す）
MAX_FEED_MEMORIES = 3


@dataclass(frozen=True)
class FeedMemory:
    """
    餌場の記憶を表す値オブジェクト。
    古い順に並ぶ（インデックス 0 が最も古い）。
    適用時は距離が近い順に使う（呼び出し側の責務）。
    """

    _entries: Tuple[FeedMemoryEntry, ...] = ()

    def __post_init__(self) -> None:
        if len(self._entries) > MAX_FEED_MEMORIES:
            raise ValueError(
                f"FeedMemory cannot hold more than {MAX_FEED_MEMORIES} entries, got {len(self._entries)}"
            )

    @classmethod
    def empty(cls) -> "FeedMemory":
        """空の記憶を作成する。"""
        return cls(_entries=())

    @property
    def entries(self) -> Tuple[FeedMemoryEntry, ...]:
        """餌場の記憶リスト（古い順、最大 MAX_FEED_MEMORIES 件）。変更不可のコピー。"""
        return self._entries

    def remember(
        self,
        object_id: WorldObjectId,
        coordinate: Coordinate,
    ) -> "FeedMemory":
        """
        餌オブジェクトの位置を記憶する。
        最大 MAX_FEED_MEMORIES 件を LRU で保持し、超えた分は古いものから追い出す。
        既に同じ object_id がある場合は更新（末尾に移動）。
        """
        entry = FeedMemoryEntry(object_id=object_id, coordinate=coordinate)
        # 同じ object_id を除いたリストにし、末尾に追加
        new_list = [e for e in self._entries if e.object_id != object_id]
        new_list.append(entry)
        if len(new_list) > MAX_FEED_MEMORIES:
            new_list = new_list[-MAX_FEED_MEMORIES:]
        return FeedMemory(_entries=tuple(new_list))

    def cleared(self) -> "FeedMemory":
        """記憶をすべてクリアした新しい状態を返す。"""
        return FeedMemory.empty()
