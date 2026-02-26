"""InMemorySpotRepository のテスト（正常・境界・例外ケース）"""

import pytest
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository


class TestInMemorySpotRepository:
    """InMemorySpotRepository のテスト"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def repo(self, data_store):
        return InMemorySpotRepository(data_store=data_store)

    def test_find_by_id_returns_none_when_empty(self, repo):
        """登録がないとき find_by_id は None"""
        assert repo.find_by_id(SpotId(1)) is None

    def test_save_and_find_by_id(self, repo):
        """save で登録したスポットを find_by_id で取得できる"""
        spot = Spot(SpotId(1), "Town", "A starting town", SpotCategoryEnum.TOWN)
        repo.save(spot)
        result = repo.find_by_id(SpotId(1))
        assert result is not None
        assert result.spot_id == SpotId(1)
        assert result.name == "Town"
        assert result.description == "A starting town"
        assert result.category == SpotCategoryEnum.TOWN

    def test_find_by_id_returns_clone(self, repo):
        """find_by_id は複製を返すため、取得後の変更がリポジトリに影響しない"""
        spot = Spot(SpotId(1), "Forest", "A dark forest")
        repo.save(spot)
        found = repo.find_by_id(SpotId(1))
        found.update_info(name="Modified")
        again = repo.find_by_id(SpotId(1))
        assert again.name == "Forest"

    def test_find_by_ids_returns_matching_spots(self, repo):
        """find_by_ids は存在するスポットのみ返す"""
        repo.save(Spot(SpotId(1), "S1", ""))
        repo.save(Spot(SpotId(2), "S2", ""))
        result = repo.find_by_ids([SpotId(1), SpotId(999), SpotId(2)])
        assert len(result) == 2
        assert {s.spot_id for s in result} == {SpotId(1), SpotId(2)}

    def test_find_by_ids_empty_list(self, repo):
        """find_by_ids に空リストを渡すと空リスト"""
        assert repo.find_by_ids([]) == []

    def test_find_all_returns_all_spots(self, repo):
        """find_all は登録済みの全スポットを返す"""
        assert repo.find_all() == []
        repo.save(Spot(SpotId(1), "A", ""))
        repo.save(Spot(SpotId(2), "B", ""))
        all_spots = repo.find_all()
        assert len(all_spots) == 2
        assert {s.name for s in all_spots} == {"A", "B"}

    def test_delete_removes_spot(self, repo):
        """delete で削除し、find_by_id が None になる"""
        repo.save(Spot(SpotId(1), "Gone", ""))
        assert repo.find_by_id(SpotId(1)) is not None
        deleted = repo.delete(SpotId(1))
        assert deleted is True
        assert repo.find_by_id(SpotId(1)) is None

    def test_delete_non_existing_returns_false(self, repo):
        """存在しないスポットの delete は False"""
        assert repo.delete(SpotId(999)) is False

    def test_save_overwrites_existing(self, repo):
        """同一 spot_id で save すると上書きされる"""
        repo.save(Spot(SpotId(1), "Old", "old desc"))
        repo.save(Spot(SpotId(1), "New", "new desc"))
        found = repo.find_by_id(SpotId(1))
        assert found.name == "New"
        assert found.description == "new desc"

    def test_spots_included_in_snapshot_and_restored(self, data_store, repo):
        """take_snapshot に spots が含まれ、restore_snapshot で復元できる"""
        repo.save(Spot(SpotId(1), "Snapshot Spot", "for snapshot"))
        snapshot = data_store.take_snapshot()
        assert "spots" in snapshot
        assert SpotId(1) in snapshot["spots"]
        assert snapshot["spots"][SpotId(1)].name == "Snapshot Spot"
        data_store.spots.clear()
        assert repo.find_by_id(SpotId(1)) is None
        data_store.restore_snapshot(snapshot)
        restored = repo.find_by_id(SpotId(1))
        assert restored is not None
        assert restored.name == "Snapshot Spot"

    def test_clear_all_removes_spots(self, data_store, repo):
        """DataStore.clear_all で spots がクリアされる"""
        repo.save(Spot(SpotId(1), "X", ""))
        data_store.clear_all()
        assert repo.find_by_id(SpotId(1)) is None
        assert repo.find_all() == []


class TestInMemorySpotRepositorySpotValidation:
    """Spot エンティティのバリデーション（リポジトリ経由で save するケース）"""

    @pytest.fixture
    def repo(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        return InMemorySpotRepository(data_store=data_store)

    def test_save_spot_with_empty_name_raises(self, repo):
        """name が空の Spot を save すると SpotNameEmptyException"""
        with pytest.raises(SpotNameEmptyException, match="cannot be empty"):
            repo.save(Spot(SpotId(1), "", "desc"))
