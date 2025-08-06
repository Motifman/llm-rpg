#!/usr/bin/env python3
"""
取引システムデモ

このデモでは、実際のアイテムを使った取引システムの動作を確認できます。
- アイテムとお金の取引
- アイテム同士の取引
- 取引のキャンセル
- 取引履歴の確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.core.game_context import GameContext
from game.trade.trade_manager import TradeManager
from game.action.actions.trade_action import (
    PostTradeCommand, AcceptTradeCommand, CancelTradeCommand,
    GetMyTradesCommand, GetAvailableTradesCommand
)
from game.enums import Role
from game.item.item import StackableItem
from game.item.consumable_item import ConsumableItem
from game.item.item_effect import ItemEffect


def setup_demo_environment():
    """デモ用の環境をセットアップ"""
    print("=== 取引システムデモ環境のセットアップ ===")
    
    # プレイヤーマネージャーを作成
    player_manager = PlayerManager()
    
    # デモ用プレイヤーを作成
    alice = Player("alice", "アリス", Role.ADVENTURER)
    bob = Player("bob", "ボブ", Role.ADVENTURER)
    charlie = Player("charlie", "チャーリー", Role.ADVENTURER)
    
    # プレイヤーをマネージャーに登録
    player_manager.add_player(alice)
    player_manager.add_player(bob)
    player_manager.add_player(charlie)
    
    # デモ用アイテムを作成
    apple = StackableItem("apple", "りんご", "甘いりんご", max_stack=10)
    orange = StackableItem("orange", "オレンジ", "酸っぱいオレンジ", max_stack=10)
    bread = StackableItem("bread", "パン", "美味しいパン", max_stack=5)
    
    potion = ConsumableItem("potion", "ポーション", "HPを回復する", 
                           ItemEffect(hp_change=50), max_stack=5)
    elixir = ConsumableItem("elixir", "エリクサー", "MPを回復する", 
                           ItemEffect(mp_change=30), max_stack=3)
    
    # プレイヤーに初期アイテムを配布
    print("プレイヤーに初期アイテムを配布中...")
    
    # アリス（売り手）
    for _ in range(10):
        alice.add_item(apple)
    for _ in range(5):
        alice.add_item(potion)
    alice.status.add_gold(500)
    print(f"アリス: りんご x10, ポーション x5, お金 500ゴールド")
    
    # ボブ（買い手）
    for _ in range(8):
        bob.add_item(orange)
    for _ in range(3):
        bob.add_item(elixir)
    bob.status.add_gold(1000)
    print(f"ボブ: オレンジ x8, エリクサー x3, お金 1000ゴールド")
    
    # チャーリー（別の買い手）
    for _ in range(5):
        charlie.add_item(bread)
    charlie.status.add_gold(800)
    print(f"チャーリー: パン x5, お金 800ゴールド")
    
    # ゲームコンテキストを作成
    trade_manager = TradeManager()
    game_context = GameContext(
        player_manager=player_manager,
        spot_manager=None,
        trade_manager=trade_manager
    )
    
    print("セットアップ完了！")
    print()
    
    return game_context, alice, bob, charlie


def demo_money_trade(game_context, alice, bob):
    """お金取引のデモ"""
    print("=== お金取引デモ ===")
    
    # アリスがりんごを100ゴールドで出品
    print("アリスがりんごを100ゴールドで出品します...")
    post_command = PostTradeCommand("apple", 3, 100, trade_type="global")
    post_result = post_command.execute(alice, game_context)
    
    if post_result.success:
        print(f"✓ 取引出品成功: {post_result.trade_details}")
        print(f"  取引ID: {post_result.trade_id}")
        print(f"  アリスのりんご: {alice.get_inventory_item_count('apple')}個")
        
        # ボブが取引を受託
        print("\nボブが取引を受託します...")
        accept_command = AcceptTradeCommand(post_result.trade_id)
        accept_result = accept_command.execute(bob, game_context)
        
        if accept_result.success:
            print(f"✓ 取引受託成功: {accept_result.trade_details}")
            print(f"  ボブのりんご: {bob.get_inventory_item_count('apple')}個")
            print(f"  ボブのお金: {bob.status.get_gold()}ゴールド")
            print(f"  アリスのお金: {alice.status.get_gold()}ゴールド")
        else:
            print(f"✗ 取引受託失敗: {accept_result.message}")
    else:
        print(f"✗ 取引出品失敗: {post_result.message}")
    
    print()


def demo_item_trade(game_context, alice, bob):
    """アイテム同士の取引デモ"""
    print("=== アイテム同士の取引デモ ===")
    
    # アリスがりんごをオレンジと交換で出品
    print("アリスがりんごをオレンジと交換で出品します...")
    post_command = PostTradeCommand("apple", 2, 0, "orange", 1, trade_type="global")
    post_result = post_command.execute(alice, game_context)
    
    if post_result.success:
        print(f"✓ 取引出品成功: {post_result.trade_details}")
        print(f"  取引ID: {post_result.trade_id}")
        
        # ボブが取引を受託
        print("\nボブが取引を受託します...")
        accept_command = AcceptTradeCommand(post_result.trade_id)
        accept_result = accept_command.execute(bob, game_context)
        
        if accept_result.success:
            print(f"✓ 取引受託成功: {accept_result.trade_details}")
            print(f"  アリスのオレンジ: {alice.get_inventory_item_count('orange')}個")
            print(f"  ボブのりんご: {bob.get_inventory_item_count('apple')}個")
            print(f"  ボブのオレンジ: {bob.get_inventory_item_count('orange')}個")
        else:
            print(f"✗ 取引受託失敗: {accept_result.message}")
    else:
        print(f"✗ 取引出品失敗: {post_result.message}")
    
    print()


def demo_trade_cancellation(game_context, alice, charlie):
    """取引キャンセルのデモ"""
    print("=== 取引キャンセルデモ ===")
    
    # アリスがポーションを200ゴールドで出品
    print("アリスがポーションを200ゴールドで出品します...")
    post_command = PostTradeCommand("potion", 2, 200, trade_type="global")
    post_result = post_command.execute(alice, game_context)
    
    if post_result.success:
        print(f"✓ 取引出品成功: {post_result.trade_details}")
        print(f"  取引ID: {post_result.trade_id}")
        print(f"  アリスのポーション: {alice.get_inventory_item_count('potion')}個")
        
        # アリスが取引をキャンセル
        print("\nアリスが取引をキャンセルします...")
        cancel_command = CancelTradeCommand(post_result.trade_id)
        cancel_result = cancel_command.execute(alice, game_context)
        
        if cancel_result.success:
            print(f"✓ 取引キャンセル成功: {cancel_result.trade_details}")
            print(f"  アリスのポーション: {alice.get_inventory_item_count('potion')}個")
        else:
            print(f"✗ 取引キャンセル失敗: {cancel_result.message}")
    else:
        print(f"✗ 取引出品失敗: {post_result.message}")
    
    print()


def demo_trade_history(game_context, alice, bob):
    """取引履歴のデモ"""
    print("=== 取引履歴デモ ===")
    
    # 複数の取引を実行
    print("複数の取引を実行中...")
    
    # 取引1: りんごを50ゴールドで
    post1 = PostTradeCommand("apple", 1, 50, trade_type="global")
    result1 = post1.execute(alice, game_context)
    if result1.success:
        accept1 = AcceptTradeCommand(result1.trade_id)
        accept1.execute(bob, game_context)
    
    # 取引2: りんごを150ゴールドで
    post2 = PostTradeCommand("apple", 2, 150, trade_type="global")
    result2 = post2.execute(alice, game_context)
    if result2.success:
        accept2 = AcceptTradeCommand(result2.trade_id)
        accept2.execute(bob, game_context)
    
    # 取引3: キャンセルされる取引
    post3 = PostTradeCommand("potion", 1, 100, trade_type="global")
    result3 = post3.execute(alice, game_context)
    if result3.success:
        cancel3 = CancelTradeCommand(result3.trade_id)
        cancel3.execute(alice, game_context)
    
    # 取引履歴を確認
    print("\n取引履歴を確認します...")
    history = game_context.get_trade_manager().get_trade_history()
    
    print(f"取引履歴数: {len(history)}")
    for i, trade in enumerate(history, 1):
        print(f"  取引{i}: {trade.get_trade_summary()} (ステータス: {trade.status.value})")
    
    print()


def demo_trade_search(game_context, alice, bob, charlie):
    """取引検索のデモ"""
    print("=== 取引検索デモ ===")
    
    # 複数の取引を出品
    print("複数の取引を出品中...")
    
    # アリスが複数の取引を出品
    post1 = PostTradeCommand("apple", 1, 50, trade_type="global")
    post2 = PostTradeCommand("potion", 1, 200, trade_type="global")
    post3 = PostTradeCommand("apple", 3, 300, trade_type="global")
    
    post1.execute(alice, game_context)
    post2.execute(alice, game_context)
    post3.execute(alice, game_context)
    
    # 全取引を取得
    print("\n全取引を取得...")
    get_all = GetAvailableTradesCommand()
    all_result = get_all.execute(bob, game_context)
    
    if all_result.success:
        print(f"利用可能な取引数: {len(all_result.trades)}")
        for i, trade in enumerate(all_result.trades, 1):
            print(f"  取引{i}: {trade.get_trade_summary()}")
    
    # 価格フィルタで検索
    print("\n価格フィルタ（100ゴールド以下）で検索...")
    filters = {"max_price": 100}
    get_filtered = GetAvailableTradesCommand(filters)
    filtered_result = get_filtered.execute(bob, game_context)
    
    if filtered_result.success:
        print(f"フィルタ適用後の取引数: {len(filtered_result.trades)}")
        for i, trade in enumerate(filtered_result.trades, 1):
            print(f"  取引{i}: {trade.get_trade_summary()}")
    
    print()


def demo_error_cases(game_context, alice, bob):
    """エラーケースのデモ"""
    print("=== エラーケースデモ ===")
    
    # アイテム不足での取引出品
    print("アイテム不足での取引出品を試行...")
    post_command = PostTradeCommand("nonexistent_item", 1, 100, trade_type="global")
    result = post_command.execute(alice, game_context)
    print(f"結果: {'成功' if result.success else '失敗'}")
    if not result.success:
        print(f"  エラーメッセージ: {result.message}")
    
    # お金不足での取引受託
    print("\nお金不足での取引受託を試行...")
    # まず取引を出品
    post_command = PostTradeCommand("apple", 1, 2000, trade_type="global")
    post_result = post_command.execute(alice, game_context)
    
    if post_result.success:
        # お金のないプレイヤーで受託を試行
        poor_player = Player("poor", "貧乏人", Role.ADVENTURER)
        game_context.get_player_manager().add_player(poor_player)
        
        accept_command = AcceptTradeCommand(post_result.trade_id)
        accept_result = accept_command.execute(poor_player, game_context)
        print(f"結果: {'成功' if accept_result.success else '失敗'}")
        if not accept_result.success:
            print(f"  エラーメッセージ: {accept_result.message}")
    
    # 自分の取引を受託しようとする
    print("\n自分の取引を受託しようとする...")
    post_command = PostTradeCommand("apple", 1, 100, trade_type="global")
    post_result = post_command.execute(alice, game_context)
    
    if post_result.success:
        accept_command = AcceptTradeCommand(post_result.trade_id)
        accept_result = accept_command.execute(alice, game_context)
        print(f"結果: {'成功' if accept_result.success else '失敗'}")
        if not accept_result.success:
            print(f"  エラーメッセージ: {accept_result.message}")
    
    print()


def main():
    """メイン関数"""
    print("取引システムデモを開始します...")
    print()
    
    # デモ環境をセットアップ
    game_context, alice, bob, charlie = setup_demo_environment()
    
    # 各デモを実行
    demo_money_trade(game_context, alice, bob)
    demo_item_trade(game_context, alice, bob)
    demo_trade_cancellation(game_context, alice, charlie)
    demo_trade_history(game_context, alice, bob)
    demo_trade_search(game_context, alice, bob, charlie)
    demo_error_cases(game_context, alice, bob)
    
    print("=== デモ完了 ===")
    print("取引システムの動作確認が完了しました。")


if __name__ == "__main__":
    main() 