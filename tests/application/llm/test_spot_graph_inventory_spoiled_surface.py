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

    def test_unspoiled_items_do_not_get_spoilage_marker(self) -> None:
        """腐敗していないアイテムにはマーカーが付かない。"""
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

    def test_item_displayed(self) -> None:
        """腐敗アイテムには 腐敗 が表示される。"""
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

    def test_quantity_displayed(self) -> None:
        """quantity と腐敗の両方が表示される。"""
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

    def test_ground_item_rendered(self) -> None:
        """地面の腐敗アイテムにも 腐敗 が出る。"""
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

    def test_ground_item_not_rendered(self) -> None:
        """地面の新鮮アイテムには 腐敗 が出ない。"""
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

    def test_inventory_entry_spoiled_default_false(self) -> None:
        """InventoryEntry の is spoiled default は False。"""
        entry = SpotGraphInventoryItemEntry(item_spec_id=1, name="x", quantity=1)
        assert entry.is_spoiled is False

    def test_ground_item_entry_spoiled_default_false(self) -> None:
        """GroundItemEntry の is spoiled default は False。"""
        entry = SpotGraphGroundItemEntry(item_instance_id=1, item_spec_id=1, name="x")
        assert entry.is_spoiled is False

    def test_inventory_entry_item_type_default_empty_string(self) -> None:
        """旧呼び出し側 (item_type を渡さない) には何のタグも付かないことを保証。"""
        entry = SpotGraphInventoryItemEntry(item_spec_id=1, name="x", quantity=1)
        assert entry.item_type == ""


class TestInventoryItemTypeTag:
    """``item_type`` を渡すと所持品行に「(食料)」「(道具)」等のタグが付与される (#404 後続)。

    LLM が ITEM_NOT_CONSUMABLE で失敗 (=「使えない物を食べようとする」誤判断)
    するのを防ぐため、所持品リストの段階で type が見えるようにする。
    """

    def _last_line(self, entry: SpotGraphInventoryItemEntry) -> str:
        snap = _empty_snapshot(inventory_items=(entry,))
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []
        builder._build_inventory_section(snap, allocator, collector, lines)
        return lines[-1]

    def test_consumable(self) -> None:
        """consumable は食料タグ。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=1, name="生の魚", quantity=1, item_type="consumable",
            )
        )
        assert "(食料)" in line

    def test_material(self) -> None:
        """PR-C: ``material`` は use_item できないため「使用不可」を明示する。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=2, name="流木", quantity=3, item_type="material",
            )
        )
        assert "(素材・使用不可)" in line

    def test_tool(self) -> None:
        """tool は道具使用不可タグ。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=3, name="火打ち石", quantity=1, item_type="tool",
            )
        )
        assert "(道具・使用不可)" in line

    def test_key_item_gets_important_and_unusable_tags(self) -> None:
        """keyitem は重要使用不可タグ。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=4, name="骨のナイフ", quantity=1, item_type="key_item",
            )
        )
        assert "(重要・使用不可)" in line

    def test_unknown_type(self) -> None:
        """fallback 動作: 未知文字列でもクラッシュせずタグ非表示。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=5, name="謎の物体", quantity=1, item_type="zzz_unknown",
            )
        )
        # 「(食料)」「(素材)」等のいずれも出ない
        for tag in ("(食料)", "(素材", "(道具", "(重要", "(装備"):
            assert tag not in line

    def test_other_type(self) -> None:
        """PR-C: ``other`` は日本語 type 名は無いが、use_item できないことだけ
        明示する。Y_after_issue621 で「分類不能で使用不可」のフィードバックが
        足りず、LLM が試行に走った例を防ぐ。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=6, name="布切れ", quantity=1, item_type="other",
            )
        )
        assert "(使用不可)" in line
        # 種別名は付かない
        for tag in ("(食料)", "(素材", "(道具", "(重要"):
            assert tag not in line

    def test_type_displayed(self) -> None:
        """腐敗食 = (食料)(腐敗) の両方が並ぶ。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=7,
                name="生の魚",
                quantity=1,
                item_type="consumable",
                is_spoiled=True,
            )
        )
        assert "(食料)" in line
        assert "(腐敗)" in line
