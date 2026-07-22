"""spot_graph resolver の不一致エラーが有効候補名を返すことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
    resolve_destination_target,
    resolve_sub_location_target,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
)


def _assert_no_internal_labels(message: str) -> None:
    """LLM 向け失敗文には OBJ1 / S1 / SL1 / P1 などの内部ラベルを出さない。"""
    for internal_label in ("S1", "S2", "OBJ1", "OBJ2", "SL1", "SL2", "P1", "P2"):
        assert internal_label not in message


def test_destination_not_found_lists_valid_destination_names() -> None:
    """接続先名が候補に無いとき、現在選べる接続先名を列挙する。"""
    context = ToolRuntimeContextDto(
        targets={
            "S1": DestinationToolRuntimeTargetDto(
                label="S1",
                kind="spot_graph_destination",
                display_name="浜辺",
                spot_id=10,
                destination_type="spot",
            ),
            "S2": DestinationToolRuntimeTargetDto(
                label="S2",
                kind="spot_graph_destination",
                display_name="森の入口",
                spot_id=11,
                destination_type="spot",
            ),
        }
    )

    with pytest.raises(ToolArgumentResolutionException) as exc:
        resolve_destination_target("山頂", context)

    message = str(exc.value)
    assert exc.value.error_code == "INVALID_DESTINATION_LABEL"
    assert "指定された接続先名は現在の候補にありません: 山頂" in message
    assert "有効な接続先: 浜辺 / 森の入口" in message
    _assert_no_internal_labels(message)


def test_destination_not_found_with_no_candidates_says_no_valid_destinations() -> None:
    """接続先候補が 0 件なら、空の候補一覧を自然文で返す。"""
    context = ToolRuntimeContextDto(targets={})

    with pytest.raises(ToolArgumentResolutionException) as exc:
        resolve_destination_target("山頂", context)

    message = str(exc.value)
    assert "有効な接続先: ありません" in message
    _assert_no_internal_labels(message)


def test_interact_not_found_lists_valid_object_names() -> None:
    """interact 対象名が候補に無いとき、現在選べるオブジェクト名を列挙する。"""
    resolver = SpotGraphArgumentResolver()
    context = ToolRuntimeContextDto(
        targets={
            "OBJ1": ToolRuntimeTargetDto(
                label="OBJ1",
                kind="spot_graph_object",
                display_name="大樫の枝",
                world_object_id=101,
            ),
            "OBJ2": ToolRuntimeTargetDto(
                label="OBJ2",
                kind="spot_graph_object",
                display_name="岩の隙間",
                world_object_id=102,
            ),
        }
    )

    with pytest.raises(ToolArgumentResolutionException) as exc:
        resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            {"object_label": "大樫の樹", "action_name": "gather"},
            context,
        )

    message = str(exc.value)
    assert exc.value.error_code == "INVALID_TARGET_LABEL"
    assert "指定されたオブジェクト名は現在の候補にありません: 大樫の樹" in message
    assert "有効なオブジェクト名: 大樫の枝 / 岩の隙間" in message
    _assert_no_internal_labels(message)


def test_sub_location_not_found_lists_valid_sub_location_names() -> None:
    """サブロケーション名が候補に無いとき、現在選べるサブロケーション名を列挙する。"""
    context = ToolRuntimeContextDto(
        targets={
            "SL1": ToolRuntimeTargetDto(
                label="SL1",
                kind="spot_graph_sub_location",
                display_name="水辺",
                sub_location_id=1,
            ),
            "SL2": ToolRuntimeTargetDto(
                label="SL2",
                kind="spot_graph_sub_location",
                display_name="岩陰",
                sub_location_id=2,
            ),
        }
    )

    with pytest.raises(ToolArgumentResolutionException) as exc:
        resolve_sub_location_target("木陰", context)

    message = str(exc.value)
    assert exc.value.error_code == "INVALID_TARGET_LABEL"
    assert "指定されたサブロケーション名は現在の候補にありません: 木陰" in message
    assert "有効なサブロケーション: 水辺 / 岩陰" in message
    _assert_no_internal_labels(message)


def test_give_item_unknown_recipient_lists_valid_player_names_in_partial_failure() -> None:
    """give_item の相手名が候補に無いとき、部分失敗 message に同席者名を列挙する。"""
    resolver = SpotGraphArgumentResolver()
    context = ToolRuntimeContextDto(
        targets={
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="流木",
                item_instance_id=9,
                real_item_instance_id=7,
                inventory_slot_id=2,
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="spot_graph_player",
                display_name="エイダ",
                player_id=1,
            ),
            "P2": PlayerToolRuntimeTargetDto(
                label="P2",
                kind="spot_graph_player",
                display_name="ノア",
                player_id=2,
            ),
        }
    )

    result = resolver.resolve_args(
        TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
        {
            "gives": [{
                "item_label": "流木",
                "target_player_label": "カイ",
            }],
            "inner_thought": "",
        },
        context,
    )

    assert result is not None
    failure = result["gives_resolved"][0]
    message = failure["message"]
    assert failure["error_code"] == "INVALID_TARGET_LABEL"
    assert "指定された相手の名前が現在の候補にありません: カイ" in message
    assert "有効な相手: エイダ / ノア" in message
    _assert_no_internal_labels(message)

