"""物理マップの保存先を除去し、他の保存先と本体を残す。"""

from dataclasses import fields
from pathlib import Path

import pytest

from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    WorldRuntimeSqliteRepositories,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore

_ROOT = Path(__file__).resolve().parents[2] / "src/ai_rpg_world"


@pytest.mark.parametrize(
    "relative_path",
    [
        "domain/world/repository/physical_map_repository.py",
        "infrastructure/repository/in_memory_physical_map_repository.py",
        "infrastructure/repository/sqlite_physical_map_repository.py",
        "infrastructure/repository/sqlite_world_state_codec.py",
    ],
)
def test_physical_map_storage_modules_are_removed(relative_path: str) -> None:
    """物理マップ保存先の契約・実装・変換器のファイルは存在しない。"""
    assert not (_ROOT / relative_path).exists()


def test_data_store_has_no_physical_map_state() -> None:
    """共有データストアは物理マップと専用の物体位置索引を持たない。"""
    store = InMemoryDataStore()
    assert "physical_maps" not in vars(store)
    assert "world_object_id_to_spot_id" not in vars(store)


def test_sqlite_runtime_bundle_has_no_physical_map_storage() -> None:
    """SQLiteの世界実行時の配線は物理マップ保存先を持たない。"""
    assert "physical_maps" not in {field.name for field in fields(WorldRuntimeSqliteRepositories)}
