"""所持品 / 地面アイテムの spoiled 表示 (Phase D-3a)。

UI builder が is_spoiled エントリに「(腐敗)」を付けることと、
inventory_builder が (spec, is_spoiled) で集約することを確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    LabelAllocator,
    RuntimeTargetCollector,
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphGroundItemEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphPlayerSnapshotDto,
)


def _empty_snapshot(**overrides) -> SpotGraphPlayerSnapshotDto:
    defaults: dict = {
        "current_spot_id": 0,
        "current_spot_name": "",
        "current_spot_description": "",
        "travel_status_line": "",
    }
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


class TestInventorySpoiledSurface:
    """所持品エントリで is_spoiled=True なら「(腐敗)」が付与される。"""

    def test_腐敗していないアイテムにはマーカーが付かない(self) -> None:
        snap = _empty_snapshot(
            inventory_items=(
                SpotGraphInventoryItemEntry(
                    item_spec_id=1, name="生の魚", quantity=1, is_spoiled=False,
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []

        builder._build_inventory_section(snap, allocator, collector, lines)

        assert "(腐敗)" not in lines[-1]
        assert "生の魚" in lines[-1]

    def test_腐敗アイテムには_腐敗_が表示される(self) -> None:
        snap = _empty_snapshot(
            inventory_items=(
                SpotGraphInventoryItemEntry(
                    item_spec_id=1, name="生の魚", quantity=1, is_spoiled=True,
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []

        builder._build_inventory_section(snap, allocator, collector, lines)

        assert "(腐敗)" in lines[-1]
        assert "生の魚" in lines[-1]

    def test_quantity_と_腐敗_の両方が表示される(self) -> None:
        snap = _empty_snapshot(
            inventory_items=(
                SpotGraphInventoryItemEntry(
                    item_spec_id=1, name="生の魚", quantity=3, is_spoiled=True,
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []

        builder._build_inventory_section(snap, allocator, collector, lines)

        # 「生の魚 x3 (腐敗)」の順
        assert "x3" in lines[-1]
        assert "(腐敗)" in lines[-1]


class TestGroundItemSpoiledSurface:
    """地面アイテムも同じく (腐敗) が付与される。"""

    def test_地面の腐敗アイテムにも_腐敗_が出る(self) -> None:
        snap = _empty_snapshot(
            ground_items=(
                SpotGraphGroundItemEntry(
                    item_instance_id=100, item_spec_id=1, name="生の魚", is_spoiled=True,
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []

        builder._build_ground_items_section(snap, allocator, collector, lines)

        assert "(腐敗)" in lines[-1]

    def test_地面の新鮮アイテムには_腐敗_が出ない(self) -> None:
        snap = _empty_snapshot(
            ground_items=(
                SpotGraphGroundItemEntry(
                    item_instance_id=100, item_spec_id=1, name="生の魚",
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []

        builder._build_ground_items_section(snap, allocator, collector, lines)

        assert "(腐敗)" not in lines[-1]


class TestDtoDefaults:
    """DTO の default 値 (既存呼び出し側に無影響であること)。"""

    def test_InventoryEntry_の_is_spoiled_default_は_False(self) -> None:
        entry = SpotGraphInventoryItemEntry(item_spec_id=1, name="x", quantity=1)
        assert entry.is_spoiled is False

    def test_GroundItemEntry_の_is_spoiled_default_は_False(self) -> None:
        entry = SpotGraphGroundItemEntry(item_instance_id=1, item_spec_id=1, name="x")
        assert entry.is_spoiled is False
