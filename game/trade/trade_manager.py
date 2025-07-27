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
    
    def accept_trade(self, trade_id: str, buyer_id: str, seller: 'Player' = None, buyer: 'Player' = None) -> TradeOffer:
        """取引を受託（アイテム・お金のやり取りを含む）"""
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
        
        # アイテム・お金のやり取りを実行
        if seller and buyer:
            self._execute_trade_transaction(trade, seller, buyer)
        
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
    
    def _execute_trade_transaction(self, trade: TradeOffer, seller: 'Player', buyer: 'Player'):
        """取引成立時のアイテム・お金のやり取りを実行"""
        # 事前チェック：全ての条件を最初に確認
        self._validate_trade_transaction(trade, seller, buyer)
        
        # アイテムの実体を事前に取得
        seller_item = None
        buyer_item = None
        
        if trade.offered_unique_id:
            # 固有アイテムの場合はunique_idで取得
            seller_item = seller.inventory.get_item_by_id(trade.offered_item_id, trade.offered_unique_id)
        else:
            # 通常アイテム
            seller_item = seller.inventory.get_item_by_id(trade.offered_item_id)
        
        if trade.is_item_trade():
            if trade.requested_unique_id:
                # 固有アイテムの場合はunique_idで取得
                buyer_item = buyer.inventory.get_item_by_id(trade.requested_item_id, trade.requested_unique_id)
            else:
                # 通常アイテム
                buyer_item = buyer.inventory.get_item_by_id(trade.requested_item_id)
        
        # 出品者のアイテムを減らす
        if trade.offered_unique_id:
            # 固有アイテムの場合はunique_idで削除
            seller_removed = seller.remove_item(trade.offered_item_id, trade.offered_item_count, trade.offered_unique_id)
        else:
            # 通常アイテム
            seller_removed = seller.remove_item(trade.offered_item_id, trade.offered_item_count)
        
        if seller_removed < trade.offered_item_count:
            raise ValueError(f"出品者のアイテムが不足しています: {trade.offered_item_id}")
        
        # 購入者のアイテムを減らす（アイテム取引の場合）
        if trade.is_item_trade():
            if trade.requested_unique_id:
                # 固有アイテムの場合はunique_idで削除
                buyer_removed = buyer.remove_item(trade.requested_item_id, trade.requested_item_count, trade.requested_unique_id)
            else:
                # 通常アイテム
                buyer_removed = buyer.remove_item(trade.requested_item_id, trade.requested_item_count)
            
            if buyer_removed < trade.requested_item_count:
                raise ValueError(f"購入者のアイテムが不足しています: {trade.requested_item_id}")
        
        # 購入者のお金を減らす（お金取引の場合）
        if trade.is_money_trade():
            buyer.status.add_money(-trade.requested_money)
        
        # 出品者にお金を渡す（お金取引の場合）
        if trade.is_money_trade():
            seller.status.add_money(trade.requested_money)
        
        # 出品者に要求アイテムを渡す（アイテム取引の場合）
        if trade.is_item_trade() and buyer_item:
            # 事前に取得したアイテムの実体を出品者に渡す
            for _ in range(trade.requested_item_count):
                seller.add_item(buyer_item)
        
        # 購入者に出品アイテムを渡す
        if seller_item:
            # 事前に取得したアイテムの実体を購入者に渡す
            for _ in range(trade.offered_item_count):
                buyer.add_item(seller_item)
    
    def _validate_trade_transaction(self, trade: TradeOffer, seller: 'Player', buyer: 'Player'):
        """取引成立前の事前チェック"""
        # 出品者のアイテム所持チェック
        if trade.offered_unique_id:
            # 固有アイテムの場合はunique_idでチェック
            if not seller.has_item(trade.offered_item_id, trade.offered_unique_id):
                raise ValueError(f"出品者が固有アイテム {trade.offered_item_id} (ID: {trade.offered_unique_id}) を所持していません")
            
            seller_item = seller.inventory.get_item_by_id(trade.offered_item_id, trade.offered_unique_id)
            if not seller_item:
                raise ValueError(f"出品者の固有アイテム {trade.offered_item_id} (ID: {trade.offered_unique_id}) が見つかりません")
            
            if not seller_item.can_be_traded():
                raise ValueError(f"固有アイテム {trade.offered_item_id} (ID: {trade.offered_unique_id}) は取引できません（破損している可能性があります）")
        else:
            # 通常アイテム
            if not seller.has_item(trade.offered_item_id):
                raise ValueError(f"出品者がアイテム {trade.offered_item_id} を所持していません")
            
            seller_item_count = seller.get_inventory_item_count(trade.offered_item_id)
            if seller_item_count < trade.offered_item_count:
                raise ValueError(f"出品者のアイテム {trade.offered_item_id} が不足しています（所持: {seller_item_count}, 必要: {trade.offered_item_count}）")
            
            # 固有アイテムの複数個取引制限チェック
            seller_item = seller.inventory.get_item_by_id(trade.offered_item_id)
            if seller_item and hasattr(seller_item, 'get_unique_id'):
                if trade.offered_item_count > 1:
                    raise ValueError(f"固有アイテム {trade.offered_item_id} は複数個の取引ができません")
                if not seller_item.can_be_traded():
                    raise ValueError(f"固有アイテム {trade.offered_item_id} は取引できません（破損している可能性があります）")
        
        # 購入者のアイテム所持チェック（アイテム取引の場合）
        if trade.is_item_trade():
            if trade.requested_unique_id:
                # 固有アイテムの場合はunique_idでチェック
                if not buyer.has_item(trade.requested_item_id, trade.requested_unique_id):
                    raise ValueError(f"購入者が固有アイテム {trade.requested_item_id} (ID: {trade.requested_unique_id}) を所持していません")
                
                buyer_item = buyer.inventory.get_item_by_id(trade.requested_item_id, trade.requested_unique_id)
                if not buyer_item:
                    raise ValueError(f"購入者の固有アイテム {trade.requested_item_id} (ID: {trade.requested_unique_id}) が見つかりません")
                
                if not buyer_item.can_be_traded():
                    raise ValueError(f"固有アイテム {trade.requested_item_id} (ID: {trade.requested_unique_id}) は取引できません（破損している可能性があります）")
            else:
                # 通常アイテム
                if not buyer.has_item(trade.requested_item_id):
                    raise ValueError(f"購入者がアイテム {trade.requested_item_id} を所持していません")
                
                buyer_item_count = buyer.get_inventory_item_count(trade.requested_item_id)
                if buyer_item_count < trade.requested_item_count:
                    raise ValueError(f"購入者のアイテム {trade.requested_item_id} が不足しています（所持: {buyer_item_count}, 必要: {trade.requested_item_count}）")
                
                # 固有アイテムの複数個取引制限チェック
                buyer_item = buyer.inventory.get_item_by_id(trade.requested_item_id)
                if buyer_item and hasattr(buyer_item, 'get_unique_id'):
                    if trade.requested_item_count > 1:
                        raise ValueError(f"固有アイテム {trade.requested_item_id} は複数個の取引ができません")
                    if not buyer_item.can_be_traded():
                        raise ValueError(f"固有アイテム {trade.requested_item_id} は取引できません（破損している可能性があります）")
        
        # 購入者のお金所持チェック（お金取引の場合）
        if trade.is_money_trade():
            if buyer.status.get_money() < trade.requested_money:
                raise ValueError(f"購入者のお金が不足しています（所持: {buyer.status.get_money()}, 必要: {trade.requested_money}）")
    
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