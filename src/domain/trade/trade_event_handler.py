from abc import ABC, abstractmethod
from typing import List
from src.domain.trade.trade_events import (
    TradeCreatedEvent,
    TradeExecutedEvent,
    TradeCancelledEvent,
    DirectTradeOfferedEvent
)
from src.domain.player.player_repository import PlayerRepository
from src.domain.player.message import Message
from datetime import datetime


class TradeEventHandler(ABC):
    """取引イベントハンドラーの基底クラス"""
    
    @abstractmethod
    def handle_trade_created(self, event: TradeCreatedEvent):
        """取引作成イベントを処理"""
        pass
    
    @abstractmethod
    def handle_trade_executed(self, event: TradeExecutedEvent):
        """取引成立イベントを処理"""
        pass
    
    @abstractmethod
    def handle_trade_cancelled(self, event: TradeCancelledEvent):
        """取引キャンセルイベントを処理"""
        pass
    
    @abstractmethod
    def handle_direct_trade_offered(self, event: DirectTradeOfferedEvent):
        """直接取引提案イベントを処理"""
        pass


class NotificationTradeEventHandler(TradeEventHandler):
    """通知機能付き取引イベントハンドラー"""
    
    def __init__(self, player_repository: PlayerRepository):
        self._player_repository = player_repository
    
    def handle_trade_created(self, event: TradeCreatedEvent):
        """取引作成時の通知処理"""
        # グローバル取引の場合は全プレイヤーに通知
        if event.trade_type.value == "global":
            self._notify_global_trade_created(event)
        # 直接取引の場合は対象プレイヤーのみに通知
        elif event.trade_type.value == "direct" and event.target_player_id:
            self._notify_direct_trade_offered(event)
    
    def handle_trade_executed(self, event: TradeExecutedEvent):
        """取引成立時の通知処理"""
        # 売り手と買い手の両方に通知
        self._notify_trade_executed_to_seller(event)
        self._notify_trade_executed_to_buyer(event)
    
    def handle_trade_cancelled(self, event: TradeCancelledEvent):
        """取引キャンセル時の通知処理"""
        # 直接取引の場合は対象プレイヤーにも通知
        if event.trade_type.value == "direct" and event.target_player_id:
            self._notify_trade_cancelled_to_target(event)
    
    def handle_direct_trade_offered(self, event: DirectTradeOfferedEvent):
        """直接取引提案時の通知処理"""
        self._notify_direct_trade_offered(event)
    
    def _notify_global_trade_created(self, event: TradeCreatedEvent):
        """グローバル取引作成の通知"""
        # 全プレイヤーを取得
        all_players = self._player_repository.find_all()
        
        # 売り手以外のプレイヤーに通知
        for player in all_players:
            if player.player_id != event.seller_id:
                item_desc = self._get_item_description(event)
                message_content = (
                    f"🛒 新しい取引が作成されました！\n"
                    f"出品者: {event.seller_name}\n"
                    f"商品: {item_desc}\n"
                    f"価格: {event.requested_gold}G"
                )
                
                notification = Message.create(
                    sender_id=0,  # システム
                    sender_name="取引システム",
                    recipient_id=player.player_id,
                    content=message_content,
                    timestamp=event.occurred_at
                )
                player.receive_message(notification)
    
    def _notify_direct_trade_offered(self, event: DirectTradeOfferedEvent):
        """直接取引提案の通知"""
        target_player = self._player_repository.find_by_id(event.target_player_id)
        if target_player:
            item_desc = self._get_item_description(event)
            message_content = (
                f"💌 直接取引の提案があります！\n"
                f"提案者: {event.seller_name}\n"
                f"商品: {item_desc}\n"
                f"価格: {event.requested_gold}G\n"
                f"取引ID: {event.trade_id}"
            )
            
            notification = Message.create(
                sender_id=event.seller_id,
                sender_name=event.seller_name,
                recipient_id=target_player.player_id,
                content=message_content,
                timestamp=event.occurred_at
            )
            target_player.receive_message(notification)
    
    def _notify_trade_executed_to_seller(self, event: TradeExecutedEvent):
        """取引成立を売り手に通知"""
        seller = self._player_repository.find_by_id(event.seller_id)
        if seller:
            item_desc = self._get_item_description(event)
            message_content = (
                f"✅ 取引が成立しました！\n"
                f"買い手: {event.buyer_name}\n"
                f"商品: {item_desc}\n"
                f"売上: {event.requested_gold}G\n"
                f"取引ID: {event.trade_id}"
            )
            
            notification = Message.create(
                sender_id=0,  # システム
                sender_name="取引システム",
                recipient_id=seller.player_id,
                content=message_content,
                timestamp=event.occurred_at
            )
            seller.receive_message(notification)
    
    def _notify_trade_executed_to_buyer(self, event: TradeExecutedEvent):
        """取引成立を買い手に通知"""
        buyer = self._player_repository.find_by_id(event.buyer_id)
        if buyer:
            item_desc = self._get_item_description(event)
            message_content = (
                f"✅ 取引が成立しました！\n"
                f"売り手: {event.seller_name}\n"
                f"商品: {item_desc}\n"
                f"支払額: {event.requested_gold}G\n"
                f"取引ID: {event.trade_id}"
            )
            
            notification = Message.create(
                sender_id=0,  # システム
                sender_name="取引システム",
                recipient_id=buyer.player_id,
                content=message_content,
                timestamp=event.occurred_at
            )
            buyer.receive_message(notification)
    
    def _notify_trade_cancelled_to_target(self, event: TradeCancelledEvent):
        """取引キャンセルを対象プレイヤーに通知"""
        target_player = self._player_repository.find_by_id(event.target_player_id)
        if target_player:
            item_desc = self._get_item_description(event)
            message_content = (
                f"❌ 直接取引がキャンセルされました\n"
                f"キャンセル者: {event.seller_name}\n"
                f"商品: {item_desc}\n"
                f"価格: {event.requested_gold}G\n"
                f"取引ID: {event.trade_id}"
            )
            
            notification = Message.create(
                sender_id=0,  # システム
                sender_name="取引システム",
                recipient_id=target_player.player_id,
                content=message_content,
                timestamp=event.occurred_at
            )
            target_player.receive_message(notification)
    
    def _get_item_description(self, event) -> str:
        """アイテムの説明を生成"""
        if event.offered_item_count:
            return f"アイテム{event.offered_item_id} x{event.offered_item_count}"
        else:
            return f"アイテム{event.offered_item_id} (固有ID:{event.offered_unique_id})"


class LoggingTradeEventHandler(TradeEventHandler):
    """ログ出力用取引イベントハンドラー"""
    
    def handle_trade_created(self, event: TradeCreatedEvent):
        """取引作成のログ出力"""
        item_desc = self._get_item_description(event)
        print(f"[{event.occurred_at}] 取引作成: ID={event.trade_id}, "
              f"売り手={event.seller_name}, 商品={item_desc}, 価格={event.requested_gold}G")
    
    def handle_trade_executed(self, event: TradeExecutedEvent):
        """取引成立のログ出力"""
        item_desc = self._get_item_description(event)
        print(f"[{event.occurred_at}] 取引成立: ID={event.trade_id}, "
              f"売り手={event.seller_name}, 買い手={event.buyer_name}, "
              f"商品={item_desc}, 価格={event.requested_gold}G")
    
    def handle_trade_cancelled(self, event: TradeCancelledEvent):
        """取引キャンセルのログ出力"""
        item_desc = self._get_item_description(event)
        print(f"[{event.occurred_at}] 取引キャンセル: ID={event.trade_id}, "
              f"売り手={event.seller_name}, 商品={item_desc}, 価格={event.requested_gold}G")
    
    def handle_direct_trade_offered(self, event: DirectTradeOfferedEvent):
        """直接取引提案のログ出力"""
        item_desc = self._get_item_description(event)
        print(f"[{event.occurred_at}] 直接取引提案: ID={event.trade_id}, "
              f"提案者={event.seller_name}, 対象={event.target_player_name}, "
              f"商品={item_desc}, 価格={event.requested_gold}G")
    
    def _get_item_description(self, event) -> str:
        """アイテムの説明を生成"""
        if event.offered_item_count:
            return f"アイテム{event.offered_item_id} x{event.offered_item_count}"
        else:
            return f"アイテム{event.offered_item_id} (固有ID:{event.offered_unique_id})"
