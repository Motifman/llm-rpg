"""InMemorySpawnTableRepository のテスト"""

import pytest
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_spawn_table_repository import (
    InMemorySpawnTableRepository,
)


class TestInMemorySpawnTableRepository:
    """InMemorySpawnTableRepository のテスト"""

    def test_find_by_spot_id_returns_none_when_empty(self):
        """登録がないとき find_by_spot_id は None"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        repo = InMemorySpawnTableRepository(data_store=data_store)
        assert repo.find_by_spot_id(SpotId(1)) is None

    def test_add_table_and_find_by_spot_id(self):
        """add_table で登録したテーブルを find_by_spot_id で取得できる"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        repo = InMemorySpawnTableRepository(data_store=data_store)
        spot_id = SpotId(1)
        slot = SpawnSlot(
            spot_id=spot_id,
            coordinate=Coordinate(1, 1, 0),
            template_id=MonsterTemplateId.create(1),
        )
        table = SpotSpawnTable(spot_id=spot_id, slots=[slot])
        repo.add_table(table)
        result = repo.find_by_spot_id(spot_id)
        assert result is not None
        assert result.spot_id == spot_id
        assert len(result.slots) == 1
        assert result.slots[0].coordinate == Coordinate(1, 1, 0)

    def test_find_by_spot_id_different_spot_returns_none(self):
        """別の spot_id では None"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        repo = InMemorySpawnTableRepository(data_store=data_store)
        table = SpotSpawnTable(
            spot_id=SpotId(1),
            slots=[
                SpawnSlot(
                    spot_id=SpotId(1),
                    coordinate=Coordinate(0, 0, 0),
                    template_id=MonsterTemplateId.create(1),
                )
            ],
        )
        repo.add_table(table)
        assert repo.find_by_spot_id(SpotId(2)) is None
        assert repo.find_by_spot_id(SpotId(1)) is not None

    def test_spawn_tables_included_in_snapshot_and_restored(self):
        """take_snapshot に spawn_tables が含まれ、restore_snapshot で復元できる（シナリオ検証用）"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        repo = InMemorySpawnTableRepository(data_store=data_store)
        spot_id = SpotId(1)
        slot = SpawnSlot(
            spot_id=spot_id,
            coordinate=Coordinate(5, 5, 0),
            template_id=MonsterTemplateId.create(1),
        )
        table = SpotSpawnTable(spot_id=spot_id, slots=[slot])
        repo.add_table(table)
        snapshot = data_store.take_snapshot()
        assert "spawn_tables" in snapshot
        assert spot_id in snapshot["spawn_tables"]
        assert len(snapshot["spawn_tables"][spot_id].slots) == 1
        assert snapshot["spawn_tables"][spot_id].slots[0].coordinate == Coordinate(5, 5, 0)
        data_store.spawn_tables.clear()
        assert repo.find_by_spot_id(spot_id) is None
        data_store.restore_snapshot(snapshot)
        restored = repo.find_by_spot_id(spot_id)
        assert restored is not None
        assert len(restored.slots) == 1
        assert restored.slots[0].coordinate == Coordinate(5, 5, 0)
        assert restored.slots[0].template_id == MonsterTemplateId.create(1)
