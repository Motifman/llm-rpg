"""SpotGraphArgumentResolver の `spot_graph_drop_item` / `pickup_item` 解決パスを検証する。

検証範囲:
- drop: item_label="I1" (inventory_item kind) → slot_id / item_instance_id に解決
- drop: ground_item kind ラベルを渡すと INVALID_TARGET_KIND で弾く
- drop: 不在ラベルは INVALID_TARGET_LABEL
- pickup: ground_item_label="G1" (ground_item kind) → item_instance_id に解決
- pickup: inventory_item kind ラベルを渡すと INVALID_TARGET_KIND で弾く
- pickup: 不在ラベルは INVALID_TARGET_LABEL
- 空ラベル文字列は両方とも INVALID_TARGET_LABEL
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
)


def _make_context() -> ToolRuntimeContextDto:
    """I1=所持流木 (slot=2, instance=7) と G1=地面流木 (instance=3) を持つコンテキスト。"""
    return ToolRuntimeContextDto(
        targets={
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="流木",
                item_instance_id=9,  # 旧 use_item 用 (実は spec_id)
                real_item_instance_id=7,
                inventory_slot_id=2,
            ),
            "G1": InventoryToolRuntimeTargetDto(
                label="G1",
                kind="ground_item",
                display_name="流木",
                real_item_instance_id=3,
            ),
        },
    )


class TestDropItemResolver:
    """drop_item: I1 (inventory_item) → slot_id / item_instance_id 解決と境界検証。"""

    def test_I1_は_slot_id_と_item_instance_id_に解決される(self) -> None:
        """所持アイテムラベルが代表 instance の slot/instance に解決される。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            {"item_label": "I1", "inner_thought": "流木を渡す"},
            _make_context(),
        )
        assert result is not None
        assert result["slot_id"] == 2
        assert result["item_instance_id"] == 7
        assert result["target_display_name"] == "流木"

    def test_drop_に_ground_item_ラベルを渡すと_INVALID_TARGET_KIND(self) -> None:
        """G1 は地面アイテム kind なので drop の対象として拒否される。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
                {"item_label": "G1", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_KIND"

    def test_drop_に不在ラベルを渡すと_INVALID_TARGET_LABEL(self) -> None:
        """ターゲット辞書に無いラベルは INVALID_TARGET_LABEL で弾かれる。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
                {"item_label": "I99", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_drop_に空ラベルを渡すと_INVALID_TARGET_LABEL(self) -> None:
        """空文字列は INVALID_TARGET_LABEL で弾かれる。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
                {"item_label": "", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"


class TestPickupItemResolver:
    """pickup_item: G1 (ground_item) → item_instance_id 解決と境界検証。"""

    def test_G1_は_item_instance_id_に解決される(self) -> None:
        """地面アイテムラベルが instance_id に解決される。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            {"ground_item_label": "G1", "inner_thought": "流木を拾う"},
            _make_context(),
        )
        assert result is not None
        assert result["item_instance_id"] == 3
        assert result["target_display_name"] == "流木"

    def test_pickup_に_inventory_item_ラベルを渡すと_INVALID_TARGET_KIND(self) -> None:
        """I1 は所持アイテム kind なので pickup の対象として拒否される。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "I1", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_KIND"

    def test_pickup_に不在ラベルを渡すと_INVALID_TARGET_LABEL(self) -> None:
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "G99", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_pickup_に空ラベルを渡すと_INVALID_TARGET_LABEL(self) -> None:
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"
