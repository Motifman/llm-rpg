"""``SpotGraphItemTransferService.give_item`` の失敗が domain error ごとに
別 exception クラスで区別される (Y_after_pr639_640_200tick 後続、PR-α)。

Y_after_pr639_640 の分析で、give_item の失敗が全て ``ITEM_TRANSFER_FAILED``
1 種類に集約され、message も英語 + 内部 ID (例:
``"inventory not found for sender 3"``) が漏れていて LLM が次に取るべき
行動を判断できない、という指摘があった。

各 domain error を専用 exception 子 class にし、LLM 向けの日本語 message
を伴わせる。executor はクラスで catch 分岐して error_code + message を
そのまま LLM に返す。

## error kinds

- ``TargetIsSelfError`` (GIVE_ITEM_TARGET_IS_SELF):
  自分自身にアイテムを渡そうとした
- ``TargetNotInSameSpotError`` (GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT):
  相手が別 spot にいる → 距離 (spot 名) を可能なら message に含める
- ``TargetInventoryFullError`` (GIVE_ITEM_TARGET_INVENTORY_FULL):
  相手のインベントリ満杯 → drop 依頼などの次アクションを示唆
- ``ItemNotInSlotError``: (既存の domain player error として存在) 元 slot が空

これら以外の「内部エラー」(inventory not found / item aggregate not found)
は稀な整合性違反であり、``ItemTransferException`` (base) のまま残す。
"""

from __future__ import annotations

import pytest


def test_TargetIsSelfError_は_ItemTransferException_の_子class(self=None) -> None:
    """type-based catch を可能にするため継承関係を保証。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        TargetIsSelfError,
    )
    assert issubclass(TargetIsSelfError, ItemTransferException)


def test_TargetNotInSameSpotError_は_ItemTransferException_の_子class() -> None:
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        TargetNotInSameSpotError,
    )
    assert issubclass(TargetNotInSameSpotError, ItemTransferException)


def test_TargetInventoryFullError_は_ItemTransferException_の_子class() -> None:
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        TargetInventoryFullError,
    )
    assert issubclass(TargetInventoryFullError, ItemTransferException)


def test_各_domain_error_は_LLM_向け_error_code_を_持つ() -> None:
    """error_code は class 属性として持ち、LLM の action feedback で
    remediation mapping と結び付く。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        TargetInventoryFullError,
        TargetIsSelfError,
        TargetNotInSameSpotError,
    )
    assert TargetIsSelfError.error_code == "GIVE_ITEM_TARGET_IS_SELF"
    assert (
        TargetNotInSameSpotError.error_code
        == "GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT"
    )
    assert (
        TargetInventoryFullError.error_code
        == "GIVE_ITEM_TARGET_INVENTORY_FULL"
    )


def test_TargetIsSelfError_の_message_は_日本語で_LLM向け() -> None:
    """英語や内部 ID を含まず、次アクションが読める日本語であること。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        TargetIsSelfError,
    )
    exc = TargetIsSelfError()
    msg = str(exc)
    assert "自分" in msg
    # 内部 ID や英単語で LLM を混乱させない
    assert "player" not in msg.lower()
    assert "player_id" not in msg


def test_TargetNotInSameSpotError_の_message_に_相手名と現在地が含まれる() -> None:
    """LLM が travel_to 判断できるよう、相手の名前と自分の現在地を含める。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        TargetNotInSameSpotError,
    )
    exc = TargetNotInSameSpotError(
        target_name="ノア",
        sender_spot_name="森の広場",
    )
    msg = str(exc)
    assert "ノア" in msg
    assert "森の広場" in msg
    # 次アクション (travel_to) を示唆
    assert "travel" in msg or "移動" in msg


def test_TargetInventoryFullError_の_message_に_相手名と_drop提案が含まれる() -> None:
    """相手のインベントリが満杯 → 相手に drop してもらう / 別の相手 の次
    アクションを示唆する。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        TargetInventoryFullError,
    )
    exc = TargetInventoryFullError(target_name="ノア", item_name="流木")
    msg = str(exc)
    assert "ノア" in msg
    assert "流木" in msg
    # 満杯・drop・別の相手 のうち少なくとも 1 つを提案
    assert (
        "満杯" in msg
        or "drop" in msg
        or "別の" in msg
    )
