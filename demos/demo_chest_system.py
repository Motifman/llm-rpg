#!/usr/bin/env python3
"""
宝箱システムのデモ
複数の宝箱がある場合の動作を確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.core.game_context import GameContext
from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.world.spot import Spot
from game.world.spot_manager import SpotManager
from game.object.chest import Chest
from game.item.item import Item
from game.action.action_orchestrator import ActionOrchestrator
from game.enums import Role


def create_test_world():
    """テスト用のワールドを作成"""
    # プレイヤーマネージャー
    player_manager = PlayerManager()
    player = Player("test_player", "テストプレイヤー", Role.CITIZEN)
    player_manager.add_player(player)
    
    # スポットマネージャー
    spot_manager = SpotManager()
    
    # 宝物部屋スポットを作成
    treasure_room = Spot("treasure_room", "宝物部屋", "複数の宝箱がある神秘的な部屋")
    spot_manager.add_spot(treasure_room)
    
    # アイテムを作成
    sword = Item("sword", "鉄の剣")
    potion = Item("potion", "回復薬")
    magic_ring = Item("magic_ring", "魔法の指輪")
    gold_coin = Item("gold_coin", "金貨")
    
    # 鍵アイテム
    golden_key = Item("golden_key", "黄金の鍵")
    silver_key = Item("silver_key", "銀の鍵")
    
    # 複数の宝箱を作成
    chest1 = Chest("chest_1", "古い宝箱", [sword, potion], is_locked=False)
    chest2 = Chest("chest_2", "銀の宝箱", [magic_ring], is_locked=True, required_item_id="silver_key")
    chest3 = Chest("chest_3", "黄金の宝箱", [gold_coin], is_locked=True, required_item_id="golden_key")
    
    # 宝箱をスポットに追加
    treasure_room.add_interactable(chest1)
    treasure_room.add_interactable(chest2)
    treasure_room.add_interactable(chest3)
    
    # プレイヤーを宝物部屋に配置
    player.set_current_spot_id("treasure_room")
    
    # ゲームコンテキストを作成
    game_context = GameContext(player_manager, spot_manager)
    
    return game_context, player


def test_chest_system():
    """宝箱システムのテスト"""
    print("=== 宝箱システムデモ ===")
    
    # ワールドを作成
    game_context, player = create_test_world()
    orchestrator = ActionOrchestrator(game_context)
    
    print(f"プレイヤー: {player.name}")
    print(f"現在地: {game_context.get_spot_manager().get_spot(player.get_current_spot_id()).name}")
    print()
    
    def print_inventory_status(title="インベントリ状態"):
        """インベントリの状態を表示"""
        print(f"=== {title} ===")
        inventory_items = player.get_inventory().get_items()
        if inventory_items:
            print("所持アイテム:")
            # アイテムを種類別にグループ化して個数を表示
            item_counts = {}
            for item in inventory_items:
                item_key = f"{item.item_id}: {item.description}"
                item_counts[item_key] = item_counts.get(item_key, 0) + 1
            
            for item_name, count in item_counts.items():
                if count > 1:
                    print(f"  - {item_name} (x{count})")
                else:
                    print(f"  - {item_name}")
        else:
            print("所持アイテム: なし")
        print()
    
    def track_inventory_change(before_items, after_items, action_name):
        """インベントリの変化を追跡して表示"""
        before_counts = {}
        after_counts = {}
        
        # アクション前のアイテム数をカウント
        for item in before_items:
            item_key = f"{item.item_id}: {item.description}"
            before_counts[item_key] = before_counts.get(item_key, 0) + 1
        
        # アクション後のアイテム数をカウント
        for item in after_items:
            item_key = f"{item.item_id}: {item.description}"
            after_counts[item_key] = after_counts.get(item_key, 0) + 1
        
        # 変化を検出
        changes = []
        all_items = set(before_counts.keys()) | set(after_counts.keys())
        
        for item_key in all_items:
            before_count = before_counts.get(item_key, 0)
            after_count = after_counts.get(item_key, 0)
            change = after_count - before_count
            
            if change > 0:
                changes.append(f"+ {item_key} (x{change})")
            elif change < 0:
                changes.append(f"- {item_key} (x{abs(change)})")
        
        if changes:
            print(f"=== {action_name}によるインベントリ変化 ===")
            for change in changes:
                print(f"  {change}")
            print()
    
    # 初期状態のインベントリを表示
    print_inventory_status("初期インベントリ状態")
    
    # 利用可能なアクションを確認
    print("=== 利用可能なアクション ===")
    candidates = orchestrator.get_action_candidates_for_llm(player.player_id)
    for candidate in candidates:
        print(f"アクション: {candidate['action_name']}")
        if candidate['required_arguments_info']:
            print(f"  引数候補: {candidate['required_arguments_info']}")
        print()
    
    # 1. 最初の宝箱を開ける（名前指定なし）
    print("=== 1. 最初の宝箱を開ける（名前指定なし） ===")
    print_inventory_status("アクション前のインベントリ")
    before_items = player.get_inventory().get_items().copy()
    
    result = orchestrator.execute_llm_action(player.player_id, "宝箱を開ける", {})
    print(f"結果: {result.message}")
    if hasattr(result, 'items_details') and result.items_details:
        print("入手アイテム:")
        for item in result.items_details:
            print(f"  - {item}")
    
    after_items = player.get_inventory().get_items()
    track_inventory_change(before_items, after_items, "宝箱を開ける")
    print_inventory_status("アクション後のインベントリ")
    print()
    
    # 2. 銀の宝箱を開けようとする（鍵なし）
    print("=== 2. 銀の宝箱を開けようとする（鍵なし） ===")
    print_inventory_status("アクション前のインベントリ")
    before_items = player.get_inventory().get_items().copy()
    
    result = orchestrator.execute_llm_action(player.player_id, "宝箱を開ける", {"chest_name": "銀の宝箱"})
    print(f"結果: {result.message}")
    
    after_items = player.get_inventory().get_items()
    track_inventory_change(before_items, after_items, "宝箱を開ける（鍵なし）")
    print_inventory_status("アクション後のインベントリ")
    print()
    
    # 3. 銀の鍵を入手して銀の宝箱を開ける
    print("=== 3. 銀の鍵を入手して銀の宝箱を開ける ===")
    print_inventory_status("鍵入手前のインベントリ")
    before_items = player.get_inventory().get_items().copy()
    
    silver_key = Item("silver_key", "銀の鍵")
    player.add_item(silver_key)
    print(f"銀の鍵を入手しました")
    
    after_items = player.get_inventory().get_items()
    track_inventory_change(before_items, after_items, "銀の鍵入手")
    print_inventory_status("鍵入手後のインベントリ")
    
    print_inventory_status("宝箱を開ける前のインベントリ")
    before_items = player.get_inventory().get_items().copy()
    
    result = orchestrator.execute_llm_action(player.player_id, "宝箱を開ける", {"chest_name": "銀の宝箱"})
    print(f"結果: {result.message}")
    if hasattr(result, 'items_details') and result.items_details:
        print("入手アイテム:")
        for item in result.items_details:
            print(f"  - {item}")
    
    after_items = player.get_inventory().get_items()
    track_inventory_change(before_items, after_items, "銀の宝箱を開ける")
    print_inventory_status("宝箱を開けた後のインベントリ")
    print()
    
    # 4. 存在しない宝箱を開けようとする
    print("=== 4. 存在しない宝箱を開けようとする ===")
    print_inventory_status("アクション前のインベントリ")
    before_items = player.get_inventory().get_items().copy()
    
    result = orchestrator.execute_llm_action(player.player_id, "宝箱を開ける", {"chest_name": "存在しない宝箱"})
    print(f"結果: {result.message}")
    
    after_items = player.get_inventory().get_items()
    track_inventory_change(before_items, after_items, "存在しない宝箱を開ける")
    print_inventory_status("アクション後のインベントリ")
    print()
    
    # 5. 利用可能なアクションを再確認
    print("=== 5. 利用可能なアクションを再確認 ===")
    print_inventory_status("最終インベントリ状態")
    
    candidates = orchestrator.get_action_candidates_for_llm(player.player_id)
    for candidate in candidates:
        print(f"アクション: {candidate['action_name']}")
        if candidate['required_arguments_info']:
            print(f"  引数候補: {candidate['required_arguments_info']}")
        print()


if __name__ == "__main__":
    test_chest_system() 