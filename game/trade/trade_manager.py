from typing import Dict, List, Any, Optional
from game.enums import TradeStatus
from game.trade.trade_data import TradeOffer


class TradeManager:
    def __init__(self):
        self.active_trades: Dict[str, TradeOffer] = {}
        self.trade_history: List[TradeOffer] = []
    
    def post_trade(self, trade_offer: TradeOffer) -> bool:
        """取引を出品"""
        if trade_offer.status != TradeStatus.ACTIVE:
            return False
        
        if trade_offer.trade_id in self.active_trades:
            return False  # 既に存在する取引ID
        
        self.active_trades[trade_offer.trade_id] = trade_offer
        return True
    
    def get_trade(self, trade_id: str) -> Optional[TradeOffer]:
        """指定IDの取引を取得"""
        return self.active_trades.get(trade_id)
    
    def view_trades(self, filters: Optional[Dict[str, Any]] = None) -> List[TradeOffer]:
        """取引一覧を取得（フィルタリング可能）"""
        trades = list(self.active_trades.values())
        
        if filters is None:
            return trades
        
        # フィルタリング処理
        filtered_trades = []
        for trade in trades:
            if self._matches_filters(trade, filters):
                filtered_trades.append(trade)
        
        return filtered_trades
    
    def _matches_filters(self, trade: TradeOffer, filters: Dict[str, Any]) -> bool:
        """取引がフィルタ条件に一致するかチェック"""
        # アイテムIDでフィルタ
        if "offered_item_id" in filters:
            if trade.offered_item_id != filters["offered_item_id"]:
                return False
        
        if "requested_item_id" in filters:
            if trade.requested_item_id != filters["requested_item_id"]:
                return False
        
        # 価格でフィルタ
        if "max_price" in filters:
            max_price = filters["max_price"]
            if trade.is_money_trade() and trade.requested_money > max_price:
                return False
        
        if "min_price" in filters:
            min_price = filters["min_price"]
            if trade.is_money_trade() and trade.requested_money < min_price:
                return False
        
        # 取引タイプでフィルタ
        if "trade_type" in filters:
            if trade.trade_type != filters["trade_type"]:
                return False
        
        # 出品者でフィルタ
        if "seller_id" in filters:
            if trade.seller_id != filters["seller_id"]:
                return False
        
        # 受託可能性でフィルタ
        if "buyer_id" in filters:
            buyer_id = filters["buyer_id"]
            if not trade.can_be_accepted_by(buyer_id):
                return False
        
        return True
    
    def accept_trade(self, trade_id: str, buyer_id: str) -> TradeOffer:
        """取引を受託"""
        if trade_id not in self.active_trades:
            raise ValueError(f"取引 {trade_id} が見つかりません")
        
        trade = self.active_trades[trade_id]
        
        if not trade.can_be_accepted_by(buyer_id):
            if trade.seller_id == buyer_id:
                raise ValueError("自分の出品は受託できません")
            elif trade.status != TradeStatus.ACTIVE:
                raise ValueError(f"取引のステータスが無効です: {trade.status.value}")
            elif trade.target_player_id and trade.target_player_id != buyer_id:
                raise ValueError("この取引は他のプレイヤー向けです")
            else:
                raise ValueError("取引を受託できません")
        
        # 取引を成立状態に変更
        completed_trade = TradeOffer(
            trade_id=trade.trade_id,
            seller_id=trade.seller_id,
            offered_item_id=trade.offered_item_id,
            offered_item_count=trade.offered_item_count,
            requested_money=trade.requested_money,
            requested_item_id=trade.requested_item_id,
            requested_item_count=trade.requested_item_count,
            trade_type=trade.trade_type,
            target_player_id=trade.target_player_id,
            status=TradeStatus.COMPLETED,
            created_at=trade.created_at
        )
        
        # アクティブな取引から削除し、履歴に追加
        del self.active_trades[trade_id]
        self.trade_history.append(completed_trade)
        
        return completed_trade
    
    def cancel_trade(self, trade_id: str, seller_id: str) -> bool:
        """取引をキャンセル"""
        if trade_id not in self.active_trades:
            return False
        
        trade = self.active_trades[trade_id]
        
        if trade.seller_id != seller_id:
            raise ValueError("取引の出品者のみがキャンセルできます")
        
        # 取引をキャンセル状態に変更
        cancelled_trade = TradeOffer(
            trade_id=trade.trade_id,
            seller_id=trade.seller_id,
            offered_item_id=trade.offered_item_id,
            offered_item_count=trade.offered_item_count,
            requested_money=trade.requested_money,
            requested_item_id=trade.requested_item_id,
            requested_item_count=trade.requested_item_count,
            trade_type=trade.trade_type,
            target_player_id=trade.target_player_id,
            status=TradeStatus.CANCELLED,
            created_at=trade.created_at
        )
        
        # アクティブな取引から削除し、履歴に追加
        del self.active_trades[trade_id]
        self.trade_history.append(cancelled_trade)
        
        return True
    
    def get_trade_history(self, filters: Optional[Dict[str, Any]] = None) -> List[TradeOffer]:
        """取引履歴を取得（フィルタリング可能）"""
        if filters is None:
            return self.trade_history.copy()
        
        filtered_history = []
        for trade in self.trade_history:
            if self._matches_filters(trade, filters):
                filtered_history.append(trade)
        
        return filtered_history
    
    def get_player_trades(self, player_id: str, include_history: bool = False) -> List[TradeOffer]:
        """指定プレイヤーの取引一覧を取得"""
        player_trades = []
        
        # アクティブな取引
        for trade in self.active_trades.values():
            if trade.seller_id == player_id:
                player_trades.append(trade)
        
        # 履歴も含める場合
        if include_history:
            for trade in self.trade_history:
                if trade.seller_id == player_id:
                    player_trades.append(trade)
        
        return player_trades
    
    def get_available_trades_for_player(self, player_id: str) -> List[TradeOffer]:
        """指定プレイヤーが受託可能な取引一覧を取得"""
        available_trades = []
        
        for trade in self.active_trades.values():
            if trade.can_be_accepted_by(player_id):
                available_trades.append(trade)
        
        return available_trades
    
    def get_statistics(self) -> Dict[str, Any]:
        """取引所の統計情報を取得"""
        return {
            "active_trades_count": len(self.active_trades),
            "total_trades_completed": len([t for t in self.trade_history if t.status == TradeStatus.COMPLETED]),
            "total_trades_cancelled": len([t for t in self.trade_history if t.status == TradeStatus.CANCELLED]),
            "total_history_count": len(self.trade_history)
        }
    
    def __str__(self):
        stats = self.get_statistics()
        return (f"TradingPost(active: {stats['active_trades_count']}, "
                f"completed: {stats['total_trades_completed']}, "
                f"cancelled: {stats['total_trades_cancelled']})")
    
    def __repr__(self):
        return f"TradingPost(active_trades={len(self.active_trades)}, trade_history={len(self.trade_history)})" 