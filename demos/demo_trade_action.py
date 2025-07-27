#!/usr/bin/env python3
"""
取引システム行動実装のデモ
"""

from game.trade.trade_manager import TradeManager
from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.core.game_context import GameContext
from game.action.actions.trade_action import (
    PostTradeStrategy, AcceptTradeStrategy, CancelTradeStrategy,
    GetMyTradesStrategy, GetAvailableTradesStrategy,
    PostTradeCommand, AcceptTradeCommand, CancelTradeCommand,
    GetMyTradesCommand, GetAvailableTradesCommand
)
from game.player.player import Player


def create_demo_players():
    """デモ用プレイヤーを作成"""
    player_manager = PlayerManager()
    
    # プレイヤー1を作成
    player1 = Player("player1", "アリス", "spot1")
    player_manager.add_player(player1)
    
    # プレイヤー2を作成
    player2 = Player("player2", "ボブ", "spot1")
    player_manager.add_player(player2)
    
    # プレイヤー3を作成
    player3 = Player("player3", "チャーリー", "spot2")
    player_manager.add_player(player3)
    
    return player_manager


def demo_trade_actions():
    """取引行動のデモ"""
    print("=== 取引システム行動実装デモ ===\n")
    
    # システムを初期化
    player_manager = create_demo_players()
    spot_manager = SpotManager()
    trade_manager = TradeManager()
    
    game_context = GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager,
        trade_manager=trade_manager
    )
    
    player1 = player_manager.get_player("player1")
    player2 = player_manager.get_player("player2")
    player3 = player_manager.get_player("player3")
    
    print("1. 取引出品デモ")
    print("-" * 30)
    
    # お金取引を出品
    post_command = PostTradeCommand("sword", 1, 100, trade_type="global")
    result = post_command.execute(player1, game_context)
    print(result.to_feedback_message(player1.get_name()))
    print()
    
    # アイテム取引を出品
    post_command2 = PostTradeCommand("shield", 1, 0, "sword", 1, trade_type="global")
    result2 = post_command2.execute(player2, game_context)
    print(result2.to_feedback_message(player2.get_name()))
    print()
    
    # 直接取引を出品
    post_command3 = PostTradeCommand("potion", 5, 50, trade_type="direct", target_player_id="player3")
    result3 = post_command3.execute(player1, game_context)
    print(result3.to_feedback_message(player1.get_name()))
    print()
    
    print("2. 受託可能取引取得デモ")
    print("-" * 30)
    
    # プレイヤー1が受託可能な取引を取得
    get_available_command = GetAvailableTradesCommand()
    available_result = get_available_command.execute(player1, game_context)
    print(available_result.to_feedback_message(player1.get_name()))
    print()
    
    # プレイヤー3が受託可能な取引を取得（直接取引を含む）
    available_result3 = get_available_command.execute(player3, game_context)
    print(available_result3.to_feedback_message(player3.get_name()))
    print()
    
    print("3. 取引受託デモ")
    print("-" * 30)
    
    # プレイヤー2がプレイヤー1の取引を受託
    if available_result.trades:
        trade_id = available_result.trades[0].trade_id
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(player2, game_context)
        print(accept_result.to_feedback_message(player2.get_name()))
        print()
    
    print("4. 自分の取引取得デモ")
    print("-" * 30)
    
    # プレイヤー1の取引を取得（アクティブのみ）
    get_my_trades_command = GetMyTradesCommand(include_history=False)
    my_trades_result = get_my_trades_command.execute(player1, game_context)
    print(my_trades_result.to_feedback_message(player1.get_name()))
    print()
    
    # プレイヤー1の取引を取得（履歴含む）
    get_my_trades_command2 = GetMyTradesCommand(include_history=True)
    my_trades_result2 = get_my_trades_command2.execute(player1, game_context)
    print(my_trades_result2.to_feedback_message(player1.get_name()))
    print()
    
    print("5. 取引キャンセルデモ")
    print("-" * 30)
    
    # 新しい取引を出品
    post_command4 = PostTradeCommand("armor", 1, 200, trade_type="global")
    result4 = post_command4.execute(player1, game_context)
    print(result4.to_feedback_message(player1.get_name()))
    print()
    
    # 取引をキャンセル
    if result4.success:
        cancel_command = CancelTradeCommand(result4.trade_id)
        cancel_result = cancel_command.execute(player1, game_context)
        print(cancel_result.to_feedback_message(player1.get_name()))
        print()
    
    print("6. フィルタリング機能デモ")
    print("-" * 30)
    
    # 新しい取引を複数出品
    post_command5 = PostTradeCommand("sword", 2, 150, trade_type="global")
    result5 = post_command5.execute(player2, game_context)
    
    post_command6 = PostTradeCommand("shield", 1, 80, trade_type="global")
    result6 = post_command6.execute(player3, game_context)
    
    # 価格フィルタで検索
    filters = {"max_price": 100}
    get_filtered_command = GetAvailableTradesCommand(filters)
    filtered_result = get_filtered_command.execute(player1, game_context)
    print(f"価格100以下の取引:")
    print(filtered_result.to_feedback_message(player1.get_name()))
    print()
    
    # アイテムフィルタで検索
    filters2 = {"offered_item_id": "sword"}
    get_filtered_command2 = GetAvailableTradesCommand(filters2)
    filtered_result2 = get_filtered_command2.execute(player1, game_context)
    print(f"swordの取引:")
    print(filtered_result2.to_feedback_message(player1.get_name()))
    print()
    
    print("7. エラーハンドリングデモ")
    print("-" * 30)
    
    # 存在しない取引を受託
    accept_invalid_command = AcceptTradeCommand("invalid_trade_id")
    accept_invalid_result = accept_invalid_command.execute(player1, game_context)
    print(accept_invalid_result.to_feedback_message(player1.get_name()))
    print()
    
    # 自分の取引を受託（エラー）
    if available_result.trades:
        my_trade_id = available_result.trades[0].trade_id
        accept_my_trade_command = AcceptTradeCommand(my_trade_id)
        accept_my_trade_result = accept_my_trade_command.execute(player1, game_context)
        print(accept_my_trade_result.to_feedback_message(player1.get_name()))
        print()
    
    print("8. 戦略クラスの引数確認デモ")
    print("-" * 30)
    
    # 各戦略の引数を確認
    strategies = [
        PostTradeStrategy(),
        AcceptTradeStrategy(),
        CancelTradeStrategy(),
        GetMyTradesStrategy(),
        GetAvailableTradesStrategy()
    ]
    
    for strategy in strategies:
        print(f"{strategy.get_name()}:")
        arguments = strategy.get_required_arguments(player1, game_context)
        for arg in arguments:
            print(f"  - {arg.name}: {arg.description}")
        print()
    
    print("=== デモ完了 ===")


if __name__ == "__main__":
    demo_trade_actions() 