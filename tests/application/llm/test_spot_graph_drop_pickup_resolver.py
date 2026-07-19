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
    PlayerToolRuntimeTargetDto,
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
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
)


def _make_context() -> ToolRuntimeContextDto:
    """I1=所持流木、G1=その場に落ちている流木を持つコンテキスト。"""
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
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="spot_graph_player",
                display_name="リン",
                player_id=2,
            ),
        },
    )


def _assert_llm_facing_message_has_no_internal_terms(message: str) -> None:
    """LLM が読む失敗文には内部 ID 解決用語を出さない。"""
    forbidden = (
        "地面アイテム",
        "item_spec_id",
        "slot",
        "instance",
        "player_id",
        "monster_id",
    )
    assert not any(term in message for term in forbidden), message


class TestDropItemResolver:
    """drop_item: I1 (inventory_item) → slot_id / item_instance_id 解決と境界検証。"""

    def test_i1_slot_id_item_instance_id_resolved(self) -> None:
        """所持アイテムラベルが内部実行に必要な ID に解決される。"""
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

    def test_drop_ground_item_label_invalid_target_kind(self) -> None:
        """G1 はその場に落ちているアイテムなので drop の対象として拒否される。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
                {"item_label": "G1", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_KIND"

    def test_drop_unresolved_inventory_target_message_hides_internal_terms(self) -> None:
        """手放す対象を内部 ID に変換できないときも、LLM には名前指定の修正方法を返す。"""
        resolver = SpotGraphArgumentResolver()
        context = ToolRuntimeContextDto(
            targets={
                "I_BROKEN": InventoryToolRuntimeTargetDto(
                    label="I_BROKEN",
                    kind="inventory_item",
                    display_name="壊れた流木",
                )
            },
        )
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
                {"item_label": "壊れた流木", "inner_thought": ""},
                context,
            )
        message = str(exc.value)
        assert "手放す対象として扱えません" in message
        assert "所持アイテム欄" in message
        _assert_llm_facing_message_has_no_internal_terms(message)

    def test_drop_label_invalid_target_label(self) -> None:
        """ターゲット辞書に無いラベルは INVALID_TARGET_LABEL で弾かれる。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
                {"item_label": "I99", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_drop_empty_label_invalid_target_label(self) -> None:
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

    def test_g1_item_instance_id_resolved(self) -> None:
        """その場に落ちているアイテムのラベルが内部実行に必要な ID に解決される。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            {"ground_item_label": "G1", "inner_thought": "流木を拾う"},
            _make_context(),
        )
        assert result is not None
        assert result["item_instance_id"] == 3
        assert result["target_display_name"] == "流木"

    def test_pickup_inventory_item_label_invalid_target_kind(self) -> None:
        """I1 は所持アイテム kind なので pickup の対象として拒否される。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "I1", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_KIND"

    def test_pickup_inventory_item_message_uses_natural_place_wording(self) -> None:
        """所持アイテムを pickup に渡した失敗文は「地面アイテム」と言わず、場所の状態を示す。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "I1", "inner_thought": ""},
                _make_context(),
            )
        message = str(exc.value)
        assert "今いる場所に落ちているものではありません" in message
        _assert_llm_facing_message_has_no_internal_terms(message)

    def test_pickup_unresolved_ground_target_message_hides_internal_terms(self) -> None:
        """拾う対象を内部 ID に変換できないときも、LLM には名前指定の修正方法を返す。"""
        resolver = SpotGraphArgumentResolver()
        context = ToolRuntimeContextDto(
            targets={
                "G_BROKEN": InventoryToolRuntimeTargetDto(
                    label="G_BROKEN",
                    kind="ground_item",
                    display_name="壊れた骨",
                    real_item_instance_id=None,
                )
            },
        )
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "壊れた骨", "inner_thought": ""},
                context,
            )
        message = str(exc.value)
        assert "拾う対象として扱えません" in message
        assert "地面に落ちているもの欄" in message
        _assert_llm_facing_message_has_no_internal_terms(message)

    def test_pickup_label_invalid_target_label(self) -> None:
        """pickup に不在ラベルを渡すと INVALID TARGET LABEL。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "G99", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_pickup_empty_label_invalid_target_label(self) -> None:
        """pickup に空ラベルを渡すと INVALID TARGET LABEL。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
                {"ground_item_label": "", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"


class TestInventoryAndPlayerFailureMessages:
    """使用・受け渡し・介抱の resolver 失敗文から内部 ID 解決用語を隠す。"""

    def test_use_unresolved_inventory_target_message_hides_internal_terms(self) -> None:
        """使用対象を内部 ID に変換できないときも、所持アイテム名の指定方法を返す。"""
        resolver = SpotGraphArgumentResolver()
        context = ToolRuntimeContextDto(
            targets={
                "I_BROKEN": InventoryToolRuntimeTargetDto(
                    label="I_BROKEN",
                    kind="inventory_item",
                    display_name="壊れた薬草",
                )
            },
        )
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM,
                {"item_label": "壊れた薬草", "inner_thought": ""},
                context,
            )
        message = str(exc.value)
        assert "使用対象として扱えません" in message
        assert "所持アイテム欄" in message
        _assert_llm_facing_message_has_no_internal_terms(message)

    def test_give_unresolved_inventory_target_message_hides_internal_terms(self) -> None:
        """渡す対象を内部 ID に変換できないときも、部分失敗の message に内部用語を出さない。"""
        resolver = SpotGraphArgumentResolver()
        context = ToolRuntimeContextDto(
            targets={
                "I_BROKEN": InventoryToolRuntimeTargetDto(
                    label="I_BROKEN",
                    kind="inventory_item",
                    display_name="壊れた薬草",
                    real_item_instance_id=10,
                ),
                "P1": PlayerToolRuntimeTargetDto(
                    label="P1",
                    kind="spot_graph_player",
                    display_name="リン",
                    player_id=2,
                ),
            },
        )
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            {
                "gives": [{
                    "item_label": "壊れた薬草",
                    "target_player_label": "リン",
                }],
                "inner_thought": "",
            },
            context,
        )
        assert result is not None
        message = result["gives_resolved"][0]["message"]
        assert "渡す対象として扱えません" in message
        assert "所持アイテム欄" in message
        _assert_llm_facing_message_has_no_internal_terms(message)

    def test_tend_unresolved_player_target_message_hides_internal_terms(self) -> None:
        """介抱する相手を内部 ID に変換できないときも、同じ場所で倒れている相手名を促す。"""
        resolver = SpotGraphArgumentResolver()
        context = ToolRuntimeContextDto(
            targets={
                "P_BROKEN": PlayerToolRuntimeTargetDto(
                    label="P_BROKEN",
                    kind="spot_graph_player",
                    display_name="リン",
                    player_id=None,
                )
            },
        )
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "リン", "inner_thought": ""},
                context,
            )
        message = str(exc.value)
        assert "介抱する相手として扱えません" in message
        assert "同じ場所で倒れているプレイヤー" in message
        _assert_llm_facing_message_has_no_internal_terms(message)

    def test_tend_missing_player_candidate_message_uses_natural_action_hint(self) -> None:
        """介抱候補にいない相手名を渡したとき、自然文で移動や別行動を促す。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "遠くのリン", "inner_thought": ""},
                _make_context(),
            )
        message = str(exc.value)
        assert "現在の場所で介抱できる候補にいません" in message
        assert "同じ場所で倒れているプレイヤーの名前" in message
        assert "先に移動" in message
        assert "話しかけるなど別の行動" in message
        assert "tool" not in message
        assert "travel_to" not in message
        assert "speech_speak" not in message
        _assert_llm_facing_message_has_no_internal_terms(message)
