#!/usr/bin/env python3
"""
Inventoryクラスの新しい機能をテストするデモスクリプト
"""

import pytest
from game.player.inventory import Inventory
from game.item.item import Item


def test_inventory_functionality():
    """Inventoryクラスの機能をテスト"""
    # インベントリを作成
    inventory = Inventory()
    
    # アイテムを作成
    sword = Item("sword", "鉄の剣 - 攻撃力+10")
    potion = Item("potion", "回復薬 - HPを50回復")
    shield = Item("shield", "木の盾 - 防御力+5")
    
    # 1. アイテムを追加
    inventory.add_item(sword)
    inventory.add_item(potion)
    inventory.add_item(sword)  # 重複アイテム
    inventory.add_item(potion)  # 重複アイテム
    inventory.add_item(shield)
    
    # 総アイテム数とユニークアイテム数の確認
    assert inventory.get_total_item_count() == 5
    assert inventory.get_unique_item_count() == 3
    
    # 2. アイテム個数確認
    assert inventory.get_item_count('sword') == 2
    assert inventory.get_item_count('potion') == 2
    assert inventory.get_item_count('shield') == 1
    
    # 3. アイテム削除テスト
    removed = inventory.remove_item_by_id("sword", 1)
    assert removed == 1
    assert inventory.get_item_count('sword') == 1
    
    # 4. 存在しないアイテムの削除
    removed = inventory.remove_item_by_id("nonexistent", 1)
    assert removed == 0
    
    # 5. アイテム存在確認
    assert inventory.has_item('sword') == True
    assert inventory.has_item('potion') == True
    assert inventory.has_item('nonexistent') == False
    
    # 6. アイテムオブジェクト取得
    sword_item = inventory.get_item_by_id("sword")
    assert sword_item is not None
    assert sword_item.item_id == "sword"
    
    # 7. 全アイテムリスト取得
    all_items = inventory.get_items()
    assert len(all_items) == 4  # sword(1), potion(2), shield(1)


def test_inventory_display():
    """インベントリ表示機能をテスト"""
    inventory = Inventory()
    
    # アイテムを追加
    sword = Item("sword", "鉄の剣 - 攻撃力+10")
    potion = Item("potion", "回復薬 - HPを50回復")
    
    inventory.add_item(sword)
    inventory.add_item(potion)
    
    # 表示機能が正常に動作することを確認
    summary = inventory.get_summary()
    assert "sword" in summary
    assert "potion" in summary
    
    display = inventory.get_inventory_display()
    assert "sword" in display
    assert "potion" in display


if __name__ == "__main__":
    test_inventory_functionality()
    test_inventory_display()
    print("すべてのテストが成功しました！") 