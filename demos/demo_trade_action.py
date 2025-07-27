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
from game.item.item import Item, StackableItem, UniqueItem
from game.item.consumable_item import ConsumableItem
from game.item.equipment_item import Weapon, Armor, WeaponType, ArmorType, WeaponEffect, ArmorEffect
from game.item.item_effect import ItemEffect


def create_demo_items():
    """デモ用アイテムを作成"""
    items = {}
    
    # スタック可能な消費アイテム
    potion_effect = ItemEffect(hp_change=50)
    items["potion"] = ConsumableItem("potion", "回復薬", "HPを50回復する薬", potion_effect, max_stack=10)
    
    herb_effect = ItemEffect(hp_change=20, mp_change=10)
    items["herb"] = ConsumableItem("herb", "薬草", "HPを20、MPを10回復する薬草", herb_effect, max_stack=20)
    
    # スタック不可能な消費アイテム
    elixir_effect = ItemEffect(hp_change=100, mp_change=50)
    items["elixir"] = ConsumableItem("elixir", "万能薬", "HPを100、MPを50回復する万能薬", elixir_effect, max_stack=1)
    
    # 通常アイテム（スタック可能）
    items["sword"] = StackableItem("sword", "鉄の剣", "基本的な鉄の剣", max_stack=5)
    items["shield"] = StackableItem("shield", "木の盾", "基本的な木の盾", max_stack=3)
    
    # 武器（固有アイテム）
    weapon_effect = WeaponEffect(attack_bonus=15)
    items["steel_sword"] = Weapon("steel_sword", "鋼の剣", "鋼で作られた剣", WeaponType.SWORD, weapon_effect)
    
    weapon_effect2 = WeaponEffect(attack_bonus=25, element_damage=10)
    items["fire_sword"] = Weapon("fire_sword", "炎の剣", "炎の力を宿した剣", WeaponType.SWORD, weapon_effect2)
    
    # 防具（固有アイテム）
    armor_effect = ArmorEffect(defense_bonus=10)
    items["leather_armor"] = Armor("leather_armor", "革の鎧", "革で作られた鎧", ArmorType.CHEST, armor_effect)
    
    armor_effect2 = ArmorEffect(defense_bonus=20, counter_damage=5, counter_chance=0.1)
    items["chain_mail"] = Armor("chain_mail", "チェインメイル", "鎖で作られた鎧", ArmorType.CHEST, armor_effect2)
    
    # 出品不可能なアイテム（クエストアイテムなど）
    class QuestItem(UniqueItem):
        def can_be_traded(self) -> bool:
            return False
        
        def get_status_description(self) -> str:
            return "クエストアイテム"
    
    items["quest_crystal"] = QuestItem("quest_crystal", "クエストの水晶", "重要なクエストアイテム")
    
    return items


def create_demo_players():
    """デモ用プレイヤーを作成"""
    player_manager = PlayerManager()
    
    # プレイヤー1を作成（アリス）
    player1 = Player("player1", "アリス", "spot1")
    player_manager.add_player(player1)
    
    # プレイヤー2を作成（ボブ）
    player2 = Player("player2", "ボブ", "spot1")
    player_manager.add_player(player2)
    
    # プレイヤー3を作成（チャーリー）
    player3 = Player("player3", "チャーリー", "spot2")
    player_manager.add_player(player3)
    
    return player_manager


def setup_player_inventories(player_manager, demo_items):
    """プレイヤーのインベントリを設定"""
    player1 = player_manager.get_player("player1")
    player2 = player_manager.get_player("player2")
    player3 = player_manager.get_player("player3")
    
    # アリス（プレイヤー1）のインベントリ
    player1.add_item(demo_items["potion"])  # スタック可能な消費アイテム
    player1.add_item(demo_items["potion"])  # 2個目
    player1.add_item(demo_items["sword"])   # スタック可能な通常アイテム
    player1.add_item(demo_items["steel_sword"])  # 固有の武器
    player1.add_item(demo_items["quest_crystal"])  # 出品不可能なアイテム
    
    # ボブ（プレイヤー2）のインベントリ
    player2.add_item(demo_items["herb"])      # スタック可能な消費アイテム
    player2.add_item(demo_items["herb"])      # 2個目
    player2.add_item(demo_items["shield"])    # スタック可能な通常アイテム
    player2.add_item(demo_items["fire_sword"])  # 固有の武器
    player2.add_item(demo_items["leather_armor"])  # 固有の防具
    
    # チャーリー（プレイヤー3）のインベントリ
    player3.add_item(demo_items["elixir"])     # スタック不可能な消費アイテム
    player3.add_item(demo_items["chain_mail"])  # 固有の防具
    player3.add_item(demo_items["sword"])      # スタック可能な通常アイテム
    player3.add_item(demo_items["sword"])      # 2個目


def demo_trade_actions():
    """取引行動のデモ"""
    print("=== 取引システム行動実装デモ ===\n")
    
    # システムを初期化
    player_manager = create_demo_players()
    spot_manager = SpotManager()
    trade_manager = TradeManager()
    demo_items = create_demo_items()
    
    # プレイヤーのインベントリを設定
    setup_player_inventories(player_manager, demo_items)
    
    game_context = GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager,
        trade_manager=trade_manager
    )
    
    player1 = player_manager.get_player("player1")
    player2 = player_manager.get_player("player2")
    player3 = player_manager.get_player("player3")
    
    print("0. プレイヤーのインベントリ確認")
    print("-" * 30)
    print(f"{player1.get_name()}のインベントリ:")
    print(player1.inventory.get_inventory_display())
    print()
    
    print(f"{player2.get_name()}のインベントリ:")
    print(player2.inventory.get_inventory_display())
    print()
    
    print(f"{player3.get_name()}のインベントリ:")
    print(player3.inventory.get_inventory_display())
    print()
    
    print("1. 取引出品デモ")
    print("-" * 30)
    
    # お金取引を出品（スタック可能な消費アイテム）
    post_command = PostTradeCommand("potion", 1, 100, trade_type="global")
    result = post_command.execute(player1, game_context)
    print(result.to_feedback_message(player1.get_name()))
    print()
    
    # アイテム取引を出品（スタック可能な通常アイテム）
    post_command2 = PostTradeCommand("shield", 1, 0, "sword", 1, trade_type="global")
    result2 = post_command2.execute(player2, game_context)
    print(result2.to_feedback_message(player2.get_name()))
    print()
    
    # 直接取引を出品（固有の武器）
    post_command3 = PostTradeCommand("steel_sword", 1, 50, trade_type="direct", target_player_id="player3")
    result3 = post_command3.execute(player1, game_context)
    print(result3.to_feedback_message(player1.get_name()))
    print()
    
    # 出品不可能なアイテムの出品を試行
    post_command_invalid = PostTradeCommand("quest_crystal", 1, 1000, trade_type="global")
    result_invalid = post_command_invalid.execute(player1, game_context)
    print(result_invalid.to_feedback_message(player1.get_name()))
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
    
    # 新しい取引を出品（固有の防具）
    post_command4 = PostTradeCommand("leather_armor", 1, 200, trade_type="global")
    result4 = post_command4.execute(player2, game_context)
    print(result4.to_feedback_message(player2.get_name()))
    print()
    
    # 取引をキャンセル
    if result4.success:
        cancel_command = CancelTradeCommand(result4.trade_id)
        cancel_result = cancel_command.execute(player2, game_context)
        print(cancel_result.to_feedback_message(player2.get_name()))
        print()
    
    print("6. フィルタリング機能デモ")
    print("-" * 30)
    
    # 新しい取引を複数出品
    post_command5 = PostTradeCommand("sword", 2, 150, trade_type="global")
    result5 = post_command5.execute(player3, game_context)
    
    post_command6 = PostTradeCommand("herb", 5, 80, trade_type="global")
    result6 = post_command6.execute(player1, game_context)
    
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