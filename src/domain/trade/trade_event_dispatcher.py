from typing import List
from src.domain.trade.trade_events import (
    TradeCreatedEvent,
    TradeExecutedEvent,
    TradeCancelledEvent,
    DirectTradeOfferedEvent
)
from src.domain.trade.trade_event_handler import TradeEventHandler


class TradeEventDispatcher:
    """取引イベントディスパッチャー"""
    
    def __init__(self):
        self._handlers: List[TradeEventHandler] = []
    
    def register_handler(self, handler: TradeEventHandler):
        """イベントハンドラーを登録"""
        self._handlers.append(handler)
    
    def unregister_handler(self, handler: TradeEventHandler):
        """イベントハンドラーを登録解除"""
        if handler in self._handlers:
            self._handlers.remove(handler)
    
    def dispatch_trade_created(self, event: TradeCreatedEvent):
        """取引作成イベントをディスパッチ"""
        for handler in self._handlers:
            try:
                handler.handle_trade_created(event)
            except Exception as e:
                print(f"Error handling trade created event: {e}")
    
    def dispatch_trade_executed(self, event: TradeExecutedEvent):
        """取引成立イベントをディスパッチ"""
        for handler in self._handlers:
            try:
                handler.handle_trade_executed(event)
            except Exception as e:
                print(f"Error handling trade executed event: {e}")
    
    def dispatch_trade_cancelled(self, event: TradeCancelledEvent):
        """取引キャンセルイベントをディスパッチ"""
        for handler in self._handlers:
            try:
                handler.handle_trade_cancelled(event)
            except Exception as e:
                print(f"Error handling trade cancelled event: {e}")
    
    def dispatch_direct_trade_offered(self, event: DirectTradeOfferedEvent):
        """直接取引提案イベントをディスパッチ"""
        for handler in self._handlers:
            try:
                handler.handle_direct_trade_offered(event)
            except Exception as e:
                print(f"Error handling direct trade offered event: {e}")
    
    def dispatch_all_events(self, events: List):
        """複数のイベントを一括でディスパッチ"""
        for event in events:
            if isinstance(event, TradeCreatedEvent):
                self.dispatch_trade_created(event)
            elif isinstance(event, TradeExecutedEvent):
                self.dispatch_trade_executed(event)
            elif isinstance(event, TradeCancelledEvent):
                self.dispatch_trade_cancelled(event)
            elif isinstance(event, DirectTradeOfferedEvent):
                self.dispatch_direct_trade_offered(event)
            else:
                print(f"Unknown event type: {type(event)}")
    
    def get_handler_count(self) -> int:
        """登録されているハンドラーの数を取得"""
        return len(self._handlers)
    
    def clear_handlers(self):
        """全てのハンドラーをクリア"""
        self._handlers.clear()
