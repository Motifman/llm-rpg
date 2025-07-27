import pytest
from game.action.actions.trade_action import (
    PostTradeStrategy, AcceptTradeStrategy, CancelTradeStrategy,
    GetMyTradesStrategy, GetAvailableTradesStrategy,
    PostTradeCommand, AcceptTradeCommand, CancelTradeCommand,
    GetMyTradesCommand, GetAvailableTradesCommand,
    PostTradeResult, AcceptTradeResult, CancelTradeResult,
    GetMyTradesResult, GetAvailableTradesResult
)
from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.core.game_context import GameContext
from game.trade.trade_manager import TradeManager
from game.trade.trade_data import TradeOffer
from game.enums import TradeType, TradeStatus, Role, WeaponType, ArmorType, Element, Race, StatusEffectType, DamageType
from game.item.item import Item, StackableItem
from game.item.consumable_item import ConsumableItem
from game.item.item_effect import ItemEffect
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect


class TestTradeActionWithRealItems:
    """実際のアイテムを使った取引アクションテスト"""
    
    def setup_method(self):
        """テスト用のプレイヤーとアイテムをセットアップ"""
        # プレイヤーマネージャーを作成
        self.player_manager = PlayerManager()
        
        # テスト用プレイヤーを作成
        self.seller = Player("seller1", "売り手", Role.ADVENTURER)
        self.buyer = Player("buyer1", "買い手", Role.ADVENTURER)
        
        # プレイヤーをマネージャーに登録
        self.player_manager.add_player(self.seller)
        self.player_manager.add_player(self.buyer)
        
        # 初期アイテムを追加
        self._setup_test_items()
        
        # ゲームコンテキストを作成
        self.trade_manager = TradeManager()
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=None,
            trade_manager=self.trade_manager
        )
    
    def _setup_test_items(self):
        """テスト用アイテムをセットアップ"""
        # スタック可能アイテムを作成
        self.apple = StackableItem("apple", "りんご", "甘いりんご", max_stack=10)
        self.orange = StackableItem("orange", "オレンジ", "酸っぱいオレンジ", max_stack=10)
        
        # 消費アイテムを作成
        self.potion = ConsumableItem("potion", "ポーション", "HPを回復する", 
                                   ItemEffect(hp_change=50), max_stack=5)
        self.elixir = ConsumableItem("elixir", "エリクサー", "MPを回復する", 
                                   ItemEffect(mp_change=30), max_stack=3)
        
        # 売り手にアイテムを追加
        for _ in range(5):
            self.seller.add_item(self.apple)
        for _ in range(3):
            self.seller.add_item(self.potion)
        
        # 買い手にアイテムとお金を追加
        for _ in range(3):
            self.buyer.add_item(self.orange)
        for _ in range(2):
            self.buyer.add_item(self.elixir)
        self.buyer.status.add_money(1000)
    
    def test_post_trade_with_real_items(self):
        """実際のアイテムを使った取引出品テスト"""
        # 売り手の初期状態を記録
        initial_apple_count = self.seller.get_inventory_item_count("apple")
        initial_potion_count = self.seller.get_inventory_item_count("potion")
        
        # りんごを100ゴールドで出品
        command = PostTradeCommand("apple", 2, 100, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert result.success is True
        assert result.trade_id is not None
        assert "apple x2 ⇄ 100ゴールド" in result.trade_details
        
        # 売り手のアイテムは出品時に減少しない（受託時にやり取りされる）
        assert self.seller.get_inventory_item_count("apple") == initial_apple_count
        
        # 取引が正しく登録されていることを確認
        trade = self.trade_manager.get_trade(result.trade_id)
        assert trade is not None
        assert trade.offered_item_id == "apple"
        assert trade.offered_item_count == 2
        assert trade.requested_money == 100
        assert trade.seller_id == "seller1"
    
    def test_accept_trade_with_real_items(self):
        """実際のアイテムを使った取引受託テスト"""
        # 売り手がりんごを100ゴールドで出品
        post_command = PostTradeCommand("apple", 2, 100, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 買い手の初期状態を記録
        initial_money = self.buyer.status.get_money()
        initial_apple_count = self.buyer.get_inventory_item_count("apple")
        
        # 買い手が取引を受託
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert accept_result.success is True
        assert accept_result.trade_id == trade_id
        
        # 買い手の状態変化を確認
        assert self.buyer.status.get_money() == initial_money - 100
        assert self.buyer.get_inventory_item_count("apple") == initial_apple_count + 2
        
        # 売り手の状態変化を確認
        assert self.seller.status.get_money() == 100  # 売り手はお金を獲得
        
        # 取引が履歴に移動していることを確認
        assert self.trade_manager.get_trade(trade_id) is None
        history = self.trade_manager.get_trade_history()
        assert len(history) == 1
        assert history[0].trade_id == trade_id
        assert history[0].status == TradeStatus.COMPLETED
    
    def test_item_to_item_trade(self):
        """アイテム同士の取引テスト"""
        # 売り手がりんごをオレンジと交換で出品
        post_command = PostTradeCommand("apple", 2, 0, "orange", 1, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 買い手の初期状態を記録
        initial_apple_count = self.buyer.get_inventory_item_count("apple")
        initial_orange_count = self.buyer.get_inventory_item_count("orange")
        
        # 買い手が取引を受託
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert accept_result.success is True
        
        # 買い手の状態変化を確認
        assert self.buyer.get_inventory_item_count("apple") == initial_apple_count + 2
        assert self.buyer.get_inventory_item_count("orange") == initial_orange_count - 1
        
        # 売り手の状態変化を確認
        assert self.seller.get_inventory_item_count("orange") == 1  # 売り手はオレンジを獲得
    
    def test_cancel_trade_with_real_items(self):
        """実際のアイテムを使った取引キャンセルテスト"""
        # 売り手がりんごを100ゴールドで出品
        post_command = PostTradeCommand("apple", 2, 100, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 売り手の初期状態を記録
        initial_apple_count = self.seller.get_inventory_item_count("apple")
        
        # 売り手が取引をキャンセル
        cancel_command = CancelTradeCommand(trade_id)
        cancel_result = cancel_command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert cancel_result.success is True
        assert cancel_result.trade_id == trade_id
        
        # 売り手のアイテムが戻っていることを確認
        assert self.seller.get_inventory_item_count("apple") == initial_apple_count + 2
        
        # 取引が履歴に移動していることを確認
        assert self.trade_manager.get_trade(trade_id) is None
        history = self.trade_manager.get_trade_history()
        assert len(history) == 1
        assert history[0].trade_id == trade_id
        assert history[0].status == TradeStatus.CANCELLED
    
    def test_insufficient_items_for_trade(self):
        """アイテム不足での取引出品失敗テスト"""
        # 売り手が持っていないアイテムで取引を試行
        command = PostTradeCommand("nonexistent_item", 1, 100, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert result.success is False
        assert "アイテム nonexistent_item を所持していません" in result.message
    
    def test_insufficient_money_for_trade(self):
        """お金不足での取引受託失敗テスト"""
        # 売り手がりんごを1000ゴールドで出品
        post_command = PostTradeCommand("apple", 1, 1000, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # お金のないプレイヤーを作成
        poor_player = Player("poor1", "貧乏人", Role.ADVENTURER)
        self.player_manager.add_player(poor_player)
        
        # 貧乏人が取引を受託しようとする
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(poor_player, self.game_context)
        
        # 結果を検証
        assert accept_result.success is False
        assert "お金が不足しています" in accept_result.message
    
    def test_get_my_trades_with_real_trades(self):
        """実際の取引を使った自分の取引取得テスト"""
        # 売り手が複数の取引を出品
        post_command1 = PostTradeCommand("apple", 1, 50, trade_type="global")
        post_command2 = PostTradeCommand("potion", 1, 200, trade_type="global")
        
        result1 = post_command1.execute(self.seller, self.game_context)
        result2 = post_command2.execute(self.seller, self.game_context)
        
        # 自分の取引を取得
        get_command = GetMyTradesCommand(include_history=False)
        get_result = get_command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert get_result.success is True
        assert len(get_result.trades) == 2
        assert get_result.include_history is False
    
    def test_get_available_trades_with_real_trades(self):
        """実際の取引を使った受託可能取引取得テスト"""
        # 売り手がりんごを100ゴールドで出品
        post_command = PostTradeCommand("apple", 2, 100, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        
        # 買い手が受託可能な取引を取得
        get_command = GetAvailableTradesCommand()
        get_result = get_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert get_result.success is True
        assert len(get_result.trades) == 1
        assert get_result.trades[0].trade_id == post_result.trade_id
    
    def test_trade_with_filters(self):
        """フィルタを使った取引検索テスト"""
        # 複数の取引を出品
        post_command1 = PostTradeCommand("apple", 1, 50, trade_type="global")
        post_command2 = PostTradeCommand("potion", 1, 200, trade_type="global")
        
        post_command1.execute(self.seller, self.game_context)
        post_command2.execute(self.seller, self.game_context)
        
        # 価格フィルタで検索
        filters = {"max_price": 100}
        get_command = GetAvailableTradesCommand(filters)
        get_result = get_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert get_result.success is True
        assert len(get_result.trades) == 1  # 50ゴールドの取引のみ
        assert get_result.trades[0].requested_money == 50
    
    def test_trade_completion_verification(self):
        """取引完了時の状態検証テスト"""
        # 売り手の初期状態を記録
        seller_initial_apple = self.seller.get_inventory_item_count("apple")
        seller_initial_money = self.seller.status.get_money()
        
        # 買い手の初期状態を記録
        buyer_initial_apple = self.buyer.get_inventory_item_count("apple")
        buyer_initial_money = self.buyer.status.get_money()
        
        # 取引を実行
        post_command = PostTradeCommand("apple", 2, 150, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 取引完了後の状態を検証
        if not accept_result.success:
            print(f"取引受託失敗: {accept_result.message}")
        assert accept_result.success is True
        
        # 売り手の状態変化
        assert self.seller.get_inventory_item_count("apple") == seller_initial_apple - 2
        assert self.seller.status.get_money() == seller_initial_money + 150
        
        # 買い手の状態変化
        assert self.buyer.get_inventory_item_count("apple") == buyer_initial_apple + 2
        assert self.buyer.status.get_money() == buyer_initial_money - 150
        
        # 取引履歴の確認
        history = self.trade_manager.get_trade_history()
        assert len(history) == 1
        completed_trade = history[0]
        assert completed_trade.status == TradeStatus.COMPLETED
        assert completed_trade.trade_id == trade_id


class TestTradeActionStrategies:
    """取引アクション戦略のテスト"""
    
    def setup_method(self):
        self.player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
        self.game_context = GameContext(
            player_manager=PlayerManager(),
            spot_manager=None,
            trade_manager=TradeManager()
        )
    
    def test_post_trade_strategy_arguments(self):
        """取引出品戦略の引数テスト"""
        strategy = PostTradeStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 7
        arg_names = [arg.name for arg in arguments]
        expected_names = [
            "offered_item_id", "offered_item_count", "requested_money",
            "requested_item_id", "requested_item_count", "trade_type",
            "target_player_id"
        ]
        for name in expected_names:
            assert name in arg_names
    
    def test_post_trade_strategy_can_execute(self):
        """取引出品戦略の実行可能性テスト"""
        strategy = PostTradeStrategy()
        
        # TradeManagerが利用可能な場合
        assert strategy.can_execute(self.player, self.game_context) is True
        
        # TradeManagerが利用できない場合
        game_context_no_trade = GameContext(
            player_manager=PlayerManager(),
            spot_manager=None,
            trade_manager=None
        )
        assert strategy.can_execute(self.player, game_context_no_trade) is False
    
    def test_accept_trade_strategy_arguments(self):
        """取引受託戦略の引数テスト"""
        strategy = AcceptTradeStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 1
        assert arguments[0].name == "trade_id"
    
    def test_cancel_trade_strategy_arguments(self):
        """取引キャンセル戦略の引数テスト"""
        strategy = CancelTradeStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 1
        assert arguments[0].name == "trade_id"
    
    def test_get_my_trades_strategy_arguments(self):
        """自分の取引取得戦略の引数テスト"""
        strategy = GetMyTradesStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 1
        assert arguments[0].name == "include_history"
        assert arguments[0].candidates == ["True", "False"]
    
    def test_get_available_trades_strategy_arguments(self):
        """受託可能取引取得戦略の引数テスト"""
        strategy = GetAvailableTradesStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 6
        arg_names = [arg.name for arg in arguments]
        expected_names = [
            "offered_item_id", "requested_item_id", "max_price",
            "min_price", "trade_type", "seller_id"
        ]
        for name in expected_names:
            assert name in arg_names


class TestTradeActionResultMessages:
    """取引アクション結果メッセージのテスト"""
    
    def test_post_trade_result_success_message(self):
        """取引出品成功メッセージのテスト"""
        result = PostTradeResult(True, "取引を出品しました", "trade123", "りんご x2 ⇄ 100ゴールド")
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー は取引を出品しました" in message
        assert "取引ID: trade123" in message
        assert "取引詳細: りんご x2 ⇄ 100ゴールド" in message
    
    def test_post_trade_result_failure_message(self):
        """取引出品失敗メッセージのテスト"""
        result = PostTradeResult(False, "アイテムが不足しています", None, "")
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー は取引を出品できませんでした" in message
        assert "理由: アイテムが不足しています" in message
    
    def test_accept_trade_result_success_message(self):
        """取引受託成功メッセージのテスト"""
        result = AcceptTradeResult(True, "取引を受託しました", "trade123", "りんご x2 ⇄ 100ゴールド")
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー は取引を受託しました" in message
        assert "取引ID: trade123" in message
        assert "取引詳細: りんご x2 ⇄ 100ゴールド" in message
    
    def test_cancel_trade_result_success_message(self):
        """取引キャンセル成功メッセージのテスト"""
        result = CancelTradeResult(True, "取引をキャンセルしました", "trade123", "りんご x2 ⇄ 100ゴールド")
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー は取引をキャンセルしました" in message
        assert "取引ID: trade123" in message
        assert "取引詳細: りんご x2 ⇄ 100ゴールド" in message 


class TestTradeActionWithUniqueItems:
    """UniqueItem（WeaponやArmor）を使った取引アクションテスト"""
    
    def setup_method(self):
        """テスト用のプレイヤーとUniqueItemをセットアップ"""
        # プレイヤーマネージャーを作成
        self.player_manager = PlayerManager()
        
        # テスト用プレイヤーを作成
        self.seller = Player("seller1", "売り手", Role.ADVENTURER)
        self.buyer = Player("buyer1", "買い手", Role.ADVENTURER)
        
        # プレイヤーをマネージャーに登録
        self.player_manager.add_player(self.seller)
        self.player_manager.add_player(self.buyer)
        
        # 初期UniqueItemを追加
        self._setup_test_unique_items()
        
        # ゲームコンテキストを作成
        self.trade_manager = TradeManager()
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=None,
            trade_manager=self.trade_manager
        )
    
    def _setup_test_unique_items(self):
        """テスト用UniqueItemをセットアップ"""
        # 武器を作成
        weapon_effect = WeaponEffect(
            attack_bonus=15,
            critical_rate_bonus=0.1,
            element=Element.FIRE,
            element_damage=10,
            effective_races={Race.DRAGON},
            race_damage_multiplier=1.5
        )
        self.fire_sword = Weapon(
            "fire_sword", "炎の剣", "火属性の強力な剣", 
            WeaponType.SWORD, weapon_effect
        )
        
        # 防具を作成
        armor_effect = ArmorEffect(
            defense_bonus=12,
            speed_bonus=3,
            evasion_bonus=0.05,
            status_resistance={StatusEffectType.POISON: 0.3},
            damage_reduction={Element.FIRE: 0.2}
        )
        self.leather_armor = Armor(
            "leather_armor", "革の鎧", "軽量で動きやすい鎧",
            ArmorType.CHEST, armor_effect
        )
        
        # 別の武器を作成
        ice_weapon_effect = WeaponEffect(
            attack_bonus=12,
            element=Element.ICE,
            element_damage=8
        )
        self.ice_dagger = Weapon(
            "ice_dagger", "氷の短剣", "氷属性の短剣",
            WeaponType.SWORD, ice_weapon_effect
        )
        
        # 売り手にUniqueItemを追加
        self.seller.add_item(self.fire_sword)
        self.seller.add_item(self.leather_armor)
        
        # 買い手にUniqueItemとお金を追加
        self.buyer.add_item(self.ice_dagger)
        self.buyer.status.add_money(2000)
    
    def test_post_trade_with_unique_weapon(self):
        """UniqueItemの武器を使った取引出品テスト"""
        # 売り手の初期状態を記録
        initial_weapon_count = self.seller.get_inventory_item_count("fire_sword")
        
        # 炎の剣を500ゴールドで出品
        command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert result.success is True
        assert result.trade_id is not None
        assert "fire_sword x1 ⇄ 500ゴールド" in result.trade_details
        
        # 売り手のアイテムは出品時に減少しない（受託時にやり取りされる）
        assert self.seller.get_inventory_item_count("fire_sword") == initial_weapon_count
        
        # 取引が正しく登録されていることを確認
        trade = self.trade_manager.get_trade(result.trade_id)
        assert trade is not None
        assert trade.offered_item_id == "fire_sword"
        assert trade.offered_item_count == 1
        assert trade.requested_money == 500
        assert trade.seller_id == "seller1"
    
    def test_post_trade_with_unique_armor(self):
        """UniqueItemの防具を使った取引出品テスト"""
        # 革の鎧を300ゴールドで出品
        command = PostTradeCommand("leather_armor", 1, 300, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert result.success is True
        assert result.trade_id is not None
        assert "leather_armor x1 ⇄ 300ゴールド" in result.trade_details
        
        # 取引が正しく登録されていることを確認
        trade = self.trade_manager.get_trade(result.trade_id)
        assert trade is not None
        assert trade.offered_item_id == "leather_armor"
        assert trade.offered_item_count == 1
        assert trade.requested_money == 300
    
    def test_accept_trade_with_unique_weapon(self):
        """UniqueItemの武器を使った取引受託テスト"""
        # 売り手が炎の剣を500ゴールドで出品
        post_command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 買い手の初期状態を記録
        initial_money = self.buyer.status.get_money()
        initial_weapon_count = self.buyer.get_inventory_item_count("fire_sword")
        
        # 買い手が取引を受託
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert accept_result.success is True
        assert accept_result.trade_id == trade_id
        
        # 買い手の状態変化を確認
        assert self.buyer.status.get_money() == initial_money - 500
        assert self.buyer.get_inventory_item_count("fire_sword") == initial_weapon_count + 1
        
        # 売り手の状態変化を確認
        assert self.seller.status.get_money() == 500  # 売り手はお金を獲得
        assert self.seller.get_inventory_item_count("fire_sword") == 0  # 売り手は武器を失う
        
        # 取引が履歴に移動していることを確認
        assert self.trade_manager.get_trade(trade_id) is None
        history = self.trade_manager.get_trade_history()
        assert len(history) == 1
        assert history[0].trade_id == trade_id
        assert history[0].status == TradeStatus.COMPLETED
    
    def test_accept_trade_with_unique_armor(self):
        """UniqueItemの防具を使った取引受託テスト"""
        # 売り手が革の鎧を300ゴールドで出品
        post_command = PostTradeCommand("leather_armor", 1, 300, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 買い手の初期状態を記録
        initial_money = self.buyer.status.get_money()
        initial_armor_count = self.buyer.get_inventory_item_count("leather_armor")
        
        # 買い手が取引を受託
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert accept_result.success is True
        
        # 買い手の状態変化を確認
        assert self.buyer.status.get_money() == initial_money - 300
        assert self.buyer.get_inventory_item_count("leather_armor") == initial_armor_count + 1
        
        # 売り手の状態変化を確認
        assert self.seller.status.get_money() == 300
        assert self.seller.get_inventory_item_count("leather_armor") == 0
    
    def test_unique_item_to_unique_item_trade(self):
        """UniqueItem同士の取引テスト"""
        # 売り手が炎の剣を氷の短剣と交換で出品
        post_command = PostTradeCommand("fire_sword", 1, 0, "ice_dagger", 1, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 買い手の初期状態を記録
        initial_fire_sword_count = self.buyer.get_inventory_item_count("fire_sword")
        initial_ice_dagger_count = self.buyer.get_inventory_item_count("ice_dagger")
        
        # 買い手が取引を受託
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert accept_result.success is True
        
        # 買い手の状態変化を確認
        assert self.buyer.get_inventory_item_count("fire_sword") == initial_fire_sword_count + 1
        assert self.buyer.get_inventory_item_count("ice_dagger") == initial_ice_dagger_count - 1
        
        # 売り手の状態変化を確認
        assert self.seller.get_inventory_item_count("ice_dagger") == 1  # 売り手は氷の短剣を獲得
        assert self.seller.get_inventory_item_count("fire_sword") == 0  # 売り手は炎の剣を失う
    
    def test_cancel_trade_with_unique_item(self):
        """UniqueItemを使った取引キャンセルテスト"""
        # 売り手が炎の剣を500ゴールドで出品
        post_command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 売り手の初期状態を記録
        initial_weapon_count = self.seller.get_inventory_item_count("fire_sword")
        
        # 売り手が取引をキャンセル
        cancel_command = CancelTradeCommand(trade_id)
        cancel_result = cancel_command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert cancel_result.success is True
        assert cancel_result.trade_id == trade_id
        
        # 売り手のアイテムが戻っていることを確認（キャンセル時はアイテムは既にインベントリにあるため変化なし）
        assert self.seller.get_inventory_item_count("fire_sword") == initial_weapon_count
        
        # 取引が履歴に移動していることを確認
        assert self.trade_manager.get_trade(trade_id) is None
        history = self.trade_manager.get_trade_history()
        assert len(history) == 1
        assert history[0].trade_id == trade_id
        assert history[0].status == TradeStatus.CANCELLED
    
    def test_insufficient_unique_items_for_trade(self):
        """UniqueItem不足での取引出品失敗テスト"""
        # 売り手が持っていないUniqueItemで取引を試行
        command = PostTradeCommand("nonexistent_weapon", 1, 100, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証
        assert result.success is False
        assert "アイテム nonexistent_weapon を所持していません" in result.message
    
    def test_unique_item_trade_with_equipment(self):
        """装備中のUniqueItemの取引テスト"""
        # 売り手が炎の剣を装備
        self.seller.equip_item("fire_sword")
        
        # 装備中のアイテムで取引を試行（失敗するはず）
        command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証（装備中のアイテムは取引できない）
        assert result.success is False
        assert "アイテム fire_sword を所持していません" in result.message
    
    def test_unique_item_trade_completion_verification(self):
        """UniqueItem取引完了時の状態検証テスト"""
        # 売り手の初期状態を記録
        seller_initial_weapon = self.seller.get_inventory_item_count("fire_sword")
        seller_initial_money = self.seller.status.get_money()
        
        # 買い手の初期状態を記録
        buyer_initial_weapon = self.buyer.get_inventory_item_count("fire_sword")
        buyer_initial_money = self.buyer.status.get_money()
        
        # 取引を実行
        post_command = PostTradeCommand("fire_sword", 1, 600, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 取引完了後の状態を検証
        if not accept_result.success:
            print(f"取引受託失敗: {accept_result.message}")
        assert accept_result.success is True
        
        # 売り手の状態変化
        assert self.seller.get_inventory_item_count("fire_sword") == seller_initial_weapon - 1
        assert self.seller.status.get_money() == seller_initial_money + 600
        
        # 買い手の状態変化
        assert self.buyer.get_inventory_item_count("fire_sword") == buyer_initial_weapon + 1
        assert self.buyer.status.get_money() == buyer_initial_money - 600
        
        # 取引履歴の確認
        history = self.trade_manager.get_trade_history()
        assert len(history) == 1
        completed_trade = history[0]
        assert completed_trade.status == TradeStatus.COMPLETED
        assert completed_trade.trade_id == trade_id
    
    def test_unique_item_trade_with_filters(self):
        """フィルタを使ったUniqueItem取引検索テスト"""
        # 複数のUniqueItem取引を出品
        post_command1 = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        post_command2 = PostTradeCommand("leather_armor", 1, 300, trade_type="global")
        
        post_command1.execute(self.seller, self.game_context)
        post_command2.execute(self.seller, self.game_context)
        
        # 価格フィルタで検索
        filters = {"max_price": 400}
        get_command = GetAvailableTradesCommand(filters)
        get_result = get_command.execute(self.buyer, self.game_context)
        
        # 結果を検証
        assert get_result.success is True
        assert len(get_result.trades) == 1  # 300ゴールドの取引のみ
        assert get_result.trades[0].requested_money == 300
        assert get_result.trades[0].offered_item_id == "leather_armor" 


class TestTradeActionWithNonTradeableItems:
    """取引不可能アイテムの取引アクションテスト"""
    
    def setup_method(self):
        """テスト用のプレイヤーとアイテムをセットアップ"""
        # プレイヤーマネージャーを作成
        self.player_manager = PlayerManager()
        
        # テスト用プレイヤーを作成
        self.seller = Player("seller1", "売り手", Role.ADVENTURER)
        self.buyer = Player("buyer1", "買い手", Role.ADVENTURER)
        
        # プレイヤーをマネージャーに登録
        self.player_manager.add_player(self.seller)
        self.player_manager.add_player(self.buyer)
        
        # 初期アイテムを追加
        self._setup_test_items()
        
        # ゲームコンテキストを作成
        self.trade_manager = TradeManager()
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=None,
            trade_manager=self.trade_manager
        )
    
    def _setup_test_items(self):
        """テスト用アイテムをセットアップ"""
        # 取引不可能なアイテムを作成
        class QuestItem(Item):
            def can_be_traded(self) -> bool:
                return False
        
        class BoundItem(Item):
            def can_be_traded(self) -> bool:
                return False
        
        # 取引可能なアイテムを作成（比較用）
        self.tradeable_item = StackableItem("tradeable_item", "取引可能アイテム", "取引可能なアイテム", max_stack=10)
        
        # 取引不可能なアイテムを作成
        self.quest_item = QuestItem("quest_item", "クエストアイテム", "重要なクエストアイテム")
        self.bound_item = BoundItem("bound_item", "バインドアイテム", "プレイヤーにバインドされたアイテム")
        
        # 売り手にアイテムを追加
        self.seller.add_item(self.tradeable_item)
        self.seller.add_item(self.quest_item)
        self.seller.add_item(self.bound_item)
        
        # 買い手にお金を追加
        self.buyer.status.add_money(1000)
    
    def test_post_trade_with_non_tradeable_quest_item(self):
        """クエストアイテムの取引出品失敗テスト"""
        # クエストアイテムで取引を試行
        command = PostTradeCommand("quest_item", 1, 1000, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証（取引不可能なアイテムは出品できない）
        assert result.success is False
        assert "取引不可能なアイテムです" in result.message
    
    def test_post_trade_with_non_tradeable_bound_item(self):
        """バインドアイテムの取引出品失敗テスト"""
        # バインドアイテムで取引を試行
        command = PostTradeCommand("bound_item", 1, 500, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証（取引不可能なアイテムは出品できない）
        assert result.success is False
        assert "取引不可能なアイテムです" in result.message
    
    def test_post_trade_with_tradeable_item_success(self):
        """取引可能アイテムの取引出品成功テスト（比較用）"""
        # 取引可能アイテムで取引を試行
        command = PostTradeCommand("tradeable_item", 1, 100, trade_type="global")
        result = command.execute(self.seller, self.game_context)
        
        # 結果を検証（取引可能なアイテムは出品できる）
        if not result.success:
            print(f"取引失敗: {result.message}")
        assert result.success is True
        assert result.trade_id is not None
        assert "tradeable_item x1 ⇄ 100ゴールド" in result.trade_details
    
    def test_non_tradeable_item_in_inventory_display(self):
        """取引不可能アイテムがインベントリに正しく表示されるテスト"""
        # 売り手のインベントリを確認
        inventory_display = self.seller.inventory.get_inventory_display()
        
        # 取引不可能アイテムがインベントリに存在することを確認
        assert "quest_item" in inventory_display
        assert "bound_item" in inventory_display
        assert "tradeable_item" in inventory_display
    
    def test_non_tradeable_item_has_item_check(self):
        """取引不可能アイテムの所持チェックテスト"""
        # 売り手が取引不可能アイテムを所持していることを確認
        assert self.seller.has_item("quest_item") is True
        assert self.seller.has_item("bound_item") is True
        assert self.seller.get_inventory_item_count("quest_item") == 1
        assert self.seller.get_inventory_item_count("bound_item") == 1 