"""ItemSpecRepository の 2 実装が同じ型を返すことを固定する契約試験。

インメモリ実装だけが ItemSpecReadModel を返していた時期があり、
`to_item_spec()` を呼ぶ呼び出し側は SQLite 配線で AttributeError になった
(Issue #1364)。この試験は、同じ ID / 条件を両実装に与えて、返る型が
ItemSpec で一致することを見張る。
"""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_repository import (
    SqliteItemSpecRepository,
    SqliteItemSpecWriter,
)

_SPEC_ID = ItemSpecId(4001)
_SPEC_NAME = "契約試験の剣"
_LANTERN_ID = ItemSpecId(4002)
_LANTERN_NAME = "契約試験のランタン"


def _seeded_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=_SPEC_ID,
        name=_SPEC_NAME,
        item_type=ItemType.EQUIPMENT,
        rarity=Rarity.RARE,
        description="両実装に同じ内容で投入する spec",
        max_stack_size=MaxStackSize(1),
        durability_max=100,
        equipment_type=EquipmentType.WEAPON,
    )


def _lantern_spec() -> ItemSpec:
    """光源・腐敗・疲労回復を同時に持つ spec。3 つとも既定値から外してある。"""
    return ItemSpec(
        item_spec_id=_LANTERN_ID,
        name=_LANTERN_NAME,
        item_type=ItemType.QUEST,
        rarity=Rarity.COMMON,
        description="暗所を照らし、時間で傷み、使うと疲れが取れる",
        max_stack_size=MaxStackSize(1),
        is_light_source=True,
        spoils_after_ticks=120,
        fatigue_recovery=15,
    )


def _in_memory_repository() -> ItemSpecRepository:
    repo = InMemoryItemSpecRepository()
    repo.replace_spec(_seeded_spec())
    repo.replace_spec(_lantern_spec())
    return repo


def _sqlite_repository() -> ItemSpecRepository:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    writer = SqliteItemSpecWriter.for_standalone_connection(connection)
    writer.replace_spec(_seeded_spec())
    writer.replace_spec(_lantern_spec())
    return SqliteItemSpecRepository.for_connection(connection)


@pytest.fixture(params=["in_memory", "sqlite"])
def repository(request: pytest.FixtureRequest) -> ItemSpecRepository:
    if request.param == "in_memory":
        return _in_memory_repository()
    return _sqlite_repository()


class TestItemSpecRepositoryReturnType:
    """ItemSpecRepository の取得系が、実装に依らず ItemSpec を返すことを保証する。"""

    def test_find_by_id_returns_item_spec(self, repository: ItemSpecRepository) -> None:
        """投入済みの ID を渡すと ItemSpec が返り、名前が投入内容と一致する。"""
        found = repository.find_by_id(_SPEC_ID)

        assert isinstance(found, ItemSpec)
        assert found.name == _SPEC_NAME

    def test_find_by_ids_returns_item_specs(self, repository: ItemSpecRepository) -> None:
        """投入済みの ID を含むリストを渡すと、要素が ItemSpec のリストで返る。"""
        found = repository.find_by_ids([_SPEC_ID])

        assert [type(spec) for spec in found] == [ItemSpec]

    def test_find_all_returns_item_specs(self, repository: ItemSpecRepository) -> None:
        """find_all が返す全要素が ItemSpec であり、投入した spec を含む。"""
        found = repository.find_all()

        assert found
        assert all(isinstance(spec, ItemSpec) for spec in found)
        assert _SPEC_ID in {spec.item_spec_id for spec in found}

    def test_find_by_type_returns_item_specs(self, repository: ItemSpecRepository) -> None:
        """投入した spec の item_type で検索すると、ItemSpec のリストに含まれて返る。"""
        found = repository.find_by_type(ItemType.EQUIPMENT)

        assert all(isinstance(spec, ItemSpec) for spec in found)
        assert _SPEC_ID in {spec.item_spec_id for spec in found}

    def test_find_by_rarity_returns_item_specs(self, repository: ItemSpecRepository) -> None:
        """投入した spec の rarity で検索すると、ItemSpec のリストに含まれて返る。"""
        found = repository.find_by_rarity(Rarity.RARE)

        assert all(isinstance(spec, ItemSpec) for spec in found)
        assert _SPEC_ID in {spec.item_spec_id for spec in found}

    def test_find_tradeable_items_returns_item_specs(self, repository: ItemSpecRepository) -> None:
        """取引可能検索の結果が ItemSpec のリストで、QUEST 以外の投入 spec を含む。"""
        found = repository.find_tradeable_items()

        assert all(isinstance(spec, ItemSpec) for spec in found)
        assert _SPEC_ID in {spec.item_spec_id for spec in found}

    def test_find_by_name_returns_item_spec(self, repository: ItemSpecRepository) -> None:
        """投入した名前で検索すると ItemSpec が返り、ID が投入内容と一致する。"""
        found = repository.find_by_name(_SPEC_NAME)

        assert isinstance(found, ItemSpec)
        assert found.item_spec_id == _SPEC_ID

    def test_find_by_id_returns_none_for_unknown_id(self, repository: ItemSpecRepository) -> None:
        """投入していない ID を渡すと None が返る。"""
        assert repository.find_by_id(ItemSpecId(999_001)) is None


class TestItemSpecRepositoryKeepsScenarioDefinedFields:
    """作者がシナリオに書く光源・腐敗・疲労回復が、実装に依らず保たれることを保証する。"""

    def test_is_light_source_survives(self, repository: ItemSpecRepository) -> None:
        """is_light_source=True で投入した spec は、取得しても True のまま返る。"""
        found = repository.find_by_id(_LANTERN_ID)

        assert found is not None
        assert found.is_light_source is True

    def test_spoils_after_ticks_survives(self, repository: ItemSpecRepository) -> None:
        """spoils_after_ticks=120 で投入した spec は、取得しても 120 のまま返る。"""
        found = repository.find_by_id(_LANTERN_ID)

        assert found is not None
        assert found.spoils_after_ticks == 120

    def test_fatigue_recovery_survives(self, repository: ItemSpecRepository) -> None:
        """fatigue_recovery=15 で投入した spec は、取得しても 15 のまま返る。"""
        found = repository.find_by_id(_LANTERN_ID)

        assert found is not None
        assert found.fatigue_recovery == 15

    def test_defaults_stay_off_when_not_declared(self, repository: ItemSpecRepository) -> None:
        """3 つを指定せずに投入した spec は、取得しても既定の無効値で返る。"""
        found = repository.find_by_id(_SPEC_ID)

        assert found is not None
        assert found.is_light_source is False
        assert found.spoils_after_ticks is None
        assert found.fatigue_recovery == 0
