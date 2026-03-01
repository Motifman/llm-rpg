"""InMemoryPhysicalMapRepository のテスト（find_spot_id_by_object_id とインデックス更新）"""

import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)


def _tile_at(x: int, y: int) -> Tile:
    coord = Coordinate(x, y, 0)
    return Tile(coord, TerrainType.grass())


def _player_object(player_id: int, x: int = 0, y: int = 0) -> WorldObject:
    return WorldObject(
        object_id=WorldObjectId.create(player_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.PLAYER,
        component=ActorComponent(
            direction=DirectionEnum.SOUTH,
            player_id=PlayerId(player_id),
        ),
    )


def _minimal_map(spot_id: int, objects: list) -> PhysicalMapAggregate:
    coord = Coordinate(0, 0, 0)
    tiles = {coord: _tile_at(0, 0)}
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
    )


class TestInMemoryPhysicalMapRepositoryFindSpotIdByObjectId:
    """find_spot_id_by_object_id の正常・境界・例外"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    def test_find_spot_id_by_object_id_returns_none_when_empty(self, repo):
        """オブジェクトが未登録のとき None"""
        assert repo.find_spot_id_by_object_id(WorldObjectId(1)) is None

    def test_find_spot_id_by_object_id_returns_spot_id_after_save(self, repo):
        """save したマップ上のオブジェクトIDでスポットIDが取れる"""
        player_oid = WorldObjectId.create(1)
        physical_map = _minimal_map(10, [_player_object(1)])
        repo.save(physical_map)
        result = repo.find_spot_id_by_object_id(player_oid)
        assert result is not None
        assert result == SpotId(10)

    def test_find_spot_id_by_object_id_returns_none_for_unknown_object_id(self, repo):
        """存在しない WorldObjectId では None"""
        physical_map = _minimal_map(1, [_player_object(1)])
        repo.save(physical_map)
        assert repo.find_spot_id_by_object_id(WorldObjectId(99999)) is None


class TestInMemoryPhysicalMapRepositoryIndexOnSave:
    """save 時の world_object_id_to_spot_id インデックス更新"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    def test_save_adds_object_ids_to_index(self, repo, data_store):
        """save でマップ内オブジェクトがインデックスに追加される"""
        physical_map = _minimal_map(5, [_player_object(1)])
        repo.save(physical_map)
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(1)) == SpotId(5)

    def test_save_replacing_map_removes_old_and_adds_new_in_index(self, repo, data_store):
        """同一 spot_id で上書き save すると旧オブジェクトはインデックスから削除され新オブジェクトが追加される"""
        map1 = _minimal_map(1, [_player_object(1)])
        repo.save(map1)
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(1)) == SpotId(1)
        # 別オブジェクトのみのマップで上書き（プレイヤー2のみ）
        map2 = _minimal_map(1, [_player_object(2)])
        repo.save(map2)
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(1)) is None
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(2)) == SpotId(1)


class TestInMemoryPhysicalMapRepositoryIndexOnDelete:
    """delete 時の world_object_id_to_spot_id インデックス削除"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    def test_delete_removes_object_ids_from_index(self, repo, data_store):
        """delete でそのマップのオブジェクトがインデックスから削除される"""
        physical_map = _minimal_map(20, [_player_object(3)])
        repo.save(physical_map)
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(3)) == SpotId(20)
        repo.delete(SpotId(20))
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(3)) is None

    def test_delete_non_existing_does_not_raise(self, repo):
        """存在しない spot_id で delete しても例外にならない"""
        result = repo.delete(SpotId(999))
        assert result is False


class TestInMemoryPhysicalMapRepositorySnapshotRestore:
    """スナップショット復元時に world_object_id_to_spot_id が復元されること"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    def test_restore_snapshot_restores_world_object_id_to_spot_id(self, data_store, repo):
        """take_snapshot / restore_snapshot で world_object_id_to_spot_id が復元される"""
        repo.save(_minimal_map(7, [_player_object(1)]))
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(1)) == SpotId(7)
        snapshot = data_store.take_snapshot()
        data_store.world_object_id_to_spot_id.clear()
        assert repo.find_spot_id_by_object_id(WorldObjectId(1)) is None
        data_store.restore_snapshot(snapshot)
        assert data_store.world_object_id_to_spot_id.get(WorldObjectId(1)) == SpotId(7)
        assert repo.find_spot_id_by_object_id(WorldObjectId(1)) == SpotId(7)
