"""``give_item`` executor が domain-specific exception を catch して、
LLM が次に取るべき行動を判断できる日本語 message + error_code を返す
(Y_after_pr639_640_200tick 後続、PR-α)。

Y_after_pr639_640 のレビューで、給付経路の失敗が全て ``ITEM_TRANSFER_FAILED``
1 種類に集約され、message も英語 + 内部 ID (``"inventory not found for sender 3"``)
が漏れていて LLM が何を修正すればいいか判断できない、という指摘があった。

本 PR で ``ItemTransferException`` の子 class を追加し、executor 側で
それぞれ catch して:

- error_code を分ける (LLM の remediation mapping と結びつく)
- 日本語 message を LLM 向けに整形 (相手名 / アイテム名を args から
  差し込み、次アクション (travel_to / drop 待ち / 別相手 等) を示唆する)
- batch entry ごとに OK/NG 集約 (partial success)
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    ItemTransferException,
    TargetInventoryFullError,
    TargetIsSelfError,
    TargetNotInSameSpotError,
)


def _make_executor(transfer_stub) -> Any:
    """必要な dependency を stub で埋めた executor を作る。"""
    from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
        SpotGraphToolExecutor,
    )
    services = MagicMock()
    services.movement = MagicMock()
    services.world_flags = MagicMock()
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        item_transfer_service=transfer_stub,
    )


def _resolved_entry(
    *,
    slot_id: int = 1,
    target_player_id: int = 2,
    target_display_name: str = "ノア",
    item_display_name: str = "野いちご",
) -> Dict[str, Any]:
    return {
        "slot_id": slot_id,
        "target_player_id": target_player_id,
        "target_display_name": target_display_name,
        "item_display_name": item_display_name,
        "item_label": item_display_name,
        "target_player_label": target_display_name,
    }


class TestGiveItemTargetIsSelf:
    """自分自身に渡そうとした場合の error_code + message。"""

    def test_全件_target_self_なら_success_False_と_error_code(self) -> None:
        stub = MagicMock()
        stub.give_item.side_effect = TargetIsSelfError()
        executor = _make_executor(stub)

        result = executor._give_item(
            1,
            {
                "gives_resolved": [
                    _resolved_entry(target_display_name="自分"),
                ],
                "inner_thought": "test",
            },
        )
        assert result.success is False
        assert result.error_code == "GIVE_ITEM_TARGET_IS_SELF"
        # 日本語で「自分」の言及がある
        assert "自分" in result.message


class TestGiveItemTargetNotInSameSpot:
    """相手が別 spot にいる → travel_to を示唆する。"""

    def test_message_に_相手名と_travel_to_が_含まれる(self) -> None:
        stub = MagicMock()
        stub.give_item.side_effect = TargetNotInSameSpotError()
        executor = _make_executor(stub)

        result = executor._give_item(
            1,
            {
                "gives_resolved": [
                    _resolved_entry(target_display_name="ノア"),
                ],
                "inner_thought": "test",
            },
        )
        assert result.success is False
        assert result.error_code == "GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT"
        # executor が args から相手名を埋め直している
        assert "ノア" in result.message
        assert "travel_to" in result.message or "移動" in result.message
        # 英語や内部 ID が漏れていない
        assert "player_id" not in result.message.lower()


class TestGiveItemTargetInventoryFull:
    """相手のインベントリ満杯 → drop 待ち / 別の相手 を示唆する。"""

    def test_message_に_相手名_item名_drop提案が含まれる(self) -> None:
        stub = MagicMock()
        stub.give_item.side_effect = TargetInventoryFullError()
        executor = _make_executor(stub)

        result = executor._give_item(
            1,
            {
                "gives_resolved": [
                    _resolved_entry(
                        target_display_name="ノア",
                        item_display_name="野いちご",
                    ),
                ],
                "inner_thought": "test",
            },
        )
        assert result.success is False
        assert result.error_code == "GIVE_ITEM_TARGET_INVENTORY_FULL"
        assert "ノア" in result.message
        assert "野いちご" in result.message
        # 「満杯」または「drop」または「別の相手」の示唆がある
        assert (
            "満杯" in result.message
            or "drop" in result.message
            or "別の" in result.message
        )


class TestGiveItemSlotIsEmpty:
    """PR-ε: give_item で送り手の空スロットを指定した場合、SlotIsEmptyError が
    executor 側で error_code / message / remediation にきちんと反映される。

    Code review HIGH #1 で「_give_item の except ItemTransferException が
    error_code を無条件で ITEM_TRANSFER_FAILED に丸めていた」抜けをカバーする。"""

    def test_空スロット_give_で_ITEM_TRANSFER_SLOT_IS_EMPTY_が_LLM_に届く(self) -> None:
        from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
            SlotIsEmptyError,
        )
        stub = MagicMock()
        stub.give_item.side_effect = SlotIsEmptyError(slot_id=5)
        executor = _make_executor(stub)

        result = executor._give_item(
            1,
            {
                "gives_resolved": [
                    _resolved_entry(
                        target_display_name="ノア",
                        item_display_name="野いちご",
                    ),
                ],
                "inner_thought": "test",
            },
        )
        assert result.success is False
        # 汎用 ITEM_TRANSFER_FAILED ではなく、専用 error_code が届く
        assert result.error_code == "ITEM_TRANSFER_SLOT_IS_EMPTY"
        # remediation も専用文言 (「指定したスロットに何も入っていません」等)
        assert result.remediation is not None
        assert "スロット" in result.remediation


class TestGiveItemPartialSuccess:
    """batch 内 1 件失敗 + 他成功 → success=True + partial 集約 message。"""

    def test_1件成功_1件_target_self_失敗の場合(self) -> None:
        stub = MagicMock()
        # 呼び出し順に成功 → 失敗 を返す
        stub.give_item.side_effect = [
            MagicMock(messages=("渡した。",)),  # 1 件目 OK
            TargetIsSelfError(),                # 2 件目 NG
        ]
        executor = _make_executor(stub)

        result = executor._give_item(
            1,
            {
                "gives_resolved": [
                    _resolved_entry(
                        target_display_name="ノア",
                        item_display_name="野いちご",
                    ),
                    _resolved_entry(
                        slot_id=2,
                        target_display_name="自分",
                        item_display_name="流木",
                    ),
                ],
                "inner_thought": "test",
            },
        )
        # 1 件でも成功していれば success=True
        assert result.success is True
        # 両 entry の結果が message に含まれる
        assert "ノア" in result.message
        assert "自分" in result.message
        assert "OK" in result.message
        assert "NG" in result.message


class TestGiveItemAllFail:
    """全件失敗 → success=False + 最初の failure の error_code。"""

    def test_全件失敗なら_success_False_かつ_first_error_code(self) -> None:
        stub = MagicMock()
        stub.give_item.side_effect = [
            TargetInventoryFullError(),        # 1 件目 NG (最初なので error_code)
            TargetNotInSameSpotError(),        # 2 件目 NG
        ]
        executor = _make_executor(stub)

        result = executor._give_item(
            1,
            {
                "gives_resolved": [
                    _resolved_entry(target_display_name="ノア"),
                    _resolved_entry(target_display_name="エイダ"),
                ],
                "inner_thought": "test",
            },
        )
        assert result.success is False
        # 最初の error_code が伝わる (LLM が remediation を取れるため)
        assert result.error_code == "GIVE_ITEM_TARGET_INVENTORY_FULL"


class TestGiveItemGivesResolvedRequired:
    """gives_resolved が無い / 空だと INVALID_ARGUMENT。"""

    def test_gives_resolved_空_なら_INVALID_ARGUMENT(self) -> None:
        stub = MagicMock()
        executor = _make_executor(stub)
        result = executor._give_item(
            1, {"gives_resolved": [], "inner_thought": "test"}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_gives_resolved_未指定_なら_INVALID_ARGUMENT(self) -> None:
        stub = MagicMock()
        executor = _make_executor(stub)
        result = executor._give_item(1, {"inner_thought": "test"})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
