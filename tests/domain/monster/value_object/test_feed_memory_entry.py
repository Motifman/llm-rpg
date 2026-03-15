"""
FeedMemoryEntry のテスト

値オブジェクトの基本振る舞い（生成・等価性・不変性）の検証。
"""

import pytest

from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestFeedMemoryEntryCreation:
    """FeedMemoryEntry の生成"""

    def test_creates_with_object_id_and_coordinate(self):
        """object_id と coordinate で作成できる"""
        oid = WorldObjectId(1001)
        coord = Coordinate(1, 2, 0)
        entry = FeedMemoryEntry(object_id=oid, coordinate=coord)
        assert entry.object_id == oid
        assert entry.coordinate == coord

    def test_creates_with_positional_args(self):
        """位置引数でも作成できる"""
        entry = FeedMemoryEntry(WorldObjectId(2001), Coordinate(3, 4, 0))
        assert entry.object_id == WorldObjectId(2001)
        assert entry.coordinate == Coordinate(3, 4, 0)


class TestFeedMemoryEntryEquality:
    """等価性のテスト"""

    def test_equal_when_same_values(self):
        """同じ object_id と coordinate のとき等しい"""
        e1 = FeedMemoryEntry(WorldObjectId(100), Coordinate(1, 2, 0))
        e2 = FeedMemoryEntry(WorldObjectId(100), Coordinate(1, 2, 0))
        assert e1 == e2
        assert hash(e1) == hash(e2)

    def test_not_equal_when_different_object_id(self):
        """object_id が異なると等しくない"""
        e1 = FeedMemoryEntry(WorldObjectId(100), Coordinate(1, 2, 0))
        e2 = FeedMemoryEntry(WorldObjectId(101), Coordinate(1, 2, 0))
        assert e1 != e2

    def test_not_equal_when_different_coordinate(self):
        """coordinate が異なると等しくない"""
        e1 = FeedMemoryEntry(WorldObjectId(100), Coordinate(1, 2, 0))
        e2 = FeedMemoryEntry(WorldObjectId(100), Coordinate(2, 3, 0))
        assert e1 != e2


class TestFeedMemoryEntryImmutability:
    """不変性のテスト"""

    def test_frozen_prevents_attribute_assignment(self):
        """frozen=True により属性の再代入ができない"""
        entry = FeedMemoryEntry(WorldObjectId(100), Coordinate(1, 2, 0))
        with pytest.raises(AttributeError):
            entry.object_id = WorldObjectId(999)
        with pytest.raises(AttributeError):
            entry.coordinate = Coordinate(0, 0, 0)
