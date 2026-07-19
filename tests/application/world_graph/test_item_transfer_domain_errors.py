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


def test_target_self_error_item_transfer_exception_class(self=None) -> None:
    """type-based catch を可能にするため継承関係を保証。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        TargetIsSelfError,
    )
    assert issubclass(TargetIsSelfError, ItemTransferException)


def test_target_not_same_spot_error_item_transfer_exception_class() -> None:
    """TargetNotInSameSpotError は ItemTransferException の子 class。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        TargetNotInSameSpotError,
    )
    assert issubclass(TargetNotInSameSpotError, ItemTransferException)


def test_target_inventory_full_error_item_transfer_exception_class() -> None:
    """TargetInventoryFullError は ItemTransferException の子 class。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        TargetInventoryFullError,
    )
    assert issubclass(TargetInventoryFullError, ItemTransferException)


def test_domain_error_llm_error_code() -> None:
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


def test_target_self_error_message_japanese_llm() -> None:
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


def test_target_not_same_spot_error_message_target_current_spot_included() -> None:
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


def test_target_inventory_full_error_message_target_drop_included() -> None:
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


# ============================================================
# PR-ε: drop / pickup 系の domain exception 情報量アップ
# ============================================================
#
# PR-α で give_item の失敗を domain exception 化したのと同じ発想を
# drop / pickup にも広げる。頻発する失敗パターン (LLM が空スロットを
# 指定した、他プレイヤーに先取りされた、自分のインベントリが満杯) を
# 汎用 ``ItemTransferException`` から専用 subclass に分けることで:
#
# - LLM が受け取る message が「システムエラー」から「そのスロットには
#   何も入っていない」「他のプレイヤーが先に拾ったかも」に具体化される
# - error_code が細分化され、remediation で「次に何をすべきか」が届く
# - trace 上で「同じ pickup を 3 tick 連続で試して同じ失敗」ループが
#   原因側から潰される


def test_slot_empty_error_item_transfer_exception_class() -> None:
    """SlotIsEmptyError は ItemTransferException の子 class。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        SlotIsEmptyError,
    )
    assert issubclass(SlotIsEmptyError, ItemTransferException)


def test_ground_item_gone_error_item_transfer_exception_class() -> None:
    """GroundItemGoneError は ItemTransferException の子 class。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        GroundItemGoneError,
        ItemTransferException,
    )
    assert issubclass(GroundItemGoneError, ItemTransferException)


def test_pickup_self_inventory_full_error_item_transfer_exception_class() -> None:
    """PickupSelfInventoryFullError は ItemTransferException の子 class。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        ItemTransferException,
        PickupSelfInventoryFullError,
    )
    assert issubclass(PickupSelfInventoryFullError, ItemTransferException)


def test_drop_pickup_domain_error_llm_error_code() -> None:
    """PR-α と同じく class attribute として error_code を持ち、
    executor で catch した際に LLM 向け remediation にマップできる。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        GroundItemGoneError,
        PickupSelfInventoryFullError,
        SlotIsEmptyError,
    )
    assert SlotIsEmptyError.error_code == "ITEM_TRANSFER_SLOT_IS_EMPTY"
    assert (
        GroundItemGoneError.error_code == "PICKUP_ITEM_GROUND_ITEM_GONE"
    )
    assert (
        PickupSelfInventoryFullError.error_code
        == "PICKUP_ITEM_SELF_INVENTORY_FULL"
    )


def test_slot_empty_error_message_japanese() -> None:
    """LLM が「slot を確認してから再試行」できるよう、日本語で inspect_target
    等を促す message にする。内部 ID (slot 番号) はコンテキストとして
    含めても OK だが、英語 identifier は避ける。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        SlotIsEmptyError,
    )
    exc = SlotIsEmptyError(slot_id=3)
    msg = str(exc)
    # 対象 slot が分かる
    assert "3" in msg
    # 何をすべきか (inventory 確認) が読める
    assert "inventory" in msg.lower() or "スロット" in msg or "確認" in msg
    # 英語だけの文にしない
    assert any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in msg)


def test_ground_item_gone_error_message_other_player() -> None:
    """典型ケースは同 tick で複数プレイヤーが同じ地面アイテムに手を伸ばし
    片方が先に成功する。LLM が同じ pickup を繰り返さないよう、
    「他のプレイヤーが先に拾った可能性」と「別行動への切替」を message で伝える。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        GroundItemGoneError,
    )
    exc = GroundItemGoneError(item_name="流木")
    msg = str(exc)
    assert "流木" in msg
    # 他プレイヤー先取り or 別行動 の示唆
    assert (
        "他" in msg
        or "先" in msg
        or "拾" in msg
        or "explore" in msg
        or "別" in msg
    )


def test_includes_pickup_self_inventory_full_error_message_drop() -> None:
    """自分のインベントリが満杯で pickup できないケース。次アクションとして
    「自分の drop で空きを作る」を示唆する。"""
    from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
        PickupSelfInventoryFullError,
    )
    exc = PickupSelfInventoryFullError(item_name="流木")
    msg = str(exc)
    assert "流木" in msg
    # drop / 満杯 / 空き のいずれかを含む
    assert (
        "drop" in msg
        or "満杯" in msg
        or "空き" in msg
        or "捨て" in msg
    )
