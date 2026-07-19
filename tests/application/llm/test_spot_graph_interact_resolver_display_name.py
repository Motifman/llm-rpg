"""PR #441: spot_graph_interact / use_item / drop_item / pickup_item resolver の
display_name fallback 経路を保証する。

PR #421/#425 で「prompt 上のラベル prefix (OBJ1 / I1 / G1)」を撤去し、LLM が
display_name (= 日本語名) で引数を渡す仕様に変わった。しかし上記 4 resolver は
require_target / require_target_type を直叩きしていて display_name lookup が
できず、実験 #438 で全 interact が INVALID_TARGET_LABEL で失敗していた
(action 成功率 7.3%)。

本テストは PR #441 の修正 (display_name fallback の追加) が効いていることを
保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
    resolve_object_target,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
)


def _make_object_context() -> ToolRuntimeContextDto:
    """interact 対象の object (kind='spot_graph_object') を 2 件持つ context。"""
    return ToolRuntimeContextDto(
        targets={
            # 内部 label は OBJ1 / OBJ2 のまま。LLM はもう label を見ない (PR #421)
            "OBJ1": ToolRuntimeTargetDto(
                label="OBJ1",
                kind="spot_graph_object",
                display_name="流木の山",
                world_object_id=101,
            ),
            "OBJ2": ToolRuntimeTargetDto(
                label="OBJ2",
                kind="spot_graph_object",
                display_name="難破船の船倉",
                world_object_id=102,
            ),
        },
    )


def _make_inventory_context() -> ToolRuntimeContextDto:
    """use_item / drop_item 対象の inventory_item を持つ context。"""
    return ToolRuntimeContextDto(
        targets={
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="真水 (食料)",
                item_instance_id=1001,
                inventory_slot_id=11,
                real_item_instance_id=2001,
            ),
            "G1": InventoryToolRuntimeTargetDto(
                label="G1",
                kind="ground_item",
                display_name="貝",
                item_instance_id=1002,
                real_item_instance_id=2002,
            ),
        },
    )


class TestResolveObjectTargetDisplayNameFallback:
    """resolve_object_target (= interact) が display_name で解決する。

    実験 #438 で 252 件 INVALID_TARGET_LABEL を引き起こした silent failure の
    root fix を保証する。
    """

    def test_resolves_after_compatible_label_obj1(self) -> None:
        """旧形式 'OBJ1' も引き続き解決できる (= 既存挙動の維持)。"""
        ctx = _make_object_context()
        target = resolve_object_target("OBJ1", ctx)
        assert target.world_object_id == 101
        assert target.display_name == "流木の山"

    def test_resolves_pr_421_display_name(self) -> None:
        """新仕様: LLM が prompt で見た '流木の山' をそのまま引数に入れる。"""
        ctx = _make_object_context()
        target = resolve_object_target("流木の山", ctx)
        assert target.world_object_id == 101
        assert target.display_name == "流木の山"

    def test_resolves_display_name_2(self) -> None:
        """同 context 内の別 object も display_name で解決できる。"""
        ctx = _make_object_context()
        target = resolve_object_target("難破船の船倉", ctx)
        assert target.world_object_id == 102

    def test_resolves_obj1(self) -> None:
        """LLM が 'OBJ1 (流木の山)' のような hallucination 表記を渡しても拾う。"""
        ctx = _make_object_context()
        target = resolve_object_target("OBJ1 (流木の山)", ctx)
        assert target.world_object_id == 101

    def test_unknown_display_name_invalid_target_label(self) -> None:
        """周囲に無い object 名を渡したら従来通り label error。"""
        ctx = _make_object_context()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolve_object_target("存在しない物", ctx)
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_empty_string_invalid_target_label(self) -> None:
        """空文字は INVALID TARGET LABEL。"""
        ctx = _make_object_context()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolve_object_target("", ctx)
        assert exc.value.error_code == "INVALID_TARGET_LABEL"


class TestResolveUseItemDisplayNameFallback:
    """spot_graph_use_item の item_label を display_name で解決する。"""

    def test_resolves_after_compatible_label_i1(self) -> None:
        """label 直書き I1 で解決する 後方互換。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            {"item_label": "I1", "inner_thought": ""},
            _make_inventory_context(),
        )
        assert result is not None
        assert result["item_spec_id"] == 1001

    def test_resolves_display_name(self) -> None:
        """実験 #438 で 42 件失敗していた '真水 (食料)' を解決できる。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            {"item_label": "真水 (食料)", "inner_thought": ""},
            _make_inventory_context(),
        )
        assert result is not None
        assert result["item_spec_id"] == 1001
        assert result["item_display_name"] == "真水 (食料)"

    def test_ground_item_display_name_kind_mismatch(self) -> None:
        """use_item は inventory_item 限定。ground_item は kind 違いで弾く。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM,
                {"item_label": "貝", "inner_thought": ""},  # 貝は ground_item
                _make_inventory_context(),
            )
        # _resolve_target_with_display_name_fallback では kind="inventory_item" で
        # 探すので、貝 (ground_item) は見つからない → INVALID_TARGET_LABEL
        assert exc.value.error_code == "INVALID_TARGET_LABEL"


class TestResolveDropItemDisplayNameFallback:
    """spot_graph_drop_item も同じ display_name fallback を持つ。"""

    def test_display_name_drop(self) -> None:
        """display name で drop できる。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            {"item_label": "真水 (食料)", "inner_thought": "", "stealth": False},
            _make_inventory_context(),
        )
        assert result is not None
        assert result["slot_id"] == 11
        assert result["item_instance_id"] == 2001


class TestResolvePickupItemDisplayNameFallback:
    """spot_graph_pickup_item も同じ display_name fallback を持つ (kind=ground_item)。"""

    def test_display_name_pickup(self) -> None:
        """display name で pickup できる。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            {"ground_item_label": "貝", "inner_thought": "", "stealth": False},
            _make_inventory_context(),
        )
        assert result is not None
        assert result["item_instance_id"] == 2002

    def test_inventory_item_display_name_pickup_kind_mismatch(self) -> None:
        """pickup は ground_item 限定。inventory item を指したら見つからず label error。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "真水 (食料)", "inner_thought": ""},
                _make_inventory_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"
