import pytest

from game.player.player import Player
from game.enums import Role, AppearanceSlot
from game.item.item import AppearanceItem


def test_clothing_basic_flow():
    player = Player(player_id="p1", name="Alice", role=Role.CITIZEN)

    # ベース容姿
    player.set_base_appearance("黒髪の青年")

    # 服飾アイテム作成
    hat = AppearanceItem(item_id="hat_simple", name="シンプルな帽子", description="布の帽子", appearance_text="小さな帽子")
    top = AppearanceItem(item_id="top_shirt", name="シャツ", description="白いシャツ", appearance_text="白いシャツ")

    # インベントリに追加
    player.add_item(hat)
    player.add_item(top)

    assert player.get_inventory_item_count("hat_simple") == 1
    assert player.get_inventory_item_count("top_shirt") == 1

    # 装着（HEADWEAR）
    removed_id = player.equip_clothing(AppearanceSlot.HEADWEAR, "hat_simple")
    assert removed_id is None  # 既存なし
    assert player.get_inventory_item_count("hat_simple") == 0

    # 装着（TOP）
    player.equip_clothing(AppearanceSlot.TOP, "top_shirt")
    assert player.get_inventory_item_count("top_shirt") == 0

    # 見た目テキスト
    text = player.get_appearance_text()
    assert "黒髪の青年" in text
    assert "headwear: 小さな帽子" in text
    assert "top: 白いシャツ" in text

    # 外す
    removed_id = player.unequip_clothing(AppearanceSlot.HEADWEAR)
    assert removed_id == "hat_simple"
    assert player.get_inventory_item_count("hat_simple") == 1


