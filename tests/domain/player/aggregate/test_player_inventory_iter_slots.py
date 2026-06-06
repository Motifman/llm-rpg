"""`PlayerInventoryAggregate` のスロット走査公開 API。

実験 #26 で executor が `inv.slots` という存在しない属性を iter して
全 use_item が SYSTEM_ERROR で死んだ事案 (#385 で hot fix) の **恒久対策**。
application 層が aggregate の内部 dict (`_inventory_slots`) に直接触れず、
spec_id でアイテムを探す典型用途を aggregate 自身が公開 API で持つ。

API:
- `iter_slots()`: 全スロット (slot_id, iid_or_None) を yield
- `iter_occupied_slots()`: item が入っているスロットだけ yield
- `find_slot_by_item_spec_id(spec, repo)`: spec_id で 1 件検索
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId


def _new_inv(player_id_val: int = 1, max_slots: int = 4) -> PlayerInventoryAggregate:
    return PlayerInventoryAggregate.create_new_inventory(
        player_id=PlayerId(player_id_val), max_slots=max_slots,
    )


def _stub_item_repo(spec_by_iid: dict) -> MagicMock:
    """{ItemInstanceId(7001): ItemSpecId(101), ...} → mock repo that returns
    a fake aggregate with .item_spec.item_spec_id matching."""
    repo = MagicMock()

    def _find_by_id(iid):
        spec_id = spec_by_iid.get(iid)
        if spec_id is None:
            return None
        agg = MagicMock()
        agg.item_spec.item_spec_id = spec_id
        return agg

    repo.find_by_id.side_effect = _find_by_id
    return repo


class TestIterSlots:
    """`iter_slots` の挙動。"""

    def test_全スロット_を_順序通り_yield(self) -> None:
        inv = _new_inv(max_slots=3)
        # 内部 dict の insertion 順 = slot_id.value 昇順 (create_new_inventory の実装)
        slots = list(inv.iter_slots())
        assert len(slots) == 3
        # 初期状態は全部 None
        for slot_id, iid in slots:
            assert iid is None

    def test_空スロットも_含む(self) -> None:
        inv = _new_inv(max_slots=4)
        inv.acquire_item(item_instance_id=ItemInstanceId(7001))
        slots = list(inv.iter_slots())
        # max_slots 件きっちり
        assert len(slots) == 4
        # 1 件は埋まっている
        occupied = [s for s in slots if s[1] is not None]
        assert len(occupied) == 1


class TestIterOccupiedSlots:
    """`iter_occupied_slots` の挙動。"""

    def test_item_が_入っているスロットだけ_yield(self) -> None:
        inv = _new_inv(max_slots=4)
        inv.acquire_item(item_instance_id=ItemInstanceId(7001))
        inv.acquire_item(item_instance_id=ItemInstanceId(7002))
        occ = list(inv.iter_occupied_slots())
        assert len(occ) == 2
        iids = {iid for _, iid in occ}
        assert iids == {ItemInstanceId(7001), ItemInstanceId(7002)}

    def test_空_inventory_は_空_iter(self) -> None:
        inv = _new_inv(max_slots=4)
        assert list(inv.iter_occupied_slots()) == []


class TestFindSlotByItemSpecId:
    """`find_slot_by_item_spec_id` の挙動 (executor の典型用途)。"""

    def test_見つかる_場合_は_slot_id_と_iid_の_ペアを返す(self) -> None:
        inv = _new_inv(max_slots=4)
        inv.acquire_item(item_instance_id=ItemInstanceId(7001))
        repo = _stub_item_repo({ItemInstanceId(7001): ItemSpecId.create(101)})
        result = inv.find_slot_by_item_spec_id(ItemSpecId.create(101), repo)
        assert result is not None
        slot_id, iid = result
        assert iid == ItemInstanceId(7001)
        assert isinstance(slot_id, SlotId)

    def test_見つからない_場合_は_None(self) -> None:
        inv = _new_inv(max_slots=4)
        inv.acquire_item(item_instance_id=ItemInstanceId(7001))
        repo = _stub_item_repo({ItemInstanceId(7001): ItemSpecId.create(101)})
        # 別の spec_id を要求 → None
        result = inv.find_slot_by_item_spec_id(ItemSpecId.create(999), repo)
        assert result is None

    def test_aggregate_が_repo_に_なければ_skip_して_None(self) -> None:
        """orphan item_instance_id (= item_repository に登録されていない)
        があってもクラッシュせず None で返す。"""
        inv = _new_inv(max_slots=4)
        inv.acquire_item(item_instance_id=ItemInstanceId(7001))
        repo = _stub_item_repo({})  # 何もない
        result = inv.find_slot_by_item_spec_id(ItemSpecId.create(101), repo)
        assert result is None

    def test_最初の_match_を_返す(self) -> None:
        """同じ spec_id の item が複数あったら最初に見つかったものを返す。"""
        inv = _new_inv(max_slots=4)
        inv.acquire_item(item_instance_id=ItemInstanceId(7001))
        inv.acquire_item(item_instance_id=ItemInstanceId(7002))
        repo = _stub_item_repo({
            ItemInstanceId(7001): ItemSpecId.create(101),
            ItemInstanceId(7002): ItemSpecId.create(101),
        })
        result = inv.find_slot_by_item_spec_id(ItemSpecId.create(101), repo)
        assert result is not None
        _, iid = result
        # insertion 順で最初の SlotId(0) には 7001 が入る
        assert iid == ItemInstanceId(7001)


class TestPrivateAccessRemoval:
    """executor が public API を使い、private `_inventory_slots` 直接アクセスを
    残していないことを source レベルで確認する。"""

    def test_executor_が_inv_inventory_slots_を_直接_参照しない(self) -> None:
        from pathlib import Path
        executor_src = (
            Path(__file__).resolve().parents[4]
            / "src/ai_rpg_world/application/llm/services/executors/spot_graph_tool_executor.py"
        )
        text = executor_src.read_text(encoding="utf-8")
        non_comment = "\n".join(
            ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
        )
        assert "inv._inventory_slots" not in non_comment, (
            "executor が aggregate の private dict `_inventory_slots` を "
            "まだ直接 iter している。`find_slot_by_item_spec_id` を使うべき"
        )
