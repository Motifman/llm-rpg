"""SpotSpawnTable 値オブジェクトのテスト"""

import pytest
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class TestSpotSpawnTable:
    """SpotSpawnTable のテスト"""

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(1)

    @pytest.fixture
    def slot_a(self, spot_id: SpotId) -> SpawnSlot:
        return SpawnSlot(
            spot_id=spot_id,
            coordinate=Coordinate(1, 1, 0),
            template_id=MonsterTemplateId.create(1),
        )

    @pytest.fixture
    def slot_b(self, spot_id: SpotId) -> SpawnSlot:
        return SpawnSlot(
            spot_id=spot_id,
            coordinate=Coordinate(2, 2, 0),
            template_id=MonsterTemplateId.create(2),
        )

    def test_create_success_empty(self, spot_id: SpotId):
        """空のスロットリストで作成できること"""
        table = SpotSpawnTable(spot_id=spot_id, slots=[])
        assert table.spot_id == spot_id
        assert table.slots == []

    def test_create_success_with_slots(
        self, spot_id: SpotId, slot_a: SpawnSlot, slot_b: SpawnSlot
    ):
        """スロットリストで作成できること"""
        table = SpotSpawnTable(spot_id=spot_id, slots=[slot_a, slot_b])
        assert table.spot_id == spot_id
        assert len(table.slots) == 2
        assert table.slots[0] == slot_a
        assert table.slots[1] == slot_b

    def test_create_fail_slots_not_list(self, spot_id: SpotId):
        """slots がリストでないときはエラー"""
        with pytest.raises(TypeError, match="slots must be a list"):
            SpotSpawnTable(spot_id=spot_id, slots=None)

    def test_create_fail_slot_wrong_type(self, spot_id: SpotId):
        """slots の要素が SpawnSlot でないときはエラー"""
        with pytest.raises(TypeError, match="must be SpawnSlot"):
            SpotSpawnTable(spot_id=spot_id, slots=[Coordinate(1, 1, 0)])

    def test_create_fail_slot_spot_id_mismatch(self, spot_id: SpotId):
        """スロットの spot_id がテーブルの spot_id と一致しないときはエラー"""
        other_spot = SpotId(2)
        slot = SpawnSlot(
            spot_id=other_spot,
            coordinate=Coordinate(1, 1, 0),
            template_id=MonsterTemplateId.create(1),
        )
        with pytest.raises(ValueError, match="spot_id must match"):
            SpotSpawnTable(spot_id=spot_id, slots=[slot])

    def test_frozen(self, spot_id: SpotId, slot_a: SpawnSlot):
        """SpotSpawnTable は不変であること"""
        table = SpotSpawnTable(spot_id=spot_id, slots=[slot_a])
        with pytest.raises(AttributeError):
            table.slots = []
