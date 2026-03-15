"""
FeedMemory のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
)
from ai_rpg_world.domain.monster.value_object.feed_memory import FeedMemory, MAX_FEED_MEMORIES
from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestFeedMemoryEmpty:
    """empty() のテスト"""

    def test_empty_has_no_entries(self):
        """空の記憶はエントリなし"""
        mem = FeedMemory.empty()
        assert mem.entries == ()
        assert len(mem.entries) == 0


class TestFeedMemoryRemember:
    """remember() のテスト"""

    def test_remember_adds_first_entry(self):
        """1 件目の記憶を追加"""
        mem = FeedMemory.empty().remember(
            object_id=WorldObjectId(1001),
            coordinate=Coordinate(1, 2, 0),
        )
        assert len(mem.entries) == 1
        assert mem.entries[0].object_id == WorldObjectId(1001)
        assert mem.entries[0].coordinate == Coordinate(1, 2, 0)

    def test_remember_returns_new_instance(self):
        """remember は新しいインスタンスを返す"""
        empty = FeedMemory.empty()
        updated = empty.remember(
            object_id=WorldObjectId(1001),
            coordinate=Coordinate(1, 2, 0),
        )
        assert updated is not empty
        assert len(empty.entries) == 0
        assert len(updated.entries) == 1

    def test_remember_same_object_id_updates_and_moves_to_end(self):
        """同じ object_id の場合は更新し末尾に移動"""
        mem = FeedMemory.empty()
        mem = mem.remember(WorldObjectId(1001), Coordinate(1, 2, 0))
        mem = mem.remember(WorldObjectId(2001), Coordinate(3, 4, 0))
        mem = mem.remember(WorldObjectId(1001), Coordinate(5, 6, 0))
        # 1001 は末尾に移動し、座標が更新される
        assert len(mem.entries) == 2
        assert mem.entries[0].object_id == WorldObjectId(2001)
        assert mem.entries[0].coordinate == Coordinate(3, 4, 0)
        assert mem.entries[1].object_id == WorldObjectId(1001)
        assert mem.entries[1].coordinate == Coordinate(5, 6, 0)

    def test_remember_evicts_oldest_when_exceeding_max(self):
        """MAX_FEED_MEMORIES を超えた場合、古いものから追い出す"""
        mem = FeedMemory.empty()
        for i in range(MAX_FEED_MEMORIES + 2):
            mem = mem.remember(
                object_id=WorldObjectId(1000 + i),
                coordinate=Coordinate(i, i, 0),
            )
        assert len(mem.entries) == MAX_FEED_MEMORIES
        # 最も古い 2 件は追い出される
        assert mem.entries[0].object_id == WorldObjectId(1002)
        assert mem.entries[1].object_id == WorldObjectId(1003)
        assert mem.entries[2].object_id == WorldObjectId(1004)


class TestFeedMemoryLruBoundary:
    """LRU 境界のテスト"""

    def test_exactly_max_entries_kept(self):
        """ちょうど MAX 件のとき全て保持"""
        mem = FeedMemory.empty()
        for i in range(MAX_FEED_MEMORIES):
            mem = mem.remember(
                object_id=WorldObjectId(2000 + i),
                coordinate=Coordinate(i, i, 0),
            )
        assert len(mem.entries) == MAX_FEED_MEMORIES
        for i in range(MAX_FEED_MEMORIES):
            assert mem.entries[i].object_id == WorldObjectId(2000 + i)

    def test_update_existing_does_not_increase_count(self):
        """既存の object_id を更新しても件数は増えない"""
        mem = FeedMemory.empty()
        mem = mem.remember(WorldObjectId(3001), Coordinate(0, 0, 0))
        mem = mem.remember(WorldObjectId(3001), Coordinate(1, 1, 0))
        mem = mem.remember(WorldObjectId(3001), Coordinate(2, 2, 0))
        assert len(mem.entries) == 1
        assert mem.entries[0].coordinate == Coordinate(2, 2, 0)


class TestFeedMemoryCleared:
    """cleared() のテスト"""

    def test_cleared_returns_empty(self):
        """cleared で空の状態に"""
        mem = FeedMemory.empty().remember(
            object_id=WorldObjectId(4001),
            coordinate=Coordinate(1, 1, 0),
        )
        cleared = mem.cleared()
        assert cleared.entries == ()
        assert len(cleared.entries) == 0
        assert cleared is not mem
        assert len(mem.entries) == 1

    def test_cleared_from_empty_returns_empty(self):
        """空の状態で cleared しても空のまま"""
        mem = FeedMemory.empty()
        cleared = mem.cleared()
        assert cleared.entries == ()
        assert cleared is not mem


class TestFeedMemoryImmutability:
    """不変性のテスト"""

    def test_entries_returns_tuple_copy(self):
        """entries は変更不可のタプル"""
        mem = FeedMemory.empty().remember(
            object_id=WorldObjectId(5001),
            coordinate=Coordinate(0, 0, 0),
        )
        entries = mem.entries
        assert isinstance(entries, tuple)
        # タプルは変更不可のため、呼び出し側で改変されない


class TestFeedMemoryValidation:
    """バリデーションのテスト"""

    def test_rejects_more_than_max_entries_direct_construction(self):
        """直接構築で MAX 超えると例外"""
        entries = tuple(
            FeedMemoryEntry(WorldObjectId(6000 + i), Coordinate(i, i, 0))
            for i in range(MAX_FEED_MEMORIES + 1)
        )
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            FeedMemory(_entries=entries)
        assert str(MAX_FEED_MEMORIES) in str(exc_info.value)

    def test_accepts_max_entries_direct_construction(self):
        """直接構築でちょうど MAX 件は OK"""
        entries = tuple(
            FeedMemoryEntry(WorldObjectId(7000 + i), Coordinate(i, i, 0))
            for i in range(MAX_FEED_MEMORIES)
        )
        mem = FeedMemory(_entries=entries)
        assert len(mem.entries) == MAX_FEED_MEMORIES


class TestFeedMemoryFromEntries:
    """entries からの構築テスト"""

    def test_from_existing_entries_preserves_order(self):
        """既存エントリで構築すると順序を保持"""
        e1 = FeedMemoryEntry(WorldObjectId(8001), Coordinate(1, 1, 0))
        e2 = FeedMemoryEntry(WorldObjectId(8002), Coordinate(2, 2, 0))
        mem = FeedMemory(_entries=(e1, e2))
        assert mem.entries[0] == e1
        assert mem.entries[1] == e2
