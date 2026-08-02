"""所持品 / 地面アイテムの spoiled 表示 (Phase D-3a)。

UI builder が is_spoiled エントリに「(腐敗)」を付けることと、
inventory_builder が (spec, is_spoiled) で集約することを確認する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    ITEM_CATEGORY_DISPLAY,
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

    def test_inventory_entry_usage_hint_default_empty_string(self) -> None:
        """旧呼び出し側 (usage_hint を渡さない) は用途ヒントなしで従来表示になる。"""
        entry = SpotGraphInventoryItemEntry(item_spec_id=1, name="x", quantity=1)
        assert entry.usage_hint == ""

    def test_inventory_entry_category_default_empty_string(self) -> None:
        """旧呼び出し側 (category を渡さない) は item_type 由来表示へフォールバックする。"""
        entry = SpotGraphInventoryItemEntry(item_spec_id=1, name="x", quantity=1)
        assert entry.category == ""


class TestInventoryItemTypeTag:
    """``item_type`` を渡すと所持品行に「食料」「素材」等の用途タグが付与される。

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
        """``material`` はそのまま食べず、interact の材料にすることを明示する。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=2, name="流木", quantity=3, item_type="material",
            )
        )
        assert "(素材・そのままは食べられない。焚き火などの材料)" in line
        assert "使用不可" not in line

    def test_tool(self) -> None:
        """tool は近くのものに使う用途を示す。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=3, name="火打ち石", quantity=1, item_type="tool",
            )
        )
        assert "(道具・そのままは食べられない。近くのものに使う)" in line
        assert "使用不可" not in line

    def test_key_item_gets_important_and_unusable_tags(self) -> None:
        """keyitem は対応する場所やものに使う用途を示す。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=4, name="骨のナイフ", quantity=1, item_type="key_item",
            )
        )
        assert "(重要品・そのままは食べられない。対応する場所やものに使う)" in line
        assert "使用不可" not in line

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
        """``other`` は全否定にせず、食べ物ではないことと確認先を示す。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=6, name="布切れ", quantity=1, item_type="other",
            )
        )
        assert "(食べ物ではない。用途は周囲のオブジェクトや行動で確認)" in line
        assert "使用不可" not in line
        # 他の種別名は付かない
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


class TestInventoryCategoryTag:
    """scenario item_specs[].category が ItemType より優先して所持品の種別文言を決める。"""

    def _last_line(self, entry: SpotGraphInventoryItemEntry) -> str:
        snap = _empty_snapshot(inventory_items=(entry,))
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []
        builder._build_inventory_section(snap, allocator, collector, lines)
        return lines[-1]

    @pytest.mark.parametrize(
        ("category", "expected"),
        [
            ("FOOD", " (食料)"),
            ("MATERIAL", " (素材・そのままは食べられない。焚き火などの材料)"),
            ("TOOL", " (道具・そのままは食べられない。近くのものに使う)"),
            ("KEY_ITEM", " (重要品・そのままは食べられない。対応する場所やものに使う)"),
            ("LORE", " (手がかり・使う物ではない)"),
            ("DOCUMENT", " (記録・読んで手がかりを得る)"),
        ],
    )
    def test_declared_category_controls_inventory_tag(
        self, category: str, expected: str
    ) -> None:
        """6 種の item category は ItemType 由来ではなく category 由来の文言で表示される。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=10,
                name="品物",
                quantity=1,
                item_type="quest",
                category=category,
            )
        )

        assert expected in line

    def test_usage_hint_overrides_category(self) -> None:
        """usage_hint があれば category 由来の既定文ではなく作者文を表示する。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=11,
                name="流木",
                quantity=1,
                item_type="quest",
                category="MATERIAL",
                usage_hint="火を起こす材料。焚き火跡で interact の材料になる",
            )
        )

        assert "用途: 火を起こす材料。焚き火跡で interact の材料になる" in line
        assert "素材・そのままは食べられない" not in line

    def test_unset_category_falls_back_to_item_type(self) -> None:
        """category が無ければ従来の item_type 由来タグへフォールバックする。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=12,
                name="謎の任務品",
                quantity=1,
                item_type="quest",
            )
        )

        assert "(任務品・そのままは食べられない。対応する場所やものに使う)" in line

    def test_unknown_category_falls_back_without_crashing(self) -> None:
        """未知 category はクラッシュせず item_type 由来タグへフォールバックする。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=13,
                name="未知分類の品",
                quantity=1,
                item_type="quest",
                category="UNKNOWN_NEW_CATEGORY",
            )
        )

        assert "(任務品・そのままは食べられない。対応する場所やものに使う)" in line

    def test_lore_does_not_claim_food_or_interact_usage(self) -> None:
        """LORE は使う物ではないため、食べられない / interact して使うとは案内しない。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=14,
                name="古い徽章",
                quantity=1,
                item_type="quest",
                category="LORE",
            )
        )

        assert "手がかり・使う物ではない" in line
        assert "食べられない" not in line
        assert "interact" not in line

    def test_consumable_key_item_does_not_claim_interact_usage(self) -> None:
        """消費可能な KEY_ITEM は、対応オブジェクトで interact する品とは表示しない。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=15,
                name="救急用品",
                quantity=1,
                item_type="consumable",
                category="KEY_ITEM",
            )
        )

        assert "重要品・そのまま使える" in line
        assert "食べられない" not in line
        assert "interact" not in line

    def test_consumable_unknown_category_falls_back_to_consumable_tag(self) -> None:
        """消費可能品の未知 category は、非消費品文言ではなく consumable 表示へ戻す。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=16,
                name="未知分類の薬",
                quantity=1,
                item_type="consumable",
                category="UNKNOWN_NEW_CATEGORY",
            )
        )

        assert "(食料)" in line
        assert "食べられない" not in line
        assert "interact" not in line

    def test_declared_item_categories_in_scenarios_are_covered(self) -> None:
        """data/scenarios の item_specs で使う category は表示表に必ず定義する。"""
        scenario_dir = Path(__file__).resolve().parents[3] / "data" / "scenarios"
        used: set[str] = set()
        for path in scenario_dir.glob("*.json"):
            raw = json.loads(path.read_text(encoding="utf-8"))
            for item in raw.get("item_specs", ()):
                if "category" in item:
                    used.add(str(item["category"]).strip().upper())

        assert used == set(ITEM_CATEGORY_DISPLAY)

    def test_consumable_items_in_scenarios_never_get_non_consumable_usage_text(self) -> None:
        """consume_effect を持つ item には「食べられない」「interact して使う」を表示しない。"""
        scenario_dir = Path(__file__).resolve().parents[3] / "data" / "scenarios"
        checked = 0
        for path in scenario_dir.glob("*.json"):
            raw = json.loads(path.read_text(encoding="utf-8"))
            for idx, item in enumerate(raw.get("item_specs", ())):
                if item.get("consume_effect") is None:
                    continue
                checked += 1
                line = self._last_line(
                    SpotGraphInventoryItemEntry(
                        item_spec_id=idx + 1,
                        name=str(item.get("name") or item.get("id") or "item"),
                        quantity=1,
                        item_type="consumable",
                        category=str(item.get("category") or ""),
                        usage_hint=str(item.get("usage_hint") or ""),
                    )
                )
                assert "食べられない" not in line, (path.name, item.get("id"), line)
                assert "interact して使う" not in line, (path.name, item.get("id"), line)

        assert checked > 0


class TestInventoryUsageHint:
    """usage_hint は所持品行に作者文として添えられ、内部 ID は出さない。"""

    def _last_line(self, entry: SpotGraphInventoryItemEntry) -> str:
        snap = _empty_snapshot(inventory_items=(entry,))
        builder = SpotGraphUiContextBuilder()
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        lines: list[str] = []
        builder._build_inventory_section(snap, allocator, collector, lines)
        return lines[-1]

    def test_usage_hint_displayed(self) -> None:
        """usage_hint があれば item 名の外側に用途文として表示される。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=900,
                name="火打ち石",
                quantity=1,
                item_type="quest",
                usage_hint="火を起こす道具。火を扱う場所で interact して使う",
            )
        )

        assert '"火打ち石"' in line
        assert "火を起こす道具。火を扱う場所で interact して使う" in line

    def test_usage_hint_unset_keeps_existing_inventory_line(self) -> None:
        """usage_hint 未設定なら所持品行は既存の種別タグ表示だけに留まる。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=901, name="火打ち石", quantity=1, item_type="quest",
            )
        )

        assert "用途:" not in line
        assert line == (
            '  - "火打ち石" '
            "(任務品・そのままは食べられない。対応する場所やものに使う)"
        )

    def test_usage_hint_does_not_render_internal_ids(self) -> None:
        """用途ヒント付きでも item_spec_id / object_id / spot_id は prompt に漏れない。"""
        line = self._last_line(
            SpotGraphInventoryItemEntry(
                item_spec_id=902,
                name="枯れ葉",
                quantity=2,
                usage_hint="火を起こす材料。火を扱う場所で interact の材料になる",
            )
        )

        assert "902" not in line
        assert "item_spec_id" not in line
        assert "object_id" not in line
        assert "spot_id" not in line
